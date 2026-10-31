"""
Costruisce il grafo delle citazioni: nodi = articoli (le fonti in
`data/raw`), archi = riferimenti incrociati estratti dal testo.

Uso: ./.venv/Scripts/python.exe src/build_graph.py --out <destinazione>

## Perche' `--out` e' obbligatorio

Fino al 2026-09-04 questo script scriveva DIRETTAMENTE su
`data/graph/grafo.gpickle`, cioe' sul grafo in carica, e la docstring lo
dichiarava come suo prodotto normale. Ma il grafo che costruisce contiene
i soli articoli: lanciarlo su un corpus maturo cancellava i 3583
provvedimenti - 155 MB - senza che niente si opponesse. Nessun candidato,
nessuno degli otto controlli di `promuovi_grafo.py`, nessun archivio.

Non e' un rischio teorico: e' esattamente il comando che serviva per
innestare quattro leggi mancanti, ed e' il primo che si sarebbe lanciato.

Ora la destinazione va detta, e lo script si RIFIUTA di sovrascrivere un
grafo che contiene provvedimenti. La via giusta resta quella di sempre:
si costruisce un candidato, e si promuove con `promuovi_grafo.py`, che
controlla e archivia il sostituito.

Produce, accanto alla destinazione:
  <out>                      - il grafo networkx degli articoli
  <out>.articoli.json        - indice leggibile (per ispezione/debug)
  <out>.stats.json           - statistiche (nodi, archi, refs non risolti)
"""

import argparse
import json
import pickle
import sys
from collections import Counter
from pathlib import Path

import networkx as nx

sys.path.insert(0, str(Path(__file__).parent))
from parser import parse_all
from references import estrai_riferimenti

ROOT = Path(__file__).parent.parent
RAW_DIR = ROOT / "data" / "raw"
GRAPH_DIR = ROOT / "data" / "graph"
#: Dove finiscono i candidati, la stessa radice che usa `aggiorna_corpus`.
CANDIDATI = GRAPH_DIR / "candidati"


class DestinazioneRifiutata(RuntimeError):
    """La destinazione contiene gia' qualcosa che questo grafo non ha."""


def controlla_destinazione(destinazione: Path) -> None:
    """Rifiuta di scrivere sopra un grafo che contiene provvedimenti.

    Il grafo degli articoli non li ha e non puo' averli: sovrascriverlo
    non e' un aggiornamento, e' una perdita. Il controllo guarda il
    CONTENUTO del file, non il suo nome, perche' e' il contenuto che
    dice cosa si sta per perdere."""
    if not destinazione.exists():
        return
    try:
        with open(destinazione, "rb") as f:
            esistente = pickle.load(f)
    except Exception:
        #: Illeggibile: non si sa cosa ci sia, e non si distrugge cio'
        #: che non si e' potuto guardare.
        raise DestinazioneRifiutata(
            "%s esiste ma non si e' potuto leggere: non lo sovrascrivo. "
            "Spostalo a mano se e' davvero da buttare." % destinazione)

    provvedimenti = sum(1 for _, d in esistente.nodes(data=True)
                        if d.get("tipo_nodo") == "provvedimento")
    if provvedimenti:
        raise DestinazioneRifiutata(
            "%s contiene %d provvedimenti, e questo script costruisce un "
            "grafo di soli articoli: sovrascriverlo li cancellerebbe. "
            "Costruisci un candidato e promuovilo con promuovi_grafo.py."
            % (destinazione, provvedimenti))


def build_lookup(articoli):
    """(codice, numero) -> node_id, con precedenza al corpo principale in caso
    di ambiguità (vedi parser.py per il perché delle sezioni duplicate)."""
    lookup: dict[tuple[str, str], str] = {}
    for a in articoli:
        key = (a.codice, a.numero)
        if key not in lookup or a.is_main_body:
            lookup[key] = a.node_id
    return lookup


def main(argv: list[str] | None = None):
    parti = argparse.ArgumentParser(description=__doc__)
    parti.add_argument("--out", type=Path, required=True,
                       help="Dove scrivere il grafo degli articoli. "
                            "Obbligatorio: vedi la docstring del modulo.")
    parti.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    args = parti.parse_args(argv)

    controlla_destinazione(args.out)
    args.out.parent.mkdir(parents=True, exist_ok=True)

    print("Parsing delle fonti in %s..." % args.raw_dir)
    articoli = parse_all(args.raw_dir)
    print(f"  {len(articoli)} articoli trovati.")

    lookup = build_lookup(articoli)

    graph = nx.MultiDiGraph()
    for a in articoli:
        graph.add_node(
            a.node_id,
            codice=a.codice,
            numero=a.numero,
            rubrica=a.rubrica,
            testo=a.testo,  # ripulito (pulisci_testo) - usato per retrieval/verifica
            testo_raw=a.testo_raw,  # originale intatto - per consultazione/vigenza
            sezione=a.sezione,
            is_main_body=a.is_main_body,
            source_url=a.source_url,
            citazione_breve=a.citazione_breve,
            abrogato=a.abrogato,
        )

    print("Estrazione riferimenti incrociati...")
    n_refs_totali = 0
    n_refs_risolti = 0
    n_refs_self = 0  # articolo che cita se stesso (es. nelle proprie note di aggiornamento) - non è un arco utile
    refs_non_risolti = Counter()  # target genuinamente fuori corpus (non nel lookup)

    for a in articoli:
        for rif in estrai_riferimenti(a.testo):
            n_refs_totali += 1
            codice_target = rif.codice_target or a.codice  # nessun qualifier -> stesso codice
            target_id = lookup.get((codice_target, rif.numero_target))
            if target_id == a.node_id:
                n_refs_self += 1
                continue
            if target_id is None:
                refs_non_risolti[(codice_target, rif.numero_target)] += 1
                continue
            n_refs_risolti += 1
            # tipo_arco='cita' uniforma questi archi con quelli aggiunti da
            # bdp_integra_grafo.py/bdp_integra_pdf.py/bankit_integra_grafo.py
            # (trovato in una revisione esterna, agosto 2026: prima 9804 archi
            # con has_seguenti ma senza tipo_arco convivevano con 741 con
            # tipo_arco='cita' ma senza has_seguenti - due popolazioni con
            # schema diverso per lo stesso concetto, entrambe rinvii
            # normativi veri, verificato). has_seguenti resta come attributo
            # aggiuntivo (True = rinvio generico "art. X e ss.", 90 casi -
            # utile per trattarli diversamente da una citazione puntuale).
            graph.add_edge(a.node_id, target_id, tipo_arco="cita", has_seguenti=rif.has_seguenti)

    print(f"  {n_refs_totali} riferimenti trovati nel testo, {n_refs_risolti} risolti in archi ({n_refs_self} auto-riferimenti scartati).")
    print(f"  {len(refs_non_risolti)} target distinti genuinamente fuori corpus (leggi speciali non scaricate, articoli abrogati citati da altri, ecc.).")

    with open(args.out, "wb") as f:
        pickle.dump(graph, f)

    articoli_index = [
        {
            "node_id": a.node_id,
            "codice": a.codice,
            "numero": a.numero,
            "rubrica": a.rubrica,
            "citazione_breve": a.citazione_breve,
            "is_main_body": a.is_main_body,
            "sezione": a.sezione,
            "source_url": a.source_url,
            "testo": a.testo,
        }
        for a in articoli
    ]
    with open(args.out.with_suffix(args.out.suffix + ".articoli.json"),
              "w", encoding="utf-8") as f:
        json.dump(articoli_index, f, ensure_ascii=False, indent=1)

    stats = {
        "n_articoli": len(articoli),
        "n_articoli_abrogati": sum(1 for a in articoli if a.abrogato),
        "n_nodi_grafo": graph.number_of_nodes(),
        "n_archi_grafo": graph.number_of_edges(),
        "n_riferimenti_estratti": n_refs_totali,
        "n_riferimenti_risolti": n_refs_risolti,
        "n_riferimenti_auto": n_refs_self,
        "n_target_non_risolti_distinti": len(refs_non_risolti),
        "top_20_non_risolti": refs_non_risolti.most_common(20),
    }
    with open(args.out.with_suffix(args.out.suffix + ".stats.json"),
              "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=1)

    print(f"\nSalvato in {args.out} (piu' .articoli.json e .stats.json)")
    print("NON e' il grafo in carica: promuovilo con promuovi_grafo.py.")


if __name__ == "__main__":
    main()
