"""Segmentazione delle motivazioni dei Provvedimenti per l'indicizzazione
semantica separata (vedi conversazione: indice diverso da quello delle
Massime, granularità diversa, punteggi non comparabili).

ATTENZIONE PRIMA DI USARE QUESTO MODULO PER COSTRUIRE UN INDICE: il testo
estratto da pdfplumber (bdp_parser_pdf.py) NON ha confini di paragrafo
riconoscibili - verificato su tutti i 31 provvedimenti con motivazione,
0/31 contengono un doppio a-capo (il separatore di paragrafo convenzionale
in testo semplice). I singoli "\n" presenti sono a-capo di IMPAGINAZIONE
del PDF originale (interruzioni di riga a larghezza di pagina, non di
significato - osservato anche un caso di frase duplicata a cavallo di un
a-capo, sintomo dello stesso artefatto), non sono utilizzabili come
confine. Marcatori numerati espliciti ("1.", "2)", "a)") esistono solo in
11/31 documenti e solo su parte del testo.

Quindi: "segmentazione per confini di paragrafo" non è ricostruibile da
questo testo con certezza. Quello implementato qui è un sostituto
dichiarato - segmentazione per FRASE, accumulando frasi consecutive in una
finestra [MIN_LUNGHEZZA_SEGMENTO, MAX_LUNGHEZZA_SEGMENTO], con un confine
di segmento forzato subito dopo un marcatore numerato quando presente
(l'unico segnale strutturale reale disponibile). Non pretende fedeltà al
paragrafo del giudice: è la miglior approssimazione disponibile sul testo
che abbiamo, dichiarata come tale.

Split di frase: euristica su [.!?] seguito da spazio e maiuscola, con
eccezione per le abbreviazioni della prassi giuridica italiana più comuni
(art., artt., sez., cfr., ecc. - lista non esaustiva, vedi
_ABBREVIAZIONI_NON_FINE_FRASE) - non un tokenizzatore linguistico vero,
stesso principio di approssimazione dichiarata di
pipeline_confutazione/extract_citations.py (CONFINE_FRASE_RE), qui più
prudente perché un errore di split qui rompe un segmento a metà frase,
non solo il contesto di una citazione.
"""

import re
from dataclasses import dataclass

MIN_LUNGHEZZA_SEGMENTO = 400  # caratteri - sotto, un segmento è poco più di una frase isolata, semanticamente troppo povero per un embedding utile
MAX_LUNGHEZZA_SEGMENTO = 1500  # caratteri - confermato a 1500 dopo confronto con 800: a 800 il 33% dei segmenti (341/1042) diventava un'eccezione a frase singola più lunga del massimo (le frasi del corpus hanno una coda destra pesante, mediana 365 ma alcune fino a 8041 caratteri) - un vincolo che fallisce un terzo delle volte non descrive più l'indice. La diluizione a 1500 (media ~1200 char/segmento) resta, accettata come costo minore

_ABBREVIAZIONI_NON_FINE_FRASE = (
    "art", "artt", "sez", "cfr", "ord", "sent", "co", "comma", "n", "nn",
    "c.c", "c.p.c", "d.lgs", "l", "r.d", "d.p.r", "cost", "ss", "vol", "pag", "pagg",
    "avv", "dott", "dott.ssa", "prof", "sig", "sig.ra", "rag", "geom",
)
_ABBREVIAZIONI_PATTERN = re.compile(
    r"(?:" + "|".join(re.escape(a) for a in _ABBREVIAZIONI_NON_FINE_FRASE) + r")\.\s*$",
    re.IGNORECASE,
)

_CONFINE_FRASE_PATTERN = re.compile(r"[.!?]+(?=\s+[A-ZÀ-Ý])")
_MARCATORE_NUMERATO_PATTERN = re.compile(r"^\s*(?:\d{1,2}[.\)]|[a-z]\))\s+", re.MULTILINE)


def _spezza_in_frasi(testo: str, confini_extra: frozenset[int] = frozenset()) -> list[tuple[int, int]]:
    """Ritorna gli span (start, end) di ogni frase in `testo` (offset
    locali). Non taglia dopo un punto se il testo appena prima combacia con
    una delle abbreviazioni note (vedi _ABBREVIAZIONI_NON_FINE_FRASE).

    `confini_extra`: posizioni aggiuntive da trattare come inizio-frase
    anche se l'euristica punto+maiuscola non le troverebbe da sole - qui
    usato per i marcatori numerati ("1. Ai fini..."), che non producono un
    confine con la sola euristica perché un marcatore non è una lettera
    maiuscola (senza questo, il forzamento del confine in
    segmenta_motivazione non avrebbe mai una frase che comincia esattamente
    sul marcatore su cui agganciarsi)."""
    confini = set(confini_extra)
    for m in _CONFINE_FRASE_PATTERN.finditer(testo):
        candidato_fine = m.end() - (len(m.group(0)) - 1)  # subito dopo l'ultimo carattere di punteggiatura, prima dello spazio
        frammento_precedente = testo[max(0, candidato_fine - 20):candidato_fine]
        if _ABBREVIAZIONI_PATTERN.search(frammento_precedente):
            continue
        confini.add(candidato_fine)
    confini_ordinati = sorted(c for c in confini if 0 < c < len(testo))
    spans = []
    inizio = 0
    for fine in confini_ordinati:
        if fine > inizio:
            spans.append((inizio, fine))
            inizio = fine
    if inizio < len(testo):
        spans.append((inizio, len(testo)))
    return [s for s in spans if testo[s[0]:s[1]].strip()]


@dataclass
class SegmentoMotivazione:
    node_id_provvedimento: str
    indice: int  # posizione del segmento nel documento, 0-based
    testo: str
    offset_inizio: int  # su testo_integrale, non su motivazione
    offset_fine: int


def segmenta_motivazione(node_id: str, motivazione: str, testo_integrale: str) -> list[SegmentoMotivazione]:
    offset_base = testo_integrale.index(motivazione)  # motivazione è sempre una sottostringa contigua di testo_integrale, vedi bdp_parser_pdf._segmenta()

    marcatori = {m.start() for m in _MARCATORE_NUMERATO_PATTERN.finditer(motivazione)}
    frasi = _spezza_in_frasi(motivazione, frozenset(marcatori))

    segmenti = []
    corrente_inizio_locale = None
    corrente_fine_locale = None
    corrente_len = 0

    def chiudi_segmento():
        nonlocal corrente_inizio_locale, corrente_fine_locale, corrente_len
        if corrente_inizio_locale is None:
            return
        grezzo = motivazione[corrente_inizio_locale:corrente_fine_locale]
        testo_segmento = grezzo.strip()
        if testo_segmento:
            spazi_iniziali = len(grezzo) - len(grezzo.lstrip())
            inizio_reale = corrente_inizio_locale + spazi_iniziali
            fine_reale = inizio_reale + len(testo_segmento)
            segmenti.append(
                SegmentoMotivazione(
                    node_id_provvedimento=node_id,
                    indice=len(segmenti),
                    testo=testo_segmento,
                    offset_inizio=offset_base + inizio_reale,
                    offset_fine=offset_base + fine_reale,
                )
            )
        corrente_inizio_locale = None
        corrente_fine_locale = None
        corrente_len = 0

    for start, end in frasi:
        # confine forzato PRIMA di una frase che comincia su un marcatore
        # numerato ("1.", "2)", "a)") - unico segnale strutturale reale
        # nel testo, ha priorità sull'accumulo per lunghezza quando il
        # minimo è già raggiunto.
        frase_inizia_su_marcatore = any(abs(start - m) <= 2 for m in marcatori)
        if corrente_inizio_locale is not None and frase_inizia_su_marcatore and corrente_len >= MIN_LUNGHEZZA_SEGMENTO:
            chiudi_segmento()

        if corrente_inizio_locale is None:
            corrente_inizio_locale = start
        lunghezza_frase = end - start

        # una singola frase più lunga del massimo diventa un segmento a sé,
        # non si spezza a metà frase - eccezione dichiarata, non un bug
        if corrente_len == 0 and lunghezza_frase > MAX_LUNGHEZZA_SEGMENTO:
            corrente_fine_locale = end
            corrente_len = lunghezza_frase
            chiudi_segmento()
            continue

        if corrente_len + lunghezza_frase > MAX_LUNGHEZZA_SEGMENTO and corrente_len >= MIN_LUNGHEZZA_SEGMENTO:
            chiudi_segmento()
            corrente_inizio_locale = start

        corrente_fine_locale = end
        corrente_len = (corrente_fine_locale - corrente_inizio_locale)

    chiudi_segmento()
    return segmenti
