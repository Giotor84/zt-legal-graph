# -*- coding: utf-8 -*-
"""Due annotazioni degli STESSI provvedimenti, a confronto.

## La domanda

Il golden set del 2026-08-30 e' stato scritto da un modello che leggeva i
documenti INTERI - lo stesso metodo della pipeline che deve misurare. Il
sospetto dichiarato in STATO_PROGETTO §7.1 e' che i due condividano i punti
ciechi: un'eccezione difficile da vedere resta invisibile a entrambi, il
confronto la conta come "non c'era", e il recall esce buono senza motivo.

`golden_esaustivo.py` produce un'annotazione con un metodo DIVERSO - ogni
segmento guardato esattamente una volta, dove saltare non e' possibile. Se
il sospetto e' fondato, la spazzata deve trovare eccezioni che la lettura
del documento intero non aveva.

**Quel numero e' la misura del punto cieco.** Non e' un giudizio su quale
delle due annotazioni sia migliore: e' la quantita' di materiale su cui
finora non stavamo misurando nulla.

Il confronto usa l'appaiamento di `valuta_golden_eccezioni.appaia` - stessa
regola, sovrapposizione di intervalli, uno-a-uno - perche' un criterio
diverso renderebbe questo numero non confrontabile con i recall gia'
misurati.

Sola lettura. Nessun modello.

Uso:
    python pipeline_confutazione/confronta_golden.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CARTELLA = Path(__file__).parent
sys.path.insert(0, str(CARTELLA))

import valuta_golden_eccezioni as vge  # noqa: E402

GRAFO = CARTELLA.parent / "data" / "graph" / "grafo.gpickle"
DOCUMENTO_LETTURA_INTERA = CARTELLA / "golden_eccezioni_2026-08-30.json"
DOCUMENTO_SPAZZATA = CARTELLA / "golden_esaustivo.json"


def voci_della_spazzata(documento: dict) -> dict[str, list[dict]]:
    """Le eccezioni della spazzata, per provvedimento. Gli offset sono gia'
    sul testo integrale: la spazzata ancora dentro il segmento e ci somma
    l'offset del segmento, che a sua volta e' sul testo integrale."""
    per_nodo: dict[str, list[dict]] = {}
    for doc in documento.get("documenti", []):
        per_nodo[doc["node_id"]] = list(doc.get("eccezioni", []))
    return per_nodo


def voci_della_lettura_intera(documento: dict, motivazioni: dict[str, str],
                              basi: dict[str, int]) -> dict[str, list[dict]]:
    """Le voci del golden precedente, convertite sul TESTO INTEGRALE.

    Le due annotazioni misurano in sistemi di coordinate diversi (la vecchia
    sulla motivazione, la spazzata sul testo integrale). Confrontarle senza
    convertire darebbe zero sovrapposizioni ovunque: non una misura bassa,
    una misura sbagliata - lo stesso errore gia' documentato in
    `valuta_golden_eccezioni.carica_offset_base`."""
    per_nodo: dict[str, list[dict]] = {}
    for voce in vge.ancora(documento, motivazioni):
        base = basi.get(voce["node_id"], 0)
        per_nodo.setdefault(voce["node_id"], []).append({
            **voce,
            "inizio": voce["inizio"] + base,
            "fine": voce["fine"] + base,
        })
    return per_nodo


def confronta(intera: dict[str, list[dict]], spazzata: dict[str, list[dict]]
              ) -> dict:
    """Per ogni provvedimento comune: quante in comune, quante solo per l'una,
    quante solo per l'altra."""
    comuni = sorted(set(intera) & set(spazzata))
    righe, totali = [], {"comuni": 0, "solo_intera": 0, "solo_spazzata": 0}
    solo_spazzata_elenco = []
    for node_id in comuni:
        appaiate, mancate, spurie = vge.appaia(intera[node_id], spazzata[node_id])
        righe.append({
            "node_id": node_id,
            "lettura_intera": len(intera[node_id]),
            "spazzata": len(spazzata[node_id]),
            "comuni": len(appaiate),
            "solo_intera": len(mancate),
            "solo_spazzata": len(spurie),
        })
        totali["comuni"] += len(appaiate)
        totali["solo_intera"] += len(mancate)
        totali["solo_spazzata"] += len(spurie)
        for voce in spurie:
            solo_spazzata_elenco.append({"node_id": node_id, **voce})
    return {
        "provvedimenti_confrontati": len(comuni),
        "solo_nella_lettura_intera": sorted(set(intera) - set(spazzata)),
        "solo_nella_spazzata": sorted(set(spazzata) - set(intera)),
        "totali": totali,
        "per_provvedimento": righe,
        "trovate_solo_dalla_spazzata": solo_spazzata_elenco,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--grafo", type=Path, default=GRAFO)
    parser.add_argument("--lettura-intera", type=Path, default=DOCUMENTO_LETTURA_INTERA)
    parser.add_argument("--spazzata", type=Path, default=DOCUMENTO_SPAZZATA)
    parser.add_argument("--esempi", type=int, default=8,
                        help="quante eccezioni trovate SOLO dalla spazzata stampare")
    argomenti = parser.parse_args()

    if not argomenti.spazzata.is_file():
        print("manca %s: la spazzata non e' stata fatta" % argomenti.spazzata)
        return 2

    motivazioni = vge.carica_motivazioni(argomenti.grafo)
    basi = vge.carica_offset_base(argomenti.grafo)
    documento_intera = json.loads(argomenti.lettura_intera.read_text(encoding="utf-8"))
    documento_spazzata = json.loads(argomenti.spazzata.read_text(encoding="utf-8"))

    esito = confronta(
        voci_della_lettura_intera(documento_intera, motivazioni, basi),
        voci_della_spazzata(documento_spazzata))

    totali = esito["totali"]
    somma = sum(totali.values()) or 1
    print("provvedimenti confrontati: %d" % esito["provvedimenti_confrontati"])
    print()
    print("  in comune                    %4d  %5.1f%%" % (totali["comuni"], 100 * totali["comuni"] / somma))
    print("  solo lettura del documento   %4d  %5.1f%%" % (totali["solo_intera"], 100 * totali["solo_intera"] / somma))
    print("  SOLO SPAZZATA ESAUSTIVA      %4d  %5.1f%%" % (totali["solo_spazzata"], 100 * totali["solo_spazzata"] / somma))
    print()
    print("Le 'solo spazzata' sono la misura del punto cieco condiviso: eccezioni")
    print("su cui il golden set precedente non faceva misurare niente.")

    if esito["trovate_solo_dalla_spazzata"]:
        print("\nesempi trovati solo dalla spazzata:")
        for voce in esito["trovate_solo_dalla_spazzata"][:argomenti.esempi]:
            testo = " ".join((voce.get("verbatim") or "").split())
            print("  [%s] %s" % (voce.get("esito"), testo[:150]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
