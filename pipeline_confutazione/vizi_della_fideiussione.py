"""
Quale vizio della fideiussione viene dedotto.

`vizi_fideiussione` e' la seconda famiglia del corpus per volume (278
coppie, 196 decise nel merito, **20,4% accolte**) ed e' la prima con una
quota di accoglimento bassa: e' la famiglia in cui una confutazione vera
e' probabile, non solo un avvertimento.

## La precondizione non e' quella che ci si aspettava

SUPERFICIE_ATTACCO.md §5 indica come precondizione la **qualita' del
fideiussore** (socio, amministratore, terzo, consumatore). Misurando i
196 casi decisi del corpus, quella non separa niente: `socio` /
`amministratore` compaiono in 3 casi in tutto, `consumatore` in 11 (2
accolte, 9 rigettate, il 18% contro una base del 20,4%). E' anche il
campo che il modello dichiara senza che nulla lo verifichi (ARRETRATO
D5), quindi sarebbe stata una regola costruita su un dato asserito.

Cio' che separa e' **quale vizio viene dedotto**, e si vede nella
contestazione stessa:

    vizio dedotto                accolta  rigettata   % accolte
    schema ABI / antitrust             2         28          7%
    genericita' / novita'              0         10          0%
    importo massimo (art. 1938)        0          6          0%
    liberazione (art. 1956)            2          7         22%
    nullita' parziale                  4         12         25%
    decadenza (art. 1957)             20         49         29%
    ------------------------------------------------------------
    base dell'intera famiglia         40        156       20,4%

Due estremi utili e opposti: lo **schema ABI** e' il vizio piu' dedotto
fra quelli riconoscibili e il piu' rigettato - 28 su 30 - mentre l'**art.
1957** e' quello che regge piu' della media, con la base piu' larga (69
casi).

## La stessa misura, con il solo testo che il rilevatore vede

La tabella sopra e' costruita su eccezione + motivazione. Il rilevatore, a
corsa, legge **solo il testo dell'eccezione**: e' li' che il vizio viene
dedotto, ma e' meno testo. Rifatta su quello - cioe' su cio' che accadra'
davvero - la misura conferma la direzione e la attenua:

    vizio riconosciuto          accolta  rigettata   % accolte
    schema ABI / antitrust            3         24         11%
    decadenza (art. 1957)            11         31         26%
    liberazione (art. 1956)           0          6          0%
    importo massimo (art. 1938)       0          2          0%
    disconoscimento                   2          1         67%
    nessuno riconosciuto             24         92         21%
    ------------------------------------------------------------
    base dell'intera famiglia        40        156       20,4%

Sono questi i numeri che le note della regola citano, perche' sono quelli
delle condizioni in cui la regola lavora. Il rilevatore riconosce un vizio
in **104 eccezioni su 278, il 37%**: sulle altre due su tre la regola cade
nel ramo che non decide, ed e' la misura onesta della sua copertura.

## Cosa questi numeri NON sono

Sono co-occorrenze di parole nel testo dell'eccezione e in quello della
ratio, non classificazioni verificate a mano, e la ratio e' presente solo
su **161 coppie su 278**. Le righe con sei e dieci casi non reggono da
sole una regola: sono nominate nelle note, non usate per decidere.
Decidono solo le due righe con trenta e sessantanove casi, ed e' anche
per questo che le due direzioni della regola non sono simmetriche.

Nessuna di queste percentuali e' una previsione sulla singola causa.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Lo schema ABI e la vicenda antitrust: il provvedimento Banca d'Italia
#: 55/2005 e le Sezioni Unite 41994/2021.
SCHEMA_ABI = re.compile(
    r"schema\s+abi|modulo\s+abi|intesa\s+restrittiv\w+|antitrust"
    r"|normativa\s+antimonopolistic\w+|legge\s+antitrust|art\w*\.?\s*2\s+l\.?\s*287"
    r"|55/2005|41994", re.IGNORECASE)

#: L'importo massimo garantito.
IMPORTO_MASSIMO = re.compile(
    r"art\w*\.?\s*1938|importo\s+massimo\s+garantit\w+|senza\s+limitazione\s+di\s+importo",
    re.IGNORECASE)

#: La decadenza per mancata proposizione delle istanze nel termine.
DECADENZA = re.compile(
    r"art\w*\.?\s*1957|decadenz\w+\s+(?:del|della|dal)|entro\s+sei\s+mesi"
    r"|termine\s+semestrale", re.IGNORECASE)

#: La liberazione del fideiussore per credito concesso senza speciale
#: autorizzazione al debitore divenuto insolvente.
LIBERAZIONE = re.compile(
    r"art\w*\.?\s*1956|liberazione\s+del\s+fideiussor\w+"
    r"|speciale\s+autorizzazion\w+", re.IGNORECASE)

#: Il disconoscimento della sottoscrizione.
DISCONOSCIMENTO = re.compile(
    r"disconosc\w+|querela\s+di\s+falso|verificazione\s+della\s+scrittura"
    r"|firma\s+apocrif\w+", re.IGNORECASE)

#: Riconosce che si parla di fideiussione: senza, non si cerca altro.
#: `garanzia` nuda ci sta - gli atti scrivono "la garanzia e' inefficace"
#: molto piu' spesso di "la garanzia personale" - ma non quando e' reale:
#: l'ipoteca e il pegno sono un'altra famiglia, e un vizio dell'ipoteca
#: letto come vizio della fideiussione manderebbe l'eccezione al ramo
#: sbagliato.
FIDEIUSSIONE = re.compile(
    r"fideiuss\w+|coobbligat\w+|garant\w+\s+(?:person|solidal)"
    r"|garanzi\w+(?!\s+(?:ipotecar|real|pignoratiz))",
    re.IGNORECASE)

#: Il vizio che decide, quando ne compare piu' d'uno. L'ordine e' quello
#: della forza del dato, non dell'importanza giuridica: prima cio' su cui
#: il corpus ha abbastanza casi per dire qualcosa.
PRIORITA = ("schema_abi", "decadenza", "liberazione", "importo_massimo",
            "disconoscimento")

_REGOLE = (("schema_abi", SCHEMA_ABI), ("decadenza", DECADENZA),
           ("liberazione", LIBERAZIONE), ("importo_massimo", IMPORTO_MASSIMO),
           ("disconoscimento", DISCONOSCIMENTO))

#: Come si chiamano in italiano, per le note.
IN_ITALIANO = {
    "schema_abi": "conformita' allo schema ABI (profilo antitrust)",
    "decadenza": "decadenza ex art. 1957 c.c.",
    "liberazione": "liberazione del fideiussore ex art. 1956 c.c.",
    "importo_massimo": "mancanza dell'importo massimo garantito (art. 1938 c.c.)",
    "disconoscimento": "disconoscimento della sottoscrizione",
}


@dataclass(frozen=True)
class Esito:
    parla_di_fideiussione: bool
    vizi: list[str] = field(default_factory=list)

    @property
    def principale(self) -> str | None:
        """Il vizio su cui la regola decide. `None` quando non se ne
        riconosce nessuno - che non vuol dire che non ce ne siano."""
        for nome in PRIORITA:
            if nome in self.vizi:
                return nome
        return None

    def perche(self) -> str:
        if not self.parla_di_fideiussione:
            return "L'eccezione non riguarda la fideiussione."
        if not self.vizi:
            return ("L'eccezione riguarda la fideiussione ma non nomina un vizio "
                    "riconoscibile. Non e' la prova che non ne deduca uno: e' l'esito "
                    "di una ricerca sul testo.")
        nomi = ", ".join(IN_ITALIANO[v] for v in self.vizi)
        if len(self.vizi) == 1:
            return "Vizio dedotto: %s." % nomi
        return ("Vizi dedotti: %s. La regola decide su %s, che e' quello su cui il "
                "corpus ha piu' casi." % (nomi, IN_ITALIANO[self.principale]))


def cerca(testo: str) -> Esito:
    """I vizi nominati in UNA eccezione.

    A differenza di `conteggi_di_parte` e `cessione_del_credito`, che
    guardano l'atto intero, qui si guarda il testo della singola
    contestazione: il vizio e' nominato dove viene dedotto, non altrove."""
    if not testo or not FIDEIUSSIONE.search(testo):
        return Esito(False)
    vizi = [nome for nome, regola in _REGOLE if regola.search(testo)]
    return Esito(True, vizi)
