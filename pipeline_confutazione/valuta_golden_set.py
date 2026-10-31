"""
Golden set, passo 2 - confronta un'annotazione manuale (prodotta da
prepara_annotazione.py, poi compilata a mano) con un'estrazione di Fase 1
(`{stem}_01_estrazione.json`, prodotta da --solo-fase1 o --solo-fase1
--batch) e calcola recall e precision.

Il confronto NON e' esatto: usa la stessa procedura di localizza.py
(spoglio del confezionamento + normalizzazione bilaterale a sette passi +
motore di similarita' rapidfuzz/difflib) - un'annotazione battuta a mano
non sara' mai carattere per carattere identica al testo_letterale della
pipeline, e pretenderlo darebbe un recall falsamente basso.

Definizioni:
- vero positivo: un'eccezione annotata a mano trova un'eccezione estratta
  dalla pipeline con similarita' >= soglia (default 0.80, la soglia
  "parziale" di localizza.py) - abbinamento 1:1 (bipartito greedy, non un
  'contiene' generico che farebbe corrispondere una frase annotata a piu'
  estratti).
- falso negativo: un'eccezione annotata senza corrispondenza - recall
  perso, materiale che la pipeline non ha trovato.
- falso positivo: un'eccezione estratta senza corrispondenza in
  annotazione - precision persa, materiale che la pipeline ha trovato ma
  che l'annotatore non ha considerato un'eccezione vera.

Uso:
    python valuta_golden_set.py annotazioni/ out_golden/
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

CARTELLA = Path(__file__).parent
sys.path.insert(0, str(CARTELLA))

import localizza

#: `[a-z0-9_]+` e NON `[a-z_]+`: due delle dieci famiglie dell'enum di Fase 1
#: contengono cifre - `documentazione_art_119_tub` e `saldaconto_art_50_tub`.
#: Con la classe senza cifre le righe di quelle due famiglie non venivano
#: lette, e non davano errore: sparivano. Un'annotazione che le usa perdeva
#: voci in silenzio, e il recall usciva sbagliato senza che nulla lo dicesse
#: (misurato il 2026-09-01: 7 righe su 54 perse su cinque atti).
_RIGA_ANNOTAZIONE_RE = re.compile(r'^\s*\d+\.\s*\[([a-z0-9_]+)\]\s*"(.+)"\s*$')


@dataclass
class Annotazione:
    famiglia: str
    testo: str


def _estrai_sezione_annotazione(markdown: str) -> str:
    """La sezione fra '## Annotazione' e la prossima '## '."""
    inizio = markdown.find("## Annotazione")
    if inizio == -1:
        raise ValueError("nessuna sezione '## Annotazione' trovata nel file")
    inizio = markdown.index("\n", inizio) + 1
    fine = markdown.find("\n## ", inizio)
    return markdown[inizio:fine if fine != -1 else len(markdown)]


def carica_annotazione(percorso: Path) -> list[Annotazione]:
    sezione = _estrai_sezione_annotazione(percorso.read_text(encoding="utf-8"))
    annotazioni = []
    for riga in sezione.splitlines():
        m = _RIGA_ANNOTAZIONE_RE.match(riga)
        if m is not None:
            annotazioni.append(Annotazione(famiglia=m.group(1), testo=m.group(2)))
    return annotazioni


def _normalizza_per_confronto(testo: str) -> str:
    """Stesso trattamento del lato 'modello' in localizza.py: spoglio del
    confezionamento (virgolette/ellissi ai bordi) poi normalizzazione
    bilaterale a sette passi - applicato a ENTRAMBI i lati qui (non solo
    al testo emesso dal modello come in localizza.localizza), perche' sia
    l'annotazione a mano sia il testo_letterale della pipeline possono
    portare virgolette o spazi non significativi."""
    spogliato, _ = localizza.spoglia_citazione(testo)
    normalizzato, _ = localizza.normalizza_con_mappa(spogliato)
    return normalizzato


def _similarita(a: str, b: str) -> float:
    return localizza._rapporto(_normalizza_per_confronto(a), _normalizza_per_confronto(b))


def confronta(annotate: list[Annotazione], estratte: list[dict],
              soglia: float = localizza.SOGLIA_PARZIALE) -> dict:
    """Abbinamento bipartito greedy sulla similarita' testuale - ogni
    annotazione e ogni estratto usati al massimo una volta, cosi' un
    singolo estratto lungo non puo' 'coprire' piu' annotazioni brevi."""
    candidati = []
    for i, ann in enumerate(annotate):
        for j, estr in enumerate(estratte):
            sim = _similarita(ann.testo, estr["testo_letterale"])
            if sim >= soglia:
                candidati.append((sim, i, j))
    candidati.sort(reverse=True)

    annotate_usate: set[int] = set()
    estratte_usate: set[int] = set()
    abbinamenti = []
    for sim, i, j in candidati:
        if i in annotate_usate or j in estratte_usate:
            continue
        annotate_usate.add(i)
        estratte_usate.add(j)
        abbinamenti.append((i, j, sim))

    falsi_negativi = [annotate[i] for i in range(len(annotate)) if i not in annotate_usate]
    falsi_positivi = [estratte[j] for j in range(len(estratte)) if j not in estratte_usate]

    concordi_famiglia = sum(1 for i, j, _ in abbinamenti if annotate[i].famiglia == estratte[j]["famiglia_probabile"])

    veri_positivi = len(abbinamenti)
    recall = veri_positivi / len(annotate) if annotate else None
    precision = veri_positivi / len(estratte) if estratte else None

    return {
        "n_annotate": len(annotate),
        "n_estratte": len(estratte),
        "veri_positivi": veri_positivi,
        "falsi_negativi": len(falsi_negativi),
        "falsi_positivi": len(falsi_positivi),
        "recall": recall,
        "precision": precision,
        "concordi_famiglia_su_abbinati": concordi_famiglia,
        "dettaglio_falsi_negativi": [f.testo for f in falsi_negativi],
        "dettaglio_falsi_positivi": [e["testo_letterale"] for e in falsi_positivi],
        "dettaglio_abbinamenti": [
            {"annotata": annotate[i].testo, "estratta": estratte[j]["testo_letterale"], "similarita": round(sim, 3),
             "famiglia_annotata": annotate[i].famiglia, "famiglia_estratta": estratte[j]["famiglia_probabile"]}
            for i, j, sim in abbinamenti
        ],
    }


def _fmt_pct(v: float | None) -> str:
    return f"{v:.0%}" if v is not None else "n/d"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("cartella_annotazioni", help="cartella con i *_annotazione.md compilati a mano")
    parser.add_argument("cartella_estrazioni", help="cartella con i *_01_estrazione.json (output di --solo-fase1 --batch)")
    parser.add_argument("--soglia", type=float, default=localizza.SOGLIA_PARZIALE,
                         help=f"soglia di similarita' per considerare un abbinamento valido (default {localizza.SOGLIA_PARZIALE})")
    parser.add_argument("--json", metavar="FILE", help="scrive anche i risultati grezzi in JSON")
    argomenti = parser.parse_args()

    cartella_ann = Path(argomenti.cartella_annotazioni)
    cartella_estr = Path(argomenti.cartella_estrazioni)

    file_annotazione = sorted(cartella_ann.glob("*_annotazione.md"))
    if not file_annotazione:
        raise SystemExit(f"nessun *_annotazione.md in {cartella_ann}")

    risultati_per_atto = {}
    for f in file_annotazione:
        stem = f.name.removesuffix("_annotazione.md")
        estrazione_path = cartella_estr / f"{stem}_01_estrazione.json"
        if not estrazione_path.exists():
            print(f"  ! {stem}: nessuna estrazione trovata ({estrazione_path}), saltato")
            continue

        annotate = carica_annotazione(f)
        estrazione = json.loads(estrazione_path.read_text(encoding="utf-8"))
        risultato = confronta(annotate, estrazione["eccezioni"], soglia=argomenti.soglia)
        risultati_per_atto[stem] = risultato
        print(f"{stem}: recall {_fmt_pct(risultato['recall'])} "
              f"({risultato['veri_positivi']}/{risultato['n_annotate']}), "
              f"precision {_fmt_pct(risultato['precision'])} "
              f"({risultato['veri_positivi']}/{risultato['n_estratte']})")

    if not risultati_per_atto:
        raise SystemExit("nessun confronto eseguito - nessuna coppia annotazione/estrazione trovata")

    tot_vp = sum(r["veri_positivi"] for r in risultati_per_atto.values())
    tot_ann = sum(r["n_annotate"] for r in risultati_per_atto.values())
    tot_estr = sum(r["n_estratte"] for r in risultati_per_atto.values())
    print(f"\nTotale: recall {_fmt_pct(tot_vp / tot_ann if tot_ann else None)} ({tot_vp}/{tot_ann}), "
          f"precision {_fmt_pct(tot_vp / tot_estr if tot_estr else None)} ({tot_vp}/{tot_estr})")

    if argomenti.json:
        Path(argomenti.json).write_text(json.dumps(risultati_per_atto, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Dettaglio in {argomenti.json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
