# -*- coding: utf-8 -*-
"""Fase 1 e la spazzata sullo stesso atto, senza che nessuna delle due
faccia da riferimento all'altra.

## Il problema che questo modulo evita

Sui cinque atti del golden set il confronto e' CIRCOLARE: la spazzata *e'*
il riferimento, quindi ha per costruzione il 100% di recall contro se'
stessa e Fase 1 non puo' che uscirne male. Un numero ottenuto cosi' non
dice quale metodo sia migliore, dice solo quale dei due e' stato eletto
metro.

Qui si lavora su atti che **nessuno dei due ha mai visto**, e si misurano
solo grandezze che non presuppongono chi abbia ragione:

- **quante** ne trova ciascuno, e quante in comune (con l'appaiamento di
  `valuta_golden_set`, lo stesso gia' usato altrove: un criterio nuovo
  renderebbe questi numeri non paragonabili ai precedenti);
- **la citabilita'** di cio' che ciascuno trova da solo, giudicata dallo
  STESSO controllo (`citabilita.py`) per entrambi. E' l'unico asse
  disponibile che non favorisce nessuno dei due: il controllo non sa da
  quale metodo venga la fetta che sta guardando.

Cio' che resta indecidibile - se una voce trovata da uno solo sia
un'eccezione vera - non viene deciso qui. Viene messo da parte in un
campione cieco per il giudizio umano, che e' l'unico che puo' scioglierlo.

Uso:
    python pipeline_confutazione/confronta_metodi.py \\
        --fase1 lavoro/confronto/fase1 --spazzata lavoro/confronto/spazzata
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

CARTELLA = Path(__file__).parent
if str(CARTELLA) not in sys.path:
    sys.path.insert(0, str(CARTELLA))

import citabilita  # noqa: E402
import valuta_golden_set as vgs  # noqa: E402


def voci_di_fase1(cartella: Path) -> dict[str, list[str]]:
    fuori: dict[str, list[str]] = {}
    for percorso in sorted(cartella.glob("*_01_estrazione.json")):
        stem = percorso.name[: -len("_01_estrazione.json")]
        dati = json.loads(percorso.read_text(encoding="utf-8"))
        #: `testo_verbatim` e non `testo_letterale`: il contratto dichiara
        #: il secondo NON citabile dalla 1.25 - e' cio' che il MODELLO dice
        #: di aver citato, e porta i suoi caratteri di scaffolding. Misurato
        #: il 2026-09-01 su un atto: `testo_verbatim` combacia con la fetta
        #: agli offset 28 volte su 28, `testo_letterale` sbaglia su 11.
        #: Leggere quello qui rendeva il confronto ASIMMETRICO - il testo
        #: dichiarato dal modello da un lato, quello ancorato dall'altro - e
        #: la citabilita' e' proprio la grandezza che ne risente.
        fuori[stem] = [e.get("testo_verbatim") or e.get("testo_letterale") or ""
                       for e in (dati.get("eccezioni") or [])]
    return fuori


def voci_della_spazzata(cartella: Path) -> dict[str, list[str]]:
    fuori: dict[str, list[str]] = {}
    for percorso in sorted(cartella.glob("*_annotazione.md")):
        stem = percorso.name[: -len("_annotazione.md")]
        fuori[stem] = [a.testo for a in vgs.carica_annotazione(percorso)]
    return fuori


def appaia(a: list[str], b: list[str]) -> tuple[int, list[str], list[str]]:
    """In comune, solo di a, solo di b - con lo stesso criterio di
    `valuta_golden_set.confronta` (similarita' >= soglia, uno a uno)."""
    #: `famiglia_probabile` c'e' perche' `vgs.confronta` conta anche
    #: l'accordo sulle famiglie. Qui non interessa - il confronto e' sul
    #: TESTO - ma il campo deve esistere, e va lasciato diverso dalla
    #: famiglia annotata: metterlo uguale gonfierebbe una statistica che
    #: questo modulo non usa e che qualcuno potrebbe leggere per buona.
    annotate = [vgs.Annotazione(famiglia="", testo=t) for t in a if t]
    estratte = [{"testo_letterale": t, "famiglia_probabile": "non_confrontata"}
                for t in b if t]
    esito = vgs.confronta(annotate, estratte)
    soli_a = [v.testo if hasattr(v, "testo") else str(v)
              for v in esito["dettaglio_falsi_negativi"]]
    soli_b = [(v.get("testo_letterale") if isinstance(v, dict) else str(v)) or ""
              for v in esito["dettaglio_falsi_positivi"]]
    return esito["veri_positivi"], soli_a, soli_b


def profilo_citabilita(base_url: str, fette: list[str], *, seed: int,
                       temperature: float) -> list[str]:
    """Una categoria per fetta, NELLO STESSO ORDINE.

    Ritorna l'elenco e non il conteggio perche' il conteggio si fa da qui
    in un passaggio, mentre dal conteggio non si torna piu' indietro: chi
    volesse poi rifare il confronto su un sottoinsieme degli atti - cosa
    che e' servita subito, il giorno stesso, per togliere un atto che Fase 1
    non era riuscita a leggere - dovrebbe rispendere una chiamata al
    modello per ogni fetta."""
    categorie: list[str] = []
    for fetta in fette:
        if not fetta or len(fetta.strip()) < 12:
            categorie.append("troppo_corta_per_giudicare")
            continue
        categorie.append(citabilita.valuta(base_url, fetta, seed=seed,
                                           temperature=temperature)["categoria"])
    return categorie


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fase1", type=Path, required=True)
    parser.add_argument("--spazzata", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--uscita", type=Path,
                        default=Path("lavoro/confronto/esito.json"))
    parser.add_argument("--seme", type=int, default=1234)
    parser.add_argument("--temperature", type=float, default=0.0)
    argomenti = parser.parse_args()

    f1 = voci_di_fase1(argomenti.fase1)
    sp = voci_della_spazzata(argomenti.spazzata)
    comuni = sorted(set(f1) & set(sp))
    if not comuni:
        print("nessun atto in comune fra le due cartelle")
        return 2

    righe, soli_f1, soli_sp = [], [], []
    tot = Counter()
    for stem in comuni:
        insieme, solo_s, solo_f = appaia(sp[stem], f1[stem])
        righe.append({
            "atto": stem,
            "spazzata": len(sp[stem]),
            "fase1": len(f1[stem]),
            "in_comune": insieme,
            "solo_spazzata": len(solo_s),
            "solo_fase1": len(solo_f),
        })
        tot["spazzata"] += len(sp[stem])
        tot["fase1"] += len(f1[stem])
        tot["in_comune"] += insieme
        soli_sp += [{"atto": stem, "testo": t} for t in solo_s]
        soli_f1 += [{"atto": stem, "testo": t} for t in solo_f]

    print("%d atti mai visti da nessuno dei due metodi\n" % len(comuni))
    print("%-46s %6s %6s %6s" % ("atto", "spazz", "fase1", "comuni"))
    for r in righe:
        print("%-46s %6d %6d %6d"
              % (r["atto"][:46], r["spazzata"], r["fase1"], r["in_comune"]))
    print("%-46s %6d %6d %6d"
          % ("TOTALE", tot["spazzata"], tot["fase1"], tot["in_comune"]))
    print()
    print("solo la spazzata: %d    solo Fase 1: %d" % (len(soli_sp), len(soli_f1)))

    print("\ncitabilita' di cio' che ciascuno trova DA SOLO")
    print("(stesso controllo per entrambi: non sa da dove venga la fetta)")
    profili = {}
    for nome, voci in (("solo la spazzata", soli_sp), ("solo Fase 1", soli_f1)):
        categorie = profilo_citabilita(
            argomenti.base_url, [v["testo"] for v in voci],
            seed=argomenti.seme, temperature=argomenti.temperature)
        #: La categoria si attacca alla voce, non solo al totale: senza
        #: questo il conteggio e' l'unica cosa che resta e un confronto su
        #: un sottoinsieme degli atti costa un'altra chiamata per fetta.
        for voce, categoria in zip(voci, categorie):
            voce["citabilita"] = categoria
        conto = Counter(categorie)
        profili[nome] = dict(conto)
        totale = sum(conto.values()) or 1
        print("  %s (%d voci)" % (nome, totale))
        for categoria, n in conto.most_common():
            print("      %-30s %3d  %4.1f%%" % (categoria, n, 100 * n / totale))

    argomenti.uscita.parent.mkdir(parents=True, exist_ok=True)
    argomenti.uscita.write_text(json.dumps({
        "atti": comuni,
        "per_atto": righe,
        "totali": dict(tot),
        "solo_spazzata": soli_sp,
        "solo_fase1": soli_f1,
        "citabilita_di_cio_che_trova_da_solo": profili,
        "non_deciso_qui": (
            "Se una voce trovata da UNO SOLO dei due sia un'eccezione vera "
            "non e' deciso qui: nessuno dei due metodi puo' arbitrare l'altro "
            "senza diventare il metro. Le voci sono qui perche' finiscano in "
            "un campione cieco per il giudizio umano."),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nscritto in %s" % argomenti.uscita)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
