"""Golden set delle eccezioni nelle motivazioni: verifica e punteggio.

Passo 1 (`--verifica`): controlla che il file del golden set sia ANCORABILE.
Per ogni voce cerca il `verbatim` nella motivazione del provvedimento e
pretende di trovarlo ESATTAMENTE una volta. Se una voce non si trova, o si
trova due volte, il file e' rifiutato: gli offset non sono un campo che si
scrive, sono un calcolo (regola 4 di CLAUDE.md - l'ancoraggio lo fa Python,
mai chi ha scritto il testo). Un golden set che non passa questo controllo
non e' un riferimento, e' un elenco di opinioni.

Passo 2 (senza `--verifica`): confronta il golden set con una corsa di
`estrai_eccezioni_corpus.py` e stampa recall, precisione, accuratezza della
parte e dell'esito, piu' l'elenco nominativo delle eccezioni MANCATE - che
e' la parte che serve davvero a decidere cosa correggere.

## Come si decide che due eccezioni sono la stessa

Una voce del golden set e una coppia estratta corrispondono se i loro
intervalli di caratteri sulla motivazione si SOVRAPPONGONO. Non si usa la
somiglianza fra i testi: il golden set cita una frase breve e mirata, la
pipeline estrae il periodo intero che la contiene, quindi due testi che
descrivono la stessa eccezione possono somigliarsi poco pur riferendosi allo
stesso punto del documento. La posizione e' il criterio piu' severo e piu'
semplice da controllare a mano.

Ogni voce del golden set puo' essere appaiata a una sola coppia estratta e
viceversa (appaiamento uno-a-uno, il primo per posizione): due coppie
estratte che coprono la stessa eccezione contano come una trovata e una
falsa, non come due trovate.

## Cosa misura e cosa non misura

Misura: quante eccezioni annotate la pipeline trova (recall), quante di
quelle che produce corrispondono a un'eccezione annotata (precisione), e
se, quando le trova, ne indovina la parte e l'esito.

NON misura se il golden set ha ragione. Vedi
`golden_eccezioni_2026-08-30.json`, campo `avvertenza_sulla_provenienza`:
quel file e' stato scritto da un modello, non da un giurista, e la misura
eredita quel limite.

Uso:
    python pipeline_confutazione/valuta_golden_eccezioni.py --verifica
    python pipeline_confutazione/valuta_golden_eccezioni.py --estrazione lavoro/X/parziale.jsonl
"""

from __future__ import annotations

import argparse
import json
import pickle
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable

RADICE = Path(__file__).parent.parent
GOLDEN_DEFAULT = Path(__file__).parent / "golden_eccezioni_2026-08-30.json"
GRAFO_DEFAULT = RADICE / "data" / "graph" / "grafo_2026-08-26_bdp816_citazioni.gpickle"

#: Ruoli del golden set ricondotti ai due lati sostanziali della lite, per
#: poter confrontare l'attribuzione della parte con quella della pipeline
#: senza pretendere la stessa parola. "opponente" e "appellato" stanno dalla
#: stessa parte in un'opposizione a decreto ingiuntivo portata in appello
#: dal creditore: e' il LATO che conta, non l'etichetta processuale.
_LATO = {
    "opponente": "debitore", "opponenti": "debitore", "appellato": "debitore",
    "appellata": "debitore", "attore": "debitore", "attori": "debitore",
    "opposta": "creditore", "opposto": "creditore", "appellante": "creditore",
    "convenuta": "creditore", "convenuto": "creditore",
}

_PAROLE_DEBITORE = re.compile(
    r"opponent|appellat|attric|attor|ricorrent|debitor|fideiussor|garant|client|correntist", re.I)
_PAROLE_CREDITORE = re.compile(
    r"opposta|opposto|appellant|convenut|resistent|banca|istituto|cessionar|creditric|creditor|"
    r"CP_\d+|Controparte", re.I)


class GoldenNonAncorabile(Exception):
    """Una voce non si trova, o si trova piu' volte, nella motivazione."""


def carica_motivazioni(grafo_path: Path) -> dict[str, str]:
    with open(grafo_path, "rb") as f:
        grafo = pickle.load(f)
    return {
        node_id: dati["motivazione"]
        for node_id, dati in grafo.nodes(data=True)
        if dati.get("tipo_nodo") == "provvedimento" and dati.get("motivazione")
    }


def carica_offset_base(grafo_path: Path) -> dict[str, int]:
    """Posizione della motivazione DENTRO il testo_integrale, per provvedimento.

    Serve perche' le due parti misurano in sistemi di coordinate diversi:
    il golden set ancora sulla MOTIVAZIONE (e' il testo che l'annotatore ha
    letto), mentre estrazione_eccezioni ancora sul TESTO_INTEGRALE
    (`offset_base + ancora["inizio"]`, perche' `eccezione_verbatim` e' una
    fetta del testo integrale). Confrontare i due senza convertire dava un
    recall dello 0.10 su documenti in cui la pipeline aveva chiaramente
    trovato le stesse eccezioni: non una misura bassa, una misura sbagliata."""
    with open(grafo_path, "rb") as f:
        grafo = pickle.load(f)
    basi = {}
    for node_id, dati in grafo.nodes(data=True):
        if dati.get("tipo_nodo") != "provvedimento" or not dati.get("motivazione"):
            continue
        integrale = dati.get("testo_integrale") or ""
        posizione = integrale.find(dati["motivazione"])
        # find() e non index(): se la motivazione non fosse una fetta esatta
        # del testo integrale, l'unica risposta onesta e' 0 (nessuna
        # conversione) invece di un'eccezione che ferma tutta la valutazione.
        basi[node_id] = posizione if posizione >= 0 else 0
    return basi


def ancora(golden: dict, motivazioni: dict[str, str]) -> list[dict]:
    """Calcola gli offset di ogni voce. Solleva GoldenNonAncorabile al primo
    verbatim che non si trova esattamente una volta - non salta la voce e non
    sceglie la prima occorrenza: un ancoraggio ambiguo e' un difetto del
    golden set, e va corretto li', non aggirato qui."""
    voci = []
    for doc in golden["documenti"]:
        node_id = doc["node_id"]
        if node_id not in motivazioni:
            raise GoldenNonAncorabile(f"doc {doc['indice']}: {node_id} non ha motivazione nel grafo")
        testo = motivazioni[node_id]
        for n, ecc in enumerate(doc["eccezioni"], 1):
            occorrenze = [m.start() for m in re.finditer(re.escape(ecc["verbatim"]), testo)]
            if len(occorrenze) != 1:
                raise GoldenNonAncorabile(
                    f"doc {doc['indice']} voce {n}: il verbatim si trova {len(occorrenze)} volte "
                    f"(atteso 1) - {ecc['verbatim']!r}"
                )
            inizio = occorrenze[0]
            voci.append({
                "node_id": node_id,
                "indice_doc": doc["indice"],
                "ufficio": doc["ufficio"],
                "area": doc["area"],
                "n": n,
                "parte": ecc["parte"],
                "lato": _LATO.get(ecc["parte"], "ignoto"),
                "esito": ecc["esito"],
                "sintesi": ecc["sintesi"],
                "verbatim": ecc["verbatim"],
                "inizio": inizio,
                "fine": inizio + len(ecc["verbatim"]),
            })
    return voci


def _lato_di(testo_parte: str | None) -> str:
    """Il lato sostanziale dedotto da come la pipeline ha nominato la parte.
    Deterministico: nessun modello, solo le parole del testo."""
    if not testo_parte:
        return "ignoto"
    debitore = bool(_PAROLE_DEBITORE.search(testo_parte))
    creditore = bool(_PAROLE_CREDITORE.search(testo_parte))
    if debitore == creditore:
        return "ignoto"
    return "debitore" if debitore else "creditore"


def _si_sovrappongono(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def appaia(voci: Iterable[dict], estratte: list[dict]) -> tuple[list, list, list]:
    """Appaiamento uno-a-uno per sovrapposizione di intervallo, in ordine di
    posizione. Ritorna (coppie appaiate, golden non trovate, estratte spurie)."""
    libere = sorted(
        [e for e in estratte if e.get("offset_inizio") is not None],
        key=lambda e: e["offset_inizio"],
    )
    usate: set[int] = set()
    appaiate, mancate = [], []
    for voce in sorted(voci, key=lambda v: v["inizio"]):
        trovata = None
        for i, e in enumerate(libere):
            if i in usate:
                continue
            if _si_sovrappongono((voce["inizio"], voce["fine"]),
                                 (e["offset_inizio"], e["offset_fine"])):
                trovata = i
                break
        if trovata is None:
            mancate.append(voce)
        else:
            usate.add(trovata)
            appaiate.append((voce, libere[trovata]))
    spurie = [e for i, e in enumerate(libere) if i not in usate]
    return appaiate, mancate, spurie


def valuta(golden: dict, motivazioni: dict[str, str], estrazione: list[dict],
           offset_base: dict[str, int] | None = None) -> dict:
    """`offset_base` porta gli offset dell'estrazione nel sistema di
    coordinate del golden set (vedi carica_offset_base). Senza, il confronto
    e' fra due righelli diversi."""
    voci = ancora(golden, motivazioni)
    basi = offset_base or {}
    per_nodo: dict[str, list[dict]] = {}
    for r in estrazione:
        base = basi.get(r["node_id"], 0)
        for c in r["coppie"]:
            if c.get("offset_inizio") is None:
                per_nodo.setdefault(r["node_id"], []).append(c)
                continue
            per_nodo.setdefault(r["node_id"], []).append(
                {**c, "offset_inizio": c["offset_inizio"] - base,
                 "offset_fine": c["offset_fine"] - base})

    tot_app = tot_mancate = tot_spurie = 0
    lato_ok = esito_ok = 0
    mancate_tutte, per_documento = [], []
    esiti_confusi = Counter()

    for doc in golden["documenti"]:
        vd = [v for v in voci if v["node_id"] == doc["node_id"]]
        ed = per_nodo.get(doc["node_id"])
        if ed is None:
            per_documento.append({"indice": doc["indice"], "ufficio": doc["ufficio"],
                                  "golden": len(vd), "stato": "non processato dalla corsa"})
            continue
        app, mancate, spurie = appaia(vd, ed)
        tot_app += len(app); tot_mancate += len(mancate); tot_spurie += len(spurie)
        for voce, e in app:
            if _lato_di(e.get("parte_che_la_solleva")) == voce["lato"] != "ignoto":
                lato_ok += 1
            if e.get("esito") == voce["esito"]:
                esito_ok += 1
            else:
                esiti_confusi[(voce["esito"], e.get("esito"))] += 1
        mancate_tutte += mancate
        per_documento.append({"indice": doc["indice"], "ufficio": doc["ufficio"], "area": doc["area"],
                              "golden": len(vd), "estratte": len(ed),
                              "trovate": len(app), "mancate": len(mancate), "spurie": len(spurie)})

    golden_valutate = tot_app + tot_mancate
    prodotte = tot_app + tot_spurie
    return {
        "golden_totali": len(voci),
        "golden_valutate": golden_valutate,
        "trovate": tot_app,
        "mancate": tot_mancate,
        "spurie": tot_spurie,
        "recall": tot_app / golden_valutate if golden_valutate else 0.0,
        "precisione": tot_app / prodotte if prodotte else 0.0,
        "lato_corretto_su_trovate": lato_ok / tot_app if tot_app else 0.0,
        "esito_corretto_su_trovate": esito_ok / tot_app if tot_app else 0.0,
        "esiti_confusi": {f"{a} -> {b}": n for (a, b), n in esiti_confusi.most_common()},
        "per_documento": per_documento,
        "mancate_elenco": mancate_tutte,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--golden", type=Path, default=GOLDEN_DEFAULT)
    parser.add_argument("--grafo", type=Path, default=GRAFO_DEFAULT)
    parser.add_argument("--estrazione", type=Path, default=None,
                        help="parziale.jsonl di una corsa di estrai_eccezioni_corpus.py")
    parser.add_argument("--verifica", action="store_true",
                        help="Solo il controllo di ancorabilita', nessun confronto")
    args = parser.parse_args()

    golden = json.loads(args.golden.read_text(encoding="utf-8"))
    motivazioni = carica_motivazioni(args.grafo)
    offset_base = carica_offset_base(args.grafo)

    try:
        voci = ancora(golden, motivazioni)
    except GoldenNonAncorabile as e:
        print(f"GOLDEN SET RIFIUTATO: {e}")
        return 1

    print(f"golden set: {len(golden['documenti'])} documenti, {len(voci)} eccezioni")
    print(f"ancoraggio: {len(voci)}/{len(voci)} verbatim trovati esattamente una volta")
    print("distribuzione degli esiti:", dict(Counter(v["esito"] for v in voci)))
    print("distribuzione dei lati:  ", dict(Counter(v["lato"] for v in voci)))
    print("distribuzione delle aree:", dict(Counter(v["area"] for v in voci)))

    if args.verifica or args.estrazione is None:
        if args.estrazione is None and not args.verifica:
            print("\n(nessuna --estrazione indicata: eseguita la sola verifica)")
        return 0

    estrazione = [json.loads(r) for r in args.estrazione.read_text(encoding="utf-8").splitlines() if r.strip()]
    esito = valuta(golden, motivazioni, estrazione, offset_base)

    print(f"\n--- Confronto con {args.estrazione} ---")
    print(f"  documenti del golden presenti nella corsa: "
          f"{sum(1 for d in esito['per_documento'] if 'stato' not in d)}/{len(esito['per_documento'])}")
    print(f"  eccezioni del golden valutate: {esito['golden_valutate']}")
    print(f"  trovate {esito['trovate']}   mancate {esito['mancate']}   spurie {esito['spurie']}")
    print(f"  RECALL      {esito['recall']:.2f}")
    print(f"  PRECISIONE  {esito['precisione']:.2f}")
    print(f"  lato della parte corretto (sulle trovate)  {esito['lato_corretto_su_trovate']:.2f}")
    print(f"  esito corretto (sulle trovate)             {esito['esito_corretto_su_trovate']:.2f}")
    if esito["esiti_confusi"]:
        print("  esiti sbagliati (golden -> pipeline):", esito["esiti_confusi"])

    print("\n  per documento:")
    for d in esito["per_documento"]:
        if "stato" in d:
            print(f"    {d['indice']:2d}  {d['ufficio']:28s} {d['stato']}")
        else:
            print(f"    {d['indice']:2d}  {d['ufficio']:28s} golden {d['golden']:2d}  "
                  f"trovate {d['trovate']:2d}  mancate {d['mancate']:2d}  spurie {d['spurie']:2d}")

    if esito["mancate_elenco"]:
        print(f"\n  LE {len(esito['mancate_elenco'])} MANCATE - e' qui che si guarda per capire cosa correggere:")
        for v in esito["mancate_elenco"]:
            print(f"    [doc {v['indice_doc']:2d} {v['area']:20s}] ({v['parte']}, {v['esito']}) {v['sintesi']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
