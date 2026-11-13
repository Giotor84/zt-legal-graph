"""
Fase 1a - segmentazione di un atto lungo in blocchi che rispettano il
budget di token del modello, senza spezzare un'eccezione a meta'.

Verificato sul testo vero (Note di replica (atto reale di prova), 16 pagine, 7647
token misurati via /tokenize - troppi per il contesto disponibile su
questa macchina): gli atti di questo tipo hanno confini naturali chiari,
punti numerati di primo livello ("1) In ordine a...", "2) ..."), non un
testo omogeneo che richiede un taglio a finestra scorrevole. Un token
sliding window (proposto e scartato in una revisione precedente, vedi
README) rischierebbe di spaccare un'eccezione in due blocchi diversi o
duplicarla nella sovrapposizione - qui invece si taglia SOLO ai confini
che l'atto stesso dichiara.

Strategia a due livelli, non uno solo:
1. Cerca intestazioni numerate di sezione (pattern comune negli atti
   giuridici italiani: "N) ..." a inizio riga, N a una o due cifre) - se
   ne trova abbastanza (>=2, altrimenti non e' un segnale affidabile),
   usa quelle come confini naturali.
2. Altrimenti, fallback su paragrafi separati da riga vuota - meno
   preciso ma sempre meglio di un taglio a token cieco.

In entrambi i casi, i segmenti naturali vengono raggruppati in blocchi
che rispettano un budget di token REALE (misurato via /tokenize di
llama-server, iniettato come funzione - questo modulo non assume un
tokenizer specifico), non stimato dai caratteri. Un segmento naturale
piu' lungo del budget da solo viene comunque tenuto intero (meglio un
blocco che sfora leggermente il budget che uno che taglia un argomento
a meta' - il chiamante puo' comunque troncare o segnalare l'anomalia).
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

# src/segmenta_provvedimenti.py: riuso del segmentatore per frase (gestisce
# le abbreviazioni della prassi giuridica italiana - art., artt., cfr. ecc.
# - vedi _dividi_per_frase). Lecito qui: la restrizione "nessun import
# verso src/" (CLAUDE.md) vale per la Fase 3 (vedi
# test_import_grafo_isolato.MODULI_FASE_3), non per la Fase 1. Il modulo
# importato non ha dipendenze proprie oltre a re/dataclasses - nessun
# percorso verso store.py o il grafo.
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from segmenta_provvedimenti import _spezza_in_frasi  # noqa: E402

ContaToken = Callable[[str], int]

# Righe con solo un numero (1-2 cifre) - artefatto del numero di pagina
# che pdfplumber estrae come testo a se stante, non contenuto vero.
_RIGA_NUMERO_PAGINA_RE = re.compile(r"^\s*\d{1,3}\s*$", re.MULTILINE)

# Intestazione di sezione numerata: "1) ...", "12) ..." a inizio riga,
# seguita da testo (non un elenco puntato dentro un paragrafo - richiede
# che la riga INIZI col numero, non che compaia ovunque).
_SEZIONE_NUMERATA_RE = re.compile(r"^(\d{1,2})\)\s+\S", re.MULTILINE)


def pulisci_numeri_pagina(testo: str) -> str:
    """Rimuove le righe che sono solo un numero di pagina isolato -
    rumore dall'estrazione PDF, non contenuto dell'atto. Non tocca i
    numeri dentro una riga di testo vera (es. "€ 80.000,00")."""
    return _RIGA_NUMERO_PAGINA_RE.sub("", testo)


@dataclass
class Segmento:
    testo: str
    intestazione: str | None  # es. "1) In ordine alla ricostruzione dei fatti" - None per il preambolo prima della prima sezione
    # Span nel testo PULITO (dopo pulisci_numeri_pagina), non nel testo
    # grezzo del PDF: e' il testo a cui si riferiscono TUTTI gli offset del
    # contratto (ancore, estratti, blocchi) ed e' quello di cui
    # atto.sha256_testo e' l'impronta. Con valore di default per non
    # cambiare le costruzioni di Segmento gia' esistenti.
    inizio: int = 0
    fine: int = 0
    #: Contratto 1.19: l'intestazione del segmento ORIGINALE (prima della
    #: sotto-segmentazione) quando questo Segmento e' un frammento di un
    #: segmento naturale troppo grande per il budget da solo - None per un
    #: segmento naturale mai diviso. Senza questo campo, una volta divisa
    #: una sezione numerata in blocchi separati non c'e' modo di sapere,
    #: guardando un blocco isolato, che faceva parte di "4)" insieme ad
    #: altri.
    segmento_padre: str | None = None


def _segmento_con_span(testo: str, inizio: int, fine: int, intestazione: str | None,
                        segmento_padre: str | None = None) -> Segmento | None:
    """Costruisce un Segmento facendo lo strip SUGLI INDICI invece che sul
    testo, cosi' `inizio`/`fine` restano offset veri nel testo pulito.

    Uno `.strip()` sulla stringa perderebbe l'informazione di quanto e'
    stato tolto davanti, e ogni offset calcolato a valle sarebbe spostato
    di quel tanto - in silenzio, e di una quantita' diversa per ogni
    blocco. None se il segmento e' vuoto una volta ripulito."""
    while inizio < fine and testo[inizio].isspace():
        inizio += 1
    while fine > inizio and testo[fine - 1].isspace():
        fine -= 1
    if inizio >= fine:
        return None
    corpo = testo[inizio:fine]
    if intestazione is _DALLA_PRIMA_RIGA:
        intestazione = corpo.split("\n", 1)[0][:120]
    return Segmento(testo=corpo, intestazione=intestazione, inizio=inizio, fine=fine, segmento_padre=segmento_padre)


#: Sentinella: "ricava l'intestazione dalla prima riga del segmento".
#: Un oggetto dedicato e non una stringa magica, che sarebbe
#: indistinguibile da un'intestazione vera con quel testo.
_DALLA_PRIMA_RIGA = object()


def _trova_sezioni_numerate(testo: str) -> list[Segmento] | None:
    """None se il pattern non e' abbastanza affidabile (<2 sezioni
    trovate) - il chiamante deve usare il fallback a paragrafi in quel
    caso, non fidarsi di un singolo match casuale."""
    match = list(_SEZIONE_NUMERATA_RE.finditer(testo))
    if len(match) < 2:
        return None

    segmenti = []
    if match[0].start() > 0:
        preambolo = _segmento_con_span(testo, 0, match[0].start(), intestazione=None)
        if preambolo is not None:
            segmenti.append(preambolo)

    for i, m in enumerate(match):
        fine = match[i + 1].start() if i + 1 < len(match) else len(testo)
        segmento = _segmento_con_span(testo, m.start(), fine, intestazione=_DALLA_PRIMA_RIGA)
        if segmento is not None:
            segmenti.append(segmento)

    return segmenti


def _segmenta_per_paragrafi(testo: str) -> list[Segmento]:
    """Fallback quando non ci sono sezioni numerate riconoscibili -
    paragrafi separati da una o piu' righe vuote.

    `finditer` sui separatori invece di `re.split`: split restituisce i
    pezzi ma non dice a quale offset ciascuno cominciava, e ricalcolarlo
    cercando il pezzo nel testo sbaglierebbe al primo paragrafo ripetuto."""
    segmenti = []
    cursore = 0
    for separatore in re.finditer(r"\n\s*\n", testo):
        segmento = _segmento_con_span(testo, cursore, separatore.start(), intestazione=None)
        if segmento is not None:
            segmenti.append(segmento)
        cursore = separatore.end()
    ultimo = _segmento_con_span(testo, cursore, len(testo), intestazione=None)
    if ultimo is not None:
        segmenti.append(ultimo)
    return segmenti


# ------------------------------------------------------------- sotto-segmentazione


# Sotto-numerazione interna a una sezione: "4.1)", "4.1.2)" o senza
# parentesi, oppure una lettera/sequenza di lettere breve seguita da ")"
# ("a)", "i)", "iv)" - non distingue romani da lettere semplici, entrambi
# sono "1-4 lettere minuscole seguite da )", distinzione non necessaria
# per riconoscere il confine).
_SOTTO_NUMERAZIONE_RE = re.compile(r"^\s*(?:\d{1,2}(?:\.\d{1,2}){1,2}\)?|[a-z]{1,4}\))\s+\S", re.MULTILINE)


def _figlio(segmento: Segmento, inizio_locale: int, fine_locale: int,
            intestazione: str | None, padre: str | None) -> Segmento | None:
    """Costruisce un sotto-segmento con span GLOBALE (nel testo_pulito
    intero) a partire da offset LOCALI dentro segmento.testo - lo stesso
    schema di _segmento_con_span, ma traslato: il chiamante lavora sempre
    su segmento.testo (piu' semplice delle regex sul testo_pulito
    intero), qui si riporta il risultato al sistema di coordinate vero."""
    figlio = _segmento_con_span(segmento.testo, inizio_locale, fine_locale, intestazione, segmento_padre=padre)
    if figlio is None:
        return None
    figlio.inizio += segmento.inizio
    figlio.fine += segmento.inizio
    return figlio


def _dividi_per_sottonumerazione(segmento: Segmento, padre: str | None) -> list[Segmento] | None:
    """Livello (a) della gerarchia. None se il segnale non e' abbastanza
    affidabile (<2 marcatori, stessa soglia della sezione top-level)."""
    match = list(_SOTTO_NUMERAZIONE_RE.finditer(segmento.testo))
    if len(match) < 2:
        return None
    pezzi = []
    if match[0].start() > 0:
        p = _figlio(segmento, 0, match[0].start(), None, padre)
        if p is not None:
            pezzi.append(p)
    for i, m in enumerate(match):
        fine = match[i + 1].start() if i + 1 < len(match) else len(segmento.testo)
        p = _figlio(segmento, m.start(), fine, _DALLA_PRIMA_RIGA, padre)
        if p is not None:
            pezzi.append(p)
    return pezzi if len(pezzi) >= 2 else None


def _dividi_per_capoverso(segmento: Segmento, padre: str | None) -> list[Segmento] | None:
    """Livello (b): paragrafi separati da riga vuota, scoped al singolo
    segmento sovradimensionato - stessa logica di _segmenta_per_paragrafi,
    non richiamata direttamente perche' quella lavora sul testo_pulito
    intero con intestazione sempre None, qui serve propagare `padre`."""
    pezzi = []
    cursore = 0
    for separatore in re.finditer(r"\n\s*\n", segmento.testo):
        p = _figlio(segmento, cursore, separatore.start(), None, padre)
        if p is not None:
            pezzi.append(p)
        cursore = separatore.end()
    ultimo = _figlio(segmento, cursore, len(segmento.testo), None, padre)
    if ultimo is not None:
        pezzi.append(ultimo)
    return pezzi if len(pezzi) >= 2 else None


def _dividi_per_frase(segmento: Segmento, padre: str | None) -> list[Segmento] | None:
    """Livello (c), ultima risorsa prima di tenere il segmento intero:
    confine di frase via segmenta_provvedimenti._spezza_in_frasi, che
    riconosce le abbreviazioni della prassi giuridica italiana (art.,
    artt., cfr., sez. ecc.) e non le tratta come fine frase."""
    spans = _spezza_in_frasi(segmento.testo)
    if len(spans) < 2:
        return None
    pezzi = []
    for inizio_locale, fine_locale in spans:
        p = _figlio(segmento, inizio_locale, fine_locale, None, padre)
        if p is not None:
            pezzi.append(p)
    return pezzi if len(pezzi) >= 2 else None


def _sotto_segmenta(segmento: Segmento, conta_token: ContaToken, budget_token: int,
                     padre: str | None = None) -> list[Segmento]:
    """Contratto 1.19: un segmento naturale piu' grande del budget viene
    SOTTO-segmentato, mai lasciato intero e mai troncato - trovato dal
    vivo (2026-08-25, atto reale di prova) che un segmento del genere (la
    sezione numerata "4)", 7516 caratteri) e' indivisibile per
    _raggruppa_con_span (che sa solo accorpare segmenti piccoli, mai
    spezzare uno grande), finiva sempre nello stesso blocco sovraffollato
    indipendentemente dal budget, e faceva perdere un'eccezione vera (il
    passaggio sulla nullita' della fideiussione, verificato con un test di
    isolamento: estratto correttamente a 1594 caratteri, perso a 7516)
    prima ancora di arrivare al filtro o al controllo di ancoraggio.

    Gerarchia di confini, in ordine di preferenza - si scende al livello
    successivo solo se quello sopra non trova un confine affidabile
    (< 2 pezzi) O se un pezzo trovato e' ANCORA piu' grande del budget da
    solo (ricorsione): (a) sotto-numerazione interna (4.1, a), i)) - (b)
    capoverso - (c) confine di frase (segmenta_provvedimenti.py, gestisce
    le abbreviazioni giuridiche). Se nessun livello trova un confine (caso
    limite: una singola frase piu' lunga del budget), il segmento resta
    intero - MAI troncato, lo stesso principio dichiarato ovunque in
    questo progetto per il testo letterale di un'eccezione."""
    etichetta_padre = padre if padre is not None else segmento.intestazione
    if conta_token(segmento.testo) <= budget_token:
        return [segmento]

    for divisore in (_dividi_per_sottonumerazione, _dividi_per_capoverso, _dividi_per_frase):
        pezzi = divisore(segmento, etichetta_padre)
        if pezzi is not None:
            risultato = []
            for pezzo in pezzi:
                risultato.extend(_sotto_segmenta(pezzo, conta_token, budget_token, padre=etichetta_padre))
            return risultato

    return [segmento]


def _espandi_oversize(segmenti: list[Segmento], conta_token: ContaToken, budget_token: int) -> list[Segmento]:
    """Applica _sotto_segmenta a ogni segmento naturale che supera il
    budget da solo, prima dell'accorpamento (_raggruppa_con_span) - che
    invece si occupa solo di raggruppare segmenti PICCOLI, mai di
    spezzarne uno grande."""
    risultato = []
    for s in segmenti:
        if conta_token(s.testo) > budget_token:
            risultato.extend(_sotto_segmenta(s, conta_token, budget_token))
        else:
            risultato.append(s)
    return risultato


def _raggruppa_in_blocchi(segmenti: list[Segmento], conta_token: ContaToken, budget_token: int) -> list[str]:
    """Accorpa segmenti CONSECUTIVI finche' il blocco risultante sta nel
    budget - mai spezza un segmento naturale (l'unica eccezione e' un
    segmento da solo piu' grande del budget, tenuto intero e segnalato
    dal chiamante tramite la sua lunghezza, non troncato qui)."""
    blocchi = []
    corrente = []
    token_correnti = 0

    for seg in segmenti:
        token_seg = conta_token(seg.testo)
        if corrente and token_correnti + token_seg > budget_token:
            blocchi.append("\n\n".join(s.testo for s in corrente))
            corrente = []
            token_correnti = 0
        corrente.append(seg)
        token_correnti += token_seg

    if corrente:
        blocchi.append("\n\n".join(s.testo for s in corrente))

    return blocchi


def segmenta_atto(testo: str, conta_token: ContaToken, budget_token: int = 6000) -> list[str]:
    """Punto di ingresso storico: solo i testi dei blocchi. budget_token=6000
    di default: con NUM_CTX=8192 lascia ~2000 token per istruzioni+risposta -
    da ricalibrare se NUM_CTX cambia (vedi esegui_locale_llamaserver.py).

    Chi deve calcolare offset (l'entry point, per `atto.blocchi` e per
    l'ancoraggio) usa `segmenta_con_span`."""
    return [blocco.testo for blocco in segmenta_con_span(testo, conta_token, budget_token)]


@dataclass
class Blocco:
    """Un blocco di lavorazione con la sua posizione nel testo PULITO."""

    testo: str
    inizio: int
    fine: int
    #: Contratto 1.19: intestazioni dei segmenti naturali che sono stati
    #: sotto-segmentati per entrare in questo blocco (vuoto per un blocco
    #: che non contiene nessun frammento) - traccia diagnostica, loggata
    #: da esegui_fase1, non parte dello schema JSON di atto.blocchi (e'
    #: un dettaglio della segmentazione, non del contratto fra le fasi).
    segmenti_padre: frozenset[str] = field(default_factory=frozenset)


def segmenta_con_span(testo: str, conta_token: ContaToken, budget_token: int = 6000) -> list[Blocco]:
    """Come segmenta_atto(), ma ogni blocco porta con se' gli offset nel
    testo pulito (`pulisci_numeri_pagina`).

    **Il testo pulito e' il testo dell'atto per il contratto**: e' quello
    di cui `atto.sha256_testo` e' l'impronta, quello a cui si riferiscono
    tutti gli offset di `ancora` e degli estratti su F01, e quello che
    `atto.n_caratteri` misura. Non il testo grezzo del PDF: la pulizia dei
    numeri di pagina CANCELLA caratteri, quindi i due hanno sistemi di
    coordinate diversi e mescolarli produrrebbe ancore spostate in modo
    crescente lungo il documento - l'errore piu' insidioso possibile qui,
    perche' all'inizio del file gli offset sarebbero ancora giusti.

    `Blocco.inizio/fine` coprono dal primo all'ultimo carattere dei
    segmenti accorpati; il `testo` resta la forma unita con "\\n\\n" che va
    nel prompt, quindi NON coincide necessariamente con
    `testo_pulito[inizio:fine]` (differisce per gli spazi fra i segmenti).
    Chi ritaglia testo usa il testo pulito e gli offset, mai `Blocco.testo`.

    Un segmento naturale piu' grande del budget da solo (contratto 1.19)
    viene sotto-segmentato PRIMA dell'accorpamento, mai lasciato intero e
    mai troncato - vedi _sotto_segmenta."""
    testo_pulito = pulisci_numeri_pagina(testo)
    segmenti = _trova_sezioni_numerate(testo_pulito)
    if segmenti is None:
        segmenti = _segmenta_per_paragrafi(testo_pulito)
    if not segmenti:
        raise ValueError("l'atto non contiene testo dopo la pulizia dei numeri di pagina")
    segmenti = _espandi_oversize(segmenti, conta_token, budget_token)
    return _raggruppa_con_span(segmenti, conta_token, budget_token)


def segmenti_naturali(testo: str, conta_token: ContaToken,
                      budget_token: int = 6000) -> list[Segmento]:
    """I segmenti naturali dell'atto, PRIMA dell'accorpamento in blocchi.

    `segmenta_con_span` li raggruppa fino a riempire il budget del modello,
    perche' la Fase 1 fa una chiamata per blocco e un blocco piccolo
    sprecherebbe contesto. Chi invece deve guardare l'atto un pezzo alla
    volta - la spazzata esaustiva del golden set - vuole l'unita' piu'
    piccola che l'atto stesso dichiara, non l'unita' di lavorazione del
    modello: e' esattamente la differenza fra "posso saltare un passaggio
    senza accorgermene" e "un no e' un no su un testo identificato".

    Stessi confini e stessi offset di `segmenta_con_span` (testo PULITO,
    sotto-segmentazione dell'oversize inclusa): manca solo l'ultimo passo,
    l'accorpamento. Sola lettura, nessun modello."""
    testo_pulito = pulisci_numeri_pagina(testo)
    segmenti = _trova_sezioni_numerate(testo_pulito)
    if segmenti is None:
        segmenti = _segmenta_per_paragrafi(testo_pulito)
    if not segmenti:
        raise ValueError("l'atto non contiene testo dopo la pulizia dei numeri di pagina")
    return _espandi_oversize(segmenti, conta_token, budget_token)


def _raggruppa_con_span(segmenti: list[Segmento], conta_token: ContaToken, budget_token: int) -> list[Blocco]:
    """Stessa politica di accorpamento di _raggruppa_in_blocchi, con gli
    span propagati: un blocco va dal `inizio` del suo primo segmento al
    `fine` del suo ultimo."""
    blocchi: list[Blocco] = []
    corrente: list[Segmento] = []
    token_correnti = 0

    def chiudi() -> None:
        blocchi.append(Blocco(
            testo="\n\n".join(s.testo for s in corrente),
            inizio=corrente[0].inizio,
            fine=corrente[-1].fine,
            segmenti_padre=frozenset(s.segmento_padre for s in corrente if s.segmento_padre is not None),
        ))

    for segmento in segmenti:
        token_segmento = conta_token(segmento.testo)
        if corrente and token_correnti + token_segmento > budget_token:
            chiudi()
            corrente = []
            token_correnti = 0
        corrente.append(segmento)
        token_correnti += token_segmento

    if corrente:
        chiudi()
    return blocchi


if __name__ == "__main__":
    # Smoke test con un conta-token approssimato (4 caratteri/token,
    # stima grezza SOLO per verificare la logica di raggruppamento senza
    # bisogno di llama-server acceso - il conteggio vero via /tokenize va
    # usato nel run reale, vedi estrazione_atto.py).
    import sys

    def conta_approssimato(testo: str) -> int:
        return len(testo) // 4

    if len(sys.argv) < 2:
        raise SystemExit("uso: python segmenta_atto.py <percorso_testo.txt>")

    with open(sys.argv[1], encoding="utf-8") as f:
        testo = f.read()

    import re as _re

    blocchi = segmenta_atto(testo, conta_approssimato, budget_token=1500)
    print(f"Testo totale: {len(testo)} caratteri (~{conta_approssimato(testo)} token stimati)")
    print(f"Blocchi prodotti: {len(blocchi)}\n")
    for i, b in enumerate(blocchi):
        intestazioni = _re.findall(r"^\d{1,2}\)\s+.{0,60}", b, _re.MULTILINE)
        etichetta = " | ".join(intestazioni) if intestazioni else "(preambolo, nessuna sezione numerata)"
        print(f"  blocco {i + 1}: {len(b)} caratteri (~{conta_approssimato(b)} token) - contiene: {etichetta}")
