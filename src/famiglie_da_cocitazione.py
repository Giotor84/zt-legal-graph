"""Le famiglie di eccezioni RICAVATE dalla struttura del grafo, invece che
disegnate a mano prima di guardare i dati.

## L'idea

`motore_regole.Famiglia` elenca 9 famiglie decise a priori (8 da
SUPERFICIE_ATTACCO.md piu' una trovata leggendo un atto vero), di cui 2
popolate. Questo modulo prende la strada opposta: ogni provvedimento e' una
lite reale, e l'insieme di articoli che la sua motivazione cita e' la firma
di quella lite. Due articoli che compaiono spesso nella STESSA motivazione
appartengono allo stesso discorso giuridico - non perche' qualcuno lo abbia
deciso, ma perche' i giudici li usano insieme.

Quindi: grafo di co-citazione fra articoli (peso = quante motivazioni li
citano entrambi), comunita' di Louvain su quel grafo, e le comunita' sono
le famiglie candidate.

Nessun modello linguistico. Solo gli archi `cita` costruiti da
bdp_archi_citazioni.py, cioe' solo riferimenti il cui codice era scritto
per esteso nel testo.

## Cosa e' stato misurato (lotto BdP 2026-08, 775 provvedimenti)

588 provvedimenti con almeno un articolo agganciato, mediana 4 articoli a
provvedimento. Tolte le coppie viste meno di SOGLIA_COPPIA volte restano
138 articoli e 722 coppie.

**Cinque** comunita' su sette coincidono con famiglie riconoscibili, e
nessuno gliel'ha detto:

    58 TUB + 1260/1262/1264 c.c. + 2721/2729/1189 c.c. + 115/116 c.p.c.
        -> legittimazione del cessionario, con il suo corredo probatorio
    1957 + 1956 + 1945 + 1938 + 1419 c.c. + art. 2 L. 287/1990
        -> vizi della fideiussione, ramo ABI/antitrust incluso
    50 TUB + 633/634/644/645/648/653 c.p.c. + 1832 c.c. + 2719 c.c.
        + 214/216 c.p.c.
        -> saldaconto e prova monitoria: la certificazione ex art. 50 TUB,
           gli articoli del decreto ingiuntivo e della sua opposizione,
           l'approvazione del conto, il disconoscimento di scrittura
    117/119/120/106 TUB + 1283/1284/1346/1815/1418/2033 c.c. + 210 c.p.c.
        -> anomalie contabili e trasparenza: anatocismo, interessi,
           determinatezza, usura, nullita', indebito, ordine di esibizione
    2935 + 2941 + 2946 c.c.
        -> prescrizione (mescolata pero' con la procedura d'appello)

Le altre due NON sono famiglie ed e' altrettanto utile saperlo: artt.
641-650 + 281-sexies + 171-ter + 91/96 c.p.c. e' l'impalcatura processuale
dell'opposizione a decreto ingiuntivo con le spese, artt. 299/305/310
c.p.c. l'interruzione del processo. Compaiono ovunque proprio perche' non
distinguono nulla.

**Correzione rispetto alla prima misura (stessa sessione, 2463 archi).**
Con 570 archi in meno, `art. 2697 c.c.` e `art. 50 TUB` cadevano nella
stessa comunita' e la conclusione scritta qui era che i giudici trattano
INCOMPLETEZZA_ESTRATTI_CONTO, SALDACONTO_ART_50_TUB,
DOCUMENTAZIONE_ART_119_TUB e ANOMALIE_CONTABILI come una battaglia sola.
Con il pattern esteso di references.py (3033 archi) quella coppia si
separa in 0 partizioni su 20, e le due aree si distinguono nettamente: da
una parte il saldaconto come prova nel monitorio, dall'altra le anomalie
del conto e la trasparenza. La conclusione precedente era un artefatto
della copertura, non un fatto sul dominio - piu' dati l'hanno smentita.

## Stabilita' (perche' non e' una partizione fortunata)

Louvain e' sensibile al seme e alla risoluzione. `stabilita()` rifa la
partizione su 5 semi x 4 risoluzioni e conta quante volte due articoli
scelti finiscono insieme. Misurato sui 3033 archi:

    58 TUB / 1264 c.c.            20/20
    1957 / 1945 c.c.              20/20
    1957 c.c. / 2 L.287/1990      20/20
    1283 c.c. / 117 TUB           20/20
    2935 / 2946 c.c.              20/20
    2697 c.c. / 50 TUB             0/20   <- si separano, vedi sopra
    CONTROLLO 1957 c.c. / 58 TUB   2/20
    CONTROLLO 2935 c.c. / 650 cpc  0/20

I due controlli negativi in fondo dicono che il metodo separa davvero, non
che aggrega tutto. Le sonde vere sono tutte a 20/20 tranne quella che si e'
rivelata una coppia sbagliata da attendersi.

## Limiti, dichiarati

- Vede solo cio' che ha un arco, quindi non i 5680 riferimenti senza
  qualificatore (STATO_PROGETTO §7.20). Un'area di diritto citata sempre in
  forma nuda sarebbe invisibile qui.
- Un articolo sta in una comunita' sola. `art. 1418 c.c.` (nullita') serve
  a piu' famiglie; la partizione lo assegna a una.
- Le comunita' sono candidate, non famiglie: il nome, i confini e la
  regola restano giudizio giuridico. Questo modulo dice DOVE guardare, non
  cosa scrivere.

Sola lettura sul grafo. Non scrive nel grafo, non tocca motore_regole.py,
non assegna famiglie.

Uso:
    python src/famiglie_da_cocitazione.py --grafo PATH [--stabilita]
"""

from __future__ import annotations

import argparse
import itertools
import json
import pickle
from collections import Counter, defaultdict
from pathlib import Path

import networkx as nx

from popolazioni_archi import e_citazione_in_motivazione  # BUG-GRAFO-5

ROOT = Path(__file__).parent.parent
GRAFO_DEFAULT = ROOT / "data" / "graph" / "grafo_2026-08-26_bdp816_citazioni.gpickle"

#: Coppie di articoli co-citate meno di cosi' vengono tolte. Con soglia 1 il
#: grafo ha 4608 coppie di cui la grande maggioranza vista una volta sola:
#: sono coincidenze, non struttura, e annegano le comunita'. A 3 restano 446
#: coppie e le comunita' diventano leggibili. Non e' una manopola da girare
#: per ottenere il risultato voluto - e' l'unico parametro del metodo, e
#: stabilita() serve a mostrare che il risultato non ci si appoggia sopra.
SOGLIA_COPPIA = 3

SEED = 20260830
RISOLUZIONE = 1.3


def articoli_per_provvedimento(grafo) -> dict[str, set[str]]:
    """Per ogni provvedimento, gli articoli che la sua MOTIVAZIONE cita.
    Solo archi con fonte_campo=='motivazione': il resto del grafo (archi
    articolo->articolo, massima->articolo) non e' una lite e non deve
    entrare nella co-citazione."""
    per_prov: dict[str, set[str]] = defaultdict(set)
    for u, v, dati in grafo.edges(data=True):
        if e_citazione_in_motivazione(dati):
            per_prov[u].add(v)
    return dict(per_prov)


def grafo_cocitazione(per_prov: dict[str, set[str]], soglia: int = SOGLIA_COPPIA) -> nx.Graph:
    co = nx.Graph()
    for articoli in per_prov.values():
        for a, b in itertools.combinations(sorted(articoli), 2):
            co.add_edge(a, b, weight=co.get_edge_data(a, b, {}).get("weight", 0) + 1)
    co.remove_edges_from([(a, b) for a, b, d in co.edges(data=True) if d["weight"] < soglia])
    co.remove_nodes_from([n for n in list(co) if co.degree(n) == 0])
    return co


def comunita(co: nx.Graph, seed: int = SEED, risoluzione: float = RISOLUZIONE) -> list[set[str]]:
    trovate = nx.community.louvain_communities(co, weight="weight", seed=seed, resolution=risoluzione)
    return sorted(trovate, key=len, reverse=True)


def stabilita(co: nx.Graph, sonde: dict[str, tuple[str, str]],
              semi=(1, 7, 42, SEED, 999), risoluzioni=(0.9, 1.1, 1.3, 1.5)) -> dict[str, tuple[int, int]]:
    """Per ogni coppia di articoli, quante partizioni su quante la tengono
    insieme. Serve a distinguere una struttura reale da una partizione
    fortunata - e va usata anche con coppie di CONTROLLO che ci si aspetta
    separate, altrimenti misura solo la propria disponibilita' ad aggregare."""
    insieme = Counter()
    prove = [(s, r) for s in semi for r in risoluzioni]
    for seme, risoluzione in prove:
        dove = {n: i for i, c in enumerate(comunita(co, seme, risoluzione)) for n in c}
        for nome, (a, b) in sonde.items():
            if a in dove and b in dove and dove[a] == dove[b]:
                insieme[nome] += 1
    return {nome: (insieme[nome], len(prove)) for nome in sonde}


def etichetta(grafo, node_id: str) -> str:
    dati = grafo.nodes[node_id]
    codice = dati.get("codice", "?").replace("codice_", "").replace("_", " ")
    return f"art. {dati.get('numero', '?')} {codice}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--grafo", type=Path, default=GRAFO_DEFAULT)
    parser.add_argument("--soglia", type=int, default=SOGLIA_COPPIA)
    parser.add_argument("--min-articoli", type=int, default=4,
                        help="Comunita' piu' piccole di cosi' non vengono stampate")
    parser.add_argument("--stabilita", action="store_true",
                        help="Rifa la partizione su 5 semi x 4 risoluzioni e misura le sonde")
    parser.add_argument("--json", type=Path, default=None, help="Scrive le comunita' anche come JSON")
    args = parser.parse_args()

    with open(args.grafo, "rb") as f:
        grafo = pickle.load(f)

    per_prov = articoli_per_provvedimento(grafo)
    co = grafo_cocitazione(per_prov, args.soglia)
    print(f"provvedimenti con almeno un articolo agganciato: {len(per_prov)}")
    lunghezze = sorted(len(s) for s in per_prov.values())
    print(f"articoli per provvedimento: mediana {lunghezze[len(lunghezze)//2]}, max {lunghezze[-1]}")
    print(f"co-citazione (peso >= {args.soglia}): {co.number_of_nodes()} articoli, {co.number_of_edges()} coppie\n")

    com = comunita(co)
    grado = dict(co.degree(weight="weight"))
    uscita = []
    for i, c in enumerate(com):
        ordinati = sorted(c, key=lambda n: -grado[n])
        uscita.append({"comunita": i, "n_articoli": len(c),
                       "articoli": [{"node_id": n, "etichetta": etichetta(grafo, n)} for n in ordinati]})
        if len(c) < args.min_articoli:
            continue
        print(f"[{i}] {len(c)} articoli")
        for n in ordinati[:12]:
            print(f"      {etichetta(grafo, n)}")
        print()

    if args.stabilita:
        sonde = {
            "cessionario (58 tub / 1264 cc)": ("tub::58", "codice_civile::1264"),
            "fideiussione (1957 / 1945 cc)": ("codice_civile::1957", "codice_civile::1945"),
            "fideiussione ABI (1957 cc / 2 l.287)": ("codice_civile::1957", "l_287_1990::2"),
            "prova del credito (2697 cc / 50 tub)": ("codice_civile::2697", "tub::50"),
            "anatocismo-conti (1283 cc / 117 tub)": ("codice_civile::1283", "tub::117"),
            "prescrizione (2935 / 2946 cc)": ("codice_civile::2935", "codice_civile::2946"),
            "CONTROLLO (1957 cc / 58 tub)": ("codice_civile::1957", "tub::58"),
            "CONTROLLO (2935 cc / 650 cpc)": ("codice_civile::2935", "codice_procedura_civile::650"),
        }
        print("Stabilita' (quante partizioni su quante tengono insieme la coppia):")
        for nome, (insieme, totale) in stabilita(co, sonde).items():
            print(f"  {insieme:2d}/{totale}  {nome}")
        print("\n  I due CONTROLLO devono stare in basso: se salgono, il metodo")
        print("  sta aggregando tutto invece di distinguere.")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(uscita, f, ensure_ascii=False, indent=2)
        print(f"\nComunita' scritte in: {args.json}")


if __name__ == "__main__":
    main()
