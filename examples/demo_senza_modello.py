"""Demo in due secondi, senza modello, senza GPU e senza grafo.

Mostra le due garanzie che non dipendono dal modello:
1. ogni citazione proposta dal modello viene ancorata al testo dell'atto con offset calcolati da Python
   (`localizza`): esatta, normalizzata, parziale o rifiutata, mai il primo match d'ufficio;
2. la regola delle anomalie contabili sa se l'avversario ha prodotto cifre (`conteggi_di_parte`),
   per non scrivere in un atto depositato che non le ha prodotte.

L'atto e le "risposte del modello" sono inventati.

    python examples/demo_senza_modello.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline_confutazione"))

import conteggi_di_parte as cdp  # noqa: E402
from localizza import localizza  # noqa: E402
from segmenta_atto import pulisci_numeri_pagina, segmenta_con_span  # noqa: E402

ATTO = """ATTO DI CITAZIONE IN OPPOSIZIONE A DECRETO INGIUNTIVO

1. Sulla carenza di legittimazione attiva
La società opposta non ha provato la titolarità del credito: l'avviso di cessione pubblicato in Gazzetta
Ufficiale non indica in modo specifico i rapporti ceduti e non consente di individuare il credito azionato.

2. Sulla nullità della fideiussione
La fideiussione riproduce lo schema ABI dichiarato in parte nullo dalla Banca d'Italia, ed è quindi nulla
nelle clausole di sopravvivenza, reviviscenza e rinuncia ai termini dell'art. 1957 c.c.

3. Sulle anomalie del rapporto di conto corrente
L'odierna attrice faceva sottoporre il rapporto a perizia econometrica, dalla quale emerge che il saldo
effettivo in favore della correntista ammonta ad euro 12.345,67 alla data di chiusura del conto.
"""

# Quello che un modello potrebbe restituire come "citazioni" a sostegno delle eccezioni estratte.
CITAZIONI = {
    "testuale": "non indica in modo specifico i rapporti ceduti",
    "con spazi e maiuscole diverse": "LA FIDEIUSSIONE  riproduce lo schema ABI",
    "parafrasi": "il saldo effettivo a favore della cliente ammonta ad euro 12.345,67",
    "inventata": "la banca ha applicato interessi usurari dal 2009",
}


def main() -> None:
    testo = pulisci_numeri_pagina(ATTO)
    blocchi = [{"blocco_id": f"B{i:02d}", "inizio": b.inizio, "fine": b.fine}
               for i, b in enumerate(segmenta_con_span(ATTO, conta_token=lambda s: len(s) // 4, budget_token=60), 1)]
    print(f"ATTO: {len(testo)} caratteri, {len(blocchi)} blocchi\n")
    print("ANCORAGGIO DELLE CITAZIONI (offset calcolati da Python, mai dal modello)")
    for nome, citazione in CITAZIONI.items():
        a = localizza(testo, blocchi, citazione)
        dove = f"[{a['inizio']}:{a['fine']}] {a['blocco_id']}" if "inizio" in a else "-"
        dettaglio = a.get("corrispondenza") or a.get("motivo") or ""
        print(f"  {nome:32s} {a['stato']:16s} {dove:16s} {dettaglio}")

    esito = cdp.cerca(testo)
    print("\nCONTEGGI DI PARTE")
    print(f"  trovati: {esito.trovati}")
    for r in esito.riscontri:
        print(f"  '{r.parola}' vicino a {r.importo}")


if __name__ == "__main__":
    main()
