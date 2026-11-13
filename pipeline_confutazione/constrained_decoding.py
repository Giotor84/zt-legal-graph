"""
Generazione vincolata - la meta' "impedisco prima" del principio del
progetto, separata dal retrieval che la precede.

Passa da "verifico dopo" a "impedisco prima": un vincolo strutturale
ammette come citazione solo le fonti gia' selezionate a monte (piu'
un'astensione esplicita), la prosa attorno resta libera. Il vincolo e'
fisico - il motore GBNF non puo' emettere altro - non disciplinare.

**Questo modulo NON tocca il grafo e non deve mai tornare a toccarlo.**
Il retrieval (che il grafo lo tocca) e' in retrieval.py dal 2026-08-20;
qui resta solo cio' che dipende da llama_server_client. E' l'invariante
architetturale della regola 3 di Claude.md: la Fase 3 non ha alcun
percorso di import verso lo store, verificato staticamente da
test_import_grafo_isolato.py.

**Correzione rispetto al documento di origine**: GBNF grezzo non è
esposto stabilmente dall'API pubblica di Ollama (richiesta di
funzionalità aperta da anni, mai integrata - issue #808/#2895/#6237 su
github.com/ollama/ollama), a differenza di llama.cpp stesso che lo
supporta nativamente. Il meccanismo realmente disponibile e documentato
(https://docs.ollama.com/capabilities/structured-outputs, da Ollama
v0.5) era **output strutturato via JSON Schema con vincoli `enum`** -
stesso motore a grammatica di llama.cpp sotto il cofano, esposto tramite
schema invece che testo GBNF.

**Aggiornamento (2026-08-18) - migrato da Ollama a llama-server**: vedi
ISTRUZIONI_ARCHITETTURA_TOOL.md - modello denso (non piu' MoE potato) su
llama-server nativo, non piu' Ollama. Il vincolo di schema resta
concettualmente identico (stesso motore GBNF di llama.cpp), cambia solo
il trasporto - vedi `llama_server_client.py` per l'adattatore e il perche'
del cambio di endpoint/campi.

Due famiglie di vincoli convivono qui, deliberatamente:

1. `costruisci_schema()` - interrogazione a domanda singola, enum sulle
   `citazione_breve` dei candidati del retrieval. Precede i contratti
   v1.1 e resta in uso per il confronto vincolato/libero.
2. `costruisci_schema_confutazione()` / `costruisci_schema_coerenza()` -
   la pipeline di confutazione a tre fasi. Enum sugli `estratto_id` del
   dossier e sugli `eccezione_id`, generati a runtime dai contratti in
   `contratti/`. E' la strada "consigliata, zero modifiche al client"
   della sezione "Integrazione con llama-server" di CONTRATTI_DATI.md:
   i file `.gbnf` restano l'espressione normativa del contratto (audit +
   test), il payload viaggia come `json_schema`, che llama-server
   converte internamente nello STESSO motore GBNF.

Uso:
    from retrieval import candidati_per_prompt
    from constrained_decoding import costruisci_schema, genera_vincolato
    candidati = candidati_per_prompt(store, embedding_index, query, k=20)
    risposta = genera_vincolato(LLAMA_SERVER_URL, prompt, candidati)
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import llama_server_client

SENTINELLA_ASTENSIONE = "NESSUN_ARTICOLO_RECUPERATO_PERTINENTE"

#: Sorgente unica dei contratti (una sola copia, in root - la copia dentro
#: pipeline_confutazione/ e' stata eliminata il 2026-08-20: due copie
#: divergono, e una specifica vincolante che diverge da se stessa non
#: vincola niente).
CONTRATTI_DIR = Path(__file__).parent.parent / "contratti"

#: Segnaposto che i contratti dichiarano al posto degli enum generati a
#: runtime - vedi CONTRATTI_DATI.md, "Generatore della regola runtime".
SEGNAPOSTO_ESTRATTI = "SEGNAPOSTO_RUNTIME_estratti_citabili"
SEGNAPOSTO_ECCEZIONI = "SEGNAPOSTO_RUNTIME_eccezione_id"


# ------------------------------------------------------------------ schema: domanda singola


def costruisci_schema(candidati: list[dict]) -> dict:
    """Schema JSON (parametro `json_schema` di llama-server, stesso motore
    GBNF gia' usato via Ollama in precedenza): la prosa (`risposta`) è
    libera, `citazioni_pertinenti` è vincolato a un enum costruito dai
    candidati del retrieval più la sentinella di astensione - il motore di
    generazione non può produrre altro, per costruzione.

    # BUG-GRAFO-4: l'enum e' costruito sulle `citazione_breve`, di cui 36
    # non sono univoche nel grafo - due fonti diverse possono presentarsi
    # al modello con la stessa etichetta e diventare indistinguibili al
    # ritorno. E' esattamente la ragione per cui la pipeline di
    # confutazione usa `estratto_id` opachi (costruisci_schema_confutazione)
    # e il contratto vieta citazione_breve come chiave. Qui resta perche'
    # questa funzione serve all'interrogazione a domanda singola, che non
    # produce un atto depositabile: segnalato, non aggirato."""
    valori_ammessi = [c["citazione_breve"] for c in candidati] + [SENTINELLA_ASTENSIONE]
    return {
        "type": "object",
        "properties": {
            "risposta": {
                "type": "string",
                "description": "La spiegazione in prosa libera, in italiano.",
            },
            "citazioni_pertinenti": {
                "type": "array",
                "description": (
                    "Solo le fonti (articoli di legge o giurisprudenza) tra "
                    "quelle elencate sopra che sono effettivamente pertinenti "
                    f"alla risposta. Se nessuna è pertinente, usa esclusivamente "
                    f"il valore '{SENTINELLA_ASTENSIONE}' - non inventarne altre."
                ),
                "items": {"type": "string", "enum": valori_ammessi},
            },
        },
        "required": ["risposta", "citazioni_pertinenti"],
    }


def costruisci_prompt_di_sistema(candidati: list[dict]) -> str:
    """Elenco dei candidati recuperati da presentare al modello nel prompt -
    lo schema vincola l'OUTPUT, ma il modello deve comunque vedere il testo
    reale (articoli DI CODICE o giurisprudenza) per poter scrivere una
    risposta sensata, non solo scegliere alla cieca tra sigle."""
    righe = [
        "Puoi citare SOLO le fonti elencate qui sotto (articoli di legge o "
        "giurisprudenza), nel campo 'citazioni_pertinenti' della risposta "
        f"strutturata. Se nessuna è pertinente alla domanda, usa il valore "
        f"'{SENTINELLA_ASTENSIONE}' invece di inventare o forzare una "
        "citazione non pertinente.\n",
    ]
    for c in candidati:
        righe.append(f"- {c['citazione_breve']} — {c['descrizione']}")
    return "\n".join(righe)


# ------------------------------------------------------------------ schema: pipeline di confutazione


def _carica_contratto(nome_file: str) -> dict:
    """Legge un contratto dalla sorgente unica. Fallisce rumorosamente se
    manca: un contratto assente non e' un caso da degradare con un default,
    e' la specifica vincolante che non c'e'."""
    percorso = CONTRATTI_DIR / nome_file
    if not percorso.is_file():
        raise FileNotFoundError(
            f"contratto '{nome_file}' non trovato in {CONTRATTI_DIR} - "
            "la sorgente unica dei contratti e' la cartella contratti/ in root del progetto"
        )
    return json.loads(percorso.read_text(encoding="utf-8"))


def _sostituisci_segnaposto(nodo: object, segnaposto: str, valori: list[str]) -> object:
    """Sostituisce ricorsivamente ogni `enum` che contiene esattamente il
    segnaposto con l'enum reale generato a runtime. Ricorsiva e non
    puntuale perche' il segnaposto puo' comparire in piu' punti dello stesso
    contratto - una sostituzione scritta a mano su un percorso fisso si
    romperebbe in silenzio al primo contratto che ne aggiunge uno. Fino
    alla 1.26 i punti in coerenza.schema.json erano due (`ordine_motivi` e
    `conflitti[].tra`); dalla 1.27 resta solo il secondo, ma la ricorsione
    e' proprio cio' che ha reso quel cambio una modifica al solo contratto."""
    if isinstance(nodo, dict):
        if nodo.get("enum") == [segnaposto]:
            nodo = dict(nodo, enum=list(valori))
        return {chiave: _sostituisci_segnaposto(valore, segnaposto, valori) for chiave, valore in nodo.items()}
    if isinstance(nodo, list):
        return [_sostituisci_segnaposto(elemento, segnaposto, valori) for elemento in nodo]
    return nodo


def _conta_segnaposto(nodo: object, segnaposto: str) -> int:
    if isinstance(nodo, dict):
        proprio = 1 if nodo.get("enum") == [segnaposto] else 0
        return proprio + sum(_conta_segnaposto(v, segnaposto) for v in nodo.values())
    if isinstance(nodo, list):
        return sum(_conta_segnaposto(e, segnaposto) for e in nodo)
    return 0


def costruisci_schema_confutazione(estratti_citabili: list[str]) -> dict:
    """Payload della SINGOLA chiamata di Fase 3 (una per eccezione con
    stato 'confutabile' nel dossier; stessa forma per la sezione FATTO,
    con gli estratti ristretti a F00/F01).

    estratti_citabili: gli `estratto_id` dell'esito di QUELLA eccezione,
    gia' estratti dal dossier dal chiamante - una lista di stringhe, non
    le voci del dossier: la forma con cui il dossier registra la
    provenienza di ogni estratto citabile non deve poter cambiare questa
    firma.

    E' il lucchetto del contratto: il motore GBNF non puo' fisicamente
    emettere un id fuori dal dossier, quindi la Fase 3 scrive SOLO su
    fonti gia' verificate a monte, per costruzione. Equivalente esatto di
    `gbnf_ancora_id()` in CONTRATTI_DATI.md, per la via json_schema.

    Solleva ValueError su lista vuota: uno schema con enum vuoto non e'
    generabile, e un esito 'confutabile' senza estratti citabili e' gia'
    vietato dal contratto (allOf/if/then su fase2_dossier.schema.json,
    ricontrollato dal controllo Python n. 4) - arrivarci significa che un
    controllo a monte non e' stato eseguito, non che serve un fallback."""
    if not estratti_citabili:
        raise ValueError(
            "estratti_citabili vuoto: nessun enum generabile per la Fase 3. "
            "Un esito 'confutabile' senza estratti citabili viola fase2_dossier.schema.json "
            "(controllo Python n. 4) - il dossier non doveva superare la validazione"
        )

    contratto = _carica_contratto("fase3_atto.schema.json")
    payload = copy.deepcopy(contratto["$defs"]["confutazione_generata"])
    attesi = _conta_segnaposto(payload, SEGNAPOSTO_ESTRATTI)
    if attesi == 0:
        raise ValueError(
            f"'{SEGNAPOSTO_ESTRATTI}' non trovato in fase3_atto.schema.json#/$defs/confutazione_generata - "
            "il contratto e' cambiato senza che il generatore runtime lo seguisse"
        )
    return _sostituisci_segnaposto(payload, SEGNAPOSTO_ESTRATTI, estratti_citabili)


def costruisci_schema_coerenza(eccezione_ids: list[str]) -> dict:
    """Payload di UNA chiamata di Fase 3-bis, su UNA finestra di motivi.
    Enum `motivo-id` generato dagli `eccezione_id` della finestra, stesso
    identico meccanismo di costruisci_schema_confutazione.

    Cio' che la grammatica NON puo' imporre resta un controllo Python
    (n. 11): che i due id di ogni conflitto stiano nella finestra e siano
    diversi fra loro.

    1.27: non c'e' piu' un `ordine_motivi` da generare. La permutazione
    completa era il campo che il modello sbagliava - e che imporre in GBNF
    avrebbe richiesto n! alternative; ora l'ordine lo calcola
    `ordine_motivi.py` per rango processuale.

    Solleva ValueError sotto i 2 motivi: senza almeno una coppia non c'e'
    nessun conflitto possibile, e il contratto prescrive di saltare la
    passata (coerenza = null, dichiarato in memoria), non di eseguirla."""
    if len(eccezione_ids) < 2:
        raise ValueError(
            f"la passata di coerenza richiede almeno 2 motivi, ricevuti {len(eccezione_ids)}: "
            "il contratto prescrive di saltarla (coerenza = null, dichiarato in memoria), non di eseguirla"
        )

    contratto = _carica_contratto("coerenza.schema.json")
    payload = copy.deepcopy(contratto["$defs"]["output"])
    attesi = _conta_segnaposto(payload, SEGNAPOSTO_ECCEZIONI)
    if attesi == 0:
        raise ValueError(
            f"'{SEGNAPOSTO_ECCEZIONI}' non trovato in coerenza.schema.json#/$defs/output - "
            "il contratto e' cambiato senza che il generatore runtime lo seguisse"
        )
    return _sostituisci_segnaposto(payload, SEGNAPOSTO_ECCEZIONI, eccezione_ids)


# ------------------------------------------------------------------ generazione


def genera_vincolato(base_url: str, prompt_utente: str, candidati: list[dict],
                      n_predict: int = 4096, timeout: int = llama_server_client.TIMEOUT_DEFAULT_SECONDI,
                      prompt_sistema_extra: str = "", pensiero_attivo: bool | None = None,
                      seed: int | None = None) -> dict:
    """Chiama POST /completion di llama-server con json_schema=schema -
    richiede requests installato e un'istanza llama-server raggiungibile
    (nessuna chiamata di rete nello smoke test locale del modulo, solo
    quando invocata esplicitamente). n_predict di default alzato a 4096
    (era 2048 su Ollama): un atto/motivazione in prosa vincolata puo'
    essere lungo, e con RispostaTroncata che ora rileva il taglio invece di
    lasciarlo passare in silenzio, meglio partire con margine ampio dato che
    il progetto non ha vincoli di velocita' (vedi conversazione).

    prompt_sistema_extra: testo aggiuntivo anteposto all'elenco dei
    candidati (es. istruzioni di ruolo/struttura per la redazione atti,
    vedi redazione.py) - vuoto di default, comportamento invariato per i
    chiamanti esistenti.

    pensiero_attivo: None (default) = ragionamento ATTIVO, comportamento
    storico non ancora corretto - il bug 2 (generazione che ripete le
    istruzioni) e' un'ipotesi ancora da confermare (conflitto tra
    grammatica JSON e blocco <think>, vedi test_confronto_vincolato_libero.py),
    non ancora un fix da applicare di default finche' non e' verificato dal
    vivo. Passare esplicitamente False una volta confermata l'ipotesi."""
    schema = costruisci_schema(candidati)
    sistema = (prompt_sistema_extra + "\n\n" if prompt_sistema_extra else "") + costruisci_prompt_di_sistema(candidati)
    prompt_completo = llama_server_client.costruisci_prompt_chatml(
        sistema, prompt_utente, pensiero_attivo=True if pensiero_attivo is None else pensiero_attivo,
    )
    return llama_server_client.completa_json(
        base_url, prompt_completo, schema, n_predict=n_predict, temperature=0.7, timeout=timeout, seed=seed,
    )


def genera_con_schema(base_url: str, sistema: str, utente: str, schema: dict,
                       n_predict: int = 3072, temperature: float = 0.7,
                       timeout: int = llama_server_client.TIMEOUT_DEFAULT_SECONDI,
                       pensiero_attivo: bool | None = None, seed: int | None = None) -> dict:
    """Generazione vincolata da uno schema GIA' costruito - la via che usa
    la pipeline di confutazione, dove l'enum non nasce da un elenco di
    candidati mostrato nel prompt di sistema (costruisci_prompt_di_sistema)
    ma dagli `estratto_id` del dossier, e il prompt di sistema e'
    responsabilita' del chiamante (redazione.py, che ha il dossier e sa
    come presentarne gli estratti).

    Separata da genera_vincolato() invece di aggiungerle un parametro:
    quella costruisce sempre lo schema dai candidati, questa non ha
    candidati affatto - fonderle significherebbe un parametro che disattiva
    meta' del corpo dell'altra."""
    prompt_completo = llama_server_client.costruisci_prompt_chatml(
        sistema, utente, pensiero_attivo=True if pensiero_attivo is None else pensiero_attivo,
    )
    return llama_server_client.completa_json(
        base_url, prompt_completo, schema, n_predict=n_predict, temperature=temperature, timeout=timeout, seed=seed,
    )


def estrai_citazioni_ammesse(risposta_json: dict) -> list[str]:
    """Le citazioni effettivamente usate dal modello, già garantite valide
    dallo schema (mai fuori dall'enum) - un controllo qui è ridondante per
    costruzione, ma resta come rete di sicurezza esplicita se lo schema
    venisse ignorato da un runtime non conforme."""
    citazioni = risposta_json.get("citazioni_pertinenti", [])
    return [c for c in citazioni if c != SENTINELLA_ASTENSIONE]


if __name__ == "__main__":
    # Smoke test locale: nessuna chiamata di rete E nessun grafo - dopo lo
    # split questo modulo non ha piu' modo di caricare lo store, ed e' il
    # punto. I candidati sono finti, la loro provenienza non interessa a
    # nessuna delle funzioni qui dentro.
    candidati_finti = [
        {"citazione_breve": "art. 2852 c.c.", "descrizione": "Grado dell'ipoteca"},
        {"citazione_breve": "art. 2808 c.c.", "descrizione": "Costituzione dell'ipoteca ed effetti"},
    ]
    schema = costruisci_schema(candidati_finti)
    print(f"Schema a domanda singola: {len(schema['properties']['citazioni_pertinenti']['items']['enum'])} valori ammessi.")
    print(costruisci_prompt_di_sistema(candidati_finti))

    schema_conf = costruisci_schema_confutazione(["F02E01", "F02E02", "F03E01"])
    enum_generato = schema_conf["oneOf"][0]["properties"]["paragrafi"]["items"]["properties"]["ancore"]["items"]["enum"]
    print(f"\nSchema Fase 3 (da contratti/fase3_atto.schema.json): ancore ammesse = {enum_generato}")

    schema_coe = costruisci_schema_coerenza(["X01", "X02", "X03"])
    print(f"Schema Fase 3-bis (da contratti/coerenza.schema.json): motivi confrontabili = "
          f"{schema_coe['properties']['conflitti']['items']['properties']['tra']['items']['enum']}")
    print("  1.27: nessun 'ordine_motivi' da generare - l'ordine lo calcola ordine_motivi.py")
    print("\nOK - nessuna chiamata di rete, nessun import del grafo in questo modulo.")
