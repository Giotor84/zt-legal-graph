"""
Configurazione di pytest per questa cartella.

Alcuni file che si chiamano `test_*.py` NON sono test: sono script di
corsa dal vivo, scritti per essere lanciati a mano contro llama-server e
il grafo reali. Eseguono lavoro all'import (estraggono un PDF, chiamano il
modello, scrivono file di risultati) e non hanno funzioni `test_`.

pytest li raccoglie per convenzione di nome e fallisce in fase di
collezione con un ConnectionRefusedError, il che rende rosso l'intero
comando anche quando ogni test vero e' verde - e nasconde i fallimenti che
contano dietro un errore d'ambiente.

Escluderli qui, invece di rinominarli, ha una ragione: sono la procedura
documentata per la prima corsa reale, e cambiargli nome adesso
significherebbe rompere le istruzioni operative proprio mentre servono. Il
loro posto e' la riga di comando, non la suite.
"""

from pathlib import Path

#: Script di corsa dal vivo: richiedono llama-server in ascolto e i dati
#: reali. Si lanciano a mano, uno per volta, guardando l'output.
CORSE_DAL_VIVO = [
    "test_estrazione_atto_reale.py",       # Fase 1 su un PDF vero, decine di minuti
    "test_confronto_vincolato_libero.py",  # confronto vincolato/libero sul catalogo allucinazioni
]

collect_ignore = list(CORSE_DAL_VIVO)

#: vecchio/ contiene codice ritirato, tenuto per riferimento storico: non
#: e' manutenuto e non deve far fallire la suite.
collect_ignore_glob = ["vecchio/*"]


def pytest_report_header(config):
    return (f"corse dal vivo escluse dalla raccolta ({len(CORSE_DAL_VIVO)}): "
            + ", ".join(Path(n).stem for n in CORSE_DAL_VIVO))
