"""
Localizzazione di una citazione nel testo dell'atto - PARTE DEL CONTRATTO,
non un dettaglio implementativo.

Implementa alla lettera la sezione "Localizzazione della citazione nel
testo" di CONTRATTI_DATI.md: la procedura, le soglie e la mappa degli
offset sono normative. Cambiarle - incluse le soglie - e' un bump di
versione del contratto, non un refactoring.

Il modello emette `testo_letterale`, Python lo localizza. Su testo
estratto da PDF il match esatto fallisce per ragioni banali (a capo dentro
la frase, sillabazione, spazi multipli, virgolette tipografiche, legature,
apostrofi), e la risposta NON e' "prendi il primo match che somiglia": e'
una scala di esiti dichiarati, di cui uno solo produce triple automatiche.

Zero dipendenze dal grafo e da llama-server: questo modulo e' interamente
testabile in isolamento, ed e' il motivo per cui il controllo Python n. 3
puo' essere verificato senza far girare niente.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass
from typing import Iterator

try:  # rapidfuzz e' il motore DI RIFERIMENTO (contratto 1.10), non solo
      # ~50x piu' veloce: le soglie 0.95/0.80 sono tarate sui suoi numeri.
      # Il fallback difflib sotto non e' equivalente - vedi il suo commento.
    from rapidfuzz.distance import Indel as _Indel

    def _rapporto(a: str, b: str) -> float:
        return _Indel.normalized_similarity(a, b)

    RAPIDFUZZ_DISPONIBILE = True
except ImportError:  # pragma: no cover - dipende dall'ambiente
    RAPIDFUZZ_DISPONIBILE = False

    def _rapporto(a: str, b: str) -> float:
        # autojunk=False OBBLIGATORIO, non un dettaglio di prestazioni.
        # L'euristica autojunk di difflib, attiva per default oltre i 200
        # caratteri, tratta come "spazzatura" i caratteri che ricorrono in
        # piu' dell'1% della sequenza - cioe' le lettere comuni di un testo
        # italiano - e il rapporto crolla. Misurato su una citazione di 400
        # caratteri con 12 corruzioni: 0.087 con autojunk contro 0.957
        # senza, che e' il valore vero e quello che rapidfuzz restituisce.
        #
        # Con la soglia a 0.95 questo significa che, su una macchina senza
        # rapidfuzz, OGNI citazione sopra i 200 caratteri finirebbe
        # `non_ancorata` - in silenzio, e con le soglie del contratto
        # apparentemente rispettate.
        #
        # ANCHE CON autojunk=False, questo NON e' equivalente a rapidfuzz
        # (contratto 1.10): SequenceMatcher.ratio() e' Ratcliff/Obershelp,
        # un'euristica greedy; rapidfuzz Indel.normalized_similarity() e'
        # basato su LCS, ottimo. Misurato su una citazione reale dell'atto
        # atto-prova: 0.8986 (rapidfuzz) contro 0.8913 (qui), 0.0072 di
        # scarto sulla STESSA finestra - non rumore, un motore diverso.
        # Vicino a una soglia (0.95 o 0.80) puo' cambiare lo stato di
        # ancoraggio. RAPIDFUZZ_DISPONIBILE finisce in
        # meta.esecuzione.motore_similarita per ogni corsa proprio perche'
        # questo ramo non e' un fallback "silenziosamente equivalente".
        return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


# ------------------------------------------------------------------ soglie di contratto (V1)

#: >= 0.95 -> `ancorata` (fuzzy). Dopo la normalizzazione il rumore
#: residuo legittimo (errori OCR isolati, residui di sillabazione) e'
#: locale e raro: una citazione davvero letterale resta sopra 0.95. Sotto,
#: l'affermazione "questo e' letteralmente nell'atto" non e' piu'
#: difendibile in automatico.
SOGLIA_ANCORATA = 0.95

#: 0.80 <= r < 0.95 -> `ancora_parziale`. Quasi certamente lo stesso
#: passaggio, ma troncato o leggermente parafrasato dal modello.
SOGLIA_PARZIALE = 0.80

#: Due finestre NON SOVRAPPOSTE entro questo scarto -> `ancora_ambigua`.
#: Due punti dell'atto quasi ugualmente plausibili non si risolvono col
#: primo match.
DELTA_AMBIGUITA = 0.02


# ------------------------------------------------------------------ normalizzazione

_APOSTROFI = "‘’ʼ´′"           # ' ' ʼ ´ ′
_VIRGOLETTE = "“”«»„″"     # " " « » „ ″
_TRATTINI = "‐‑‒–—―"       # ‐ ‑ ‒ – — ―
_SPAZI = " \t\r\n     \v\f"

_SOSTITUZIONI = {c: "'" for c in _APOSTROFI}
_SOSTITUZIONI.update({c: '"' for c in _VIRGOLETTE})
_SOSTITUZIONI.update({c: "-" for c in _TRATTINI})

_TUTTI_I_TRATTINI = "-" + _TRATTINI


def _cluster(testo: str, i: int) -> int:
    """Fine del cluster che inizia in `i`: il carattere di base piu' gli
    eventuali segni combinanti che lo seguono.

    Serve perche' NFKC va applicata al cluster, non al singolo carattere:
    su un carattere solo, "e" + U+0301 resterebbe decomposto e non
    combacerebbe mai con la "é" precomposta che il modello emette. Un PDF
    puo' produrre l'una o l'altra forma, e le due devono normalizzare allo
    stesso risultato - e' esattamente il compito di NFKC nel contratto."""
    j = i + 1
    while j < len(testo) and unicodedata.combining(testo[j]):
        j += 1
    return j


def normalizza_con_mappa(testo: str) -> tuple[str, list[int]]:
    """I sette passi del contratto, nell'ordine, costruendo la mappa degli
    offset carattere per carattere.

    Ritorna (normalizzato, mappa) dove `mappa[i]` e' l'offset nel testo
    ORIGINALE del carattere che ha generato `normalizzato[i]`. I caratteri
    soppressi (sillabazione, spazi collassati) non emettono nulla; una run
    di spazi collassata mappa sul PRIMO carattere della run.

    Gli offset scritti in `ancora` sono SEMPRE riferiti al testo originale:
    `inizio = mappa[i]`, `fine = mappa[j-1] + 1` per un match `[i, j)` nel
    normalizzato (vedi `rimappa`)."""
    uscita: list[str] = []
    mappa: list[int] = []
    i = 0
    n = len(testo)

    while i < n:
        ch = testo[i]

        # 4. de-sillabazione: trattino + fine riga, SOLO fra lettere
        # minuscole. Il vincolo sulle minuscole evita di incollare
        # "art. 1832-" + "bis" dove il trattino non e' sillabazione.
        if ch in _TUTTI_I_TRATTINI and uscita and uscita[-1].isalpha() and uscita[-1].islower():
            k = i + 1
            while k < n and testo[k] in " \t":
                k += 1
            if k < n and testo[k] in "\r\n":
                while k < n and testo[k] in _SPAZI:
                    k += 1
                if k < n and testo[k].isalpha() and testo[k].islower():
                    i = k  # trattino e spazi soppressi: nessuna emissione
                    continue

        # 5. run di spazi (NBSP, tab, newline, spazi multipli) -> UNO spazio
        if ch in _SPAZI:
            k = i
            while k < n and testo[k] in _SPAZI:
                k += 1
            uscita.append(" ")
            mappa.append(i)  # la run collassata mappa sul primo carattere
            i = k
            continue

        # 1-2-3-6 sul cluster: NFKC (scioglie le legature, ricompone gli
        # accenti), sostituzioni tipografiche, casefold.
        fine_cluster = _cluster(testo, i)
        pezzo = unicodedata.normalize("NFKC", testo[i:fine_cluster])
        pezzo = "".join(_SOSTITUZIONI.get(c, c) for c in pezzo)
        for carattere in pezzo.casefold():
            uscita.append(carattere)
            mappa.append(i)
        i = fine_cluster

    # 7. strip esterno - tolto dall'uscita E dalla mappa, insieme
    inizio_utile, fine_utile = 0, len(uscita)
    while inizio_utile < fine_utile and uscita[inizio_utile] == " ":
        inizio_utile += 1
    while fine_utile > inizio_utile and uscita[fine_utile - 1] == " ":
        fine_utile -= 1

    return "".join(uscita[inizio_utile:fine_utile]), mappa[inizio_utile:fine_utile]


# ------------------------------------------------------------------ spoglio (ASIMMETRICO)

#: Virgolette di ogni tipo, dritte e tipografiche, doppie e singole.
_VIRGOLETTE_SPOGLIO = "\"'“”„‟«»‘’‚‛`´"
#: Puntini di sospensione AI BORDI: ellissi tipografica e sequenze di punti,
#: in coda e in testa. In coda e' il caso frequente (`"testo troncato..."`);
#: in testa e' piu' raro ma esiste (`"...prosegue cosi'"`, il modello che
#: segnala di aver preso la frase a meta').
#:
#: Toglierla anche in testa NON e' un'estensione arbitraria della regola
#: "solo ai bordi": e' proprio un bordo. E ometterlo farebbe danno, non
#: solo lasciare sporco - `_ELLISSI_INTERNA` cerca ovunque nella stringa,
#: quindi un `...` iniziale sopravvissuto verrebbe scambiato per
#: un'omissione centrale e manderebbe la citazione in `ancora_parziale`
#: per una ragione falsa.
_ELLISSI_IN_CODA = re.compile(r"(?:\.{2,}|…)+\s*$")
_ELLISSI_IN_TESTA = re.compile(r"^\s*(?:\.{2,}|…)+")
#: Ellissi INTERNA: la citazione ha un buco in mezzo.
_ELLISSI_INTERNA = re.compile(r"(?:\.{3,}|…)")


def spoglia_citazione(citazione: str) -> tuple[str, bool]:
    """Toglie il CONFEZIONAMENTO che il modello mette attorno alla
    citazione. Ritorna `(spogliata, ha_ellissi_interna)`.

    **ASIMMETRICO, e va tenuto tale.** Si applica alla stringa emessa dal
    MODELLO, mai al testo dell'atto: gli offset dell'ancora si riferiscono
    all'atto, e toccarlo sposterebbe ogni posizione calcolata. Non e'
    un'ottava voce della normalizzazione bilaterale (che si applica a
    entrambi i lati): e' un passo AGGIUNTIVO e PRECEDENTE, su un lato solo.
    Chi lo legge come simmetrico rompe gli offset.

    Perche' serve, misurato e non supposto: sulle 10 eccezioni della corsa
    reale atto-prova, 10/10 iniziavano con una virgoletta e 4/10 finivano
    con dei puntini. Quei 2-4 caratteri ai bordi bastavano a far scendere
    un match altrimenti perfetto a 0.95-0.98, portando i match esatti da
    9/10 a 1/10. Nessun esito cambiava, ma nove ancore passavano da
    deterministiche a dipendenti da una soglia (una stava esattamente a
    0.9500).

    Regola: SOLO AI BORDI, mai al centro. Virgolette in apertura e
    chiusura, ellissi terminali, spazi; iterato finche' stabile, perche'
    il modello produce combinazioni come `"...testo..."` in cui togliere
    una virgoletta scopre dei puntini e viceversa.

    Un'ellissi INTERNA non viene toccata: segnala una citazione con
    omissione centrale (`"testo A ... testo B"`), che non e' ancorabile
    come intervallo unico. Viene RILEVATA e riportata al chiamante, che
    per contratto assegna `ancora_parziale` - ancorare per segmenti
    sarebbe possibile ma e' scope non aperto."""
    testo = citazione.strip()
    while True:
        precedente = testo
        if testo and testo[0] in _VIRGOLETTE_SPOGLIO:
            testo = testo[1:]
        if testo and testo[-1] in _VIRGOLETTE_SPOGLIO:
            testo = testo[:-1]
        testo = _ELLISSI_IN_CODA.sub("", testo).strip()
        testo = _ELLISSI_IN_TESTA.sub("", testo).strip()
        if testo == precedente:
            break

    return testo, bool(_ELLISSI_INTERNA.search(testo))


# ------------------------------------------------------------------ ricerca

def trova_tutte(testo: str, ago: str) -> list[tuple[int, int]]:
    """Tutte le occorrenze di `ago`, anche sovrapposte, come `[inizio, fine)`.

    Sovrapposte e non disgiunte: due occorrenze che si accavallano restano
    due punti distinti dell'atto, e il contratto chiede di registrarli
    tutti invece di sceglierne uno d'ufficio."""
    if not ago:
        return []
    trovate = []
    posizione = testo.find(ago)
    while posizione != -1:
        trovate.append((posizione, posizione + len(ago)))
        posizione = testo.find(ago, posizione + 1)
    return trovate


def _inizi_di_parola(testo: str) -> Iterator[int]:
    """Passo della finestra scorrevole: UN confine di parola, come impone
    il contratto - non un carattere (costo proibitivo) e non una finestra
    fissa (perderebbe l'allineamento)."""
    yield 0
    for corrispondenza in re.finditer(r"(?<= )\S", testo):
        yield corrispondenza.start()


def _finestre_fuzzy(norm_atto: str, norm_cit: str) -> list[tuple[float, int, int]]:
    """(rapporto, inizio, fine) per ogni finestra con similarita' >= 0.80.

    Con difflib si prefiltra con real_quick_ratio/quick_ratio, che sono
    limiti superiori del rapporto vero e costano O(1)/O(n): saltano la
    grande maggioranza delle finestre senza mai scartarne una buona
    (essendo limiti SUPERIORI, se sono sotto soglia il rapporto vero lo e'
    di sicuro). Con rapidfuzz non serve: e' gia' abbastanza veloce."""
    larghezza = len(norm_cit)
    if larghezza == 0 or larghezza > len(norm_atto):
        return []

    candidati: list[tuple[float, int, int]] = []
    confronto = None if RAPIDFUZZ_DISPONIBILE else difflib.SequenceMatcher(None, norm_cit, "", autojunk=False)

    for inizio in _inizi_di_parola(norm_atto):
        fine = inizio + larghezza
        if fine > len(norm_atto):
            break
        finestra = norm_atto[inizio:fine]

        if confronto is None:
            rapporto = _rapporto(norm_cit, finestra)
        else:
            confronto.set_seq2(finestra)
            if confronto.real_quick_ratio() < SOGLIA_PARZIALE or confronto.quick_ratio() < SOGLIA_PARZIALE:
                continue
            rapporto = confronto.ratio()

        if rapporto >= SOGLIA_PARZIALE:
            candidati.append((rapporto, inizio, fine))
    return candidati


def _sovrapposte(a: tuple[float, int, int], b: tuple[float, int, int]) -> bool:
    return a[1] < b[2] and b[1] < a[2]


def _screma_sovrapposte(candidati: list[tuple[float, int, int]]) -> list[tuple[float, int, int]]:
    """Da un insieme di finestre candidate tiene, fra quelle che si
    accavallano fra loro, solo la migliore.

    Serve perche' i rivali venivano confrontati SOLO con il migliore, mai
    fra loro: la finestra scorrevole avanza di un confine di parola, quindi
    lo stesso punto dell'atto produce piu' finestre quasi identiche e
    finivano tutte in `occorrenze`. Misurato su corsa reale (2026-08-26,
    opposizione Verdi): X14 dichiarata ambigua su 4 punti, di cui tre
    sovrapposti fra loro ([12935:13260], [12943:13268], [12946:13271]) -
    cioe' lo stesso punto contato tre volte; X13, X22, X56 lo stesso.

    NON rende citabile un'ancora ambigua e non e' pensato per farlo: dopo
    lo scremo restano comunque i punti VERI in cui il testo compare
    davvero ripetuto nell'atto. Corregge il conteggio, che un campo
    diagnostico non puo' permettersi di sbagliare."""
    tenute: list[tuple[float, int, int]] = []
    for candidato in sorted(candidati, key=lambda c: (-c[0], c[1])):
        if not any(_sovrapposte(candidato, tenuta) for tenuta in tenute):
            tenute.append(candidato)
    return tenute


# ------------------------------------------------------------------ esito

@dataclass(frozen=True)
class Posizione:
    blocco_id: str
    inizio: int
    fine: int

    def come_dict(self) -> dict:
        return {"blocco_id": self.blocco_id, "inizio": self.inizio, "fine": self.fine}


def blocco_di(blocchi: list[dict], inizio: int) -> str:
    """Il blocco che contiene l'offset. I blocchi coprono l'atto senza
    sovrapposizioni (segmenta_atto non sovrappone mai), quindi il primo
    che contiene l'offset e' l'unico.

    Se nessuno lo contiene, l'ancora non e' rappresentabile nel contratto
    (`blocco_id` e' obbligatorio e ha pattern `^B[0-9]{2}$`): fallisce
    rumorosamente invece di inventare "B00"."""
    for blocco in blocchi:
        if blocco["inizio"] <= inizio < blocco["fine"]:
            return blocco["blocco_id"]
    raise ValueError(
        f"offset {inizio} non ricade in nessun blocco dell'atto "
        f"(blocchi: {[(b['blocco_id'], b['inizio'], b['fine']) for b in blocchi]}) - "
        "la segmentazione e il testo su cui si calcolano gli offset non sono lo stesso testo"
    )


def rimappa(mappa: list[int], inizio: int, fine: int) -> tuple[int, int]:
    """Da un match `[inizio, fine)` nel normalizzato agli offset nel testo
    ORIGINALE: `mappa[i]`, `mappa[j-1] + 1`."""
    return mappa[inizio], mappa[fine - 1] + 1


def localizza(testo_atto: str, blocchi: list[dict], citazione: str) -> dict:
    """La procedura normativa. Ritorna un `ancora` conforme al `oneOf` di
    `fase1_estrazione.schema.json`.

    Quattro esiti, e uno solo produce triple automatiche:
    - `ancorata` (esatta / normalizzata / fuzzy >= 0.95): una sola
      posizione;
    - `ancora_ambigua`: >= 2 occorrenze, o piu' finestre fuzzy entro 0.02
      dalla migliore - MAI il primo match d'ufficio, la scelta e' umana;
    - `ancora_parziale`: migliore finestra in [0.80, 0.95), probabile
      troncamento o parafrasi;
    - `non_ancorata`: niente sopra 0.80.

    La Fase 2 tratta comunque l'eccezione: la classificazione non dipende
    dall'ancora. Cio' che dipende dall'ancora e' la citabilita' automatica
    dell'estratto F01."""
    def posizioni(coppie: list[tuple[int, int]]) -> list[dict]:
        return [Posizione(blocco_di(blocchi, i), i, f).come_dict() for i, f in coppie]

    # Passo di SPOGLIO, asimmetrico: solo sulla stringa del modello, mai
    # sull'atto (vedi spoglia_citazione). Precede tutto il resto.
    citazione, ellissi_interna = spoglia_citazione(citazione)
    if ellissi_interna:
        return _ancora_con_omissione(testo_atto, blocchi, citazione)

    # 0. match esatto grezzo, senza normalizzazione
    trovate = trova_tutte(testo_atto, citazione)
    if len(trovate) == 1:
        inizio, fine = trovate[0]
        return {"stato": "ancorata", "blocco_id": blocco_di(blocchi, inizio),
                "inizio": inizio, "fine": fine, "corrispondenza": "esatta", "similarita": None}
    if len(trovate) >= 2:
        return {"stato": "ancora_ambigua", "occorrenze": posizioni(trovate)}

    # 1. match esatto sul normalizzato, offset rimappati
    norm_atto, mappa = normalizza_con_mappa(testo_atto)
    norm_cit, _ = normalizza_con_mappa(citazione)
    if not norm_cit:
        return {"stato": "non_ancorata", "motivo": "la citazione e' vuota dopo la normalizzazione"}

    trovate = trova_tutte(norm_atto, norm_cit)
    if len(trovate) == 1:
        inizio, fine = rimappa(mappa, *trovate[0])
        return {"stato": "ancorata", "blocco_id": blocco_di(blocchi, inizio),
                "inizio": inizio, "fine": fine, "corrispondenza": "normalizzata", "similarita": None}
    if len(trovate) >= 2:
        return {"stato": "ancora_ambigua",
                "occorrenze": posizioni([rimappa(mappa, i, f) for i, f in trovate])}

    # 2. fuzzy
    candidati = _finestre_fuzzy(norm_atto, norm_cit)
    if not candidati:
        return {"stato": "non_ancorata",
                "motivo": f"nessuna finestra con similarita' >= {SOGLIA_PARZIALE:.2f}"}

    migliore = max(candidati, key=lambda c: c[0])
    rivali = [c for c in candidati
              if not _sovrapposte(c, migliore) and migliore[0] - c[0] <= DELTA_AMBIGUITA]
    if rivali:
        # Scremati fra loro, non solo contro il migliore: vedi
        # _screma_sovrapposte. Se dopo lo scremo resta solo il migliore,
        # non c'era ambiguita' - erano finestre dello stesso punto.
        insieme = _screma_sovrapposte([migliore] + rivali)
        if len(insieme) >= 2:
            insieme.sort(key=lambda c: c[1])
            return {"stato": "ancora_ambigua",
                    "occorrenze": posizioni([rimappa(mappa, c[1], c[2]) for c in insieme])}

    rapporto, inizio_norm, fine_norm = migliore
    inizio, fine = rimappa(mappa, inizio_norm, fine_norm)
    if rapporto >= SOGLIA_ANCORATA:
        return {"stato": "ancorata", "blocco_id": blocco_di(blocchi, inizio),
                "inizio": inizio, "fine": fine, "corrispondenza": "fuzzy", "similarita": rapporto}

    return {"stato": "ancora_parziale",
            "migliore_candidato": Posizione(blocco_di(blocchi, inizio), inizio, fine).come_dict(),
            "similarita": rapporto,
            "motivo": "probabile troncamento o parafrasi del modello"}


MOTIVO_OMISSIONE_INTERNA = (
    "citazione con omissione interna (il modello ha scritto \"...\" in mezzo al testo): "
    "il passaggio citato non e' un intervallo unico dell'atto, quindi non ha una tripla "
    "(fonte_id, inizio, fine) sola. Ancorata al PRIMO segmento, come punto di partenza per "
    "la revisione - l'ancoraggio per segmenti sarebbe possibile ma non e' implementato"
)


def _ancora_con_omissione(testo_atto: str, blocchi: list[dict], citazione: str) -> dict:
    """Esito per una citazione con ellissi INTERNA.

    `ancora_parziale` PER PROGETTO, non per punteggio: una citazione con
    un buco in mezzo non e' ancorabile come intervallo unico, per quanto
    bene i suoi pezzi combacino. Forzare `ancorata` produrrebbe una tripla
    che copre anche il testo omesso - cioe' un estratto F01 che afferma
    "la controparte ha scritto questo" includendo righe che la citazione
    dichiara di aver saltato.

    Il primo segmento viene localizzato lo stesso: serve a dare al revisore
    un punto da cui partire, che e' esattamente il ruolo di
    `migliore_candidato`."""
    primo = _ELLISSI_INTERNA.split(citazione)[0].strip()
    if primo:
        esito = localizza(testo_atto, blocchi, primo)
        if esito["stato"] == "ancorata":
            candidato = Posizione(esito["blocco_id"], esito["inizio"], esito["fine"]).come_dict()
            return {"stato": "ancora_parziale", "migliore_candidato": candidato,
                    "similarita": esito["similarita"] if esito["similarita"] is not None else 1.0,
                    "motivo": MOTIVO_OMISSIONE_INTERNA}
        if esito["stato"] == "ancora_parziale":
            return {**esito, "motivo": MOTIVO_OMISSIONE_INTERNA}
        if esito["stato"] == "ancora_ambigua":
            return {"stato": "ancora_ambigua", "occorrenze": esito["occorrenze"]}

    return {"stato": "non_ancorata",
            "motivo": "citazione con omissione interna, e il primo segmento non e' "
                       "localizzabile nell'atto: ne' l'intervallo ne' il punto di partenza"}


if __name__ == "__main__":
    atto = (
        "TRIBUNALE DI ROMA\n\n"
        "1) In ordine alla ricostruzione dei fatti, si osserva quanto segue.\n"
        "La banca non ha prodotto gli estratti conto sin dall’apertura del rap-\n"
        "porto, con conseguente indeterminatezza del credito azionato.\n\n"
        "2) Nel merito, si eccepisce la prescrizione del credito."
    )
    blocchi = [{"blocco_id": "B01", "inizio": 0, "fine": 90},
               {"blocco_id": "B02", "inizio": 90, "fine": len(atto)}]

    prove = [
        ("esatta", "Nel merito, si eccepisce la prescrizione del credito."),
        ("normalizzata + sillabazione + apostrofo tipografico",
         "La banca non ha prodotto gli estratti conto sin dall'apertura del rapporto, "
         "con conseguente indeterminatezza del credito azionato."),
        ("fuzzy (una parola cambiata)",
         "La banca non ha prodotto gli estratti conto sin dall'apertura del rapporto, "
         "con conseguente indeterminatezza del credito richiesto."),
        # Un TRONCAMENTO resta `ancorata`: la citazione troncata e' pur
        # sempre una sottostringa esatta del normalizzato, e il passo 1 la
        # trova. `ancora_parziale` copre i casi che NON combaciano - testo
        # corrotto (OCR) o riscritto dal modello. Qui: 10 caratteri
        # sostituiti su 130, che portano il rapporto in [0.80, 0.95).
        ("parziale (testo corrotto, ~8% dei caratteri)",
         "La banxa non ha prodotto gli xstratti conto sxn dall'apertura dexl rapporto, "
         "cxn conseguentx indeterminatxzza del creditx azxonato."),
        ("non ancorata", "Il fideiussore eccepisce la nullita' della garanzia omnibus."),
    ]
    print(f"rapidfuzz disponibile: {RAPIDFUZZ_DISPONIBILE}\n")
    for etichetta, citazione in prove:
        esito = localizza(atto, blocchi, citazione)
        dettaglio = ""
        if esito["stato"] == "ancorata":
            dettaglio = (f"{esito['corrispondenza']}, [{esito['inizio']}:{esito['fine']}] "
                         f"{esito['blocco_id']}, sim={esito['similarita']}")
            estratto = atto[esito["inizio"]:esito["fine"]]
            dettaglio += f"\n      testo reale: {estratto[:70]!r}"
        elif esito["stato"] == "ancora_parziale":
            dettaglio = f"sim={esito['similarita']:.3f}, {esito['migliore_candidato']}"
        elif esito["stato"] == "ancora_ambigua":
            dettaglio = f"{len(esito['occorrenze'])} occorrenze"
        else:
            dettaglio = esito["motivo"]
        print(f"  [{esito['stato']:16s}] {etichetta}\n      {dettaglio}")

    ambiguo = "Roma. Roma."
    b = [{"blocco_id": "B01", "inizio": 0, "fine": len(ambiguo)}]
    print(f"\n  ambiguita' esatta: {localizza(ambiguo, b, 'Roma')['stato']}")
