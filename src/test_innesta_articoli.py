# -*- coding: utf-8 -*-
"""Un grafo maturo si accresce, non si ricostruisce.

La ricostruzione era stata provata il 2026-09-04 ed e' stata bocciata
dal controllo di promozione: `massima 185->0, bankit_disposizione 84->0`.
`build_graph.py` legge solo `data/raw`, e nessuno tiene a mente tutti i
produttori che hanno scritto nel grafo. Questi test fissano la garanzia
che ne e' seguita: **non si toglie mai niente**."""

from __future__ import annotations

import os
import pickle
import sys

import networkx as nx
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import innesta_articoli as ia  # noqa: E402


def _grafo(nodi: dict, archi: list | None = None) -> nx.MultiDiGraph:
    g = nx.MultiDiGraph()
    for identificativo, dati in nodi.items():
        g.add_node(identificativo, **dati)
    for a, b in (archi or []):
        g.add_edge(a, b, tipo_arco="cita")
    return g


def _maturo() -> nx.MultiDiGraph:
    """Un grafo con dentro cio' che la ricostruzione perdeva."""
    return _grafo({
        "art1": {"codice": "tub", "numero": "117", "testo": "vecchio"},
        "art2": {"codice": "codice_civile", "numero": "1"},
        "prov1": {"tipo_nodo": "provvedimento"},
        "mass1": {"tipo_nodo": "massima"},
        "bank1": {"tipo_nodo": "bankit_disposizione"},
    }, [("art1", "art2")])


def _candidato() -> nx.MultiDiGraph:
    """Solo articoli, come li produce `build_graph.py`."""
    return _grafo({
        "art1": {"codice": "tub", "numero": "117", "testo": "corretto"},
        "art2": {"codice": "codice_civile", "numero": "1"},
        "nuovo1": {"codice": "l_108_1996", "numero": "2"},
        "nuovo2": {"codice": "dlgs_58_1998", "numero": "21"},
    }, [("art1", "art2"), ("nuovo1", "art1"), ("nuovo1", "nuovo2")])


# ------------------------------------------- non si toglie mai niente

def test_massime_e_bankit_sopravvivono_all_innesto():
    """E' il guasto che la ricostruzione aveva prodotto davvero: 269 nodi
    persi perche' il candidato non li conosceva."""
    accresciuto, _ = ia.innesta(_maturo(), _candidato())
    for rimasto in ("prov1", "mass1", "bank1"):
        assert rimasto in accresciuto.nodes(), rimasto
    assert accresciuto.nodes["mass1"]["tipo_nodo"] == "massima"


def test_il_censimento_dichiara_cosa_il_candidato_non_ha():
    """La meta' che conta: dice quanto il candidato e' PIU POVERO del
    grafo, che e' il modo in cui una ricostruzione cancella in silenzio.
    Va dichiarato, non dedotto da una differenza fra totali."""
    conto = ia.censimento(_maturo(), _candidato())
    assert conto["nodi_del_grafo_assenti_dal_candidato"] == 3
    assert conto["classi_assenti"] == {"provvedimento": 1, "massima": 1,
                                       "bankit_disposizione": 1}


def test_un_arco_che_il_candidato_non_ha_resta():
    grafo = _maturo()
    grafo.add_edge("art2", "art1", tipo_arco="cita")
    accresciuto, _ = ia.innesta(grafo, _candidato())
    assert accresciuto.has_edge("art2", "art1")


# ------------------------------------------------ cio' che si aggiunge

def test_aggiunge_i_nodi_nuovi_con_i_loro_campi():
    accresciuto, conto = ia.innesta(_maturo(), _candidato())
    assert conto["nodi_da_aggiungere"] == 2
    assert accresciuto.nodes["nuovo1"]["codice"] == "l_108_1996"
    assert conto["per_fonte"] == {"l_108_1996": 1, "dlgs_58_1998": 1}


def test_aggiunge_gli_archi_che_toccano_un_nodo_nuovo():
    """Anche quelli da un articolo VECCHIO a uno nuovo: sono i rinvii che
    prima restavano irrisolti perche' il bersaglio non c'era."""
    accresciuto, conto = ia.innesta(_maturo(), _candidato())
    assert accresciuto.has_edge("nuovo1", "art1")
    assert accresciuto.has_edge("nuovo1", "nuovo2")
    assert conto["archi_aggiunti"] == 2


def test_non_duplica_gli_archi_gia_presenti():
    """Il grafo e' un MultiDiGraph: riaggiungere `art1 -> art2`
    creerebbe un secondo arco identico, e i conteggi per popolazione
    (vedi popolazioni_archi) comincerebbero a contare doppio."""
    accresciuto, _ = ia.innesta(_maturo(), _candidato())
    assert accresciuto.number_of_edges("art1", "art2") == 1


# ---------------------------------------------- la correzione dei testi

def test_i_testi_non_si_toccano_se_non_si_chiede():
    """Cambiare il testo di un nodo sposta gli offset di chi lo cita."""
    accresciuto, conto = ia.innesta(_maturo(), _candidato())
    assert accresciuto.nodes["art1"]["testo"] == "vecchio"
    assert conto["testi_diversi"] == 1
    assert conto["testi_corretti"] == 0


def test_con_la_richiesta_esplicita_i_testi_si_aggiornano():
    accresciuto, conto = ia.innesta(_maturo(), _candidato(),
                                    correggi_testi=True)
    assert accresciuto.nodes["art1"]["testo"] == "corretto"
    assert conto["testi_corretti"] == 1


# ------------------------------------------------------- il rifiuto

def test_un_candidato_che_non_aggiunge_niente_e_rifiutato():
    """O e' gia' innestato, o e' il candidato sbagliato: in entrambi i
    casi proseguire scriverebbe un file identico con un nome nuovo, che
    poi qualcuno promuove credendo di aggiornare."""
    with pytest.raises(ia.InnestoRifiutato) as scoppio:
        ia.innesta(_maturo(), _grafo({"art1": {"codice": "tub"}}))
    assert "nessun nodo" in str(scoppio.value)


def test_il_grafo_di_partenza_non_viene_modificato():
    """Il chiamante deve poter confrontare il prima e il dopo."""
    grafo = _maturo()
    prima = grafo.number_of_nodes()
    ia.innesta(grafo, _candidato())
    assert grafo.number_of_nodes() == prima
    assert "nuovo1" not in grafo.nodes()


# --------------------------------------------------------- da riga

def test_scrive_il_candidato_e_non_promuove(tmp_path):
    grafo = tmp_path / "grafo.gpickle"
    cand = tmp_path / "articoli.gpickle"
    fuori = tmp_path / "accresciuto.gpickle"
    with open(grafo, "wb") as f:
        pickle.dump(_maturo(), f)
    with open(cand, "wb") as f:
        pickle.dump(_candidato(), f)

    assert ia.main(["--grafo", str(grafo), "--candidato-articoli", str(cand),
                    "--out", str(fuori)]) == 0

    with open(grafo, "rb") as f:
        intatto = pickle.load(f)
    assert "nuovo1" not in intatto.nodes(), "il grafo di partenza resta intatto"
    with open(fuori, "rb") as f:
        scritto = pickle.load(f)
    assert "nuovo1" in scritto.nodes() and "mass1" in scritto.nodes()
