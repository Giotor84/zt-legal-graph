# -*- coding: utf-8 -*-
"""Ricerca per parole e frequenza di citazione, e la loro fusione.

## Perche' esiste

Misurato il 2026-09-03 con `valuta_retrieval.py` su 1200 passaggi di
motivazione tenuti fuori dall'addestramento (verita' di riferimento: i
15.889 archi provvedimento -> articolo del grafo, cioe' quale norma il
giudice ha citato scrivendo quel passaggio):

    strategia                    R@1    R@5   R@10   R@20    MRR
    vettoriale (quella di ieri)  3,6%   8,3%  10,8%  14,6%  0,058
    BM25 (parole)                8,4%  18,8%  24,5%  32,1%  0,135
    frequenza (cieca)            4,4%  18,7%  32,9%  48,7%  0,120
    RRF parole + frequenza      23,5%  42,3%  48,8%  60,5%  0,321
    RRF vett + parole + freq.   16,5%  26,2%  32,2%  41,1%  0,214

Rifatta con `python src/valuta_retrieval.py --quanti 1200`.

Tre cose, tutte contrarie a quel che ci si aspettava.

**La ricerca semantica era la strategia peggiore provata.** Peggio della
ricerca per parole, e peggio di una strategia che **non legge nemmeno la
domanda** e propone sempre gli articoli piu' citati del corpus.

**Aggiungerla alla fusione la peggiora** - 60,5% -> 41,1% di R@20 - e
questo e' il fatto che decide: non e' un segnale debole da pesare di
meno, e' rumore che sposta in basso le risposte giuste. Il modello di
embedding e' `intfloat/multilingual-e5-small`, 118 milioni di parametri,
generico e multilingue, mai addestrato su italiano giuridico: su
un'eccezione di *mediazione* pesca i *mediatori creditizi* (E3), e la
misura dice che non e' un caso sfortunato ma il comportamento normale.

**La frequenza di citazione, da sola e cieca, batteva tutto.** Non
perche' sia intelligente: perche' le citazioni sono concentratissime
(l'art. 117 TUB compare in 613 motivazioni) e una lista dei venti
articoli piu' citati contiene quello giusto il 48,7% delle volte. E' un
fatto sul dominio, non sul metodo.

## Cosa cambia nella composizione della lista, compreso cio' che si perde

Misurato su 120 query vere, contando i primi 20 candidati:

    tipo di nodo            prima    oggi
    articolo                30,5%   69,0%
    massima                 64,7%   30,5%
    disposizione Bankitalia  4,8%    0,5%

Le massime sono **185 nodi su 5892, il 3,1% dell'indice, e occupavano il
64,7% dei primi venti**: venti volte la loro quota. E' un'altra faccia
dello stesso guasto - il modello generico trova le massime piu' simili
fra loro e alla query di quanto non trovi il testo di legge, che e'
scritto in un'altra lingua. Oggi la giurisprudenza resta presente a un
terzo dei posti, che e' una proporzione sana e non una sparizione.

**La perdita vera sono le disposizioni di Banca d'Italia**, da 4,8% a
0,5%, e va detta invece di essere nascosta dietro il miglioramento
complessivo: la graduatoria di citazione le ignora per costruzione (nel
grafo nessun arco da motivazione punta a loro) e sono testi lunghi, che
BM25 penalizza. Se serviranno, la strada e' una quota riservata, non un
peso diverso.

## Perche' la fusione e' RRF e non una somma pesata

Somma pesata vuol dire scegliere i pesi, e i pesi si scelgono sui
risultati - cioe' si taratura la misura sulla risposta che piace. RRF
(Reciprocal Rank Fusion) usa solo le POSIZIONI, non i punteggi, quindi
non richiede che due strategie abbiano punteggi confrontabili (BM25 e la
frequenza non ce li hanno) e ha una sola costante, che resta a 60, il
valore della letteratura, mai tarato qui.

## Cosa questa misura NON dice

Che la lista trovata sia giuridicamente la migliore: dice che contiene
**la norma che il giudice ha citato** scrivendo quel passaggio. E' un
riferimento imperfetto - un giudice cita anche per completezza, e tace
cio' che presuppone - ma non lo abbiamo scritto noi ed e' grande 24.832
casi.

E non dice nulla sulle norme **assenti dal grafo**: il d.lgs. 28/2010 e'
citato dal 10,9% delle motivazioni e nel corpus non c'e', quindi non
produce nessun arco e nessun caso. Su quelle nessuna ricerca puo'
funzionare, e resta il primo buco di `STATO_PROGETTO §3.2`.
"""

from __future__ import annotations

import collections
import math
import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Sequence

import popolazioni_archi

#: Le parole su cui si cerca. Tre lettere come minimo: sotto quella
#: soglia in italiano ci sono quasi solo preposizioni, che compaiono
#: ovunque e non discriminano niente.
_PAROLA = re.compile(r"[a-zà-ù]{3,}", re.IGNORECASE)

#: Costanti BM25 nei valori classici. Non sono state tarate su questo
#: corpus, e non vanno tarate senza rifare la misura di
#: `valuta_retrieval.py`: tarare i parametri sui casi di prova e poi
#: dichiarare il risultato sugli stessi casi e' il modo piu' comune di
#: pubblicare un miglioramento che non esiste.
K1 = 1.5
B = 0.75

#: La costante di RRF, dal lavoro originale (Cormack e altri). Una sola
#: costante e mai toccata: vedi il docstring del modulo.
K_RRF = 60


def parole(testo: str) -> list[str]:
    return _PAROLA.findall(testo.lower())


def testo_indicizzabile(dati: Mapping[str, Any]) -> str:
    """Il testo su cui si cerca, per tipo di nodo.

    Stessa composizione di `build_embeddings._testo_indicizzabile`, cosi'
    la ricerca per parole e quella semantica vedono lo stesso testo e un
    confronto fra le due e' un confronto fra metodi, non fra ingressi.
    """
    tipo = dati.get("tipo_nodo") or "articolo"
    if tipo == "massima":
        return (dati.get("titolo") or "") + ". " + (dati.get("testo") or "")
    if tipo == "bankit_disposizione":
        return (dati.get("citazione_breve") or "") + ". " + (dati.get("testo") or "")
    return (dati.get("rubrica") or "") + ". " + (dati.get("testo") or "")


@dataclass
class IndiceLessicale:
    """BM25 su un insieme di nodi del grafo.

    Costruito con un indice invertito: la versione ingenua (un giro su
    tutti i documenti per ogni parola) ci metteva minuti su 1200 query,
    questa ci mette secondi. Nessuna differenza nei risultati - stessa
    formula, solo i documenti che contengono la parola.
    """

    node_ids: list[str]
    _liste: dict[str, list[tuple[int, int]]]
    _idf: dict[str, float]
    _lunghezze: list[int]
    _lunghezza_media: float

    @classmethod
    def costruisci(cls, testi: Mapping[str, str]) -> "IndiceLessicale":
        node_ids = list(testi)
        documenti = [parole(testi[n]) for n in node_ids]
        lunghezze = [len(d) for d in documenti]
        totale = len(documenti)
        media = (sum(lunghezze) / totale) if totale else 0.0

        liste: dict[str, list[tuple[int, int]]] = collections.defaultdict(list)
        for indice, documento in enumerate(documenti):
            for parola, frequenza in collections.Counter(documento).items():
                liste[parola].append((indice, frequenza))

        idf = {parola: math.log(1 + (totale - len(posting) + 0.5) / (len(posting) + 0.5))
               for parola, posting in liste.items()}
        return cls(node_ids=node_ids, _liste=dict(liste), _idf=idf,
                   _lunghezze=lunghezze, _lunghezza_media=media)

    def cerca(self, query: str, k: int) -> list[str]:
        punteggi: dict[int, float] = collections.defaultdict(float)
        for parola in set(parole(query)):
            posting = self._liste.get(parola)
            if not posting:
                continue
            peso = self._idf[parola]
            for indice, frequenza in posting:
                norma = 1 - B + B * (self._lunghezze[indice] / self._lunghezza_media
                                     if self._lunghezza_media else 1.0)
                punteggi[indice] += peso * frequenza * (K1 + 1) / (frequenza + K1 * norma)
        # A parita' di punteggio vince il node_id piu' piccolo: senza,
        # l'ordine dipenderebbe dall'ordine di inserimento in un dict e
        # due corse potrebbero dare liste diverse.
        ordinati = sorted(punteggi.items(), key=lambda kv: (-kv[1], self.node_ids[kv[0]]))
        return [self.node_ids[i] for i, _ in ordinati[:k]]


def frequenza_di_citazione(grafo: Any, *,
                           escludi_provvedimenti: Iterable[str] = ()) -> dict[str, int]:
    """Quante motivazioni citano ciascun articolo.

    `escludi_provvedimenti` serve alla misura, non alla produzione:
    calcolare la frequenza anche sui provvedimenti del banco di prova
    farebbe contribuire ogni caso alla propria risposta, e il numero che
    ne uscirebbe sarebbe piu' alto e falso.
    """
    fuori = set(escludi_provvedimenti)
    conta: collections.Counter[str] = collections.Counter()
    for origine, destinazione, dati in grafo.edges(data=True):
        if origine in fuori:
            continue
        if popolazioni_archi.e_citazione_in_motivazione(dati):
            conta[destinazione] += 1
    return dict(conta)


def graduatoria_per_frequenza(frequenze: Mapping[str, int],
                              ammessi: Iterable[str] | None = None) -> list[str]:
    """Gli articoli dal piu' al meno citato. A parita', ordine alfabetico
    del node_id: la lista deve essere la stessa a ogni corsa."""
    consentiti = set(ammessi) if ammessi is not None else None
    voci = [(n, c) for n, c in frequenze.items()
            if consentiti is None or n in consentiti]
    voci.sort(key=lambda nc: (-nc[1], nc[0]))
    return [n for n, _ in voci]


#: Una strategia: dalla query ai node_id in ordine di pertinenza.
Strategia = Callable[[str, int], Sequence[str]]


def fondi(*strategie: Strategia, k_rrf: int = K_RRF, profondita: int = 100) -> Strategia:
    """Reciprocal Rank Fusion: unisce piu' strategie usando le posizioni.

    `profondita` e' quanti risultati chiedere a ciascuna strategia prima
    di fondere. Piu' alta di `k` di proposito: una risposta che sta al
    posto 40 in due strategie diverse deve poter risalire, ed e'
    esattamente il caso che la fusione esiste per prendere.
    """
    if not strategie:
        raise ValueError("almeno una strategia")

    def cerca(query: str, k: int) -> list[str]:
        punti: dict[str, float] = collections.defaultdict(float)
        for strategia in strategie:
            for posizione, node_id in enumerate(strategia(query, profondita), 1):
                punti[node_id] += 1.0 / (k_rrf + posizione)
        ordinati = sorted(punti.items(), key=lambda kv: (-kv[1], kv[0]))
        return [node_id for node_id, _ in ordinati[:k]]

    return cerca


def strategia_costante(graduatoria: Sequence[str]) -> Strategia:
    """La lista fissa, che non guarda la domanda. Da sola vale il 47% di
    R@20 ed e' il pavimento che qualunque strategia deve battere."""

    def cerca(_query: str, k: int) -> list[str]:
        return list(graduatoria[:k])

    return cerca


def strategia_lessicale(indice: IndiceLessicale) -> Strategia:
    def cerca(query: str, k: int) -> list[str]:
        return indice.cerca(query, k)

    return cerca


def indice_dal_grafo(grafo: Any, node_ids: Iterable[str]) -> IndiceLessicale:
    """L'indice per parole sui nodi indicati (di norma quelli gia'
    presenti nell'indice semantico, cosi' le due ricerche pescano dallo
    stesso insieme e restano confrontabili)."""
    return IndiceLessicale.costruisci(
        {n: testo_indicizzabile(grafo.nodes[n]) for n in node_ids if n in grafo.nodes})
