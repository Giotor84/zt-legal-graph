# -*- coding: utf-8 -*-
"""Il valutatore del golden set degli atti.

Cio' che difende e' che nessuna voce annotata sparisca senza dirlo: un
recall calcolato su meno voci di quante ne sono state annotate e' sbagliato
e sembra giusto.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import valuta_golden_set  # noqa: E402

def test_ogni_famiglia_di_fase_1_sopravvive_al_giro_di_andata_e_ritorno(tmp_path):
    """Due famiglie dell'enum contengono cifre. La regex le leggeva con
    `[a-z_]+`, quindi le righe di quelle famiglie non venivano lette e NON
    davano errore: sparivano, e il recall usciva sbagliato in silenzio.

    Il test parte dall'enum di Fase 1, non da un elenco riscritto qui: e' la
    divergenza fra i due elenchi la cosa che deve restare impossibile."""
    from estrazione_atto import SCHEMA_ECCEZIONI

    famiglie = SCHEMA_ECCEZIONI["properties"]["eccezioni_sollevate"]["items"][
        "properties"]["famiglia_probabile"]["enum"]
    righe = ["# x", "", "## Annotazione", ""]
    righe += ['%d. [%s] "frase di prova numero %d"' % (i, f, i)
              for i, f in enumerate(famiglie, start=1)]
    percorso = tmp_path / "x_annotazione.md"
    percorso.write_text("\n".join(righe), encoding="utf-8")

    lette = valuta_golden_set.carica_annotazione(percorso)

    assert [a.famiglia for a in lette] == list(famiglie), (
        "una famiglia che non sopravvive alla lettura sparisce senza errore"
    )
