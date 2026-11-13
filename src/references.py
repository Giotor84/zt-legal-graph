"""Estrazione dei riferimenti incrociati ("art. N c.c.", "artt. X e ss.", ecc.)
dal testo di un articolo, verso altri articoli dello stesso corpus.

Semplificazione dichiarata: un riferimento come "artt. 1241 e seguenti" produce
un solo arco verso l'art. 1241 (il primo della serie), con il flag `has_seguenti`
a True - non si espande automaticamente l'intera serie, che richiederebbe capire
dove si ferma "e seguenti" (non è markup esplicito nel testo sorgente).

## Estensione 2026-08-30: le forme delle MOTIVAZIONI

Il pattern era stato scritto sui testi di Normattiva, che citano in forma
canonica ("art. 1957 c.c."). Le motivazioni dei giudici no. Sulle 629
motivazioni BdP ingerite, 5680 riferimenti su 9463 restavano senza codice
e quindi non producevano alcun arco (STATO_PROGETTO §7.20).

Due cause, entrambe di COPERTURA del pattern - non di ambiguità: in tutti
i casi qui sotto il codice è scritto per esteso nel testo, e non viene
indovinato nulla.

1. **La sottoarticolazione interrompeva la cattura.** "art. 117, comma 3,
   del d.lgs. n. 385 del 1993": il qualificatore doveva seguire
   immediatamente il numero, e un ", comma 3," in mezzo lo faceva perdere.
   Da sola questa è la causa maggiore: 1477 riferimenti nudi hanno un
   ", comma N" subito dopo il numero. Risolta da _PONTE_SOTTOARTICOLAZIONE.
2. **Grafie del codice non previste**: "TUB" senza punti (849 occorrenze),
   "cod. civ." per esteso (277), "cod. proc. civ." (51), il TUB citato per
   numero di decreto "d.lgs. n. 385/1993" (45), "cpc" senza punti.

Misurato sull'insieme reale, non stimato:
- riferimenti risolti sulle 629 motivazioni: **3783 -> 5129 (+1346)**;
- **zero regressioni**: nessun riferimento già risolto cambia codice, né
  nelle motivazioni né nei testi degli articoli;
- sui 5867 testi degli articoli il numero di riferimenti trovati non
  cambia (6012 prima, 6012 dopo) e quelli con un codice esplicito passano
  da **285 a 297**. I 12 in più sono tutti rinvii DA un codice A un altro
  che prima si perdevano, riletti a mano uno per uno: il Codice della
  crisi che cita l'"articolo 2751-bis, n. 1, del codice civile" (5 volte)
  e l'"articolo 2112, commi 1, 3 e 4, del codice civile", il TUB che cita
  l'"articolo 2483, comma 3, del codice civile", il d.p.r. 602/1973 che
  cita l'"art. 140, del codice di procedura civile". Senza il ponte il
  qualificatore andava perso e il riferimento veniva risolto sullo STESSO
  codice della fonte (`codice_target=None`), cioè su un articolo che in
  quel codice non esiste - l'arco spariva in silenzio. Ricostruire il
  grafo con questo pattern non toglie nulla e aggiunge quei 12.

Restano fuori di proposito gli ELENCHI ("artt. 127 ter, 181, 309, 359
c.p.c.", ~1358 casi): lì il qualificatore è attaccato all'ultimo numero e
attribuirlo agli altri è un'inferenza, per quanto breve. Decisione
separata, non presa qui.
"""

import re
from dataclasses import dataclass

#: Frammenti di sottoarticolazione che possono stare FRA il numero
#: dell'articolo e il qualificatore di codice, senza spezzare il
#: riferimento ("art. 2, comma 2, lett. a) L. 287/1990").
#:
#: È deliberatamente un elenco CHIUSO e corto, mai testo libero: un ponte
#: del tipo `.{0,40}` potrebbe scavalcare la fine di una citazione e
#: agganciare il codice di quella successiva nella stessa frase, creando
#: un arco sbagliato. Misurato sulle 629 motivazioni: il riferimento
#: agganciato più lungo è di 59 caratteri, 83% stanno sotto i 20, nessuno
#: supera i 60.
_VALORE_SOTTOARTICOLAZIONE = (
    r"(?:\d{1,4}(?:[\-\s]?(?:bis|ter|quater|quinquies|sexies|septies|octies|novies|decies))?"
    r"|[a-z]\)|[ivx]{1,6}\)|[a-z]\b)"
)
_PONTE_SOTTOARTICOLAZIONE = (
    r"(?:\s*,\s*(?:commi|comma|co\.|nn\.|n\.|lettere|lettera|lett\.|paragrafo|par\.|punto)\s*"
    + _VALORE_SOTTOARTICOLAZIONE
    + r"(?:\s*(?:e|,)\s*" + _VALORE_SOTTOARTICOLAZIONE + r")*)*"
)

REF_PATTERN = re.compile(
    r"art(?:t|icol[oi])?\.?\s*(\d+(?:[\-\s]?(?:bis|ter|quater|quinquies|sexies|septies|octies|novies|decies))?(?:\.\d+)?)"
    r"(\s*(?:e\s+seguenti|e\s+ss\.?|ss\.?))?"
    + _PONTE_SOTTOARTICOLAZIONE +
    # Virgola di chiusura della sottoarticolazione, prima del codice:
    # "art. 117, comma 3, del d.lgs. ..." e anche il semplice "art. 96,
    # c.p.c.". UNA sola, e il qualificatore deve seguire subito dopo -
    # quindi "artt. 1341, 1342 c.c." non fa prendere il c.c. all'art. 1341
    # (fra la virgola e il codice c'e' un numero, che non e' un
    # qualificatore): gli elenchi restano fuori, come dichiarato sopra.
    r"(?:\s*,)?"
    r"(?:\s*(?:del(?:l[ao])?\s+)?("
    r"codice\s+civile|codice\s+di\s+procedura\s+civile|codice\s+della\s+crisi\s+d['’]impresa|testo\s+unico\s+bancario"
    r"|c\.\s?c\.\s?i\.|c\.\s?c\.|c\.\s?p\.\s?c\.|t\.\s?u\.\s?b\.?"
    # L. 241/1990 e D.P.R. 602/1973: qualificatore stesso numerico (a
    # differenza dei codici sopra, il nome della legge include l'anno), verificato
    # sul testo reale (references incrociate dentro dpr_602_1973.md/rd_267_1942.md
    # verso c.c./c.p.c. usano già il "del "/"della " sopra; queste voci coprono
    # invece citazioni VERSO le leggi appena aggiunte).
    r"|legge\s*(?:n\.?\s*)?241\s*/\s*1990|l\.\s*(?:n\.?\s*)?241\s*/\s*1990"
    r"|d\.?\s*p\.?\s*r\.?\s*(?:n\.?\s*)?602\s*/\s*1973"
    # Legge Fallimentare (R.D. 267/1942): sigla "L. Fall." di gran lunga la più
    # diffusa nella prassi forense, oltre al nome per esteso (già visto usato
    # nel corpus, dentro codice_crisi_impresa.md, per citare articoli specifici).
    r"|legge\s+fallimentare|l\.\s?fall\.?"
    r"|legge\s*(?:n\.?\s*)?689\s*/\s*1981|l\.\s*(?:n\.?\s*)?689\s*/\s*1981"
    r"|legge\s*(?:n\.?\s*)?287\s*/\s*1990|l\.\s*(?:n\.?\s*)?287\s*/\s*1990"
    # D.Lgs. 150/2011 (riti speciali): il rinvio da art. 22 L. 689/1981 usa
    # per esteso "decreto legislativo 1[°] settembre 2011, n. 150" - senza
    # questa voce il riferimento risolverebbe (sbagliato) sullo stesso codice
    # della fonte invece che su dlgs_150_2011 (vedi _normalize_qualifier).
    r"|d\.?\s*lgs\.?\s*(?:n\.?\s*)?150\s*/\s*2011"
    r"|decreto\s+legislativo\s+1°?\s+settembre\s+2011,?\s*n\.?\s*150"
    # \b/lookahead qui (assenti altrove nel pattern) perche' "cost" senza
    # confine rischierebbe di combaciare come prefisso di parole comuni
    # ("costante", "costoso") subito dopo un numero di articolo - gli altri
    # qualificatori sono al riparo da questo perche' sono frasi multi-parola
    # o già terminano con un punto letterale.
    r"|\bcostituzione\b|\bcost\.(?!\w)"
    # --- Grafie delle MOTIVAZIONI (2026-08-30, vedi docstring del modulo).
    # Sono in coda perche' l'alternanza e' valutata in ordine e queste sono
    # le forme piu' larghe: le voci sopra, piu' specifiche, devono vincere.
    # "TUB" senza punti: 849 occorrenze, la singola forma piu' frequente
    # fra quelle che si perdevano. La voce t.u.b. sopra pretende i punti.
    r"|\bT\.?U\.?B\.?\b"
    # "cod. proc. civ." PRIMA di "cod. civ.": altrimenti la seconda
    # combacerebbe sul prefisso e attribuirebbe al codice civile una
    # citazione del codice di rito.
    r"|\bcod\.?\s*proc\.?\s*civ\.?"
    r"|\bcod\.?\s*civ\.?"
    # "cpc"/"c.p.c" senza punto finale. Il \b in coda evita di agganciare
    # l'iniziale di una parola che segue.
    r"|\bc\.?p\.?c\b\.?"
    # Il TUB citato per numero di decreto invece che per sigla.
    r"|d\.?\s*lgs\.?\s*(?:n\.?\s*)?385\s*(?:/|\s+del\s+)\s*1993"
    r"|decreto\s+legislativo\s+(?:n\.?\s*)?385\s*(?:/|\s+del\s+)\s*1993"
    # --- Le quattro fonti innestate il 2026-09-04. Sono citate piu' di sei
    # delle undici gia' presenti (l. 108/1996 dall'11,4% delle sentenze,
    # d.lgs. 28/2010 dal 10,4%, cod. consumo dall'8,0%, TUF dal 6,1%): senza
    # queste voci gli articoli entravano nel grafo e nessun arco li
    # raggiungeva. Le grafie sono quelle lette nel corpus, non immaginate.
    r"|T\.?U\.?F\.?"
    r"|testo\s+unico\s+della\s+finanza"
    r"|d\.?\s*lgs\.?\s*(?:n\.?\s*)?58\s*(?:/|\s+del\s+)\s*1998"
    r"|decreto\s+legislativo\s+(?:n\.?\s*)?58\s*(?:/|\s+del\s+)\s*1998"
    r"|codice\s+del\s+consumo"
    r"|d\.?\s*lgs\.?\s*(?:n\.?\s*)?206\s*(?:/|\s+del\s+)\s*2005"
    r"|d\.?\s*lgs\.?\s*(?:n\.?\s*)?28\s*(?:/|\s+del\s+)\s*2010"
    # "L. 108/96" con l'anno a due cifre: e' la forma piu' diffusa per
    # l'usura, e senza le due cifre si perdeva.
    r"|legge\s*(?:n\.?\s*)?108\s*(?:/|\s+del\s+)\s*(?:19)?96"
    r"|l\.\s*(?:n\.?\s*)?108\s*(?:/|\s+del\s+)\s*(?:19)?96"
    r"|legge\s+antiusura"
    r"))?",
    re.IGNORECASE,
)

CODE_QUALIFIER_MAP = {
    "codice civile": "codice_civile",
    "c.c.": "codice_civile",
    "codice di procedura civile": "codice_procedura_civile",
    "c.p.c.": "codice_procedura_civile",
    "codice della crisi d'impresa": "codice_crisi_impresa",
    "codice della crisi d’impresa": "codice_crisi_impresa",
    "c.c.i.": "codice_crisi_impresa",
    "testo unico bancario": "tub",
    "t.u.b.": "tub",
    "t.u.b": "tub",
    "legge 241/1990": "l_241_1990",
    "legge n. 241/1990": "l_241_1990",
    "l. 241/1990": "l_241_1990",
    "l. n. 241/1990": "l_241_1990",
    "d.p.r. 602/1973": "dpr_602_1973",
    "d.p.r. n. 602/1973": "dpr_602_1973",
    "dpr 602/1973": "dpr_602_1973",
    "d p r 602/1973": "dpr_602_1973",
    "legge fallimentare": "rd_267_1942",
    "l. fall.": "rd_267_1942",
    "l.fall.": "rd_267_1942",
    "l. fall": "rd_267_1942",
    "legge 689/1981": "l_689_1981",
    "legge n. 689/1981": "l_689_1981",
    "l. 689/1981": "l_689_1981",
    "l. n. 689/1981": "l_689_1981",
    "legge 287/1990": "l_287_1990",
    "legge n. 287/1990": "l_287_1990",
    "l. 287/1990": "l_287_1990",
    "l. n. 287/1990": "l_287_1990",
    "costituzione": "costituzione",
    "cost.": "costituzione",
    "d.lgs. 150/2011": "dlgs_150_2011",
    "d.lgs. n. 150/2011": "dlgs_150_2011",
    "dlgs 150/2011": "dlgs_150_2011",
    "decreto legislativo 1° settembre 2011, n. 150": "dlgs_150_2011",
    "decreto legislativo 1 settembre 2011, n. 150": "dlgs_150_2011",
    # --- Grafie delle MOTIVAZIONI (2026-08-30, vedi docstring del modulo).
    # Le chiavi sono la forma normalizzata da _normalize_qualifier
    # (minuscolo, spazi compattati), quindi vanno elencate tutte le varianti
    # di punteggiatura osservate nei testi reali - non e' ridondanza.
    "tub": "tub", "t.u.b": "tub", "t.u.b.": "tub", "t. u. b.": "tub",
    "cod. civ.": "codice_civile", "cod. civ": "codice_civile",
    "cod.civ.": "codice_civile", "cod.civ": "codice_civile",
    "cod civ": "codice_civile", "cod civ.": "codice_civile",
    "cod. proc. civ.": "codice_procedura_civile", "cod. proc. civ": "codice_procedura_civile",
    "cod.proc.civ.": "codice_procedura_civile", "cod.proc.civ": "codice_procedura_civile",
    "cod proc civ": "codice_procedura_civile", "cod proc civ.": "codice_procedura_civile",
    "cpc": "codice_procedura_civile", "cpc.": "codice_procedura_civile",
    "c.p.c": "codice_procedura_civile",
    "d.lgs. n. 385/1993": "tub", "d.lgs. 385/1993": "tub",
    "d.lgs. n. 385 del 1993": "tub", "d.lgs. 385 del 1993": "tub",
    "d. lgs. n. 385 del 1993": "tub", "d. lgs. 385/1993": "tub",
    "dlgs 385/1993": "tub", "dlgs n. 385/1993": "tub",
    "decreto legislativo n. 385 del 1993": "tub",
    "decreto legislativo 385 del 1993": "tub",
    "decreto legislativo n. 385/1993": "tub",
    "decreto legislativo 385/1993": "tub",
    # --- Le quattro fonti innestate il 2026-09-04. Le chiavi sono la forma
    # normalizzata da _normalize_qualifier (minuscolo, spazi compattati):
    # vanno elencate tutte le varianti di punteggiatura osservate, non e'
    # ridondanza.
    "tuf": "dlgs_58_1998", "t.u.f": "dlgs_58_1998", "t.u.f.": "dlgs_58_1998",
    "t. u. f.": "dlgs_58_1998",
    "testo unico della finanza": "dlgs_58_1998",
    "d.lgs. n. 58/1998": "dlgs_58_1998", "d.lgs. 58/1998": "dlgs_58_1998",
    "d.lgs. n. 58 del 1998": "dlgs_58_1998",
    "d.lgs. 58 del 1998": "dlgs_58_1998",
    "d. lgs. n. 58 del 1998": "dlgs_58_1998",
    "dlgs 58/1998": "dlgs_58_1998", "dlgs n. 58/1998": "dlgs_58_1998",
    "decreto legislativo n. 58 del 1998": "dlgs_58_1998",
    "decreto legislativo 58/1998": "dlgs_58_1998",
    "decreto legislativo n. 58/1998": "dlgs_58_1998",
    "codice del consumo": "dlgs_206_2005",
    "d.lgs. n. 206/2005": "dlgs_206_2005", "d.lgs. 206/2005": "dlgs_206_2005",
    "d.lgs. n. 206 del 2005": "dlgs_206_2005",
    "d.lgs. 206 del 2005": "dlgs_206_2005",
    "dlgs 206/2005": "dlgs_206_2005",
    "d.lgs. n. 28/2010": "dlgs_28_2010", "d.lgs. 28/2010": "dlgs_28_2010",
    "d.lgs. n. 28 del 2010": "dlgs_28_2010",
    "d.lgs. 28 del 2010": "dlgs_28_2010",
    "dlgs 28/2010": "dlgs_28_2010",
    "legge 108/1996": "l_108_1996", "legge n. 108/1996": "l_108_1996",
    "legge 108/96": "l_108_1996", "legge n. 108/96": "l_108_1996",
    "l. 108/1996": "l_108_1996", "l. n. 108/1996": "l_108_1996",
    "l. 108/96": "l_108_1996", "l. n. 108/96": "l_108_1996",
    "legge 108 del 1996": "l_108_1996",
    "legge n. 108 del 1996": "l_108_1996",
    "legge antiusura": "l_108_1996",
}


#: Suffissi ordinali di numerazione degli articoli, gli stessi di
#: REF_PATTERN. Ripetuti qui e non ricavati dal pattern perche' servono a
#: normalizzare il numero GIA' catturato, non a catturarlo.
_SUFFISSI_ORDINALI = (
    "bis", "ter", "quater", "quinquies", "sexies", "septies", "octies", "novies", "decies",
)

_SUFFISSO_ATTACCATO_PATTERN = re.compile(
    r"^(\d+)(" + "|".join(_SUFFISSI_ORDINALI) + r")$", re.IGNORECASE
)


def _normalize_numero(raw: str) -> str:
    # "129 bis" -> "129-bis" (nel nostro corpus il separatore è sempre "-")
    numero = re.sub(r"\s+", "-", raw.strip())
    # "281sexies" -> "281-sexies": REF_PATTERN ammette il suffisso attaccato
    # (il separatore e' `[\-\s]?`, opzionale) ma il corpus lo scrive sempre
    # col trattino, quindi senza questa riga il riferimento non risolve su
    # nessun nodo. Misurato sulle 660 motivazioni del lotto BdP 2026-08:
    # 281sexies (7), 125bis (6), 348bis (4), 171ter (4), 127ter (3),
    # 281decies (3), 702ter, 363bis - 30 riferimenti non risolti su 37.
    return _SUFFISSO_ATTACCATO_PATTERN.sub(r"\1-\2", numero)


def _normalize_qualifier(raw: str | None) -> str | None:
    if not raw:
        return None
    key = re.sub(r"\s+", " ", raw.strip().lower())
    return CODE_QUALIFIER_MAP.get(key)


@dataclass
class Riferimento:
    numero_target: str
    codice_target: str | None  # None = stesso codice della fonte (da risolvere dopo)
    has_seguenti: bool


def estrai_riferimenti(testo: str) -> list[Riferimento]:
    riferimenti = []
    for numero_raw, seguenti_raw, qualifier_raw in REF_PATTERN.findall(testo):
        riferimenti.append(
            Riferimento(
                numero_target=_normalize_numero(numero_raw),
                codice_target=_normalize_qualifier(qualifier_raw),
                has_seguenti=bool(seguenti_raw.strip()),
            )
        )
    return riferimenti
