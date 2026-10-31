# -*- coding: utf-8 -*-
"""Il grafo degli articoli non deve poter cancellare il corpus.

Fino al 2026-09-04 `build_graph.py` scriveva direttamente sul grafo in
carica, e la sua docstring lo dichiarava come prodotto normale. Ma il
grafo che costruisce contiene i soli articoli: lanciarlo sul corpus
maturo avrebbe cancellato 3583 provvedimenti - 155 MB - senza che niente
si opponesse.

Non era un rischio teorico: era esattamente il comando che serviva per
innestare quattro leggi mancanti, ed e' il primo che si sarebbe
lanciato."""

from __future__ import annotations

import os
import pickle
import sys

import networkx as nx
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import build_graph  # noqa: E402


def _grafo(**nodi) -> nx.MultiDiGraph:
    g = nx.MultiDiGraph()
    for identificativo, dati in nodi.items():
        g.add_node(identificativo, **dati)
    return g


def _scrivi(percorso, grafo) -> None:
    with open(percorso, "wb") as f:
        pickle.dump(grafo, f)


# ------------------------------------------------ il rifiuto che conta

def test_rifiuta_di_sovrascrivere_un_grafo_con_provvedimenti(tmp_path):
    bersaglio = tmp_path / "grafo.gpickle"
    _scrivi(bersaglio, _grafo(
        p1={"tipo_nodo": "provvedimento"},
        p2={"tipo_nodo": "provvedimento"},
        a1={"codice": "codice_civile", "numero": "1"}))

    with pytest.raises(build_graph.DestinazioneRifiutata) as scoppio:
        build_graph.controlla_destinazione(bersaglio)

    detto = str(scoppio.value)
    assert "2 provvedimenti" in detto, (
        "deve dire QUANTI se ne perderebbero: e' il numero che ferma la mano")
    assert "promuovi_grafo" in detto, "e deve dire qual e' la via giusta"


def test_guarda_il_contenuto_non_il_nome(tmp_path):
    """Un file che si chiama `candidato.gpickle` ma contiene il corpus va
    protetto lo stesso: e' il contenuto che dice cosa si perde."""
    bersaglio = tmp_path / "candidato_qualsiasi.gpickle"
    _scrivi(bersaglio, _grafo(p1={"tipo_nodo": "provvedimento"}))
    with pytest.raises(build_graph.DestinazioneRifiutata):
        build_graph.controlla_destinazione(bersaglio)


def test_un_file_illeggibile_non_si_distrugge(tmp_path):
    """Non si sa cosa ci sia dentro, quindi non si sa cosa si stia per
    buttare. `None` vuol dire "non lo so", mai "no"."""
    bersaglio = tmp_path / "rotto.gpickle"
    bersaglio.write_bytes(b"non e' un pickle")
    with pytest.raises(build_graph.DestinazioneRifiutata) as scoppio:
        build_graph.controlla_destinazione(bersaglio)
    assert "non si e' potuto leggere" in str(scoppio.value)


# ------------------------------------------------ cio' che deve passare

def test_una_destinazione_nuova_va_bene(tmp_path):
    build_graph.controlla_destinazione(tmp_path / "mai_vista.gpickle")


def test_un_grafo_di_soli_articoli_si_puo_rifare(tmp_path):
    """Rifare il candidato degli articoli e' l'operazione normale: il
    controllo non deve renderla scomoda, o si aggirera'."""
    bersaglio = tmp_path / "articoli.gpickle"
    _scrivi(bersaglio, _grafo(
        a1={"codice": "codice_civile", "numero": "1"},
        a2={"codice": "tub", "numero": "117"}))
    build_graph.controlla_destinazione(bersaglio)


# ------------------------------------------------------ l'uso da riga

def test_out_e_obbligatorio(tmp_path):
    """Senza, il valore di prima era il grafo in carica: il difetto stava
    tutto nel default."""
    with pytest.raises(SystemExit):
        build_graph.main([])


def test_scrive_dove_gli_si_dice_e_non_altrove(tmp_path):
    """Il grafo e i due file di corredo vanno accanto alla destinazione,
    non in `data/graph/`: un candidato che sparge indici nella cartella
    del grafo in carica li fa sembrare quelli buoni."""
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "tub.md").write_text(
        "# TUB\n\n## Art. 117\n\nI contratti sono redatti per iscritto.\n",
        encoding="utf-8")
    uscita = tmp_path / "candidato.gpickle"

    build_graph.main(["--out", str(uscita), "--raw-dir", str(raw)])

    assert uscita.exists()
    assert (tmp_path / "candidato.gpickle.articoli.json").exists()
    assert (tmp_path / "candidato.gpickle.stats.json").exists()
    with open(uscita, "rb") as f:
        g = pickle.load(f)
    assert g.number_of_nodes() >= 1
    assert all(d.get("tipo_nodo") != "provvedimento"
               for _, d in g.nodes(data=True))
