# -*- coding: utf-8 -*-
"""Aggiunge fonti normative nuove al grafo, senza rifarlo.

## Perche' esiste

Per innestare quattro leggi mancanti la via ovvia era rilanciare
`build_graph.py` e rimettere sopra i provvedimenti. E' stata provata il
2026-09-04, ed e' stata bocciata dal controllo di promozione:

    BOCCIATO: classi di nodo in calo: massima 185->0,
              bankit_disposizione 84->0

`build_graph.py` costruisce i soli articoli letti da `data/raw`. Le 185
massime e le 84 disposizioni della Banca d'Italia entrano da altri passi,
che non fanno parte della catena dei PDF: ricostruire da zero le
perdeva. Il controllo ha fatto il suo mestiere e il grafo in carica non
e' stato toccato, ma la lezione e' che **un grafo maturo non si
ricostruisce, si accresce**: nessuno tiene a mente tutti i produttori
che ci hanno scritto dentro.

Costa anche molto meno: rimettere i provvedimenti significava rileggere
3639 PDF, 37 minuti misurati. Qui non si rilegge niente.

## Cosa fa, e cosa si rifiuta di fare

Aggiunge i nodi che il candidato ha e il grafo no, e gli archi che li
toccano. **Non toglie mai niente**: se il candidato non ha un nodo o un
arco che il grafo ha, il grafo se lo tiene. La differenza fra i due non
e' una correzione da applicare, e' una differenza fra due produttori
diversi, e chi accresce non ha modo di sapere quale dei due abbia
ragione.

L'unica eccezione e' `--correggi-testi`, che aggiorna il testo dei nodi
gia' presenti: va chiesta apposta, perche' cambiare il testo di un nodo
sposta gli offset di chi lo cita e va fatta solo insieme al rifacimento
dell'indice dei segmenti.

## Cosa NON fa

Non promuove: scrive un candidato. La promozione resta di
`promuovi_grafo.py`, con i suoi otto controlli e il suo archivio.
"""

from __future__ import annotations

import argparse
import collections
import pickle
import sys
from pathlib import Path
from typing import Any

import networkx as nx


class InnestoRifiutato(RuntimeError):
    """L'innesto toglierebbe qualcosa, o non aggiungerebbe niente."""


def _articoli(grafo: nx.MultiDiGraph) -> set[str]:
    return {n for n, d in grafo.nodes(data=True) if d.get("codice")}


def censimento(grafo: nx.MultiDiGraph, candidato: nx.MultiDiGraph) -> dict[str, Any]:
    """Cosa entrerebbe, e cosa il candidato non ha.

    La seconda meta' e' quella che conta: dice quanto il candidato e' PIU
    POVERO del grafo, che e' il modo in cui una ricostruzione cancella in
    silenzio. Si dichiara sempre, anche quando e' zero."""
    nodi_grafo = set(grafo.nodes())
    nuovi = [n for n in candidato.nodes() if n not in nodi_grafo]
    assenti = [n for n in nodi_grafo if n not in set(candidato.nodes())]

    per_fonte: dict[str, int] = collections.Counter(
        candidato.nodes[n].get("codice") or "(senza codice)" for n in nuovi)
    classi_assenti: dict[str, int] = collections.Counter(
        grafo.nodes[n].get("tipo_nodo") or "articolo" for n in assenti)

    insieme = set(nuovi)
    archi = sum(1 for a, b in candidato.edges()
                if a in insieme or b in insieme)

    testi_diversi = [
        n for n in candidato.nodes()
        if n in nodi_grafo
        and (candidato.nodes[n].get("testo") or "")
        != (grafo.nodes[n].get("testo") or "")]

    return {
        "nodi_da_aggiungere": len(nuovi),
        "per_fonte": dict(per_fonte),
        "archi_da_aggiungere": archi,
        "nodi_del_grafo_assenti_dal_candidato": len(assenti),
        "classi_assenti": dict(classi_assenti),
        "testi_diversi": len(testi_diversi),
    }


def innesta(grafo: nx.MultiDiGraph, candidato: nx.MultiDiGraph, *,
            correggi_testi: bool = False) -> tuple[nx.MultiDiGraph, dict[str, Any]]:
    """Il grafo accresciuto, e cosa e' successo.

    Lavora su una copia: il chiamante deve poter confrontare il prima e
    il dopo, e un innesto che modifica in luogo rende impossibile dire
    cosa e' cambiato."""
    conto = censimento(grafo, candidato)
    if not conto["nodi_da_aggiungere"] and not (
            correggi_testi and conto["testi_diversi"]):
        raise InnestoRifiutato(
            "il candidato non aggiunge nessun nodo: o e' gia' innestato, "
            "o e' il candidato sbagliato")

    accresciuto = grafo.copy()
    gia_presenti = set(grafo.nodes())

    for n in candidato.nodes():
        if n not in gia_presenti:
            accresciuto.add_node(n, **candidato.nodes[n])
        elif correggi_testi:
            for campo in ("testo", "testo_raw", "rubrica"):
                if campo in candidato.nodes[n]:
                    accresciuto.nodes[n][campo] = candidato.nodes[n][campo]

    nuovi = {n for n in candidato.nodes() if n not in gia_presenti}
    aggiunti = 0
    for a, b, dati in candidato.edges(data=True):
        if a in nuovi or b in nuovi:
            accresciuto.add_edge(a, b, **dati)
            aggiunti += 1

    conto["archi_aggiunti"] = aggiunti
    conto["nodi_prima"] = grafo.number_of_nodes()
    conto["nodi_dopo"] = accresciuto.number_of_nodes()
    conto["archi_prima"] = grafo.number_of_edges()
    conto["archi_dopo"] = accresciuto.number_of_edges()
    conto["testi_corretti"] = conto["testi_diversi"] if correggi_testi else 0

    #: La garanzia che rende questo modulo additivo, controllata e non
    #: promessa: nessun nodo del grafo di partenza puo' mancare
    #: dall'accresciuto.
    perduti = gia_presenti - set(accresciuto.nodes())
    if perduti:
        raise InnestoRifiutato(
            "l'innesto avrebbe perso %d nodi: %r" % (len(perduti),
                                                     sorted(perduti)[:5]))
    return accresciuto, conto


def _carica(percorso: Path) -> nx.MultiDiGraph:
    with open(percorso, "rb") as f:
        return pickle.load(f)


def main(argv: list[str] | None = None) -> int:
    parti = argparse.ArgumentParser(description=__doc__)
    parti.add_argument("--grafo", type=Path, required=True,
                       help="Il grafo da accrescere (di norma quello in carica)")
    parti.add_argument("--candidato-articoli", type=Path, required=True,
                       help="Il grafo di soli articoli prodotto da build_graph.py")
    parti.add_argument("--out", type=Path, required=True,
                       help="Dove scrivere il grafo accresciuto. NON promuove.")
    parti.add_argument("--correggi-testi", action="store_true",
                       help="Aggiorna anche il testo dei nodi gia' presenti. "
                            "Sposta gli offset: da fare solo insieme al "
                            "rifacimento dell'indice dei segmenti.")
    args = parti.parse_args(argv)

    grafo = _carica(args.grafo)
    candidato = _carica(args.candidato_articoli)

    try:
        accresciuto, conto = innesta(grafo, candidato,
                                     correggi_testi=args.correggi_testi)
    except InnestoRifiutato as guasto:
        print("INNESTO RIFIUTATO: %s" % guasto)
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "wb") as f:
        pickle.dump(accresciuto, f)

    print("nodi  %d -> %d  (+%d)" % (conto["nodi_prima"], conto["nodi_dopo"],
                                     conto["nodi_da_aggiungere"]))
    print("archi %d -> %d  (+%d)" % (conto["archi_prima"], conto["archi_dopo"],
                                     conto["archi_aggiunti"]))
    for fonte, quanti in sorted(conto["per_fonte"].items(),
                                key=lambda x: -x[1]):
        print("   %5d  %s" % (quanti, fonte))
    if conto["nodi_del_grafo_assenti_dal_candidato"]:
        print("\nnodi del grafo che il candidato NON ha (tenuti): %d"
              % conto["nodi_del_grafo_assenti_dal_candidato"])
        for classe, quanti in sorted(conto["classi_assenti"].items(),
                                     key=lambda x: -x[1]):
            print("   %5d  %s" % (quanti, classe))
    print("\ntesti diversi dal candidato: %d | corretti: %d"
          % (conto["testi_diversi"], conto["testi_corretti"]))
    print("\nScritto in %s" % args.out)
    print("NON e' il grafo in carica: promuovilo con promuovi_grafo.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
