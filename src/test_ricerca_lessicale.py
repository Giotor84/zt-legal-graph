# -*- coding: utf-8 -*-
"""Cosa deve reggere in `ricerca_lessicale`.

Il test che conta di piu' e'
`test_la_fusione_promuove_chi_e_a_meta_classifica_in_entrambe`: e' la sola
ragione per cui la fusione esiste. Se la fusione si limitasse a
concatenare le due liste, l'unione di due strategie mediocri resterebbe
mediocre, mentre la misura dice che passa da 32,1% e 48,7% a 60,5%.
"""

from __future__ import annotations

import pytest

import ricerca_lessicale as rl


def _indice(**testi: str) -> rl.IndiceLessicale:
    return rl.IndiceLessicale.costruisci(testi)


def test_trova_il_documento_che_contiene_le_parole():
    indice = _indice(
        anatocismo="capitalizzazione trimestrale degli interessi sul conto corrente",
        spese="condanna alle spese di lite e distrazione in favore del difensore",
    )
    assert indice.cerca("capitalizzazione trimestrale interessi", 1) == ["anatocismo"]


def test_le_parole_rare_pesano_piu_di_quelle_comuni():
    """E' l'idf, ed e' il motivo per cui BM25 batte il conteggio nudo: la
    parola che compare ovunque non distingue niente."""
    indice = _indice(
        a="contratto contratto contratto anatocismo",
        b="contratto contratto contratto contratto",
        c="contratto contratto contratto contratto contratto",
    )
    assert indice.cerca("contratto anatocismo", 1) == ["a"]


def test_le_parole_di_due_lettere_non_contano():
    """In italiano sotto le tre lettere ci sono quasi solo preposizioni:
    cercarle vorrebbe dire far somigliare fra loro tutti i documenti."""
    assert rl.parole("di un contratto in essere") == ["contratto", "essere"]


def test_l_ordine_non_dipende_dall_ordine_di_inserimento():
    """A parita' di punteggio vince il node_id piu' piccolo. Senza, due
    corse identiche potrebbero dare due liste diverse, e un confronto fra
    due configurazioni misurerebbe il caso."""
    uno = _indice(zeta="mediazione obbligatoria", alfa="mediazione obbligatoria")
    due = _indice(alfa="mediazione obbligatoria", zeta="mediazione obbligatoria")
    assert uno.cerca("mediazione", 2) == due.cerca("mediazione", 2) == ["alfa", "zeta"]


def test_una_query_senza_parole_note_non_restituisce_niente():
    """Meglio una lista vuota di una lista qualunque: e' la stessa regola
    di `foro_di`, che davanti a un comune ignoto torna None invece di un
    foro di ripiego."""
    indice = _indice(a="anatocismo bancario")
    assert indice.cerca("xilofono marziano", 5) == []


def test_la_lista_costante_non_guarda_la_domanda():
    """Da sola vale il 48,7% di R@20 - piu' del doppio della ricerca
    semantica - e va saputo che e' cieca: non e' brava, e' che le
    citazioni sono concentratissime."""
    costante = rl.strategia_costante(["a", "b", "c"])
    assert costante("qualunque cosa", 2) == costante("tutt'altro", 2) == ["a", "b"]


def test_la_fusione_promuove_chi_e_a_meta_classifica_in_entrambe():
    """La ragione d'essere di RRF. `comune` non e' primo da nessuna parte,
    ma e' in alto in tutte e due: deve battere chi e' primo in una sola.
    Una semplice concatenazione lo lascerebbe dov'e'."""
    prima = rl.strategia_costante(["solo_prima", "comune", "x", "y"])
    seconda = rl.strategia_costante(["solo_seconda", "comune", "z", "w"])
    assert rl.fondi(prima, seconda)("q", 1) == ["comune"]


def test_la_fusione_usa_le_posizioni_non_i_punteggi():
    """BM25 e la frequenza hanno scale incomparabili (un punteggio BM25
    di 12 e 613 citazioni non si sommano). RRF guarda solo il posto, e
    per questo non richiede pesi - che sarebbero tarati sui risultati."""
    lunga = rl.strategia_costante([f"n{i}" for i in range(100)])
    corta = rl.strategia_costante(["n99"])
    # n99 e' ultimo nella prima e primo nella seconda: la fusione lo porta su.
    assert rl.fondi(lunga, corta)("q", 1) == ["n99"]


def test_la_fusione_senza_strategie_e_un_errore():
    with pytest.raises(ValueError):
        rl.fondi()


def test_la_frequenza_puo_escludere_i_provvedimenti_del_banco_di_prova():
    """Senza questa esclusione ogni caso contribuirebbe alla propria
    risposta e il numero pubblicato sarebbe piu' alto e falso."""

    class Grafo:
        def edges(self, data=False):
            archi = [("prov::A", "art::1", {"tipo_arco": "cita", "fonte_campo": "motivazione",
                                            "occorrenze": 1, "ancore": []}),
                     ("prov::B", "art::1", {"tipo_arco": "cita", "fonte_campo": "motivazione",
                                            "occorrenze": 1, "ancore": []})]
            return archi if data else [(u, v) for u, v, _ in archi]

    assert rl.frequenza_di_citazione(Grafo()) == {"art::1": 2}
    assert rl.frequenza_di_citazione(Grafo(), escludi_provvedimenti=["prov::B"]) == {"art::1": 1}


def test_la_frequenza_conta_solo_le_citazioni_in_motivazione():
    """Gli archi del grafo sono tre popolazioni (BUG-GRAFO-5). Contarle
    tutte mescolerebbe le citazioni dei giudici con quelle delle massime."""

    class Grafo:
        def edges(self, data=False):
            archi = [("prov::A", "art::1", {"tipo_arco": "cita", "fonte_campo": "motivazione",
                                            "occorrenze": 1, "ancore": []}),
                     ("massima::X", "art::1", {"tipo_arco": "cita"}),
                     ("art::9", "art::1", {"tipo_arco": "cita", "has_seguenti": False})]
            return archi if data else [(u, v) for u, v, _ in archi]

    assert rl.frequenza_di_citazione(Grafo()) == {"art::1": 1}


def test_la_graduatoria_e_stabile_e_filtrabile():
    frequenze = {"b": 5, "a": 5, "c": 9, "fuori": 100}
    assert rl.graduatoria_per_frequenza(frequenze, {"a", "b", "c"}) == ["c", "a", "b"]


def test_il_testo_indicizzabile_dipende_dal_tipo_di_nodo():
    """Deve comporre come `build_embeddings`, altrimenti confrontare la
    ricerca per parole con quella semantica sarebbe confrontare due
    ingressi diversi e non due metodi."""
    assert rl.testo_indicizzabile(
        {"rubrica": "Interessi", "testo": "corpo"}) == "Interessi. corpo"
    assert rl.testo_indicizzabile(
        {"tipo_nodo": "massima", "titolo": "T", "testo": "corpo"}) == "T. corpo"
    assert rl.testo_indicizzabile(
        {"tipo_nodo": "bankit_disposizione", "citazione_breve": "B", "testo": "corpo"}) == "B. corpo"


def test_un_nodo_chiesto_ma_assente_dal_grafo_non_fa_saltare_l_indice():
    class Nodi(dict):
        pass

    class Grafo:
        def __init__(self):
            self.nodes = Nodi({"a": {"rubrica": "R", "testo": "anatocismo"}})

    indice = rl.indice_dal_grafo(Grafo(), ["a", "mai_visto"])
    assert indice.node_ids == ["a"]
