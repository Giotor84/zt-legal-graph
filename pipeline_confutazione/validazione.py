"""
Validazione di schema e i controlli Python numerati di CONTRATTI_DATI.md.

**Bloccanti per i dati, diagnostici per l'argomentazione.** La maggioranza
solleva `ControlloFallito` e basta: un dato strutturalmente rotto (offset
fuori dal blocco, id fuori dall'enum, eccezione persa nell'accorpamento)
ferma la pipeline rumorosamente, non la degrada - il chiamante non e'
libero di ignorarlo. I controlli 10, 14 e 17 sono l'eccezione dichiarata:
NON verificano l'integrita' dei dati ma la qualita' di un'argomentazione
che il modello potrebbe legittimamente non raggiungere (una data invalida
da annullare, un paragrafo fondato solo sull'atto avversario, un
accorpamento confutato a meta') - restituiscono una lista che l'entry
point registra e piega in `verifica_post_generazione_superata`, non un
`raise`: bloccare l'intera corsa per un difetto di prosa sposterebbe il
confine fra "dato rotto" e "argomento debole" che il contratto tiene
apposta separati.

GBNF garantisce la FORMA, mai la verita'. jsonschema garantisce un po' di
piu' (`if/then`, `uniqueItems`) ma non l'identita' testuale di un
estratto, non l'integrita' referenziale fra due sezioni dello stesso file,
non una permutazione. Questi controlli sono la terza rete, e vivono qui
perche' l'entry point li applichi a OGNI confine di fase.

Zero dipendenze dal grafo: si validano i DATI, e i dati del contratto sono
tutto cio' che serve. E' anche il motivo per cui questo modulo e' testabile
per intero senza store.py.
"""

from __future__ import annotations

import datetime
import json
from functools import lru_cache
from pathlib import Path

import jsonschema

CONTRATTI_DIR = Path(__file__).parent.parent / "contratti"

SCHEMA_FASE1 = "fase1_estrazione.schema.json"
SCHEMA_FASE2 = "fase2_dossier.schema.json"
SCHEMA_FASE3 = "fase3_atto.schema.json"
SCHEMA_COERENZA = "coerenza.schema.json"


class ContrattoViolato(Exception):
    """Base di tutti i fallimenti di questo modulo. Catturarla e proseguire
    e' sempre un errore: se un dato non rispetta il contratto, cio' che
    viene dopo lavora su materiale che non e' quello promesso."""


class SchemaNonValido(ContrattoViolato):
    def __init__(self, nome_schema: str, errori: list[str]):
        self.nome_schema = nome_schema
        self.errori = errori
        elenco = "\n".join(f"  - {e}" for e in errori)
        super().__init__(f"{nome_schema}: {len(errori)} violazioni di schema\n{elenco}")


class ControlloFallito(ContrattoViolato):
    def __init__(self, numero: int, titolo: str, dettaglio: str):
        self.numero = numero
        self.titolo = titolo
        self.dettaglio = dettaglio
        super().__init__(f"controllo Python n. {numero} ({titolo}) FALLITO: {dettaglio}")


# ------------------------------------------------------------------ schema


@lru_cache(maxsize=None)
def _validatore(nome_schema: str) -> jsonschema.protocols.Validator:
    percorso = CONTRATTI_DIR / nome_schema
    if not percorso.is_file():
        raise FileNotFoundError(
            f"contratto '{nome_schema}' non trovato in {CONTRATTI_DIR} - "
            "la sorgente unica dei contratti e' la cartella contratti/ in root del progetto"
        )
    schema = json.loads(percorso.read_text(encoding="utf-8"))
    return jsonschema.Draft202012Validator(schema)


def valida(nome_schema: str, dati: dict, dove: str = "") -> None:
    """Valida contro uno schema di contratto. Solleva SchemaNonValido con
    TUTTE le violazioni, non solo la prima: chi ripara vuole vedere il
    quadro, non scoprirne una per esecuzione."""
    errori = sorted(_validatore(nome_schema).iter_errors(dati), key=lambda e: list(e.path))
    if errori:
        raise SchemaNonValido(
            f"{nome_schema}{f' ({dove})' if dove else ''}",
            [f"{list(e.path) or '(radice)'}: {e.message}" for e in errori],
        )


def valida_sotto_schema(nome_schema: str, puntatore_defs: str, dati: dict, dove: str = "") -> None:
    """Come valida(), ma contro un `$defs/<nome>` invece che contro la
    radice - serve per `coerenza.schema.json`, che descrive due payload
    (input e output) e non un file."""
    schema = json.loads((CONTRATTI_DIR / nome_schema).read_text(encoding="utf-8"))
    sotto = dict(schema["$defs"][puntatore_defs])
    sotto["$defs"] = schema["$defs"]
    errori = sorted(jsonschema.Draft202012Validator(sotto).iter_errors(dati), key=lambda e: list(e.path))
    if errori:
        raise SchemaNonValido(
            f"{nome_schema}#/$defs/{puntatore_defs}{f' ({dove})' if dove else ''}",
            [f"{list(e.path) or '(radice)'}: {e.message}" for e in errori],
        )


# ------------------------------------------------------------------ utilita'


def _data_valida(valore: str | None) -> bool:
    """Controllo 10: la grammatica impone solo la forma
    `[0-9]{4}-[0-9]{2}-[0-9]{2}` - "2026-99-99" e "2026-02-31" passano."""
    if valore is None:
        return True
    try:
        datetime.date.fromisoformat(valore)
        return True
    except ValueError:
        return False


def _ids_citabili(esito: dict) -> list[str]:
    return [voce["estratto_id"] for voce in esito["estratti_citabili"]]


# ------------------------------------------------------------------ i controlli


def controllo_01_integrita_referenziale(dossier: dict, estrazione: dict | None = None,
                                         atto: dict | None = None) -> None:
    """Ogni `eccezione_id` degli esiti esiste in Fase 1; ogni `fonte_id`
    degli estratti esiste in `fonti`; ogni `estratto_id` in
    `estratti_citabili`/`ancore` esiste in `estratti`.

    L'enum runtime lo impone gia' alla GENERAZIONE - il ricontrollo qui e'
    il doppio binario applicato ai dati: se la generazione ha rispettato
    l'enum ma l'assemblaggio Python ha sbagliato a comporre il file, la
    grammatica non se ne accorge."""
    fonti = {f["fonte_id"] for f in dossier["fonti"]}
    estratti = {e["estratto_id"] for e in dossier["estratti"]}

    for estratto in dossier["estratti"]:
        if estratto["fonte_id"] not in fonti:
            raise ControlloFallito(1, "integrita' referenziale",
                                   f"estratto {estratto['estratto_id']} riferisce la fonte "
                                   f"{estratto['fonte_id']}, assente dal registro 'fonti'")

    for esito in dossier["esiti"]:
        for estratto_id in _ids_citabili(esito):
            if estratto_id not in estratti:
                raise ControlloFallito(1, "integrita' referenziale",
                                       f"esito {esito['eccezione_id']}: estratto citabile {estratto_id} "
                                       "assente dal registro 'estratti'")

    if estrazione is not None:
        eccezioni = {e["eccezione_id"] for e in estrazione["eccezioni"]}
        for esito in dossier["esiti"]:
            if esito["eccezione_id"] not in eccezioni:
                raise ControlloFallito(1, "integrita' referenziale",
                                       f"esito {esito['eccezione_id']} non corrisponde a nessuna "
                                       "eccezione della Fase 1")

    if atto is not None:
        for motivo in atto["motivi"]:
            for paragrafo in motivo["paragrafi"]:
                for ancora in paragrafo["ancore"]:
                    if ancora not in estratti:
                        raise ControlloFallito(1, "integrita' referenziale",
                                               f"paragrafo {paragrafo['paragrafo_id']}: ancora {ancora} "
                                               "assente dal registro 'estratti' del dossier")
        for paragrafo in atto["fatto"]["paragrafi"]:
            for ancora in paragrafo["ancore"]:
                if ancora not in estratti:
                    raise ControlloFallito(1, "integrita' referenziale",
                                           f"paragrafo {paragrafo['paragrafo_id']}: ancora {ancora} "
                                           "assente dal registro 'estratti' del dossier")


def controllo_02_offset(dossier: dict, testi_fonte: dict[str, str]) -> None:
    """`0 <= inizio < fine <= len(testo_fonte)` e
    `estratto.testo == testo_fonte[inizio:fine]`.

    L'identita' TESTUALE non e' esprimibile ne' in JSON Schema ne' in
    GBNF, ed e' la promessa centrale del progetto: la tripla
    (fonte_id, inizio, fine) deve puntare davvero al testo che l'estratto
    dichiara. Un estratto che non supera questo controllo e' una citazione
    inventata, per quanto lo schema sia formalmente rispettato.

    testi_fonte: {fonte_id: testo integrale}. Una fonte assente da questa
    mappa non viene saltata - e' un errore: significa che non si sa contro
    cosa verificare."""
    for estratto in dossier["estratti"]:
        fonte_id = estratto["fonte_id"]
        if fonte_id not in testi_fonte:
            raise ControlloFallito(2, "offset",
                                   f"estratto {estratto['estratto_id']}: testo della fonte {fonte_id} "
                                   "non disponibile, impossibile verificare l'identita' testuale")
        testo = testi_fonte[fonte_id]
        inizio, fine = estratto["inizio"], estratto["fine"]
        if not (0 <= inizio < fine <= len(testo)):
            raise ControlloFallito(2, "offset",
                                   f"estratto {estratto['estratto_id']}: intervallo [{inizio}:{fine}] "
                                   f"fuori dal testo di {fonte_id} (lungo {len(testo)})")
        if estratto["testo"] != testo[inizio:fine]:
            raise ControlloFallito(2, "offset",
                                   f"estratto {estratto['estratto_id']}: il testo dichiarato NON coincide con "
                                   f"{fonte_id}[{inizio}:{fine}].\n"
                                   f"      dichiarato: {estratto['testo'][:90]!r}\n"
                                   f"      reale     : {testo[inizio:fine][:90]!r}")


def controllo_03_ancoraggio_fase1(estrazione: dict) -> None:
    """Ogni esito diverso da `ancorata` produce una voce in `buchi`, e mai
    il primo match d'ufficio.

    La localizzazione vera la fa localizza.py; qui si verifica che il
    RISULTATO sia stato dichiarato: un'ancora ambigua o parziale che non
    compare fra i buchi e' un'omissione silenziosa, cioe' il modo esatto
    in cui un processo asincrono diventa pericoloso."""
    # 1.24: le voci di `buchi` sono {tipo, testo}; il controllo cerca
    # l'eccezione_id nel TESTO, come prima - il tipo non lo sostituisce.
    buchi = " ".join(b["testo"] for b in estrazione["buchi"])
    for eccezione in estrazione["eccezioni"]:
        stato = eccezione["ancora"]["stato"]
        if stato == "ancorata":
            continue
        if eccezione["eccezione_id"] not in buchi:
            raise ControlloFallito(3, "ancoraggio Fase 1",
                                   f"eccezione {eccezione['eccezione_id']} ha ancora '{stato}' ma non "
                                   "compare in 'buchi' - un ancoraggio non riuscito va dichiarato")


def controllo_18_non_ancorate_fuori_da_eccezioni(estrazione: dict) -> None:
    """Contratto 1.15: nessuna eccezione ha `ancora.stato == 'non_ancorata'`.

    Il filtro (estrazione_atto._scarta_non_ancorate) gira PRIMA che una
    unita' diventi un'eccezione, quindi in condizioni normali questo
    controllo non trova mai niente da segnalare - e' la rete di sicurezza
    che verifica che quel filtro abbia davvero funzionato, non un secondo
    meccanismo che fa lo stesso lavoro. Trovato dal vivo (2026-08-24, atto
    atto-prova): senza questo vincolo, un passaggio fabbricato dal modello
    (mai esistito nell'atto) diventava un'eccezione reale (X01), veniva
    classificato in Fase 2 e poteva essere confutato in Fase 3 - un
    'ancoraggio non riuscito dichiarato' (controllo 3) non e' la stessa
    cosa di 'un fatto inesistente mai diventato un'eccezione'."""
    for eccezione in estrazione["eccezioni"]:
        if eccezione["ancora"]["stato"] == "non_ancorata":
            raise ControlloFallito(18, "non_ancorata fuori da eccezioni",
                                   f"eccezione {eccezione['eccezione_id']} ha ancora 'non_ancorata' - "
                                   "il testo non esiste nell'atto e non doveva mai diventare un'eccezione "
                                   "(vedi estrazione_atto._scarta_non_ancorate)")


def controllo_04_condizionali(dossier: dict, atto: dict | None = None) -> None:
    """`motivo_astensione` sse `stato ∈ {astensione, non_classificata}`;
    `motivo_errore` sse `stato = errore_tecnico`; mai entrambi;
    `estratti_citabili` non vuoto sse `stato = confutabile`.

    Negli schemi c'e' gia' via `if/then`, ma il convertitore json_schema
    di llama.cpp li IGNORA in silenzio: se un giorno uno di questi payload
    passasse dal convertitore, la garanzia sparirebbe senza rumore. Qui
    e' Python, e Python non ignora niente."""
    for esito in dossier["esiti"]:
        stato = esito["stato"]
        eid = esito["eccezione_id"]
        ha_astensione = esito["motivo_astensione"] is not None
        ha_errore = esito["motivo_errore"] is not None

        if ha_astensione and ha_errore:
            raise ControlloFallito(4, "condizionali",
                                   f"esito {eid}: motivo_astensione e motivo_errore entrambi valorizzati - "
                                   "un'astensione e un guasto non sono la stessa cosa e non coesistono")
        if (stato in ("astensione", "non_classificata")) != ha_astensione:
            raise ControlloFallito(4, "condizionali",
                                   f"esito {eid}: stato '{stato}' e motivo_astensione "
                                   f"{'presente' if ha_astensione else 'assente'} - devono corrispondere")
        if (stato == "errore_tecnico") != ha_errore:
            raise ControlloFallito(4, "condizionali",
                                   f"esito {eid}: stato '{stato}' e motivo_errore "
                                   f"{'presente' if ha_errore else 'assente'} - devono corrispondere")
        if (stato == "confutabile") != bool(esito["estratti_citabili"]):
            raise ControlloFallito(4, "condizionali",
                                   f"esito {eid}: stato '{stato}' con "
                                   f"{len(esito['estratti_citabili'])} estratti citabili - "
                                   "non vuoti se e solo se confutabile")

    if atto is not None:
        # FATTO (contratto 1.11): stessa forma di un motivo, ristretta a
        # tre stati - niente 'astensione_dossier' ne' 'eccezione_fondata',
        # il FATTO non ha un motore di regole a monte che possa deciderle
        # prima della chiamata.
        fatto = atto["fatto"]
        ha_dichiarazione_fatto = fatto["dichiarazione_astensione"] is not None
        ha_errore_fatto = fatto["motivo_errore"] is not None
        if ha_dichiarazione_fatto and ha_errore_fatto:
            raise ControlloFallito(4, "condizionali",
                                   "FATTO: dichiarazione_astensione e motivo_errore entrambi valorizzati")
        if (fatto["esito"] == "errore_tecnico") != ha_errore_fatto:
            raise ControlloFallito(4, "condizionali",
                                   f"FATTO: esito '{fatto['esito']}' e motivo_errore "
                                   f"{'presente' if ha_errore_fatto else 'assente'} - devono corrispondere")
        if (fatto["esito"] == "astensione_modello") != ha_dichiarazione_fatto:
            raise ControlloFallito(4, "condizionali",
                                   f"FATTO: esito '{fatto['esito']}' e dichiarazione_astensione "
                                   f"{'presente' if ha_dichiarazione_fatto else 'assente'} - "
                                   f"{'attesa' if fatto['esito'] == 'astensione_modello' else 'attesa null'}")

        for motivo in atto["motivi"]:
            esito, mid = motivo["esito"], motivo["eccezione_id"]
            ha_dichiarazione = motivo["dichiarazione_astensione"] is not None
            ha_errore = motivo["motivo_errore"] is not None
            if ha_dichiarazione and ha_errore:
                raise ControlloFallito(4, "condizionali",
                                       f"motivo {mid}: dichiarazione_astensione e motivo_errore entrambi valorizzati")
            if (esito == "errore_tecnico") != ha_errore:
                raise ControlloFallito(4, "condizionali",
                                       f"motivo {mid}: esito '{esito}' e motivo_errore "
                                       f"{'presente' if ha_errore else 'assente'} - devono corrispondere")
            # Tre casi, non due. La versione precedente esigeva
            # `dichiarazione_astensione` per OGNI esito diverso da
            # "trattata", ed era scritta per l'enum a quattro valori del
            # contratto 1.1: con l'arrivo di `errore_tecnico` (1.2) faceva
            # fallire il controllo proprio sui guasti, che per contratto
            # hanno dichiarazione null e motivo_errore valorizzato.
            # Trovato da test_integrazione_mockata, non a lettura: lo
            # schema aveva gia' i tre rami, il controllo Python no - ed e'
            # esattamente il tipo di divergenza per cui il doppio binario
            # esiste.
            deve_avere_dichiarazione = esito in ("astensione_modello", "astensione_dossier",
                                                  "eccezione_fondata")
            if deve_avere_dichiarazione != ha_dichiarazione:
                raise ControlloFallito(4, "condizionali",
                                       f"motivo {mid}: esito '{esito}' e dichiarazione_astensione "
                                       f"{'presente' if ha_dichiarazione else 'assente'} - "
                                       f"{'attesa' if deve_avere_dichiarazione else 'attesa null'}")


def controllo_05_copertura(estrazione: dict, dossier: dict, atto: dict | None = None) -> None:
    """|esiti| == |eccezioni| == |motivi|, STESSO ORDINE.

    Nessuna eccezione saltata in silenzio, in nessuna direzione. L'ordine
    conta quanto il conteggio: e' cio' che rende lecito accoppiare la
    i-esima eccezione con l'i-esimo esito senza una chiave esplicita."""
    ids_eccezioni = [e["eccezione_id"] for e in estrazione["eccezioni"]]

    # Dal contratto 1.7 un esito puo' coprire PIU' eccezioni (accorpamento
    # per stessa famiglia e stesse fonti): la copertura si verifica
    # sull'unione di eccezioni_accorpate, non sul rappresentante.
    coperte: list[str] = []
    for esito in dossier["esiti"]:
        coperte.extend(esito["eccezioni_accorpate"])
        if esito["eccezione_id"] not in esito["eccezioni_accorpate"]:
            raise ControlloFallito(5, "copertura totale",
                                   f"esito {esito['eccezione_id']}: il rappresentante non compare "
                                   f"fra le eccezioni accorpate {esito['eccezioni_accorpate']}")

    doppie = sorted({i for i in coperte if coperte.count(i) > 1})
    if doppie:
        raise ControlloFallito(5, "copertura totale",
                               f"eccezioni coperte da piu' di un esito: {doppie} - "
                               "l'accorpamento ha duplicato invece di fondere")
    if sorted(coperte) != sorted(ids_eccezioni):
        mancanti = sorted(set(ids_eccezioni) - set(coperte))
        estranee = sorted(set(coperte) - set(ids_eccezioni))
        raise ControlloFallito(5, "copertura totale",
                               f"eccezioni di Fase 1 non coperte dagli esiti: {mancanti or 'nessuna'}; "
                               f"esiti che citano eccezioni inesistenti: {estranee or 'nessuno'}")

    if atto is not None:
        ids_esiti = [e["eccezione_id"] for e in dossier["esiti"]]
        ids_motivi = [m["eccezione_id"] for m in atto["motivi"]]
        if ids_esiti != ids_motivi:
            raise ControlloFallito(5, "copertura totale",
                                   f"esiti di Fase 2 {ids_esiti} != motivi di Fase 3 {ids_motivi} "
                                   "(conteggio o ordine)")
        for esito, motivo in zip(dossier["esiti"], atto["motivi"]):
            if esito["eccezioni_accorpate"] != motivo["eccezioni_accorpate"]:
                raise ControlloFallito(5, "copertura totale",
                                       f"motivo {motivo['eccezione_id']}: accorpamento diverso da "
                                       f"quello del dossier ({motivo['eccezioni_accorpate']} contro "
                                       f"{esito['eccezioni_accorpate']})")


def controllo_06_non_degenere(atto: dict) -> None:
    """`uniqueItems` sulle ancore, `testo` non vuoto dopo `strip()`
    (la grammatica ammette `"   "`), nessun paragrafo duplicato letterale."""
    visti: dict[str, str] = {}
    for paragrafo in _tutti_i_paragrafi(atto):
        pid, testo = paragrafo["paragrafo_id"], paragrafo["testo"]
        if not testo.strip():
            raise ControlloFallito(6, "contenuto non degenere",
                                   f"paragrafo {pid}: testo vuoto dopo strip() - "
                                   "la grammatica ammette '   ', il contratto no")
        if len(set(paragrafo["ancore"])) != len(paragrafo["ancore"]):
            raise ControlloFallito(6, "contenuto non degenere",
                                   f"paragrafo {pid}: ancore duplicate {paragrafo['ancore']}")
        chiave = " ".join(testo.split())
        if chiave in visti:
            raise ControlloFallito(6, "contenuto non degenere",
                                   f"paragrafo {pid} e' identico a {visti[chiave]}")
        visti[chiave] = pid


def controllo_06_bis_unicita_citabili(dossier: dict) -> None:
    """Unicita' degli `estratto_id` dentro `estratti_citabili`.

    Non e' esprimibile con `uniqueItems`: dalla 1.2 sono oggetti, e due
    voci con lo stesso id e provenienza diversa sarebbero formalmente
    "uniche" pur essendo lo stesso estratto offerto due volte - il che
    genererebbe un enum GBNF con un'alternativa ripetuta."""
    for esito in dossier["esiti"]:
        ids = _ids_citabili(esito)
        if len(set(ids)) != len(ids):
            raise ControlloFallito(6, "unicita' degli estratti citabili",
                                   f"esito {esito['eccezione_id']}: estratto_id ripetuti in "
                                   f"estratti_citabili ({ids})")


def controllo_07_citazioni_nella_prosa(righe_verifica: list, righe_giurisprudenza: list) -> list[str]:
    """La grammatica vincola le `ancore`, NON il campo `testo`: il modello
    puo' ancora NOMINARE nella prosa una fonte non ancorata ("come noto,
    l'art. 1957 c.c. ...").

    Unico controllo che RITORNA invece di sollevare, e non per
    incoerenza: il contratto prescrive una risposta graduata (sezione
    respinta, rigenerata una volta, poi astensione dichiarata) e
    `meta.verifica_post_generazione_superata = false`. Un'eccezione qui
    impedirebbe di scrivere il file, che invece DEVE essere scritto e
    marcato come non pronto. Ritorna i problemi; sta all'entry point
    agire e marcare il file."""
    problemi = []
    for riga in righe_verifica:
        esito = riga.esito
        if not esito.trovato or esito.tema_in_linea is False:
            problemi.append(f"citazione normativa nella prosa non verificata: "
                            f"art. {riga.citazione.numero} ({riga.citazione.codice}) - {esito.dettaglio}")
    for riga in righe_giurisprudenza:
        esito = riga.esito
        if not esito.verificabile:
            problemi.append(f"citazione di giurisprudenza non verificabile nel corpus: "
                            f"{riga.citazione.ufficio} - {esito.dettaglio}")
        elif not esito.trovato or esito.tema_in_linea is False:
            problemi.append(f"citazione di giurisprudenza nella prosa non verificata: "
                            f"{riga.citazione.ufficio} - {esito.dettaglio}")
    return problemi


def controllo_10_date_di_calendario(*documenti: dict) -> list[str]:
    """`datetime.date.fromisoformat` su ogni `data_rilevante`,
    `data_vigenza`, `data_criterio_risoluzione`.

    Ritorna le date invalide invece di sollevare, perche' il contratto
    prescrive esattamente questo: "data invalida -> trattata come null +
    voce in buchi/memoria". E' l'unica risposta sensata - una data
    sbagliata non invalida il resto dell'estrazione, e buttare via
    un'intera Fase 1 per un "2026-02-31" sarebbe sproporzionato. Sta al
    chiamante annullare il campo e registrare la voce.

    Limite dichiarato: che `data_rilevante` sia DAVVERO dichiarata nel
    testo non e' verificabile ne' in grammatica ne' in modo affidabile in
    Python (l'atto la scrive "14 marzo 2018") - istruzione di prompt +
    revisione."""
    invalide = []
    for documento in documenti:
        if documento is None:
            continue
        for norma in documento.get("citazioni_controparte", {}).get("norme", []):
            if not _data_valida(norma.get("data_rilevante")):
                invalide.append(f"data_rilevante non valida come data di calendario: "
                                f"{norma['data_rilevante']!r} (norma {norma['testo'][:50]!r})")
        for fonte in documento.get("fonti", []):
            for campo in ("data_vigenza", "data_criterio_risoluzione"):
                if not _data_valida(fonte.get(campo)):
                    invalide.append(f"{campo} non valida come data di calendario: "
                                    f"{fonte[campo]!r} (fonte {fonte['fonte_id']})")
        for affermazione in documento.get("affermazioni", []):
            if not _data_valida(affermazione.get("data_vigenza")):
                invalide.append(f"data_vigenza non valida come data di calendario: "
                                f"{affermazione['data_vigenza']!r} "
                                f"(affermazione {affermazione['paragrafo_id']})")
    return invalide


def controllo_11_conflitti_coerenza(conflitti: list[dict], eccezione_ids: list[str]) -> str | None:
    """Ogni conflitto mette in relazione due motivi DIVERSI e appartenenti
    entrambi alla finestra su cui la chiamata ha lavorato.

    La grammatica impone l'enum degli id ma non queste due proprieta'
    (`tra[0] != tra[1]`, e l'appartenenza resta da verificare perche' lo
    schema runtime potrebbe essere stato costruito su un'altra lista).
    Ritorna il motivo del rifiuto, o None se valido - il contratto
    prescrive di scartare la finestra e dichiararlo nella copertura, non
    di fermare la pipeline: la coerenza e' un avviso all'avvocato, non
    una condizione di validita' dell'atto.

    1.27: fino alla 1.26 questo controllo verificava anche che
    `ordine_motivi` fosse una permutazione esatta degli id. Quel campo non
    esiste piu': l'ordine lo calcola Python (`ordine_motivi.py`), quindi e'
    una permutazione per costruzione e non c'e' piu' niente da verificare.
    """
    ammessi = set(eccezione_ids)
    for conflitto in conflitti:
        primo, secondo = conflitto["tra"][0], conflitto["tra"][1]
        if primo == secondo:
            return f"conflitto con tra[0] == tra[1] ({primo}): un motivo non confligge con se stesso"
        fuori = sorted({primo, secondo} - ammessi)
        if fuori:
            return (f"conflitto fra motivi estranei alla finestra ({fuori}): "
                    f"la finestra conteneva {sorted(ammessi)}")
    return None


def controllo_12_conservazione_fonti(proposte_per_eccezione: dict[str, list[str]],
                                      dossier: dict) -> None:
    """|proposte dalla regola| == |risolte nel registro| + |scartate|,
    nessuna terza via, nessuna sparizione silenziosa.

    E' il lucchetto del percorso "risolvi_fonte unico ingresso": senza
    questo controllo una fonte raccomandata da una regola potrebbe
    svanire fra la proposta e il dossier, e l'unico modo di accorgersene
    sarebbe rileggere il catalogo delle regole a mano.

    proposte_per_eccezione: {eccezione_id: [citazione_breve, ...]} come
    proposte dal catalogo, PRIMA della risoluzione."""
    scartate_per_eccezione: dict[str, int] = {}
    for scartata in dossier["fonti_scartate"]:
        scartate_per_eccezione[scartata["eccezione_id"]] = scartate_per_eccezione.get(scartata["eccezione_id"], 0) + 1

    # Dal contratto 1.7 un esito puo' coprire piu' eccezioni: le fonti di
    # una regola stanno sull'esito che COPRE l'eccezione, non su uno che
    # porta il suo id. Contarle per eccezione_id farebbe risultare sparite
    # tutte le fonti delle eccezioni assorbite.
    risolte_per_eccezione: dict[str, int] = {}
    estratti_per_id = {e["estratto_id"]: e for e in dossier["estratti"]}
    for esito in dossier["esiti"]:
        fonti_da_regola = {
            estratti_per_id[voce["estratto_id"]]["fonte_id"]
            for voce in esito["estratti_citabili"]
            if voce["provenienza"] == "regola" and voce["estratto_id"] in estratti_per_id
        }
        for eccezione_id in esito["eccezioni_accorpate"]:
            risolte_per_eccezione[eccezione_id] = len(fonti_da_regola)

    for eccezione_id, proposte in proposte_per_eccezione.items():
        risolte = risolte_per_eccezione.get(eccezione_id, 0)
        scartate = scartate_per_eccezione.get(eccezione_id, 0)
        if len(proposte) != risolte + scartate:
            raise ControlloFallito(12, "conservazione delle fonti di regola",
                                   f"eccezione {eccezione_id}: {len(proposte)} fonti proposte dal motore "
                                   f"({proposte}) ma {risolte} risolte + {scartate} scartate = "
                                   f"{risolte + scartate} - una fonte e' sparita fra il catalogo e il dossier")


def controllo_13_nullabilita_node_id(dossier: dict) -> None:
    """`node_id == null` <=> `tipo ∈ {fatti_di_causa, atto_controparte}`.

    Gia' imposto dall'`allOf/if/then` nello schema, ricontrollato qui
    perche' e' il lucchetto del controllo 12: una fonte di grafo senza
    node_id reale non puo' superare il controllo 2 sull'identita'
    testuale degli estratti - non ci sarebbe un testo contro cui
    confrontarli."""
    senza_grafo = {"fatti_di_causa", "atto_controparte"}
    for fonte in dossier["fonti"]:
        atteso_null = fonte["tipo"] in senza_grafo
        e_null = fonte["node_id"] is None
        if atteso_null != e_null:
            raise ControlloFallito(13, "nullabilita' di node_id",
                                   f"fonte {fonte['fonte_id']} di tipo '{fonte['tipo']}' ha node_id "
                                   f"{'null' if e_null else repr(fonte['node_id'])} - "
                                   f"atteso {'null' if atteso_null else 'un node_id reale'}")


def controllo_14_atto_controparte_non_e_autorita(atto: dict, dossier: dict) -> list[str]:
    """Nessun paragrafo puo' avere come UNICA ancora un estratto con
    `provenienza: "atto_controparte"`.

    Un estratto F01 riporta cio' che la controparte AFFERMA: serve a dire
    "la controparte deduce X", mai "come stabilito in X". Un paragrafo
    ancorato solo a F01 fonda un argomento sull'atto avversario.

    La grammatica non puo' imporlo - l'enum ammette l'id F01 perche' il
    paragrafo che riferisce l'eccezione DEVE poterlo ancorare: e' l'USO,
    non la disponibilita', a essere vincolato.

    Ritorna i paragrafi in violazione invece di sollevare: il contratto
    prescrive la stessa scala di risposta del controllo 7 (sezione
    respinta, rigenerata una volta, poi errore dichiarato), che e' una
    decisione dell'orchestratore."""
    provenienza_per_estratto: dict[str, set[str]] = {}
    for esito in dossier["esiti"]:
        for voce in esito["estratti_citabili"]:
            provenienza_per_estratto.setdefault(voce["estratto_id"], set()).add(voce["provenienza"])
    fonti_controparte = {f["fonte_id"] for f in dossier["fonti"] if f["tipo"] == "atto_controparte"}
    estratti_controparte = {
        e["estratto_id"] for e in dossier["estratti"] if e["fonte_id"] in fonti_controparte
    }

    violazioni = []
    for paragrafo in _tutti_i_paragrafi(atto):
        ancore = paragrafo["ancore"]
        if ancore and all(a in estratti_controparte for a in ancore):
            violazioni.append(
                f"paragrafo {paragrafo['paragrafo_id']}: ancorato SOLO all'atto di controparte "
                f"({ancore}) - l'atto avversario riferisce una tesi, non fonda un argomento"
            )
    return violazioni


def controllo_15_fonti_non_verificate(dossier: dict, verificabilita: dict[str, tuple[bool, str | None]]) -> None:
    """Nessun estratto citabile puo' venire da una fonte che il grafo
    dichiara non affidabile: `stato_verifica != "verificato"` oppure
    `motivazione_certa is False`.

    Non e' un'etichetta informativa. `stato_verifica = estremi_incerti`
    significa che non si sa con certezza QUALE provvedimento sia quel
    testo: citarlo in un atto significa attribuire un principio a una
    sentenza che potrebbe essere un'altra. `motivazione_certa = False`
    significa che non si sa quale parte del testo sia la motivazione:
    un estratto ritagliato da li' puo' spacciare per principio di diritto
    una porzione che non lo e' - lo svolgimento del processo, o la tesi
    della parte soccombente riportata per essere respinta.

    I nodi restano interrogabili dal retrieval e visibili nella memoria:
    e' la CITAZIONE AUTOMATICA a essere vietata, non la consultazione.

    verificabilita: {node_id: (citabile, motivo)} - fornito dal chiamante,
    perche' questo modulo non tocca il grafo."""
    fonti_per_id = {f["fonte_id"]: f for f in dossier["fonti"]}
    estratti_per_id = {e["estratto_id"]: e for e in dossier["estratti"]}

    for esito in dossier["esiti"]:
        for voce in esito["estratti_citabili"]:
            estratto = estratti_per_id.get(voce["estratto_id"])
            if estratto is None:
                continue  # gia' preso dal controllo 1
            fonte = fonti_per_id.get(estratto["fonte_id"])
            if fonte is None or not fonte["node_id"]:
                continue  # F00/F01: nessun nodo di grafo da verificare
            citabile, motivo = verificabilita.get(fonte["node_id"], (True, None))
            if not citabile:
                raise ControlloFallito(15, "fonti non verificate",
                                       f"esito {esito['eccezione_id']}: l'estratto {voce['estratto_id']} "
                                       f"viene dalla fonte {fonte['fonte_id']} "
                                       f"({fonte['citazione_breve']}), che NON e' citabile "
                                       f"automaticamente - {motivo}")


def controllo_16_estratti_parziali_non_ancorabili(atto: dict, dossier: dict) -> None:
    """Un estratto con `parziale: true` e' MATERIALE DI PROMPT: la Fase 3
    puo' leggerlo, non puo' ancorarvi nulla.

    Contratto 1.5. Nasce da un caso concreto: sull'atto reale di prova, un
    motivo confutabile su quattro non aveva l'estratto della controparte
    perche' la sua ancora era `ancora_parziale`, e la Fase 3 lo avrebbe
    argomentato senza avere davanti le parole avversarie. Dargli
    l'estratto risolve quello; lasciarlo ancorabile ne aprirebbe uno
    peggiore - una tripla (fonte_id, inizio, fine) che dichiara "questo e'
    letteralmente nell'atto" su un ritaglio che la procedura di
    localizzazione ha gia' giudicato non abbastanza simile.

    Le due cose che il contratto tiene separate sono "cosa il modello puo'
    LEGGERE" e "cosa il contratto garantisce come LETTERALE". Questo
    controllo e' il confine fra le due."""
    parziali = {e["estratto_id"] for e in dossier["estratti"] if e.get("parziale")}
    if not parziali:
        return
    for paragrafo in _tutti_i_paragrafi(atto):
        usate = parziali.intersection(paragrafo["ancore"])
        if usate:
            raise ControlloFallito(
                16, "estratti parziali non ancorabili",
                f"paragrafo {paragrafo['paragrafo_id']}: ancorato a {sorted(usate)}, che sono "
                "estratti con parziale=true - materiale di prompt, non testo verificato. "
                "L'ancoraggio di Fase 1 per quella citazione non e' riuscito "
                "(ancora_parziale): il ritaglio serve al modello per capire cosa dice la "
                "controparte, non per essere citato come letterale")


def controllo_17_copertura_f01_negli_accorpamenti(atto: dict, dossier: dict) -> list[str]:
    """Un motivo che accorpa piu' eccezioni deve confutarle TUTTE, non solo
    la prima.

    `accorpa_esiti` (contratto 1.7) fonde N eccezioni con stessa famiglia e
    stesse fonti in un esito solo, e porta dentro l'estratto F01 di
    OGNUNA - la premessa era che il modello, avendole tutte davanti, le
    avrebbe confutate tutte in una chiamata sola invece di una per
    ciascuna. Niente lo garantiva: la grammatica vincola la FORMA di
    'ancore', non quali id il modello sceglie di usare, e un motivo che
    ancora solo il primo F01 e ignora gli altri sei e' peggio di sette
    motivi ripetitivi - copre la stessa eccezione nella contabilita' del
    controllo 5 (`eccezioni_accorpate`), ma nel testo effettivo ne resta
    fuori una tesi avversaria su sette senza che nulla lo segnali.

    Verifica, per ogni esito accorpato (len(eccezioni_accorpate) > 1), che
    OGNI estratto F01 (`atto_controparte`) di quell'esito compaia in almeno
    un'ancora fra TUTTI i paragrafi del motivo corrispondente - non
    necessariamente nello stesso paragrafo, l'accorpamento non impone una
    prosa unica.

    Stessa scala di risposta del controllo 14 (non solleva): un'insieme di
    paragrafi che copre solo in parte le eccezioni accorpate e' un difetto
    di ARGOMENTAZIONE del modello, non un dato strutturalmente rotto - lo
    stesso confine per cui il controllo 14 e' diagnostico e il controllo 16
    e' bloccante."""
    motivo_per_eccezione = {m["eccezione_id"]: m for m in atto["motivi"]}
    violazioni = []
    for esito in dossier["esiti"]:
        accorpate = esito["eccezioni_accorpate"]
        if len(accorpate) <= 1 or esito["stato"] != "confutabile":
            continue
        f01_attesi = [v["estratto_id"] for v in esito["estratti_citabili"]
                      if v["provenienza"] == "atto_controparte"]
        if not f01_attesi:
            continue
        motivo = motivo_per_eccezione.get(esito["eccezione_id"])
        if motivo is None:
            continue  # controllo 5 se ne accorge e ferma prima di arrivare qui
        ancore_usate = {a for paragrafo in motivo["paragrafi"] for a in paragrafo["ancore"]}
        mancanti = [f for f in f01_attesi if f not in ancore_usate]
        if mancanti:
            violazioni.append(
                f"motivo {esito['eccezione_id']}: accorpa {len(accorpate)} eccezioni "
                f"({', '.join(accorpate)}) ma {len(mancanti)}/{len(f01_attesi)} estratti F01 non "
                f"compaiono in nessuna ancora del motivo: {mancanti} - almeno una tesi avversaria "
                "resta senza risposta nel testo, anche se il controllo 5 la conta come coperta"
            )
    return violazioni


def _tutti_i_paragrafi(atto: dict) -> list[dict]:
    paragrafi = list(atto["fatto"]["paragrafi"])
    for motivo in atto["motivi"]:
        paragrafi.extend(motivo["paragrafi"])
    return paragrafi


# ------------------------------------------------------------------ confini


def confine_fase1(estrazione: dict) -> list[str]:
    """Validazione + controlli applicabili all'uscita della Fase 1.
    Ritorna le date invalide da annullare e registrare (controllo 10)."""
    valida(SCHEMA_FASE1, estrazione, "uscita Fase 1")
    controllo_03_ancoraggio_fase1(estrazione)
    controllo_18_non_ancorate_fuori_da_eccezioni(estrazione)
    return controllo_10_date_di_calendario(estrazione)


def confine_fase2(estrazione: dict, dossier: dict, testi_fonte: dict[str, str],
                   proposte_per_eccezione: dict[str, list[str]],
                   verificabilita: dict[str, tuple[bool, str | None]] | None = None) -> list[str]:
    """Validazione + controlli 1, 2, 4, 5, 6-bis, 12, 13, 15 all'uscita
    della Fase 2. Ritorna le date invalide (controllo 10).

    verificabilita: {node_id: (citabile, motivo)} per il controllo 15.
    None lo salta - e in quel caso il salto e' esplicito nella firma, non
    un silenzio: chi chiama senza quella mappa sta dichiarando di non
    avere il grafo sotto mano."""
    valida(SCHEMA_FASE2, dossier, "uscita Fase 2")
    controllo_01_integrita_referenziale(dossier, estrazione=estrazione)
    controllo_02_offset(dossier, testi_fonte)
    controllo_04_condizionali(dossier)
    controllo_05_copertura(estrazione, dossier)
    controllo_06_bis_unicita_citabili(dossier)
    controllo_12_conservazione_fonti(proposte_per_eccezione, dossier)
    controllo_13_nullabilita_node_id(dossier)
    if verificabilita is not None:
        controllo_15_fonti_non_verificate(dossier, verificabilita)
    return controllo_10_date_di_calendario(dossier)


def confine_fase3(estrazione: dict, dossier: dict, atto: dict) -> tuple[list[str], list[str], list[str]]:
    """Validazione + controlli 1, 4, 5, 6, 14, 16, 17 all'uscita della Fase 3.
    Ritorna (date invalide, violazioni del controllo 14, violazioni del
    controllo 17)."""
    valida(SCHEMA_FASE3, atto, "uscita Fase 3")
    controllo_01_integrita_referenziale(dossier, estrazione=estrazione, atto=atto)
    controllo_04_condizionali(dossier, atto=atto)
    controllo_05_copertura(estrazione, dossier, atto=atto)
    controllo_06_non_degenere(atto)
    controllo_16_estratti_parziali_non_ancorabili(atto, dossier)
    return (controllo_10_date_di_calendario(atto),
            controllo_14_atto_controparte_non_e_autorita(atto, dossier),
            controllo_17_copertura_f01_negli_accorpamenti(atto, dossier))


def blocco_esecuzione_coerente() -> None:
    """I tre schemi di file dichiarano `meta.esecuzione` con lo stesso
    identico blocco.

    E' duplicato per scelta - un `$ref` fra file richiederebbe un resolver
    a caricamento e renderebbe gli schemi non validabili da soli - ma la
    duplicazione senza un controllo e' esattamente la deriva silenziosa
    che l'eliminazione della seconda cartella contratti/ voleva togliere
    di mezzo. Qui la deriva diventa un errore rosso."""
    blocchi = {}
    for nome in (SCHEMA_FASE1, SCHEMA_FASE2, SCHEMA_FASE3):
        schema = json.loads((CONTRATTI_DIR / nome).read_text(encoding="utf-8"))
        blocchi[nome] = json.dumps(schema["properties"]["meta"]["properties"]["esecuzione"],
                                    sort_keys=True, ensure_ascii=False)
    distinti = set(blocchi.values())
    if len(distinti) != 1:
        divergenti = [n for n, b in blocchi.items() if b != blocchi[SCHEMA_FASE1]]
        raise ContrattoViolato(
            "il blocco meta.esecuzione e' DIVERSO fra gli schemi di file: "
            f"{divergenti} divergono da {SCHEMA_FASE1}. Le tre copie devono restare identiche - "
            "un campo di riproducibilita' presente in un file e assente in un altro rende "
            "una corsa non ricostruibile proprio dove serve"
        )


if __name__ == "__main__":
    print(f"Contratti letti da: {CONTRATTI_DIR}")
    for nome in (SCHEMA_FASE1, SCHEMA_FASE2, SCHEMA_FASE3, SCHEMA_COERENZA):
        schema = json.loads((CONTRATTI_DIR / nome).read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
        print(f"  {nome:32s} schema valido")

    blocco_esecuzione_coerente()
    print("  meta.esecuzione identico nei tre schemi di file")

    print("\nControlli disponibili:")
    for nome, funzione in sorted(globals().items()):
        if nome.startswith("controllo_") and callable(funzione):
            solleva = "solleva" if "Ritorna" not in (funzione.__doc__ or "") else "ritorna i problemi"
            print(f"  {nome:48s} {solleva}")
