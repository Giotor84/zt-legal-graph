# -*- coding: utf-8 -*-
"""Le tre popolazioni di archi del grafo, dette una volta sola.

## Il difetto (BUG-GRAFO-5)

Gli archi del grafo non hanno uno schema. Ne hanno tre, uno per
produttore, e nessuno di loro lo dichiara. Censimento sui 9117 archi di
`grafo.gpickle` (2026-09-02):

    articolo -> articolo         5442   tipo_arco, has_seguenti
    provvedimento -> articolo    3229   tipo_arco, fonte_campo, occorrenze,
                                        ancore, data_provvedimento,
                                        articolo_abrogato_oggi
    massima/bankit -> articolo    446   tipo_arco

`tipo_arco` e' l'unico attributo che c'e' sempre, e vale `cita` su 9114
archi su 9117 (gli altri tre sono `massima_di`). Chi legge
`dati["has_seguenti"]` va in errore su 3675 archi; chi legge
`dati["ancore"]` su 5888.

## Cosa NON e' il difetto

Non e' che il grafo sia sporco: i tipi sono puliti (`has_seguenti` e
`articolo_abrogato_oggi` sono `bool` veri, `occorrenze` e' `int`), e
nessun consumatore va oggi in errore - tutti e tre usano `.get()` con un
default, verificato.

Il difetto e' che **il significato di una popolazione e' scritto
nell'assenza di un campo**, e la stessa deduzione e' ripetuta a mano in
tre moduli (`famiglie_da_cocitazione`, `golden_dal_grafo`,
`profili_famiglia`), ognuno con la sua copia di
`dati.get("fonte_campo") == "motivazione"`. Il giorno in cui una
popolazione nuova porta `fonte_campo`, tutti e tre cambiano
comportamento insieme e in silenzio, e nessuno dei tre dice di dipendere
da quella coincidenza.

## Cosa fa questo modulo

Nomina le tre popolazioni e basta. Non riscrive il grafo (vincolo 2), non
aggiunge attributi, non cambia il comportamento di nessuno: e' lo stesso
criterio di prima, scritto una volta invece di tre, con un censimento che
**si accorge di una forma nuova** invece di assorbirla.

Alla migrazione temporale il punto da riaprire e' questo, uno.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

#: Citazioni fra articoli di codice, prodotte da `build_graph.py`.
FRA_ARTICOLI = "articolo_articolo"

#: Citazioni tratte dal testo di un provvedimento, prodotte da
#: `bdp_archi_citazioni.py`. Le uniche che portano le ancore agli offset,
#: cioe' le uniche su cui la regola 4 puo' poggiare.
DA_PROVVEDIMENTO = "provvedimento_articolo"

#: Citazioni di una massima o di una disposizione Banca d'Italia verso un
#: articolo: `tipo_arco` e nient'altro.
DA_FONTE_ESTERNA = "fonte_esterna_articolo"

#: Nessuna delle tre. Non e' un valore che il grafo di oggi produca: e'
#: quello che `censimento` restituisce se un produttore nuovo comincia a
#: scrivere archi di una quarta forma.
SCONOSCIUTA = "sconosciuta"

#: Il campo che dice da quale parte del provvedimento viene la citazione.
#: Oggi vale `motivazione` su tutti e 3229 gli archi che ce l'hanno - non
#: esiste ancora nessun arco tratto da dispositivo o svolgimento. Il
#: filtro dei tre moduli e' quindi **corretto e per ora inerte**: divide
#: davvero quando l'ingestione comincera' a leggere anche il resto.
CAMPO_MOTIVAZIONE = "motivazione"


def popolazione(dati: Mapping[str, Any]) -> str:
    """A quale delle tre famiglie appartiene un arco, dai suoi attributi.

    Si guardano gli attributi e non i nodi agli estremi: e' l'arco a
    portare la sua forma, e chi itera con `edges(data=True)` ha in mano
    quella, non i nodi."""
    if "fonte_campo" in dati:
        return DA_PROVVEDIMENTO
    if "has_seguenti" in dati:
        return FRA_ARTICOLI
    if "tipo_arco" in dati:
        return DA_FONTE_ESTERNA
    return SCONOSCIUTA


def e_citazione_in_motivazione(dati: Mapping[str, Any]) -> bool:
    """L'arco viene dalla MOTIVAZIONE di un provvedimento.

    E' il criterio che `famiglie_da_cocitazione`, `golden_dal_grafo` e
    `profili_famiglia` usavano ognuno per conto suo: la co-citazione ha
    senso solo fra articoli che un giudice ha messo insieme decidendo -
    un arco articolo->articolo non e' una lite, e il resto della sentenza
    riporta invece di decidere."""
    return dati.get("fonte_campo") == CAMPO_MOTIVAZIONE


def ha_ancore(dati: Mapping[str, Any]) -> bool:
    """L'arco porta gli offset da cui la regola 4 puo' citare.

    Solo la popolazione dei provvedimenti li ha. Chiederli a un arco
    articolo->articolo non e' un errore da gestire: e' una domanda che a
    quell'arco non si fa."""
    return bool(dati.get("ancore"))


def censimento(archi: Iterable[tuple[Any, Any, Mapping[str, Any]]]) -> dict[str, int]:
    """Quanti archi per popolazione, `SCONOSCIUTA` compresa.

    Serve a rendere rumorosa una forma nuova. Senza, un produttore che
    scrive archi di una quarta forma non se ne accorge nessuno: i
    consumatori usano tutti `.get()` con un default, quindi non falliscono
    - semplicemente non contano quegli archi, e il numero che ne esce e'
    plausibile."""
    conteggio = {FRA_ARTICOLI: 0, DA_PROVVEDIMENTO: 0,
                 DA_FONTE_ESTERNA: 0, SCONOSCIUTA: 0}
    for _origine, _destinazione, dati in archi:
        conteggio[popolazione(dati)] += 1
    return conteggio
