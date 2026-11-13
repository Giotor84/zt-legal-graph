"""Test di famiglie_da_cocitazione.py su un grafo sintetico con due
famiglie note e costruite apposta. Servono a fissare due proprieta': il
metodo separa cio' che va separato, e la soglia sulle coppie toglie le
coincidenze invece che la struttura."""

import networkx as nx

from famiglie_da_cocitazione import (
    articoli_per_provvedimento,
    comunita,
    etichetta,
    grafo_cocitazione,
    stabilita,
)

# Due gruppi di articoli che non si incontrano mai, piu' un articolo
# "processuale" citato da tutti - la forma esatta dei dati reali.
FIDEIUSSIONE = ["codice_civile::1957", "codice_civile::1945", "codice_civile::1419"]
CESSIONE = ["tub::58", "codice_civile::1264", "codice_civile::1260"]
OVUNQUE = "codice_procedura_civile::645"


def _grafo(n_per_gruppo: int = 6, con_rumore: bool = False) -> nx.MultiDiGraph:
    g = nx.MultiDiGraph()
    for a in FIDEIUSSIONE + CESSIONE + [OVUNQUE]:
        codice, numero = a.split("::")
        g.add_node(a, codice=codice, numero=numero, abrogato=False, is_main_body=True)

    def provvedimento(nome, articoli):
        g.add_node(nome, tipo_nodo="provvedimento", motivazione="x", data_deposito="2024-01-01")
        for a in articoli:
            g.add_edge(nome, a, tipo_arco="cita", fonte_campo="motivazione",
                       occorrenze=1, ancore=[], data_provvedimento="2024-01-01",
                       articolo_abrogato_oggi=False)

    for i in range(n_per_gruppo):
        provvedimento(f"provvedimento::F{i}", FIDEIUSSIONE + [OVUNQUE])
        provvedimento(f"provvedimento::C{i}", CESSIONE + [OVUNQUE])
    if con_rumore:
        # UNA sola lite che tocca entrambi i gruppi: e' una coincidenza, e
        # la soglia sulle coppie deve toglierla.
        provvedimento("provvedimento::RUMORE", ["codice_civile::1957", "tub::58"])
    return g


def test_articoli_per_provvedimento_legge_solo_gli_archi_di_motivazione():
    g = _grafo(n_per_gruppo=1)
    # un arco articolo->articolo, senza fonte_campo, non deve entrare
    g.add_edge("codice_civile::1957", "codice_civile::1945", tipo_arco="cita", has_seguenti=False)
    per_prov = articoli_per_provvedimento(g)
    assert set(per_prov) == {"provvedimento::F0", "provvedimento::C0"}
    assert "codice_civile::1957" not in per_prov


def test_le_due_famiglie_finiscono_in_comunita_diverse():
    co = grafo_cocitazione(articoli_per_provvedimento(_grafo()))
    dove = {n: i for i, c in enumerate(comunita(co)) for n in c}
    assert dove["codice_civile::1957"] == dove["codice_civile::1945"]
    assert dove["tub::58"] == dove["codice_civile::1264"]
    assert dove["codice_civile::1957"] != dove["tub::58"]


def test_la_soglia_toglie_la_coppia_vista_una_volta_sola():
    per_prov = articoli_per_provvedimento(_grafo(con_rumore=True))
    co_grezzo = grafo_cocitazione(per_prov, soglia=1)
    co_tagliato = grafo_cocitazione(per_prov, soglia=3)
    ponte = ("codice_civile::1957", "tub::58")
    assert co_grezzo.has_edge(*ponte), "senza soglia il ponte spurio c'e'"
    assert not co_tagliato.has_edge(*ponte), "con la soglia il ponte spurio sparisce"


def test_la_soglia_non_toglie_le_coppie_vere():
    co = grafo_cocitazione(articoli_per_provvedimento(_grafo(con_rumore=True)), soglia=3)
    assert co.has_edge("codice_civile::1957", "codice_civile::1945")
    assert co.has_edge("tub::58", "codice_civile::1264")


def test_i_pesi_contano_le_motivazioni_non_le_occorrenze():
    co = grafo_cocitazione(articoli_per_provvedimento(_grafo(n_per_gruppo=6)), soglia=1)
    assert co["codice_civile::1957"]["codice_civile::1945"]["weight"] == 6


def test_stabilita_separa_le_sonde_vere_dai_controlli():
    # La proprieta' che rende la misura utile: le coppie vere in alto, i
    # controlli in basso. Una misura che alza tutti non dice nulla.
    co = grafo_cocitazione(articoli_per_provvedimento(_grafo()))
    esito = stabilita(co, {
        "vera": ("codice_civile::1957", "codice_civile::1945"),
        "controllo": ("codice_civile::1957", "tub::58"),
    })
    vera_insieme, totale = esito["vera"]
    controllo_insieme, _ = esito["controllo"]
    assert vera_insieme == totale
    assert controllo_insieme == 0


def test_etichetta_leggibile():
    g = _grafo(n_per_gruppo=1)
    assert etichetta(g, "tub::58") == "art. 58 tub"
    assert etichetta(g, "codice_civile::1957") == "art. 1957 civile"
