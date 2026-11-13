"""I vizi della fideiussione - famiglia 5.

Seconda del corpus per volume e la prima con una quota di accoglimento
bassa: e' la prima famiglia in cui la regola confuta davvero, invece di
avvertire. Per questo i test guardano soprattutto due cose - che il
contro-argomento non ecceda cio' che il dato regge, e che i rami fondati
su sei o dieci casi non esistano.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import motore_regole as mr  # noqa: E402
import vizi_della_fideiussione as vf  # noqa: E402

FAMIGLIA = mr.Famiglia.VIZI_FIDEIUSSIONE


def _applica(**campi) -> mr.RisultatoRegola:
    campi.setdefault("natura_rapporto", "conto_corrente")
    return mr.applica_regola(FAMIGLIA, mr.Precondizioni(**campi))


# --- lo schema ABI: l'unico ramo che confuta con una fonte -------------

def test_lo_schema_abi_si_confuta():
    esito = _applica(vizio_fideiussione="schema_abi")
    assert esito.fondata is False
    assert esito.contro_argomento
    assert [f.citazione_breve for f in esito.fonti] == ["art. 1419 c.c."]


def test_il_contro_argomento_attacca_la_conseguenza_non_la_premessa():
    """Non nega che le clausole siano nulle: nega che la nullita' di
    alcune clausole travolga l'intera garanzia. E' la distinzione su cui
    l'argomento sta in piedi."""
    contro = _applica(vizio_fideiussione="schema_abi").contro_argomento
    assert "non travolge il contratto" in contro
    assert "L'obbligazione di garanzia resta" in contro


def test_non_si_citano_le_sezioni_unite_che_non_abbiamo():
    """41994/2021 non e' nel corpus. Una regola che la citasse
    dichiarerebbe una fonte mai verificata - e la nota lo scrive invece
    di tacerlo."""
    esito = _applica(vizio_fideiussione="schema_abi")
    assert all("41994" not in f.citazione_breve for f in esito.fonti)
    assert "41994/2021" in esito.nota and "non sono nel nostro corpus" in esito.nota


def test_la_nota_dichiara_la_numerosita_e_nega_la_previsione():
    nota = _applica(vizio_fideiussione="schema_abi").nota
    assert "24 rigetti su 27" in nota
    assert "non una previsione su questa causa" in nota


# --- l'art. 1957: qui l'eccezione regge --------------------------------

def test_la_decadenza_fa_reggere_l_eccezione():
    esito = _applica(vizio_fideiussione="decadenza")
    assert esito.fondata is True
    assert esito.contro_argomento is None and esito.fonti == []


def test_quando_regge_la_nota_indica_i_due_fatti_da_cercare():
    nota = _applica(vizio_fideiussione="decadenza").nota
    assert "clausola di deroga" in nota
    assert "nel termine" in nota
    assert "NOSTRO fascicolo" in nota


# --- i rami che NON esistono, e devono non esistere ---------------------

def test_i_vizi_con_pochi_casi_non_hanno_un_ramo():
    """Sei casi per l'art. 1938 e nove per l'art. 1956: un rigetto su sei
    casi e' un aneddoto, non una regola. La regola lo dice e si ferma."""
    for vizio in ("importo_massimo", "liberazione", "disconoscimento"):
        esito = _applica(vizio_fideiussione=vizio)
        assert esito.fondata is False
        assert esito.contro_argomento is None
        assert "aneddoto" in esito.nota


def test_il_vizio_ignoto_non_decide():
    esito = _applica(vizio_fideiussione=None)
    assert esito.contro_argomento is None
    assert "non nomina un vizio riconoscibile" in esito.nota


# --- la genericita', che vale solo dove non c'e' un vizio nominato ------

def test_la_deduzione_generica_si_confuta():
    esito = _applica(vizio_fideiussione=None, specificita_eccezione="generica")
    assert esito.contro_argomento
    assert {f.citazione_breve for f in esito.fonti} == {"art. 2697 c.c.", "art. 1419 c.c."}


def test_un_vizio_nominato_batte_la_genericita():
    """Se l'eccezione nomina lo schema ABI, il ramo giusto e' quello -
    anche se il modello l'ha etichettata generica. Il vizio e' un fatto
    del testo, la specificita' e' un giudizio."""
    esito = _applica(vizio_fideiussione="schema_abi", specificita_eccezione="generica")
    assert "art. 1419 c.c." in [f.citazione_breve for f in esito.fonti]
    assert "schema ABI" in esito.nota


def test_la_qualita_del_fideiussore_non_cambia_nulla():
    """SUPERFICIE_ATTACCO.md la indicava come precondizione; sul corpus
    non separa niente, ed e' il campo che il modello asserisce senza che
    nulla lo verifichi. Se un giorno contasse, questo test va riscritto -
    non cancellato."""
    esiti = {_applica(vizio_fideiussione="schema_abi", qualita_fideiussore=q).contro_argomento
             for q in ("socio", "amministratore", "terzo_estraneo", "consumatore",
                       "non_desumibile")}
    assert len(esiti) == 1


# --- l'invariante di tutte le regole ------------------------------------

def test_nessun_ramo_promette_una_confutazione_che_non_ha():
    for campi in ({"vizio_fideiussione": "schema_abi"},
                  {"vizio_fideiussione": "decadenza"},
                  {"vizio_fideiussione": "importo_massimo"},
                  {"vizio_fideiussione": None},
                  {"vizio_fideiussione": None, "specificita_eccezione": "generica"}):
        esito = _applica(**campi)
        if esito.contro_argomento is None:
            assert esito.fonti == [], campi


# --- il rilevatore ------------------------------------------------------

def test_riconosce_i_cinque_vizi():
    casi = {
        "schema_abi": "la fideiussione riproduce lo schema ABI dichiarato nullo dal "
                      "provvedimento della Banca d'Italia n. 55/2005",
        "decadenza": "la garanzia e' inefficace per decadenza ex art. 1957 c.c., non "
                     "essendo state proposte le istanze nel termine",
        "liberazione": "il fideiussore e' liberato ai sensi dell'art. 1956 c.c.",
        "importo_massimo": "la fideiussione omnibus e' nulla per mancanza "
                           "dell'importo massimo garantito ex art. 1938 c.c.",
        "disconoscimento": "si disconosce la sottoscrizione apposta in calce alla "
                           "fideiussione",
    }
    for atteso, testo in casi.items():
        assert vf.cerca(testo).principale == atteso, testo[:40]


def test_senza_fideiussione_non_si_cerca_nulla():
    esito = vf.cerca("Si eccepisce la decadenza ex art. 1957 c.c. dal contratto.")
    assert not esito.parla_di_fideiussione and esito.principale is None


def test_piu_vizi_insieme_decidono_per_priorita():
    """Un'eccezione che deduce ABI e 1957 insieme e' comune. Decide
    quello su cui il corpus ha piu' casi, e la spiegazione lo dice."""
    esito = vf.cerca("la fideiussione conforme allo schema ABI e' nulla, e comunque "
                     "e' intervenuta la decadenza ex art. 1957 c.c.")
    assert set(esito.vizi) == {"schema_abi", "decadenza"}
    assert esito.principale == "schema_abi"
    assert "La regola decide su" in esito.perche()


def test_la_spiegazione_negativa_non_dichiara_un_assenza():
    perche = vf.cerca("la fideiussione prestata e' invalida").perche()
    assert "Non e' la prova che non ne deduca uno" in perche


def test_la_famiglia_e_registrata():
    assert FAMIGLIA in mr._REGISTRO


def test_una_garanzia_reale_non_e_una_fideiussione():
    """L'ipoteca e il pegno sono un'altra famiglia: un vizio della
    garanzia reale letto come vizio della fideiussione manderebbe
    l'eccezione al ramo sbagliato."""
    assert not vf.cerca("la garanzia ipotecaria e' nulla per difetto di forma").parla_di_fideiussione
    assert not vf.cerca("si contesta la garanzia reale prestata").parla_di_fideiussione
