"""
Fase 3 - redazione vincolata a partire dal dossier, e Fase 3-bis - passata
di coerenza d'insieme.

**Questo modulo non puo' fare retrieval, perche' non ha da dove.** Non
importa lo store, non importa il grafo, non importa retrieval.py: dopo lo
split del 2026-08-20 dipende solo da `constrained_decoding` e
`llama_server_client`. E' la regola 3 di Claude.md resa fisica invece che
disciplinare, verificata staticamente da test_import_grafo_isolato.py -
il grafo non e' raggiungibile nemmeno per sbaglio.

Tutto cio' che la Fase 3 puo' citare sta in `02_dossier.json`, e
l'enum della grammatica e' generato dagli `estratti_citabili` della
singola eccezione: il modello non puo' fisicamente emettere un id fuori
dal dossier. Il vincolo e' del motore GBNF, non del prompt.

Firma cambiata (era `redigi_atto(store, embedding_index, base_url,
obiettivo, fatti_di_causa, atto_controparte, k, fonti_aggiuntive_verificate)`):

- `store`, `embedding_index`, `k` -> il retrieval e' Fase 2b, i suoi
  risultati arrivano gia' come `fonti`/`estratti` del dossier;
- `fonti_aggiuntive_verificate` -> non serve piu': le fonti delle regole
  sono gia' nel dossier, non vanno "iniettate" nei candidati;
- `obiettivo`, `fatti_di_causa`, `atto_controparte` -> campi del dossier;
- `verifica_risposta`/`verifica_risposta_giurisprudenza` (richiedono lo
  store) -> le chiama l'entry point sul testo renderizzato;
- `estrai_da_atto_controparte` (richiede lo store) -> spostata in
  pipeline.py, di cui era gia' una composizione di due sole funzioni.

Cosa `redigi_atto` NON compila del payload di `fase3_atto.schema.json`,
lasciandolo all'entry point che e' l'unico ad avere grafo, argomenti di
riga di comando e testo renderizzato:

- `affermazioni` (richiede il grafo: node_id e data_vigenza per ancora);
- `conclusioni` (testo dell'avvocato, argomento obbligatorio della CLI -
  non generato dal modello, mai);
- `meta.verifica_post_generazione_superata` (dipende dal doppio binario
  sul testo renderizzato);
- `coerenza`, restituita a `null`: la Fase 3-bis gira DOPO l'assemblaggio
  (vedi `passata_coerenza`), e il controllo Python n. 11 sulla
  permutazione sta nell'entry point.

Uso:
    from redazione import redigi_atto
    atto = redigi_atto(LLAMA_SERVER_URL, dossier)   # dossier gia' validato
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).parent))
import constrained_decoding
import llama_server_client

VERSIONE_CONTRATTO = "1.36"

#: Fonti riservate dal contratto: F00 = fatti di causa (testo fornito
#: dall'avvocato), F01 = atto di controparte. Sono le uniche ancorabili
#: dalla sezione FATTO.
FONTI_DEL_FATTO = ("F00", "F01")

SISTEMA_EX_PARTE_CREDITORIS = """Sei un assistente che aiuta un avvocato italiano a redigere atti processuali per conto della PARTE CREDITRICE.

Regole vincolanti:
1. Scrivi in italiano giuridico corretto. Stai scrivendo UNA SOLA sezione dell'atto, non l'atto intero: non ripetere l'intestazione, non scrivere le conclusioni, non annunciare quello che stai per fare.
2. Dove la legge lascia margine di interpretazione, argomenta nella direzione più favorevole al creditore - MAI però piegando o forzando il significato reale di una norma o di un precedente: un'argomentazione scorretta in diritto danneggia il cliente più di una prudente.
3. Ogni paragrafo che scrivi deve essere sostenuto da uno o più ESTRATTI elencati sotto, indicati con il loro identificativo (es. F02E01) nel campo 'ancore'. Non esistono altre fonti citabili: quelle elencate sono tutto ciò che hai.
4. Nella prosa del campo 'testo' non nominare norme, sentenze o principi che non corrispondano a un estratto elencato sotto. Una citazione nominata nella prosa ma non ancorata viene respinta dal controllo automatico a valle e fa scartare l'intera sezione.

Prima di ancorare un paragrafo a un estratto, valutalo con rigore:
5. CONTRASTO SEMANTICO: verifica esplicitamente che l'estratto non riguardi un istituto affine ma normativamente distinto da quello richiesto (es. la differenza tra interruzione e durata della prescrizione, tra revoca e annullamento di un provvedimento) - una fonte topicamente vicina ma sbagliata è un errore, non un'approssimazione accettabile.
6. ONERE DELLA PROVA: se il contenuto dell'estratto non copre in modo inequivocabile il punto che dovrebbe sostenere, NON usarlo - un'attinenza dubbia non è sufficiente.
7. L'ASTENSIONE è un esito di prima classe, non un fallimento: se gli estratti disponibili non sostengono l'argomento, scegli il ramo 'astensione' e dichiara perché. È preferibile a un paragrafo plausibile ma non sostenuto.

Ogni estratto è marcato [FONTE] oppure [ATTO DI CONTROPARTE]. La differenza è vincolante:
8. Un estratto [ATTO DI CONTROPARTE] riporta ciò che la controparte AFFERMA. Non è autorità, non è legge, non è giurisprudenza: è la tesi avversaria, cioè l'oggetto dell'attacco, non un suo fondamento. Puoi ancorarvi un paragrafo che RIFERISCE la deduzione avversaria ("la controparte deduce che...", "si eccepisce in atti che..."). Non puoi mai usarlo come premessa di un argomento: "come stabilito in..." riferito a un estratto [ATTO DI CONTROPARTE] è sempre un errore.
9. Di conseguenza un paragrafo che argomenta in diritto deve avere almeno un'ancora [FONTE]. Un paragrafo ancorato SOLO all'atto di controparte viene respinto dal controllo automatico a valle."""

SISTEMA_FATTO = """Sei un assistente che aiuta un avvocato italiano a redigere la sezione FATTO di un atto processuale per conto della PARTE CREDITRICE.

Regole vincolanti:
1. Esposizione dei fatti, non argomentazione in diritto: nessuna norma, nessun precedente, nessuna valutazione di fondatezza. L'argomentazione sta nei MOTIVI, che scrive un'altra chiamata.
2. Riassumi oggettivamente i fatti di causa e, dove pertinente, cosa la controparte ha dedotto. Neutro nel tono, favorevole al creditore nella selezione di ciò che è rilevante.
3. Ogni paragrafo deve essere ancorato a uno o più ESTRATTI elencati sotto, indicati con il loro identificativo nel campo 'ancore'. Non affermare fatti che nessun estratto elencato sostiene.
4. Se gli estratti disponibili non permettono di esporre i fatti, scegli il ramo 'astensione' e dichiara perché."""

SISTEMA_COERENZA = """Sei un assistente che aiuta un avvocato italiano a rivedere la COERENZA D'INSIEME dei motivi di un atto già scritto.

Ricevi solo i RIASSUNTI di un GRUPPO di motivi, non il testo integrale né le fonti. Devi produrre una cosa sola:

'conflitti': le coppie di motivi in tensione fra loro, con il tipo:
   - 'contraddizione': sostengono tesi incompatibili;
   - 'subordinazione': un motivo presuppone l'esito di un altro (es. una subordinata che presuppone il rigetto della principale) senza che l'ordine lo rifletta;
   - 'sovrapposizione': argomentano la stessa cosa.

Se non ne vedi, restituisci una lista vuota: inventare un conflitto è peggio che non trovarne. Segnala solo coppie fra i motivi che hai davanti, mai altri.

NON ordinare i motivi: l'ordine è già stato deciso e non ti viene chiesto. NON riscrivere il testo dei motivi, NON risolvere i conflitti, NON suggerire modifiche: li segnali soltanto. La decisione resta all'avvocato."""


# ------------------------------------------------------------------ utilita' di contratto


def sha256_canonico(dati: dict) -> str:
    """sha256 della forma canonica di un contratto - la stessa forma con
    cui l'entry point scrive il file su disco, cosi' che
    `meta.sha256_dossier` corrisponda davvero ai byte di `02_dossier.json`
    e non a una serializzazione diversa che gli somiglia.

    Vive qui, e non in un modulo condiviso, perche' questo e' l'unico
    modulo di Fase 3 che ne ha bisogno e non puo' importare nulla che
    tocchi il grafo. L'entry point lo importa da qui: il verso
    entry point -> redazione e' lecito, il contrario no."""
    return hashlib.sha256(serializza_contratto(dati).encode("utf-8")).hexdigest()


def serializza_contratto(dati: dict) -> str:
    """Forma canonica di un file di contratto: UTF-8 leggibile (gli atti
    sono in italiano, `\\u00e8` al posto di `è` renderebbe illeggibile un
    artefatto di ispezione), chiavi ordinate, separatori compatti."""
    return json.dumps(dati, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _adesso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ------------------------------------------------------------------ costruzione dei prompt


def ids_citabili(estratti_citabili: list[dict]) -> list[str]:
    """Gli `estratto_id` da cui si genera l'enum della grammatica.

    Dalla 1.2 `estratti_citabili` e' una lista di oggetti
    `{estratto_id, provenienza}`: la grammatica vincola gli ID, la
    provenienza governa l'USO (controllo Python n. 14) e non entra
    nell'enum - il modello non deve poter scegliere in base a essa, deve
    solo non poter uscire dalla lista."""
    return [voce["estratto_id"] for voce in estratti_citabili]


def _testo_estratti(dossier: dict, estratti_citabili: list[dict]) -> str:
    """Elenco degli estratti citabili da mostrare al modello: id opaco +
    marcatura della provenienza + citazione breve della fonte (per
    orientarsi) + testo integrale ritagliato da Python.

    La citazione breve serve SOLO a rendere leggibile l'elenco: il modello
    risponde con l'`estratto_id`, mai con la citazione (principio 2 del
    contratto - l'identita' e' l'id, la citazione breve puo' collidere).

    La marcatura [ATTO DI CONTROPARTE] / [FONTE] e' l'unico modo di far
    rispettare il controllo n. 14 in GENERAZIONE: l'enum della grammatica
    e' piatto e non puo' distinguere gli id per provenienza, quindi la
    distinzione dev'essere visibile nel prompt. Resta comunque
    ricontrollata da Python sul risultato - il prompt persuade, il
    controllo vincola."""
    per_id = {e["estratto_id"]: e for e in dossier["estratti"]}
    breve_per_fonte = {f["fonte_id"]: f["citazione_breve"] for f in dossier["fonti"]}

    righe = []
    for voce in estratti_citabili:
        estratto_id = voce["estratto_id"]
        estratto = per_id.get(estratto_id)
        if estratto is None:
            raise ValueError(
                f"estratto '{estratto_id}' citabile ma assente dal registro 'estratti' del dossier - "
                "integrita' referenziale violata (controllo Python n. 1): il dossier non doveva superare la validazione"
            )
        marca = "ATTO DI CONTROPARTE" if voce["provenienza"] == "atto_controparte" else "FONTE"
        breve = breve_per_fonte.get(estratto["fonte_id"], "(fonte senza citazione breve)")
        righe.append(f"[{estratto_id}] [{marca}] {breve}\n{estratto['testo']}")
    return "\n\n".join(righe)


def _estratti_avversari(dossier: dict, esito: dict) -> list[tuple[str, str]]:
    """(estratto_id, testo) per ogni estratto F01 (`atto_controparte`) di
    QUESTO esito, nell'ordine di `estratti_citabili`. Base condivisa di
    `_testo_eccezione_avversaria` (che li concatena) e del promemoria di
    accorpamento (che li elenca separati, vedi `_prompt_per_eccezione`)."""
    per_id = {e["estratto_id"]: e for e in dossier["estratti"]}
    return [
        (voce["estratto_id"], per_id[voce["estratto_id"]]["testo"])
        for voce in esito["estratti_citabili"]
        if voce["provenienza"] == "atto_controparte" and voce["estratto_id"] in per_id
    ]


def _testo_eccezione_avversaria(dossier: dict, esito: dict) -> str | None:
    """Il testo letterale dell'eccezione da confutare, se raggiungibile.

    Arriva come estratto su F01 con `provenienza: "atto_controparte"`,
    che il contratto 1.2 impone alla Fase 2 di includere SEMPRE fra gli
    `estratti_citabili` di quell'esito, quando esiste - e che non conta
    nel tetto di 6 (i 6 sono le fonti a supporto, questo e' l'oggetto
    dell'attacco). Il suo `testo` e' `atto_originale[inizio:fine]`
    calcolato da Python, mai la stringa emessa dal modello in Fase 1.

    Puo' comunque mancare: l'estratto F01 esiste solo per le eccezioni
    con ancora `ancorata`. Quando manca, il prompt lo dice invece di far
    finta di avere l'eccezione sotto gli occhi - e il modello viene
    istruito a non attribuire alla controparte parole che non ha
    davanti."""
    testi = [testo for _, testo in _estratti_avversari(dossier, esito)]
    return "\n\n".join(testi) if testi else None


def _prompt_per_eccezione(dossier: dict, esito: dict) -> tuple[str, str]:
    """(sistema, utente) per la chiamata di UNA eccezione confutabile.
    Mai piu' di un'eccezione per chiamata, mai l'atto intero nel prompt -
    e' la ragione per cui il budget di 16k regge (vedi CONTRATTI_DATI.md)."""
    estratti = _testo_estratti(dossier, esito["estratti_citabili"])
    sistema = f"{SISTEMA_EX_PARTE_CREDITORIS}\n\nESTRATTI CITABILI PER QUESTO MOTIVO:\n\n{estratti}"

    testo_eccezione = _testo_eccezione_avversaria(dossier, esito)
    parti = [f"Obiettivo dell'atto: {dossier['obiettivo']}"]
    if testo_eccezione:
        parti.append(
            f"Eccezione sollevata da controparte ({esito['eccezione_id']}), da confutare:\n{testo_eccezione}"
        )
    else:
        famiglia = f" (famiglia: {esito['famiglia']})" if esito.get("famiglia") else ""
        parti.append(
            f"Eccezione da confutare: {esito['eccezione_id']}{famiglia}. "
            "Il testo letterale dell'eccezione non è fra gli estratti citabili di questo motivo: "
            "argomenta sulla base della linea di confutazione e della nota della regola qui sotto, "
            "senza attribuire alla controparte parole che non hai davanti."
        )
    if esito.get("contro_argomento"):
        parti.append(f"Linea di confutazione individuata dal motore delle regole:\n{esito['contro_argomento']}")
    if esito.get("nota"):
        parti.append(f"Nota della regola applicata:\n{esito['nota']}")
    if esito.get("consolidamento"):
        parti.append(
            f"Consolidamento dell'orientamento: {esito['consolidamento']}. "
            "Se non è 'pacifico', esponi l'argomento come sostenibile, non come acquisito."
        )
    accorpate = esito.get("eccezioni_accorpate") or [esito["eccezione_id"]]
    if len(accorpate) > 1:
        elenco = "\n".join(f"- [{eid}] {txt}" for eid, txt in _estratti_avversari(dossier, esito))
        parti.append(
            f"Questo motivo ACCORPA {len(accorpate)} eccezioni distinte della controparte "
            f"({', '.join(accorpate)}), perché condividono famiglia e fonti a supporto - non perché "
            "siano la stessa cosa. Sono le seguenti affermazioni, ciascuna con il proprio estratto:\n"
            f"{elenco}\n\n"
            "Il motivo deve confutarle TUTTE, non solo la prima: nell'insieme dei paragrafi che scrivi "
            "per questo motivo, ogni estratto elencato sopra deve comparire in almeno un campo 'ancore' "
            "- puoi trattarle nello stesso paragrafo se l'argomento è davvero unico per tutte, o in "
            "paragrafi distinti se richiedono sfumature diverse, ma nessuna delle affermazioni elencate "
            "può restare senza risposta."
        )
    parti.append("Scrivi i paragrafi di questo singolo motivo di diritto, ciascuno ancorato agli estratti.")
    return sistema, "\n\n".join(parti)


def _prompt_fatto(dossier: dict, estratti_citabili: list[dict]) -> tuple[str, str]:
    """(sistema, utente) per la sezione FATTO, ancorata a F00/F01."""
    estratti = _testo_estratti(dossier, estratti_citabili)
    sistema = f"{SISTEMA_FATTO}\n\nESTRATTI CITABILI PER IL FATTO:\n\n{estratti}"
    utente = (
        f"Obiettivo dell'atto: {dossier['obiettivo']}\n\n"
        f"Fatti di causa come esposti dall'avvocato:\n{dossier['fatti_di_causa']}\n\n"
        "Scrivi i paragrafi della sezione FATTO, ciascuno ancorato agli estratti."
    )
    return sistema, utente


def _paragrafi_con_id(prefisso: str, paragrafi_generati: list[dict]) -> list[dict]:
    """Assegna i `paragrafo_id` - Python, mai il modello (il contratto lo
    dice esplicitamente in `$defs/paragrafo_ancorato`)."""
    return [
        {
            "paragrafo_id": f"{prefisso}P{indice:02d}",
            "testo": paragrafo["testo"],
            "ancore": paragrafo["ancore"],
        }
        for indice, paragrafo in enumerate(paragrafi_generati, start=1)
    ]


# ------------------------------------------------------------------ Fase 3


def _notifica(on_progresso: Callable[[dict], None] | None, **campi) -> None:
    """Duplicata da estrazione_atto._notifica, non importata: questo
    modulo dichiara di dipendere SOLO da constrained_decoding e
    llama_server_client (vedi docstring in testa al file, verificato
    staticamente da test_import_grafo_isolato.py) - importare da
    estrazione_atto per risparmiare sei righe romperebbe quell'invariante
    per un motivo che non c'entra niente col perche' esiste.

    Ingoia OGNI `Exception` che `on_progresso` solleva (mai
    `BaseException`: `KeyboardInterrupt` deve continuare a propagarsi).
    Un campo diagnostico non deve mai poter interrompere la redazione -
    qui il rischio e' piu' concreto che altrove: `redigi_atto` avvolge
    l'intero ciclo dei motivi in un `except Exception` che, senza questa
    garanzia, scambierebbe un `on_progresso` che solleva per
    un'interruzione VERA della generazione (`GenerazioneFase3Parziale`),
    buttando via un atto parziale scrivibile per un guasto che non ha
    niente a che fare col modello."""
    if on_progresso is None:
        return
    try:
        on_progresso(campi)
    except Exception:
        pass


def redigi_atto(base_url: str, dossier: dict, seed: int | None = None,
                 on_progresso: Callable[[dict], None] | None = None) -> dict:
    """Genera la sezione FATTO e un motivo per ogni esito del dossier.

    dossier: gia' validato contro `fase2_dossier.schema.json` dall'entry
    point - questa funzione non lo rivalida (sarebbe il secondo binario
    dello stesso controllo, non un binario diverso) ma fallisce
    rumorosamente se l'integrita' referenziale che il contratto promette
    non regge.

    Ritorna il payload conforme a `fase3_atto.schema.json` privo di
    `affermazioni`, `conclusioni` e `meta.verifica_post_generazione_superata`,
    con `coerenza = null` - vedi il docstring del modulo per il perche' di
    ciascuno.

    UNA chiamata LLM per esito `confutabile`, piu' una per il FATTO.
    Nessuna chiamata per gli altri esiti: un'astensione decisa in Fase 2
    non si "riprova" in Fase 3, si dichiara.

    Un troncamento (`RispostaTroncata`) su una singola chiamata NON
    interrompe le altre: quel motivo diventa `errore_tecnico` con
    `motivo_errore` valorizzato, cosi' l'esito finisce nel file e nella
    memoria invece di sparire. E' lo stesso principio di fallimento
    parziale dichiarato gia' adottato in
    `estrazione_atto.EsitoEstrazione.passaggi_falliti`.

    `errore_tecnico`, NON `astensione_modello` (contratto 1.2): un
    guasto e un'astensione sono cose diverse e non vanno mai collassate.
    L'astensione e' il sistema che funziona e rifiuta di argomentare
    senza ancoraggio; il troncamento e' il sistema rotto. Confonderli
    farebbe sembrare prudenza un guasto - e all'avvocato che legge la
    memoria devono apparire come due cose diverse, perche' lo sono.

    Dalla 1.11: un'eccezione IMPREVISTA (non RispostaTroncata, gia'
    gestita per-esito qui sotto e sul FATTO - una rottura di rete, un
    bug) non fa piu' sparire i motivi gia' generati. Caso reale che ha
    motivato la correzione: un crash sulla sezione FATTO, generata per
    ultima, ha buttato via 4 chiamate di Fase 3 gia' completate e pagate
    in tempo di GPU - nessun file le conservava. Solleva
    `GenerazioneFase3Parziale`, che porta con se' i motivi completati (e
    quelli mancanti, riempiti con un placeholder `errore_tecnico`, cosi'
    l'array resta lungo quanto `dossier['esiti']` - il controllo 5 di
    copertura non lo saprebbe altrimenti gestire): il chiamante decide se
    e come salvarli, questa funzione si limita a non perderli.

    on_progresso: None (default) = comportamento invariato. Notificato
    UNA volta per ogni chiamata LLM EFFETTIVA (non per gli esiti che
    astensione/errore_tecnico decidono senza chiamare il modello - vedi
    _motivo_per_esito), con {'passo': 'fase3_motivo_<eccezione_id>'} o
    {'passo': 'fase3_fatto'}. Vedi _notifica() per la garanzia di
    non-interferenza."""
    motivi: list[dict] = []
    try:
        for esito in dossier["esiti"]:
            motivi.append(_motivo_per_esito(base_url, dossier, esito, seed=seed, on_progresso=on_progresso))
        fatto = _sezione_fatto(base_url, dossier, seed=seed, on_progresso=on_progresso)
    except Exception as errore:
        for esito in dossier["esiti"][len(motivi):]:
            motivi.append(_motivo_in_errore(
                esito["eccezione_id"],
                f"Non generato: la corsa si e' interrotta su un'eccezione imprevista prima di "
                f"raggiungere questo esito ({type(errore).__name__}: {errore}).",
                esito["eccezioni_accorpate"],
            ))
        raise GenerazioneFase3Parziale(errore, motivi) from errore

    return {
        "meta": {
            "versione_contratto": VERSIONE_CONTRATTO,
            "generato_il": _adesso(),
            "sha256_dossier": sha256_canonico(dossier),
        },
        "fatto": fatto,
        "motivi": motivi,
        "coerenza": None,
    }


class GenerazioneFase3Parziale(Exception):
    """Sollevata da `redigi_atto` quando un'eccezione imprevista interrompe
    la generazione DOPO che almeno una chiamata e' gia' andata a buon
    fine. Porta `motivi_parziali` (lunghezza sempre pari a
    `dossier['esiti']`, i mancanti come `errore_tecnico` - vedi
    `redigi_atto`) cosi' il chiamante puo' scrivere un atto parziale ma
    valido contro lo schema invece di perdere il lavoro fatto. La causa
    originale resta in `causa` e come `__cause__` (`raise ... from`)."""

    def __init__(self, causa: BaseException, motivi_parziali: list[dict]):
        self.causa = causa
        self.motivi_parziali = motivi_parziali
        super().__init__(str(causa))


def _motivo_per_esito(base_url: str, dossier: dict, esito: dict, seed: int | None = None,
                      on_progresso: Callable[[dict], None] | None = None) -> dict:
    """Una voce di `motivi` per OGNI esito del dossier, stesso ordine -
    le astensioni compaiono come voci esplicite, mai come omissioni
    (principio 3 del contratto, controllo Python n. 5 di copertura)."""
    eccezione_id = esito["eccezione_id"]
    stato = esito["stato"]

    if stato == "eccezione_fondata":
        return _motivo_astenuto(
            eccezione_id, "eccezione_fondata",
            esito.get("nota") or "Il motore delle regole ritiene l'eccezione avversaria fondata: "
                                  "nessuna confutazione tentata, cercare terreno diverso.",
            esito["eccezioni_accorpate"],
        )

    if stato in ("astensione", "non_classificata"):
        return _motivo_astenuto(
            eccezione_id, "astensione_dossier",
            esito.get("motivo_astensione") or "Astensione decisa in Fase 2, motivo non registrato nel dossier.",
            esito["eccezioni_accorpate"],
        )

    if stato == "errore_tecnico":
        # Il guasto e' avvenuto in Fase 2 e si propaga come tale: non si
        # "riprova" in Fase 3 e non diventa un'astensione strada facendo.
        return _motivo_in_errore(
            eccezione_id,
            esito.get("motivo_errore") or "Errore tecnico in Fase 2, motivo non registrato nel dossier.",
            esito["eccezioni_accorpate"],
        )

    if stato != "confutabile":
        raise ValueError(
            f"esito '{eccezione_id}': stato '{stato}' non previsto da fase2_dossier.schema.json - "
            "il dossier non doveva superare la validazione"
        )

    schema = constrained_decoding.costruisci_schema_confutazione(ids_citabili(esito["estratti_citabili"]))
    sistema, utente = _prompt_per_eccezione(dossier, esito)
    _notifica(on_progresso, passo=f"fase3_motivo_{eccezione_id}")
    try:
        generato = constrained_decoding.genera_con_schema(base_url, sistema, utente, schema, n_predict=3072, seed=seed)
    except llama_server_client.RispostaTroncata as troncata:
        return _motivo_in_errore(
            eccezione_id,
            f"Chiamata di Fase 3 troncata per questo motivo: {troncata.motivo}, "
            f"n_predict={troncata.n_predict_usato}, "
            f"{len(troncata.contenuto_parziale)} caratteri parziali scartati. "
            f"Nessun testo generato. Rilanciare la Fase 3 per la sola eccezione "
            f"{eccezione_id} con n_predict maggiore, oppure trattare il motivo a mano.",
            esito["eccezioni_accorpate"],
        )

    if generato["esito"] == "astensione":
        return _motivo_astenuto(eccezione_id, "astensione_modello", generato["dichiarazione"],
                                 esito["eccezioni_accorpate"])

    return {
        "eccezione_id": eccezione_id,
        "eccezioni_accorpate": list(esito["eccezioni_accorpate"]),
        "esito": "trattata",
        "paragrafi": _paragrafi_con_id(eccezione_id, generato["paragrafi"]),
        "dichiarazione_astensione": None,
        "motivo_errore": None,
    }


def _motivo_astenuto(eccezione_id: str, esito: str, dichiarazione: str,
                     accorpate: list[str] | None = None) -> dict:
    """Voce di `motivi` senza paragrafi, per un esito in cui il sistema ha
    funzionato e non si argomenta - il contratto impone `paragrafi: []`,
    `dichiarazione_astensione` non vuota e `motivo_errore` null
    (allOf/if/then, ricontrollato dal controllo Python n. 4)."""
    return {
        "eccezione_id": eccezione_id,
        "eccezioni_accorpate": list(accorpate or [eccezione_id]),
        "esito": esito,
        "paragrafi": [],
        "dichiarazione_astensione": dichiarazione,
        "motivo_errore": None,
    }


def _motivo_in_errore(eccezione_id: str, motivo_errore: str,
                      accorpate: list[str] | None = None) -> dict:
    """Voce di `motivi` per un GUASTO, mai per un'astensione. Il contratto
    impone `paragrafi: []`, `motivo_errore` non vuoto e
    `dichiarazione_astensione` null: sono due campi distinti apposta,
    perche' un file in cui i due si confondono non permette piu' di
    contare quante volte il sistema ha scelto di tacere e quante volte si
    e' rotto."""
    return {
        "eccezione_id": eccezione_id,
        "eccezioni_accorpate": list(accorpate or [eccezione_id]),
        "esito": "errore_tecnico",
        "paragrafi": [],
        "dichiarazione_astensione": None,
        "motivo_errore": motivo_errore,
    }


def _sezione_fatto(base_url: str, dossier: dict, seed: int | None = None,
                   on_progresso: Callable[[dict], None] | None = None) -> dict:
    """La sezione FATTO e' ancorata a F00/F01: anche i fatti hanno ancore
    risolvibili, non solo il diritto (vedi la convenzione riservata di
    `fonti` in fase2_dossier.schema.json).

    Dalla 1.11: l'astensione e' un esito di prima classe (contratto
    1.11, changelog). Prima faceva fallire l'intera corsa con un
    RuntimeError - una decisione rivista dopo un caso reale in cui il
    modello si e' astenuto CORRETTAMENTE (il dossier aveva una sola
    fonte F00 sintetica, materiale davvero insufficiente): trattare quella
    prudenza come un guasto tecnico confondeva "il sistema ha funzionato
    ed e' stato cauto" con "il sistema si e' rotto", esattamente la
    distinzione che il contratto impone di non confondere per i motivi.
    Stessa gestione del troncamento gia' usata in `_motivo_per_esito`."""
    citabili = [
        {
            "estratto_id": e["estratto_id"],
            # F01 resta "atto di controparte" anche nel FATTO: qui riferire
            # cosa la controparte deduce e' l'uso legittimo per eccellenza,
            # ma la marcatura serve comunque - un paragrafo del FATTO non
            # deve poter fondare nulla sull'atto avversario (controllo 14).
            "provenienza": "atto_controparte" if e["fonte_id"] == "F01" else "regola",
        }
        for e in dossier["estratti"] if e["fonte_id"] in FONTI_DEL_FATTO
    ]
    if not citabili:
        raise ValueError(
            "nessun estratto su F00/F01 nel dossier: la sezione FATTO non ha nulla a cui ancorarsi. "
            "F00 (fatti di causa) e' obbligatorio per costruzione in Fase 2 - il dossier e' malformato"
        )

    schema = constrained_decoding.costruisci_schema_confutazione(ids_citabili(citabili))
    sistema, utente = _prompt_fatto(dossier, citabili)
    _notifica(on_progresso, passo="fase3_fatto")
    try:
        generato = constrained_decoding.genera_con_schema(base_url, sistema, utente, schema, n_predict=3072, seed=seed)
    except llama_server_client.RispostaTroncata as troncata:
        return {
            "esito": "errore_tecnico", "paragrafi": [], "dichiarazione_astensione": None,
            "motivo_errore": f"Chiamata della sezione FATTO troncata: {troncata.motivo}, "
                              f"n_predict={troncata.n_predict_usato}, "
                              f"{len(troncata.contenuto_parziale)} caratteri parziali scartati. "
                              "Nessun testo generato. Rilanciare la Fase 3 con n_predict maggiore.",
        }

    if generato["esito"] == "astensione":
        return {
            "esito": "astensione_modello", "paragrafi": [],
            "dichiarazione_astensione": generato["dichiarazione"], "motivo_errore": None,
        }

    return {
        "esito": "trattata", "paragrafi": _paragrafi_con_id("FATTO", generato["paragrafi"]),
        "dichiarazione_astensione": None, "motivo_errore": None,
    }


# ------------------------------------------------------------------ Fase 3-bis


def costruisci_input_coerenza(obiettivo: str, riassunti: list[dict]) -> dict:
    """Input della passata di coerenza, conforme a
    `coerenza.schema.json#/$defs/input`. Costruito deterministicamente da
    Python: NESSUNA chiamata LLM di riassunto (sarebbe una generazione in
    piu' proprio dove il punto e' spendere una sola chiamata).

    obiettivo troncato a 300 char e riassunti a 400 come impone lo schema.
    1.27: cio' che tiene il budget non e' piu' il numero totale di motivi
    (era 15, e su 24 atti reali su 45 non bastava) ma l'ampiezza della
    finestra - 8 x 400 char = ~1k token per chiamata, qualunque sia il
    numero di motivi dell'atto."""
    return {
        "obiettivo": obiettivo[:300],
        "motivi": [
            {
                "eccezione_id": r["eccezione_id"],
                "esito": r["esito"],
                "famiglia": r["famiglia"],
                "riassunto": r["riassunto"][:400],
            }
            for r in riassunti
        ],
    }


def passata_coerenza(base_url: str, obiettivo: str, motivi_finestra: list[dict],
                     seed: int | None = None,
                     on_progresso: Callable[[dict], None] | None = None,
                     passo: str = "fase3bis_coerenza") -> dict | None:
    """UNA chiamata LLM sui riassunti di UNA finestra di motivi, DOPO
    l'assemblaggio e PRIMA del rendering. Ritorna `{conflitti}` grezzo,
    oppure None se la chiamata e' stata troncata.

    1.27: la passata non produce piu' l'ordine. L'ordine lo calcola
    `ordine_motivi.py` da rango processuale, perche' una permutazione
    generata su 56 motivi il modello non la produce (vedi il docstring di
    quel modulo per la misura). Qui resta il compito per cui il modello
    serve davvero: accorgersi che due motivi si contraddicono. E' un
    giudizio locale, a coppie, e su una finestra corta il bias posizionale
    che rende inaffidabile una lista lunga non ha spazio per mordere.

    Il chiamante (entry point) applica il controllo Python n. 11 - due id
    diversi e appartenenti alla finestra - che la grammatica non impone.
    Violazione o None -> la finestra viene scartata e il fatto entra nella
    copertura dichiarata: le altre finestre proseguono, e una coppia mai
    esaminata non viene mai spacciata per una coppia senza conflitti.

    Non riscrive il testo dei paragrafi, non tocca le ancore, non risolve
    i conflitti: li dichiara. La decisione resta all'avvocato."""
    eccezione_ids = [m["eccezione_id"] for m in motivi_finestra]
    schema = constrained_decoding.costruisci_schema_coerenza(eccezione_ids)

    righe = [f"Obiettivo dell'atto: {obiettivo}", "", "Motivi già redatti:"]
    for motivo in motivi_finestra:
        famiglia = motivo["famiglia"] or "famiglia non classificata"
        righe.append(f"\n[{motivo['eccezione_id']}] ({motivo['esito']}, {famiglia})\n{motivo['riassunto']}")
    righe.append("\nSegnala i conflitti che vedi fra questi motivi.")

    _notifica(on_progresso, passo=passo)
    try:
        return constrained_decoding.genera_con_schema(
            base_url, SISTEMA_COERENZA, "\n".join(righe), schema, n_predict=1536, temperature=0.3, seed=seed,
        )
    except llama_server_client.RispostaTroncata:
        return None


if __name__ == "__main__":
    # Smoke test locale: nessuna chiamata di rete, nessun grafo. Costruisce
    # i prompt e gli schemi runtime da un dossier finto ma conforme alla
    # forma del contratto - dimostra che la Fase 3 lavora interamente
    # dentro il dossier, che e' il punto dello split.
    dossier_finto = {
        "meta": {"versione_contratto": VERSIONE_CONTRATTO, "generato_il": _adesso(), "sha256_estrazione": "0" * 64},
        "obiettivo": "Memoria di replica in opposizione a decreto ingiuntivo",
        "fatti_di_causa": "Il debitore ha eccepito la prescrizione del credito derivante da un finanziamento.",
        "fonti": [
            {"fonte_id": "F00", "tipo": "fatti_di_causa", "node_id": None, "citazione_breve": "Fatti di causa",
             "provenienza": "input", "verificata": True, "data_vigenza": None, "data_criterio_risoluzione": None},
            {"fonte_id": "F01", "tipo": "atto_controparte", "node_id": None,
             "citazione_breve": "Atto di controparte", "provenienza": "input", "verificata": True,
             "data_vigenza": None, "data_criterio_risoluzione": None},
            {"fonte_id": "F02", "tipo": "articolo", "node_id": "articolo:codice_civile:2946",
             "citazione_breve": "art. 2946 c.c.", "provenienza": "regola", "verificata": True,
             "data_vigenza": None, "data_criterio_risoluzione": None},
        ],
        "estratti": [
            {"estratto_id": "F00E01", "fonte_id": "F00", "inizio": 0, "fine": 84,
             "testo": "Il debitore ha eccepito la prescrizione del credito derivante da un finanziamento."},
            {"estratto_id": "F01E01", "fonte_id": "F01", "inizio": 1204, "fine": 1264,
             "testo": "Il credito è prescritto essendo decorsi oltre cinque anni."},
            {"estratto_id": "F02E01", "fonte_id": "F02", "inizio": 0, "fine": 96,
             "testo": "Salvi i casi in cui la legge dispone diversamente, i diritti si estinguono per prescrizione."},
        ],
        "esiti": [
            {"eccezione_id": "X01", "famiglia": "prescrizione", "stato": "confutabile",
             "contro_argomento": "Il termine ordinario è decennale, non quinquennale.",
             "consolidamento": "pacifico", "nota": "Precondizione: natura_rapporto = finanziamento_rateale.",
             "estratti_citabili": [
                 {"estratto_id": "F01E01", "provenienza": "atto_controparte"},
                 {"estratto_id": "F02E01", "provenienza": "regola"},
             ],
             "motivo_astensione": None, "motivo_errore": None},
            {"eccezione_id": "X02", "famiglia": None, "stato": "non_classificata",
             "contro_argomento": None, "consolidamento": None,
             "nota": "Euristica per keyword senza riscontro.",
             "estratti_citabili": [],
             "motivo_astensione": "Famiglia non riconosciuta - richiede lettura manuale.",
             "motivo_errore": None},
            {"eccezione_id": "X03", "famiglia": "anomalie_contabili", "stato": "errore_tecnico",
             "contro_argomento": None, "consolidamento": None,
             "nota": "Famiglia riconosciuta, regola applicata.",
             "estratti_citabili": [], "motivo_astensione": None,
             "motivo_errore": "Indice semantico non disponibile durante il retrieval per-eccezione "
                              "(layer semantico assente in questo interprete) - rilanciare la Fase 2 nel venv zt_legal_graph_ml."},
        ],
        "fonti_scartate": [],
    }

    sistema, utente = _prompt_per_eccezione(dossier_finto, dossier_finto["esiti"][0])
    print("=== Prompt di sistema, motivo X01 (primi 400 caratteri) ===")
    print(sistema[:400] + "...\n")
    print("=== Prompt utente, motivo X01 ===")
    print(utente + "\n")

    schema = constrained_decoding.costruisci_schema_confutazione(ids_citabili(dossier_finto["esiti"][0]["estratti_citabili"]))
    enum_ancore = schema["oneOf"][0]["properties"]["paragrafi"]["items"]["properties"]["ancore"]["items"]["enum"]
    print(f"Enum runtime delle ancore per X01: {enum_ancore} - il modello non puo' emettere altro.")

    estratti_fatto = [e["estratto_id"] for e in dossier_finto["estratti"] if e["fonte_id"] in FONTI_DEL_FATTO]
    print(f"Estratti ancorabili dalla sezione FATTO (solo F00/F01): {estratti_fatto}")

    print("\n=== Esiti non trattati: astensione e guasto restano distinti ===")
    for esito in dossier_finto["esiti"][1:]:
        motivo = _motivo_per_esito("http://non-chiamato", dossier_finto, esito)
        print(f"  {motivo['eccezione_id']}: esito={motivo['esito']}")
        print(f"      dichiarazione_astensione = {str(motivo['dichiarazione_astensione'])[:60]!r}")
        print(f"      motivo_errore            = {str(motivo['motivo_errore'])[:60]!r}")

    print(f"\nsha256 canonico del dossier: {sha256_canonico(dossier_finto)}")

    riassunti = [
        {"eccezione_id": "X01", "esito": "trattata", "famiglia": "prescrizione",
         "riassunto": "Il termine ordinario è decennale, non quinquennale."},
        {"eccezione_id": "X02", "esito": "astensione_dossier", "famiglia": None,
         "riassunto": "Famiglia non riconosciuta - richiede lettura manuale."},
        {"eccezione_id": "X03", "esito": "errore_tecnico", "famiglia": "anomalie_contabili",
         "riassunto": "Guasto in Fase 2: indice semantico non disponibile."},
    ]
    ingresso = costruisci_input_coerenza(dossier_finto["obiettivo"], riassunti)
    schema_coe = constrained_decoding.costruisci_schema_coerenza([m["eccezione_id"] for m in ingresso["motivi"]])
    print(f"Enum runtime dei motivi per la Fase 3-bis: {schema_coe['properties']['ordine_motivi']['items']['enum']}")
    print("\nOK - nessuna chiamata di rete, nessun import del grafo in questo modulo.")
