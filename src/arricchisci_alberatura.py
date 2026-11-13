"""Scrive l'albero del codice sui nodi Articolo del grafo.

Aggiunge a ogni articolo collocabile un campo `alberatura`:

    {"libro": ..., "titolo": ..., "capo": ..., "sezione": ...,
     "fonte": "wikisource" | "adiacenza_numerica",
     "dedotta_da": "art. 171"}       # solo se fonte == adiacenza_numerica

Gli articoli che non si collocano NON ricevono il campo: l'assenza e' piu'
onesta di un valore nullo, e chi legge il grafo deve poter distinguere "non
collocato" da "collocato in nessun capo".

## Perche' un campo nuovo e non `sezione`

`sezione` esiste gia' sui nodi Articolo e significa un'altra cosa: e' il
titolo della sezione `## ` del markdown di Normattiva, che `src/parser.py`
usa per costruire il node_id degli articoli fuori dal corpo principale
(preleggi, disposizioni di attuazione). Sovrascriverlo cambierebbe l'identita'
dei nodi. `alberatura.sezione` e' un'altra cosa e sta in un'altra chiave.

## Cosa NON fa

Non tocca `testo`, `testo_raw`, `rubrica`, `numero`, `codice`,
`is_main_body`, `abrogato`, `citazione_breve` ne' alcun arco. Il controllo 4
di `promuovi_grafo.py` (testo di legge identico byte per byte) resta verde
per costruzione, ed e' la verifica che questo modulo non ha fatto danni.

Per ora copre il solo **codice di procedura civile**: e' quello da cui
dipende il tipo di atto, ed e' quello per cui le sorgenti sono state
scaricate. Gli altri codici si aggiungono mettendo il loro wikitext in
`data/raw/wikisource/` ed estendendo `alberatura_codici.LIBRI_CPC`.

Sola lettura sul grafo di partenza: scrive sempre un file diverso.

Uso:
    python src/arricchisci_alberatura.py --grafo-input IN --grafo-output OUT
"""

from __future__ import annotations

import argparse
import pickle
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from alberatura_codici import (FONTE_DEDOTTA, FONTE_LETTA, carica_albero_cc,
                               carica_albero_cpc, colloca)

ROOT = Path(__file__).parent.parent
GRAPH_DIR = ROOT / "data" / "graph"
GRAFO_INPUT = GRAPH_DIR / "grafo_2026-08-26_bdp816_citazioni.gpickle"
GRAFO_OUTPUT = GRAPH_DIR / "grafo_2026-08-26_bdp816_citazioni_alberatura.gpickle"

CODICE = "codice_procedura_civile"


def arricchisci(grafo, albero: dict[str, dict[str, str]], codice: str = CODICE) -> dict:
    """Scrive `alberatura` sui nodi del codice indicato. Ritorna il riepilogo."""
    nodi = {node_id: dati for node_id, dati in grafo.nodes(data=True)
            if dati.get("codice") == codice}
    numeri = {dati["numero"] for dati in nodi.values()}
    collocati, non_collocati = colloca(numeri, albero)

    for node_id, dati in nodi.items():
        posizione = collocati.get(dati["numero"])
        if posizione is not None:
            grafo.nodes[node_id]["alberatura"] = dict(posizione)

    fonti = Counter(p["fonte"] for p in collocati.values())
    return {
        "codice": codice,
        "articoli_nel_grafo": len(numeri),
        "collocati": len(collocati),
        "da_wikisource": fonti[FONTE_LETTA],
        "per_adiacenza": fonti[FONTE_DEDOTTA],
        "non_collocati": sorted(non_collocati, key=lambda x: (int(x.split("-")[0]), x)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--grafo-input", type=Path, default=GRAFO_INPUT,
                        help=f"Grafo di partenza, SOLA LETTURA (default: {GRAFO_INPUT})")
    parser.add_argument("--grafo-output", type=Path, default=GRAFO_OUTPUT)
    parser.add_argument("--sorgenti", type=Path, default=None,
                        help="Cartella del wikitext (default: data/raw/wikisource/)")
    args = parser.parse_args()

    if args.grafo_output.resolve() == args.grafo_input.resolve():
        raise SystemExit(
            f"--grafo-output coincide con --grafo-input ({args.grafo_input}): "
            "questo script non sovrascrive mai il grafo di partenza."
        )

    print(f"Carico (sola lettura): {args.grafo_input}")
    with open(args.grafo_input, "rb") as f:
        grafo = pickle.load(f)

    # Un lettore per codice: le fonti hanno forme diverse e non si
    # generalizzano a mano (vedi alberatura_codici). Il c.p.c. sta in
    # quattro pagine per libro, il c.c. in 53 sottopagine per titolo.
    caricatori = {"codice_procedura_civile": carica_albero_cpc,
                  "codice_civile": carica_albero_cc}

    for codice, carica in caricatori.items():
        albero = carica(args.sorgenti) if args.sorgenti else carica()
        print(f"albero {codice}: {len(albero)} articoli nelle sorgenti")

        esito = arricchisci(grafo, albero, codice)

        print(f"--- {esito['codice']} ---")
        print(f"  articoli nel grafo : {esito['articoli_nel_grafo']}")
        print(f"  collocati          : {esito['collocati']} "
              f"({100 * esito['collocati'] // esito['articoli_nel_grafo']}%)")
        print(f"    da wikisource    : {esito['da_wikisource']}")
        print(f"    per adiacenza    : {esito['per_adiacenza']}  (dedotti, marcati sul nodo)")
        print(f"  NON collocati      : {len(esito['non_collocati'])}")
        print()

    args.grafo_output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.grafo_output, "wb") as f:
        pickle.dump(grafo, f)
    print(f"\n  Salvato in:   {args.grafo_output}")
    print(f"  Non toccato:  {args.grafo_input}")


if __name__ == "__main__":
    main()
