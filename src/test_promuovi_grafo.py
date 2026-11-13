"""Test dei controlli di promuovi_grafo.py. Verificano che ogni controllo
BOCCI davvero quando deve: un controllo che non ha mai detto di no non e'
un controllo, e qui la cosa che sta dietro il no e' il grafo in carica."""

import networkx as nx
import pytest

from promuovi_grafo import Bocciato, verifica, verifica_indice_segmenti


def _articolo(g, node_id, testo="Il fideiussore e' liberato...", abrogato=False,
              is_main_body=True):
    # La citazione breve viene dal numero, come nel grafo vero. Quando era
    # fissa ("art. x c.c.") tutti gli articoli del finto grafo collidevano
    # fra loro, ed e' il controllo 8 ad averlo scoperto: la finzione era
    # piu' rotta del grafo che doveva imitare.
    numero = node_id.split("::")[-1]
    g.add_node(node_id, codice="codice_civile", numero=numero,
               is_main_body=is_main_body, abrogato=abrogato,
               sezione="CODICE CIVILE", testo=testo, testo_raw=testo,
               rubrica="", source_url="", citazione_breve=f"art. {numero} c.c.")
    return g


def _in_carica() -> nx.MultiDiGraph:
    g = nx.MultiDiGraph()
    _articolo(g, "codice_civile::1957")
    _articolo(g, "codice_civile::1264", testo="La cessione ha effetto...")
    g.add_node("massima::M1", tipo_nodo="massima", testo="massima")
    return g


def _candidato_valido() -> nx.MultiDiGraph:
    g = _in_carica()
    motivazione = "Il collegio richiama l'art. 1957 c.c. e conclude."
    g.add_node("provvedimento::P1", tipo_nodo="provvedimento",
               motivazione=motivazione, data_deposito="2024-05-06")
    inizio = motivazione.index("art. 1957 c.c.")
    fine = inizio + len("art. 1957 c.c.")
    g.add_edge("provvedimento::P1", "codice_civile::1957",
               tipo_arco="cita", fonte_campo="motivazione", occorrenze=1,
               ancore=[{"inizio": inizio, "fine": fine,
                        "testo_verbatim": motivazione[inizio:fine]}],
               data_provvedimento="2024-05-06", articolo_abrogato_oggi=False)
    return g


def test_candidato_valido_passa_tutti_i_controlli():
    referto = verifica(_candidato_valido(), _in_carica())
    assert len(referto) >= 6
    assert any("ancoraggio" in r for r in referto)


def test_boccia_se_non_e_un_multidigraph():
    with pytest.raises(Bocciato, match="MultiDiGraph"):
        verifica(nx.DiGraph(), _in_carica())


def test_boccia_se_sparisce_una_classe_di_nodo():
    # Il caso concreto: un candidato che ha perso le massime per strada.
    candidato = _candidato_valido()
    candidato.remove_node("massima::M1")
    with pytest.raises(Bocciato, match="classi di nodo in calo"):
        verifica(candidato, _in_carica())


def test_boccia_se_sparisce_un_articolo():
    candidato = _candidato_valido()
    candidato.remove_node("codice_civile::1264")
    with pytest.raises(Bocciato, match="articoli spariti|classi di nodo in calo"):
        verifica(candidato, _in_carica())


def test_boccia_se_il_testo_di_legge_e_cambiato():
    # Un'ingestione di giurisprudenza non ha alcuna ragione di riscrivere
    # il testo di una norma: se succede e' un bug, e va visto prima.
    candidato = _candidato_valido()
    candidato.nodes["codice_civile::1957"]["testo"] = "testo diverso"
    with pytest.raises(Bocciato, match="testo alterato"):
        verifica(candidato, _in_carica())


def test_boccia_se_il_testo_raw_e_cambiato():
    candidato = _candidato_valido()
    candidato.nodes["codice_civile::1957"]["testo_raw"] = "raw diverso"
    with pytest.raises(Bocciato, match="testo alterato"):
        verifica(candidato, _in_carica())


def test_boccia_se_un_ancora_non_e_verbatim():
    # Regola 4 di CLAUDE.md verificata sul prodotto finito.
    candidato = _candidato_valido()
    for _u, _v, d in candidato.edges(data=True):
        d["ancore"][0]["testo_verbatim"] = "art. 9999 c.c."
    with pytest.raises(Bocciato, match="ancore"):
        verifica(candidato, _in_carica())


def test_boccia_se_un_ancora_ha_offset_spostati():
    candidato = _candidato_valido()
    for _u, _v, d in candidato.edges(data=True):
        d["ancore"][0]["inizio"] += 3
    with pytest.raises(Bocciato, match="ancore"):
        verifica(candidato, _in_carica())


def test_archi_senza_fonte_campo_non_sono_controllati_per_ancoraggio():
    # Gli archi articolo->articolo preesistenti non hanno ne' fonte_campo
    # ne' ancore: il controllo 5 deve ignorarli, non inciamparci.
    candidato = _candidato_valido()
    candidato.add_edge("codice_civile::1957", "codice_civile::1264",
                       tipo_arco="cita", has_seguenti=False)
    referto = verifica(candidato, _in_carica())
    assert any("1 ancore" in r for r in referto)


def test_un_candidato_identico_all_in_carica_passa():
    # Promuovere un grafo identico e' inutile ma non pericoloso: i
    # controlli non devono inventarsi un motivo per bocciarlo.
    assert verifica(_in_carica(), _in_carica())


# --- Controllo 9: indice dei segmenti e grafo devono essere coetanei -------


def _indice(*node_ids):
    return [{"node_id": n, "indice_segmento": 0, "offset_inizio": 0,
             "offset_fine": 10, "motivazione_certa": True,
             "stato_verifica": "verificato"} for n in node_ids]


def test_indice_coerente_col_candidato_passa():
    candidato = _candidato_valido()
    riga = verifica_indice_segmenti(candidato, _indice("provvedimento::P1"))
    assert "1 segmenti su 1 provvedimenti" in riga


def test_boccia_un_indice_che_nomina_nodi_assenti():
    # L'errore che rompe davvero: retrieval che legge graph.nodes[node_id]
    # di un nodo che non c'e'. Non si vede prima di una corsa.
    with pytest.raises(Bocciato, match="non ha"):
        verifica_indice_segmenti(_candidato_valido(), _indice("provvedimento::FANTASMA"))


def test_boccia_un_indice_che_nomina_nodi_non_provvedimento():
    with pytest.raises(Bocciato, match="non sono provvedimenti"):
        verifica_indice_segmenti(_candidato_valido(), _indice("codice_civile::1957"))


def test_indice_vuoto_non_solleva_ma_lo_dichiara():
    riga = verifica_indice_segmenti(_candidato_valido(), [])
    assert "0 segmenti su 0 provvedimenti" in riga


# ------------------------- controllo 7: le forme di arco (BUG-GRAFO-5)

def test_boccia_un_arco_di_forma_sconosciuta():
    """Il danno di una forma nuova non e' un errore, e' un conteggio piu'
    piccolo del vero: i consumatori usano tutti `.get()` con un default,
    quindi non falliscono - quegli archi semplicemente non li contano.
    La promozione e' il momento in cui si vede."""
    g = _candidato_valido()
    g.add_edge("codice_civile::1957", "codice_civile::1264", peso=0.7)
    with pytest.raises(Bocciato, match="forma"):
        verifica(g, _in_carica())


def test_il_referto_conta_le_tre_popolazioni():
    g = _candidato_valido()
    g.add_edge("codice_civile::1957", "codice_civile::1264",
               tipo_arco="cita", has_seguenti=False)
    g.add_edge("massima::M1", "codice_civile::1264", tipo_arco="cita")
    referto = verifica(g, _in_carica())
    assert any("articolo_articolo" in r for r in referto)
    assert any("provvedimento_articolo" in r for r in referto)
    assert any("fonte_esterna_articolo" in r for r in referto)


# --------------- controllo 8: le citazioni brevi doppie (BUG-GRAFO-4/1)

def test_una_citazione_doppia_sciolta_da_un_solo_main_body_passa():
    """E' il caso reale: nel grafo in carica 36 citazioni brevi valgono per
    piu' di un articolo - le preleggi contro il corpo del codice civile -
    e ognuna ha esattamente un `is_main_body` vero."""
    g = _candidato_valido()
    _articolo(g, "codice_civile::PRELEGGI::1957", is_main_body=False)
    referto = verifica(g, _in_carica())
    assert any("citazioni brevi" in r for r in referto)


def test_boccia_una_citazione_doppia_con_DUE_main_body():
    """E' l'unicita' che fa decidere `GraphStore._build_lookup` chi vince.
    Con due vincitori `store.trova` ne restituisce uno dei due e non lo
    dice: l'articolo sbagliato, con l'aria di quello giusto."""
    g = _candidato_valido()
    _articolo(g, "codice_civile::ALTRA::1957", is_main_body=True)
    with pytest.raises(Bocciato, match="citazioni brevi doppie"):
        verifica(g, _in_carica())


def test_boccia_una_citazione_doppia_con_NESSUN_main_body():
    g = _candidato_valido()
    g.nodes["codice_civile::1957"]["is_main_body"] = False
    _articolo(g, "codice_civile::ALTRA::1957", is_main_body=False)
    with pytest.raises(Bocciato, match="citazioni brevi doppie"):
        verifica(g, _in_carica())
