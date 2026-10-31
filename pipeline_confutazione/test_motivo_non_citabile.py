# -*- coding: utf-8 -*-
"""BUG-GRAFO-3: un nodo che non porta norma non puo' reggere una citazione.

Il test che conta e' `test_lo_stub_di_abrogazione_non_diventa_una_fonte`.
Prima di questo modulo `[ARTICOLO ABROGATO]` passava `strip()` come
qualunque altro testo, diventava una fonte del dossier, e l'estratto
ritagliato da li' finiva nell'atto con i suoi offset regolari e il
controllo di identita' testuale soddisfatto: tutto in regola tranne il
contenuto.

La misura che ha motivato il modulo (2026-09-02, sui 5867 articoli di
`grafo.gpickle`): i 244 abrogati hanno `testo` lungo 19 caratteri -
minimo, mediana e massimo - e 230 di loro sono il nodo che
`store.trova()` restituisce.
"""

from __future__ import annotations

import networkx as nx
import pytest

from retrieval import SEGNAPOSTO_ABROGATO, motivo_non_citabile


class _Store:
    """Il minimo che `motivo_non_citabile` tocca: un grafo con i nodi."""

    def __init__(self, graph: nx.MultiDiGraph) -> None:
        self.graph = graph


def _store(**nodi: dict) -> _Store:
    g = nx.MultiDiGraph()
    for node_id, dati in nodi.items():
        g.add_node(node_id, **dati)
    return _Store(g)


# ------------------------------------------------- il caso che ha guastato

def test_lo_stub_di_abrogazione_non_diventa_una_fonte():
    s = _store(abrogato={"tipo_nodo": "articolo", "abrogato": True,
                         "testo": SEGNAPOSTO_ABROGATO})
    motivo = motivo_non_citabile(s, "abrogato")
    assert motivo is not None
    assert "ABROGATO" in motivo and "BUG-GRAFO-3" in motivo


def test_il_segnaposto_e_quello_vero_del_grafo():
    """Se un giorno l'ingestione cambiasse la stringa, il confronto
    esatto smetterebbe di riconoscerla e il difetto tornerebbe muto.
    Questa costante e' misurata, non scelta."""
    assert SEGNAPOSTO_ABROGATO == "[ARTICOLO ABROGATO]"
    assert len(SEGNAPOSTO_ABROGATO) == 19


def test_lo_stub_passava_il_controllo_del_testo_vuoto():
    """La prova che il controllo precedente non bastava: 19 caratteri
    sopravvivono a `strip()`. E' per questo che serviva un caso a parte
    e non e' bastato riusare quello del testo vuoto."""
    assert SEGNAPOSTO_ABROGATO.strip() != ""


# --------------------------------------------------- cosa deve passare

def test_il_flag_abrogato_non_basta_e_non_e_lui_a_decidere():
    """21 nodi su 265 hanno il segnaposto come unico testo e
    `abrogato=False` (art. 17, 155, 342-bis, 342-ter c.c. fra gli altri).
    Il verso e' solo quello - nessun nodo ha `abrogato=True` con un testo
    vero - quindi il flag sotto-dichiara. Un controllo scritto sul flag
    ne avrebbe lasciati passare 21."""
    s = _store(bugiardo={"tipo_nodo": "articolo", "abrogato": False,
                         "testo": SEGNAPOSTO_ABROGATO})
    assert motivo_non_citabile(s, "bugiardo") is not None


def test_un_articolo_vero_passa():
    s = _store(vero={"tipo_nodo": "articolo", "abrogato": False,
                     "testo": "Il debitore che non esegue esattamente la "
                              "prestazione dovuta e' tenuto al risarcimento."})
    assert motivo_non_citabile(s, "vero") is None


def test_un_abrogato_CON_testo_passa_e_non_e_questa_funzione_a_decidere():
    """Oggi non esiste (0 su 244), ma la migrazione temporale lo creera':
    la versione vigente all'epoca dei fatti e' spesso proprio quella che
    serve all'avvocato. Decidere qui che un abrogato non serve mai
    sarebbe decidere al posto suo - e sarebbe la stessa scorciatoia che
    `candidati_per_prompt` ha sempre rifiutato."""
    s = _store(storico={"tipo_nodo": "articolo", "abrogato": True,
                        "testo": "Testo della norma nella versione in vigore "
                                 "fino alla riforma, conservato per intero."})
    assert motivo_non_citabile(s, "storico") is None


# ------------------------------------------------------- il caso vuoto

def test_il_testo_vuoto_resta_scartato_con_il_suo_motivo():
    s = _store(vuoto={"tipo_nodo": "articolo", "abrogato": False, "testo": ""})
    motivo = motivo_non_citabile(s, "vuoto")
    assert motivo is not None and "senza testo citabile" in motivo


def test_i_due_motivi_sono_distinguibili():
    """Un nodo mai popolato e un articolo abrogato sono due guasti
    diversi: se il dossier li chiama con lo stesso nome, chi legge
    `fonti_scartate` non sa quale dei due sta guardando."""
    vuoto = motivo_non_citabile(
        _store(v={"tipo_nodo": "articolo", "testo": "   "}), "v")
    stub = motivo_non_citabile(
        _store(s={"tipo_nodo": "articolo", "abrogato": True,
                  "testo": SEGNAPOSTO_ABROGATO}), "s")
    assert vuoto != stub


def test_un_provvedimento_senza_testo_ma_con_motivazione_passa():
    """`testo_di_fonte` ricade su motivazione/dispositivo: il controllo
    non deve scartare un provvedimento solo perche' non ha `testo`."""
    s = _store(prov={"tipo_nodo": "provvedimento",
                     "motivazione": "Il collegio osserva che l'eccezione e' "
                                    "infondata per le ragioni che seguono."})
    assert motivo_non_citabile(s, "prov") is None


@pytest.mark.parametrize("testo", [
    SEGNAPOSTO_ABROGATO,
    "  " + SEGNAPOSTO_ABROGATO + "  ",
    "\n" + SEGNAPOSTO_ABROGATO + "\n",
])
def test_lo_stub_si_riconosce_anche_con_spazi_intorno(testo: str):
    s = _store(a={"tipo_nodo": "articolo", "abrogato": True, "testo": testo})
    assert motivo_non_citabile(s, "a") is not None
