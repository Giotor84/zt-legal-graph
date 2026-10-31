"""
La contestazione della cessione: com'e' formulata nell'atto avversario.

Serve alla regola della legittimazione del cessionario, che e' la
famiglia con piu' materiale nel corpus (**393 coppie, 279 decise nel
merito, 40,5% accolte** sui 666 provvedimenti del 2026-09-02) e la sola
in cui l'avversario vince quattro volte su dieci.

## Perche' non si e' potuta ricavare la regola dal corpus

Il tentativo e' stato fatto ed e' andato male, e vale la pena scriverlo
perche' il prossimo non lo rifaccia. Cercando nelle motivazioni dei 279
casi decisi i marcatori che dovrebbero distinguere l'accoglimento dal
rigetto, il segnale non c'e':

    segnale                 accolta  rigettata   % accolte
    gazzetta ufficiale           16         29         36%
    contratto di cessione        16         22         42%
    art. 58 TUB                   7         17         29%
    estratto / elenco crediti     4          9         31%
    ------------------------------------------------------
    base dell'intera famiglia   113        166       40,5%

Nessuno scarto dalla base che voglia dire qualcosa, e la ragione e'
strutturale: il giudice nomina la Gazzetta Ufficiale sia quando basta sia
quando non basta. Il fatto che decide non e' una parola nella
motivazione, e `ratio_letterale` e' presente solo su 209 coppie su 393.
**Non ritentare con altre parole chiave sullo stesso campo.**

## Cosa invece si vede, e si vede bene

Il fatto che decide - lo dice SUPERFICIE_ATTACCO.md §3 - e' *che cosa ha
prodotto il cessionario*: il solo avviso in Gazzetta Ufficiale, oppure il
contratto di cessione con l'evidenza che quel credito ci sta dentro. Non
sta nel corpus delle decisioni, ma sta nell'ATTO AVVERSARIO, perche' e'
esattamente cio' di cui l'avversario si lamenta.

Misurato sui 52 atti leggibili di `atti_input/`: 42 parlano di cessione,
e **13 contengono l'allegazione specifica** - *"la pubblicazione nella
Gazzetta Ufficiale non e' sufficiente a dimostrare la titolarita'"*, *"si
e' semplicemente limitata a produrre l'avviso di cessione pubblicato
sulla Gazzetta"*, *"in mancanza di produzione del contratto di cessione,
la titolarita' del credito ceduto..."*. Tutti e 13 sono riscontri veri:
nessun falso positivo alla lettura.

## La direzione dell'errore

Opposta a quella di `conteggi_di_parte`, e per la stessa ragione di
fondo. Qui un riscontro porta la regola a dire *"l'eccezione REGGE"*, che
e' l'esito prudente: nessuna confutazione viene tentata. Un falso
positivo costa quindi una confutazione non tentata; un falso negativo
riporta la regola al ramo che non decide, che e' dove sarebbe stata
comunque. **Nessuno dei due errori puo' produrre una confutazione
sbagliata**, ed e' il motivo per cui questo modulo puo' permettersi di
essere piu' largo del suo gemello.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: L'atto parla di cessione del credito. Da solo non vuol dire niente -
#: 42 atti su 52 lo fanno - e serve solo a non cercare il resto dove non
#: c'e' nulla da cercare.
CESSIONE = re.compile(
    r"cession\w+|cessionari\w+|art\w*\.?\s*58\s*t\.?u\.?b|cartolarizzaz\w+",
    re.IGNORECASE)

#: L'allegazione specifica: e' stato prodotto SOLO l'avviso in Gazzetta.
#: Due forme, perche' l'avversario la scrive in due modi - "solo la
#: pubblicazione" e "la pubblicazione non basta".
SOLO_GAZZETTA = re.compile(
    r"(?:sol[ao]|mera|semplice|unicamente|limitat\w+ a)\D{0,40}"
    r"(?:pubblicazione|avviso|estratto)\D{0,40}gazzetta"
    r"|gazzetta ufficiale\D{0,60}non\D{0,30}(?:prova|sufficient|idone|bast)",
    re.IGNORECASE)

#: L'altra faccia: manca il contratto di cessione.
CONTRATTO_NON_PRODOTTO = re.compile(
    r"non ha (?:prodotto|depositato|allegato|offerto|fornito)\D{0,60}"
    r"(?:contratto di cessione|atto di cessione|cessione)"
    r"|(?:manca\w*|in mancanza di|difetta\w*)\D{0,40}"
    r"(?:produzione del |deposito del )?(?:contratto|atto) di cessione",
    re.IGNORECASE)

#: Cessioni a catena: l'onere si moltiplica, e il corpus contiene
#: un'autorita' AVVERSA su questo (Trib. Bologna, decreto 29/05/2025).
#: Riconoscerla serve a scriverlo nella nota, non a citarla.
CESSIONI_PLURIME = re.compile(
    r"cession\w+ (?:plurim|success|multipl|a catena)|nemo plus iuris"
    r"|(?:seconda|terza|ulteriore) cessione", re.IGNORECASE)

MAX_ESEMPI = 3


@dataclass(frozen=True)
class Riscontro:
    tipo: str  # "solo_gazzetta" | "contratto_non_prodotto" | "cessioni_plurime"
    contesto: str


@dataclass(frozen=True)
class Esito:
    parla_di_cessione: bool
    contestata_solo_gazzetta: bool
    cessioni_plurime: bool
    riscontri: list[Riscontro] = field(default_factory=list)

    def perche(self) -> str:
        if not self.parla_di_cessione:
            return "L'atto non contesta la cessione del credito."
        if not self.contestata_solo_gazzetta:
            return ("L'atto parla di cessione ma non si e' trovata l'allegazione "
                    "specifica che sia stato prodotto il solo avviso in Gazzetta "
                    "Ufficiale. Non e' la prova che non ci sia: e' l'esito di una "
                    "ricerca sul testo.")
        primo = self.riscontri[0]
        coda = (" L'atto lamenta inoltre una catena di cessioni: in quel caso l'onere "
                "di provarle TUTTE, comprese le intermedie, grava sull'ultimo "
                "cessionario." if self.cessioni_plurime else "")
        return ("L'atto contesta che sia stato prodotto il solo avviso in Gazzetta "
                "Ufficiale (\"...%s...\").%s" % (primo.contesto, coda))


def cerca(testo: str) -> Esito:
    """Come l'atto avversario formula la contestazione sulla cessione.

    Funzione pura sul testo: nessun modello, nessun grafo."""
    if not testo or not CESSIONE.search(testo):
        return Esito(False, False, False)

    riscontri: list[Riscontro] = []
    for tipo, regola in (("solo_gazzetta", SOLO_GAZZETTA),
                         ("contratto_non_prodotto", CONTRATTO_NON_PRODOTTO),
                         ("cessioni_plurime", CESSIONI_PLURIME)):
        for trovato in regola.finditer(testo):
            da = max(0, trovato.start() - 50)
            a = min(len(testo), trovato.end() + 50)
            riscontri.append(Riscontro(tipo, " ".join(testo[da:a].split())))
            break

    tipi = {r.tipo for r in riscontri}
    specifica = bool(tipi & {"solo_gazzetta", "contratto_non_prodotto"})
    # I riscontri si ordinano mettendo davanti quelli che decidono: la
    # nota mostra il primo, e "cessioni plurime" da solo non e' la
    # contestazione, e' un'aggravante di essa.
    riscontri.sort(key=lambda r: r.tipo == "cessioni_plurime")
    return Esito(parla_di_cessione=True,
                 contestata_solo_gazzetta=specifica,
                 cessioni_plurime="cessioni_plurime" in tipi,
                 riscontri=riscontri[:MAX_ESEMPI])
