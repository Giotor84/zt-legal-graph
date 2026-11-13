"""Test di valuta_golden_eccezioni.py su dati sintetici.

Il controllo che conta e' il primo gruppo: un golden set il cui verbatim non
si trova, o si trova due volte, deve essere RIFIUTATO. Se passasse, gli
offset diventerebbero un campo scritto a mano invece che calcolato, e la
misura poggerebbe su una posizione che nessuno ha verificato.
"""

import pytest

from valuta_golden_eccezioni import (
    GoldenNonAncorabile,
    _lato_di,
    _si_sovrappongono,
    ancora,
    appaia,
    valuta,
)

MOTIVAZIONE = (
    "Con atto di citazione Parte_1 proponeva opposizione. "                 # 0-56
    "Eccepiva l'opponente la nullita' della fideiussione per vessatorieta'. "
    "Eccepiva altresi' la decadenza della banca ex art. 1957 c.c. "
    "La banca opposta chiedeva la provvisoria esecutivita'. "
    "L'opposizione e' fondata e va accolta."
)
NODE = "provvedimento::TEST"


def _golden(*voci):
    return {
        "documenti": [{
            "indice": 1, "ufficio": "TRIBUNALE DI PROVA", "area": "fideiussione",
            "node_id": NODE, "eccezioni": list(voci),
        }]
    }


def _voce(verbatim, parte="opponente", esito="accolta", sintesi="x"):
    return {"parte": parte, "esito": esito, "verbatim": verbatim, "sintesi": sintesi}


# --- Ancoraggio: il controllo che rende il golden set un riferimento ------

def test_ancora_calcola_gli_offset_e_non_li_legge():
    voce = _voce("la nullita' della fideiussione per vessatorieta'")
    (v,) = ancora(_golden(voce), {NODE: MOTIVAZIONE})
    assert MOTIVAZIONE[v["inizio"]:v["fine"]] == voce["verbatim"]


def test_ancora_rifiuta_un_verbatim_che_non_si_trova():
    with pytest.raises(GoldenNonAncorabile, match="si trova 0 volte"):
        ancora(_golden(_voce("una frase che nel testo non c'e' mai")), {NODE: MOTIVAZIONE})


def test_ancora_rifiuta_un_verbatim_ambiguo():
    # "Eccepiva" compare due volte: un ancoraggio ambiguo e' un difetto del
    # golden set, e va corretto li'. Il valutatore non sceglie per conto suo.
    with pytest.raises(GoldenNonAncorabile, match="si trova 2 volte"):
        ancora(_golden(_voce("Eccepiva")), {NODE: MOTIVAZIONE})


def test_ancora_rifiuta_un_provvedimento_assente_dal_grafo():
    with pytest.raises(GoldenNonAncorabile, match="non ha motivazione"):
        ancora(_golden(_voce("qualunque")), {})


def test_ancora_riporta_il_documento_e_la_voce_che_hanno_fallito():
    g = _golden(_voce("la nullita' della fideiussione per vessatorieta'"), _voce("inesistente"))
    with pytest.raises(GoldenNonAncorabile, match="doc 1 voce 2"):
        ancora(g, {NODE: MOTIVAZIONE})


# --- Lato della parte, dedotto senza modello -----------------------------

def test_lato_debitore():
    assert _lato_di("l'opponente") == "debitore"
    assert _lato_di("il fideiussore") == "debitore"


def test_lato_creditore():
    assert _lato_di("la banca opposta") == "creditore"
    assert _lato_di("CP_3") == "creditore"


def test_lato_ignoto_se_ambiguo_o_assente():
    # "l'opponente e la banca" nomina entrambi i lati: non si sceglie.
    assert _lato_di("l'opponente e la banca") == "ignoto"
    assert _lato_di(None) == "ignoto"
    assert _lato_di("il consulente tecnico") == "ignoto"


# --- Appaiamento ----------------------------------------------------------

def test_si_sovrappongono():
    assert _si_sovrappongono((10, 20), (15, 25))
    assert not _si_sovrappongono((10, 20), (20, 30))


def test_appaia_riconosce_la_sovrapposizione_anche_se_i_testi_differiscono():
    # Il golden cita una frase breve, la pipeline estrae il periodo intero:
    # e' il caso normale, e deve contare come trovata.
    voci = ancora(_golden(_voce("la decadenza della banca ex art. 1957 c.c.")), {NODE: MOTIVAZIONE})
    inizio = MOTIVAZIONE.index("Eccepiva altresi'")
    estratte = [{"offset_inizio": inizio, "offset_fine": inizio + 60,
                 "parte_che_la_solleva": "l'opponente", "esito": "accolta"}]
    app, mancate, spurie = appaia(voci, estratte)
    assert (len(app), len(mancate), len(spurie)) == (1, 0, 0)


def test_appaia_e_uno_a_uno():
    # Due coppie estratte sulla stessa eccezione: una trovata, una spuria.
    voci = ancora(_golden(_voce("la decadenza della banca ex art. 1957 c.c.")), {NODE: MOTIVAZIONE})
    i = voci[0]["inizio"]
    estratte = [{"offset_inizio": i - 5, "offset_fine": i + 10, "parte_che_la_solleva": None, "esito": "accolta"},
                {"offset_inizio": i, "offset_fine": i + 20, "parte_che_la_solleva": None, "esito": "accolta"}]
    app, mancate, spurie = appaia(voci, estratte)
    assert (len(app), len(mancate), len(spurie)) == (1, 0, 1)


def test_appaia_ignora_le_coppie_senza_offset():
    voci = ancora(_golden(_voce("la decadenza della banca ex art. 1957 c.c.")), {NODE: MOTIVAZIONE})
    app, mancate, spurie = appaia(voci, [{"offset_inizio": None, "offset_fine": None}])
    assert (len(app), len(mancate), len(spurie)) == (0, 1, 0)


# --- Punteggio ------------------------------------------------------------

def _estrazione(coppie):
    return [{"node_id": NODE, "coppie": coppie}]


def test_valuta_recall_e_precisione():
    g = _golden(
        _voce("la nullita' della fideiussione per vessatorieta'"),
        _voce("la decadenza della banca ex art. 1957 c.c."),
    )
    i = MOTIVAZIONE.index("la nullita'")
    esito = valuta(g, {NODE: MOTIVAZIONE}, _estrazione([
        {"offset_inizio": i, "offset_fine": i + 20, "parte_che_la_solleva": "l'opponente", "esito": "accolta"},
        {"offset_inizio": 0, "offset_fine": 5, "parte_che_la_solleva": None, "esito": "rigettata"},
    ]))
    assert esito["trovate"] == 1 and esito["mancate"] == 1 and esito["spurie"] == 1
    assert esito["recall"] == 0.5
    assert esito["precisione"] == 0.5


def test_valuta_conta_lato_ed_esito_solo_sulle_trovate():
    g = _golden(_voce("la decadenza della banca ex art. 1957 c.c.", parte="opponente", esito="accolta"))
    i = MOTIVAZIONE.index("la decadenza")
    esito = valuta(g, {NODE: MOTIVAZIONE}, _estrazione([
        {"offset_inizio": i, "offset_fine": i + 10, "parte_che_la_solleva": "la banca", "esito": "rigettata"},
    ]))
    assert esito["trovate"] == 1
    assert esito["lato_corretto_su_trovate"] == 0.0
    assert esito["esito_corretto_su_trovate"] == 0.0
    assert esito["esiti_confusi"] == {"accolta -> rigettata": 1}


def test_valuta_segnala_un_documento_non_processato():
    g = _golden(_voce("la decadenza della banca ex art. 1957 c.c."))
    esito = valuta(g, {NODE: MOTIVAZIONE}, [])
    assert esito["per_documento"][0]["stato"] == "non processato dalla corsa"
    assert esito["golden_valutate"] == 0
