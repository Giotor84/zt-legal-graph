"""
L'atto avversario porta dei conteggi, o contesta e basta?

Serve a una cosa sola, e a quella e' meglio che serva bene: la regola
delle anomalie contabili confuta la contestazione generica dicendo che
l'avversario non ha messo cifre sul tavolo. **Se le cifre ci sono, quel
contro-argomento e' falso**, e finirebbe in un atto vero a sostenere una
cosa che il fascicolo smentisce.

## Perche' non basta il campo del modello

`conteggi_allegati` esiste nel contratto ed e' per-eccezione, ma sulle
365 eccezioni estratte in tutte le corse presenti in `runs/` e `lavoro/`
al 2026-09-02 e' vero **una volta sola**: nello schema della chiamata era
un booleano senza descrizione, quindi al modello non e' mai stato
spiegato che cosa significasse, e un booleano senza domanda risponde
falso. Il prompt e' stato corretto lo stesso giorno, ma un campo che ha
sbagliato 364 volte su 365 non si usa da solo il giorno dopo.

## Perche' non basta guardare il testo dell'eccezione

Delle stesse 365 eccezioni, **6** hanno un importo dentro il proprio
`testo_verbatim`, e sono tutte dello stesso atto. Le cifre non stanno
nella frase che contesta: stanno nel paragrafo che riassume la
consulenza, qualche pagina prima. Il fatto e' dell'ATTO, non della
singola eccezione - ed e' anche cio' che `conteggi_allegati` vuol dire in
sostanza: se la controparte ha prodotto un ricalcolo, l'ha prodotto per
il giudizio, non per un'eccezione.

## Perche' non basta cercare un importo

Misurato sui 52 atti leggibili di `atti_input/`: **44 su 52, l'85%**,
contengono almeno un importo o una percentuale. Ovvio - c'e' dentro la
somma ingiunta. Un segnale vero all'85% non e' un segnale.

Il criterio che discrimina e' la **vicinanza** fra un importo e una
parola che nomina un ricalcolo: `perizia`, `conteggio`, `ricalcolo`,
`rideterminazione`, `prospetto`, `consulenza tecnica di parte`. Con una
finestra di 400 caratteri: **14 su 52, il 27%**. I passaggi che pesca
sono quelli giusti - *"perizia econometrica dalla quale si evinceva che
il saldo eff..."*, *"nella perizia di parte, versata in atti, ha
accertato e provato"*.

## La direzione dell'errore, che qui e' tutto

Un falso positivo (un atto in cui `perizia` e un importo si sfiorano per
caso - fra i 14 ce n'e' uno, *"vendita del lotto 1 in perizia"*) costa
una confutazione non tentata. Un falso negativo costa una confutazione
SBAGLIATA in un atto depositato. I due errori non sono commensurabili, e
per questo la funzione e' tarata larga: **dice `True` facilmente**, e chi
la usa si astiene.

Per la stessa ragione `False` non significa "non ci sono conteggi": vuol
dire "non se ne sono trovati nel testo". La regola che la consuma lo
scrive nella propria nota.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Un importo in euro: `€ 12.345,67`, `12.345,67 euro`, `EUR 1.000,00`.
#: I decimali sono obbligatori - un numero tondo senza virgola e' quasi
#: sempre un anno, un articolo di legge o un numero di ruolo.
IMPORTO = re.compile(
    r"(?:€|EUR\b|euro\b)\s*\d{1,3}(?:[.\s]\d{3})*,\d{2}"
    r"|\d{1,3}(?:[.\s]\d{3})*,\d{2}\s*(?:€|EUR\b|euro)", re.IGNORECASE)

#: Un tasso: `24,375%`. Anche qui i decimali sono richiesti, perche' `30
#: %` compare in contesti che non sono tassi.
PERCENTUALE = re.compile(r"\d{1,3}[,.]\d{1,4}\s*%")

#: Le parole che nominano un ricalcolo di parte. Non `CTU`: la consulenza
#: d'ufficio e' chiesta al giudice, non prodotta dalla parte, e chiederla
#: e' semmai la prova che i conteggi NON ci sono.
RICALCOLO = re.compile(
    r"ricalcol\w*|riconteggi\w*|rideterminaz\w*|conteggi\w*|prospett\w*"
    r"|perizia|perizie|consulenza tecnica di parte|\bC\.?T\.?P\.?\b",
    re.IGNORECASE)

#: Quanti caratteri possono separare la cifra dalla parola. 400 e' circa
#: un paragrafo: sotto, si perdono i casi in cui la cifra e' nella frase
#: dopo; sopra, la vicinanza smette di voler dire qualcosa su un atto
#: denso di numeri.
FINESTRA = 400

#: Oltre questo numero di riscontri non se ne cercano altri: servono a
#: far vedere a un umano perche' la funzione ha detto True, non a essere
#: contati.
MAX_ESEMPI = 3


@dataclass(frozen=True)
class Riscontro:
    """Un importo vicino a una parola di ricalcolo, col suo contorno."""

    parola: str
    importo: str
    contesto: str


@dataclass(frozen=True)
class Esito:
    trovati: bool
    riscontri: list[Riscontro] = field(default_factory=list)

    def perche(self) -> str:
        """La spiegazione da mettere in una nota, gia' in italiano."""
        if not self.trovati:
            return ("Nel testo dell'atto non si sono trovati importi in prossimita' di "
                    "un richiamo a un ricalcolo, una perizia o un conteggio di parte. "
                    "Non e' la prova che non ce ne siano: e' l'esito di una ricerca sul "
                    "testo.")
        primo = self.riscontri[0]
        return ("L'atto porta dei conteggi: nel testo compare l'importo %s in "
                "prossimita' del richiamo a %s (\"...%s...\")." % (
                    primo.importo, primo.parola.lower(), primo.contesto))


def cerca(testo: str) -> Esito:
    """I riscontri di un conteggio di parte nel testo dell'atto.

    Nessuna chiamata al modello, nessun accesso al grafo: una funzione
    pura sul testo, quindi verificabile per intero senza far girare
    niente - come il resto di cio' che decide."""
    if not testo:
        return Esito(trovati=False)

    zone = [(m.start(), m.end(), m.group(0)) for m in RICALCOLO.finditer(testo)]
    if not zone:
        return Esito(trovati=False)

    riscontri: list[Riscontro] = []
    cifre = list(IMPORTO.finditer(testo)) + list(PERCENTUALE.finditer(testo))
    for cifra in sorted(cifre, key=lambda m: m.start()):
        inizio, fine = cifra.span()
        for zona_i, zona_f, parola in zone:
            if zona_i - FINESTRA < inizio and fine < zona_f + FINESTRA:
                da = max(0, min(zona_i, inizio) - 40)
                a = min(len(testo), max(zona_f, fine) + 40)
                riscontri.append(Riscontro(
                    parola=parola, importo=cifra.group(0).strip(),
                    contesto=" ".join(testo[da:a].split())))
                break
        if len(riscontri) >= MAX_ESEMPI:
            break

    return Esito(trovati=bool(riscontri), riscontri=riscontri)


def nell_atto(testo: str) -> bool:
    """Solo il booleano, per chi non deve spiegare niente."""
    return cerca(testo).trovati
