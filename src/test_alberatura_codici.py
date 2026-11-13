"""Test dell'albero dei codici e del suo innesto sui nodi Articolo.

Il grosso gira su wikitext sintetico: le sorgenti vere stanno in `data/`,
che non e' versionata, e un test che si rompe su una macchina appena
clonata non e' un test. I due che le richiedono si saltano da soli.

Cosa proteggono, in ordine di importanza:
1. che una collocazione DEDOTTA non venga mai scambiata per una LETTA;
2. che l'innesto non tocchi il testo di legge ne' il campo `sezione`, che
   sui nodi Articolo significa un'altra cosa e fa parte del node_id;
3. che entrambi i formati di articolo di Wikisource siano riconosciuti -
   saltare il secondo lascerebbe fuori l'intero libro dell'esecuzione.
"""

import pickle
from pathlib import Path

import networkx as nx
import pytest

from alberatura_codici import (
    carica_albero_cc,
    leggi_sottopagina_cc,
    FONTE_DEDOTTA,
    FONTE_LETTA,
    SORGENTI,
    carica_albero_cpc,
    colloca,
    leggi_wikitext,
    normalizza_numero,
    numero_base,
)
from arricchisci_alberatura import arricchisci

# Un libro in miniatura con ENTRAMBI i formati: gli articoli 1 e 2 come
# heading (forma dei libri I e II), il 633 come riga di testo (forma dei
# libri III e IV).
WIKITEXT = """{{Qualità|avz=75%|data=27 marzo 2010|arg=diritto}}

=Libro primo: DISPOSIZIONI GENERALI=

==Titolo I: DEGLI ORGANI GIUDIZIARI==

===Capo I: DEL GIUDICE===

====Sezione I: DELLA GIURISDIZIONE====

=====Art. 1 (Giurisdizione dei giudici ordinari) =====
La giurisdizione civile e' esercitata dai giudici ordinari.

=====''[abrogato]'' Art. 2 (Inderogabilita') =====
Testo dell'articolo abrogato.

==Titolo VI: DEGLI ATTI PROCESSUALI==

===Capo I: DELLE FORME DEGLI ATTI===

=====Art. 125 (Contenuto degli atti di parte) =====
Salvo che la legge disponga altrimenti.

=Libro Quarto: DEI PROCEDIMENTI SPECIALI=

==Titolo I: DEI PROCEDIMENTI SOMMARI==

===Capo I: DEL PROCEDIMENTO DI INGIUNZIONE===

Art. 633 Condizioni di ammissibilita'
Su domanda di chi e' creditore di una somma liquida.

Art. 650 Opposizione tardiva
L'intimato puo' fare opposizione anche dopo scaduto il termine.
"""


@pytest.fixture
def albero():
    return leggi_wikitext(WIKITEXT)


# --- Lettura del wikitext -------------------------------------------------

def test_riconosce_gli_articoli_scritti_come_heading(albero):
    assert albero["1"]["capo"] == "Capo I: DEL GIUDICE"
    assert albero["1"]["sezione"] == "Sezione I: DELLA GIURISDIZIONE"


def test_riconosce_gli_articoli_scritti_come_riga_di_testo(albero):
    # I libri III e IV usano questa forma: saltarla lascerebbe fuori
    # l'esecuzione e i procedimenti speciali, cioe' proprio gli articoli
    # da cui dipende il tipo di atto.
    assert albero["633"]["capo"] == "Capo I: DEL PROCEDIMENTO DI INGIUNZIONE"
    assert albero["650"]["capo"] == "Capo I: DEL PROCEDIMENTO DI INGIUNZIONE"


def test_un_articolo_abrogato_resta_collocato(albero):
    # Il marcatore ''[abrogato]'' non deve impedire la collocazione: un
    # articolo abrogato oggi era in vigore quando le sentenze lo citavano.
    assert albero["2"]["capo"] == "Capo I: DEL GIUDICE"


def test_il_contesto_si_azzera_ai_livelli_superiori(albero):
    # Passando da "Titolo I > Capo I > Sezione I" a "Titolo VI > Capo I",
    # la Sezione del titolo precedente non deve sopravvivere.
    assert "sezione" not in albero["125"]
    assert albero["125"]["titolo"] == "Titolo VI: DEGLI ATTI PROCESSUALI"


def test_il_libro_cambia_e_il_resto_si_azzera(albero):
    assert albero["633"]["libro"] == "Libro Quarto: DEI PROCEDIMENTI SPECIALI"
    assert albero["633"]["titolo"] == "Titolo I: DEI PROCEDIMENTI SOMMARI"


def test_il_problema_di_partenza_e_risolto(albero):
    # E' l'intera ragione di questo modulo: il grafo deve poter distinguere
    # una norma che DEFINISCE un atto da una che ne regola la FORMA.
    assert albero["650"]["capo"] != albero["125"]["capo"]
    assert "INGIUNZIONE" in albero["650"]["capo"]
    assert "FORME DEGLI ATTI" in albero["125"]["capo"]


# --- Normalizzazione ------------------------------------------------------

def test_normalizza_numero():
    assert normalizza_numero("281 decies") == "281-decies"
    assert normalizza_numero(" 650 ") == "650"
    assert normalizza_numero("171-TER") == "171-ter"


def test_numero_base():
    assert numero_base("171-ter") == "171"
    assert numero_base("650") == "650"
    assert numero_base("281-duodecies") == "281"


# --- Collocazione e provenienza ------------------------------------------

def test_collocazione_letta_e_marcata_come_tale(albero):
    collocati, non_collocati = colloca({"650"}, albero)
    assert collocati["650"]["fonte"] == FONTE_LETTA
    assert "dedotta_da" not in collocati["650"]
    assert non_collocati == []


def test_collocazione_per_adiacenza_e_marcata_come_dedotta(albero):
    # 633-bis non c'e' nella fonte (e' un articolo posteriore): eredita il
    # capo del 633, ma la differenza DEVE restare visibile sul dato.
    collocati, _ = colloca({"633-bis"}, albero)
    assert collocati["633-bis"]["capo"] == albero["633"]["capo"]
    assert collocati["633-bis"]["fonte"] == FONTE_DEDOTTA
    assert collocati["633-bis"]["dedotta_da"] == "art. 633"


def test_un_articolo_senza_base_nella_fonte_non_si_colloca(albero):
    collocati, non_collocati = colloca({"999", "999-bis"}, albero)
    assert collocati == {}
    assert sorted(non_collocati) == ["999", "999-bis"]


def test_l_adiacenza_non_si_applica_a_un_numero_semplice(albero):
    # "999" non deve trovare una base diversa da se stesso.
    _, non_collocati = colloca({"999"}, albero)
    assert non_collocati == ["999"]


# --- Innesto sul grafo ----------------------------------------------------

def _grafo_con_articoli(*numeri) -> nx.MultiDiGraph:
    g = nx.MultiDiGraph()
    for numero in numeri:
        g.add_node(f"codice_procedura_civile::{numero}",
                   codice="codice_procedura_civile", numero=numero,
                   rubrica="r", testo="il testo di legge", testo_raw="il testo ((di legge))",
                   sezione="CODICE DI PROCEDURA CIVILE", is_main_body=True,
                   abrogato=False, citazione_breve=f"art. {numero} c.p.c.", source_url="u")
    return g


def test_innesto_scrive_alberatura_solo_dove_si_colloca(albero):
    g = _grafo_con_articoli("650", "999")
    esito = arricchisci(g, albero)
    assert "alberatura" in g.nodes["codice_procedura_civile::650"]
    # l'assenza e' piu' onesta di un valore nullo
    assert "alberatura" not in g.nodes["codice_procedura_civile::999"]
    assert esito["non_collocati"] == ["999"]


def test_innesto_non_tocca_il_testo_di_legge(albero):
    # E' il controllo 4 di promuovi_grafo.py, verificato qui a monte.
    g = _grafo_con_articoli("650")
    prima = dict(g.nodes["codice_procedura_civile::650"])
    arricchisci(g, albero)
    dopo = g.nodes["codice_procedura_civile::650"]
    for campo in ("testo", "testo_raw", "rubrica", "numero", "codice",
                  "is_main_body", "abrogato", "citazione_breve"):
        assert dopo[campo] == prima[campo], campo


def test_innesto_non_tocca_il_campo_sezione(albero):
    # `sezione` sui nodi Articolo e' la sezione del markdown di Normattiva e
    # fa parte del node_id degli articoli fuori dal corpo principale:
    # sovrascriverla cambierebbe l'identita' dei nodi.
    g = _grafo_con_articoli("1")
    arricchisci(g, albero)
    nodo = g.nodes["codice_procedura_civile::1"]
    assert nodo["sezione"] == "CODICE DI PROCEDURA CIVILE"
    assert nodo["alberatura"]["sezione"] == "Sezione I: DELLA GIURISDIZIONE"


def test_innesto_conta_le_due_provenienze_separatamente(albero):
    g = _grafo_con_articoli("650", "633-bis")
    esito = arricchisci(g, albero)
    assert esito["da_wikisource"] == 1
    assert esito["per_adiacenza"] == 1
    assert esito["collocati"] == 2


def test_innesto_ignora_gli_altri_codici(albero):
    g = _grafo_con_articoli("650")
    g.add_node("codice_civile::650", codice="codice_civile", numero="650",
               testo="x", testo_raw="x", sezione="CODICE CIVILE", is_main_body=True)
    arricchisci(g, albero)
    assert "alberatura" not in g.nodes["codice_civile::650"]


# --- Sulle sorgenti vere, se ci sono --------------------------------------

_sorgenti_assenti = not (SORGENTI / "codice_procedura_civile_libro_primo.wikitext").is_file()
saltare = pytest.mark.skipif(_sorgenti_assenti,
                             reason="sorgenti Wikisource assenti (data/ non e' versionata)")


@saltare
def test_sorgenti_vere_coprono_i_quattro_libri():
    albero = carica_albero_cpc()
    libri = {p["libro"] for p in albero.values() if "libro" in p}
    assert len(libri) == 4, libri
    assert len(albero) > 900


@saltare
def test_sorgenti_vere_gli_articoli_che_definiscono_gli_atti():
    albero = carica_albero_cpc()
    assert "INGIUNZIONE" in albero["645"]["capo"].upper()
    assert "OPPOSIZIONI" in albero["615"]["capo"].upper()
    assert "IMPUGNAZIONI" in albero["342"]["titolo"].upper()
    assert "FORME DEGLI ATTI" in albero["125"]["capo"].upper()


# --- Codice civile: sottopagine per titolo, non pagine per libro ----------

WIKITEXT_CC = """{{Qualità|avz=25%}}
==Capo XXII: Della fideiussione==
===Sezione I: Disposizioni generali===
====Art. 1936 Nozione====
Testo che nomina l'Art. 1470 come rimando, e non deve rubargli la posizione.
====Art. 1937 Volontà di prestare fideiussione====
===Sezione V: Dell'estinzione della fideiussione===
=====Art. 1957 Scadenza dell'obbligazione principale=====
==Capo XXIII: Del mandato==
=====Art. 1703 Nozione=====
"""


def test_cc_capo_e_sezione_dal_prefisso_non_dal_livello():
    """Nelle sottopagine del c.c. il livello dell'heading non e' il livello
    dell'albero: gli articoli stanno a `====` in certe pagine e a `=====` in
    altre, e capo/sezione sono `==`/`===`. Si classifica per prefisso."""
    albero = leggi_sottopagina_cc(WIKITEXT_CC, "Libro IV", "Titolo III")

    assert albero["1936"] == {
        "libro": "Libro IV", "titolo": "Titolo III",
        "capo": "Capo XXII: Della fideiussione",
        "sezione": "Sezione I: Disposizioni generali",
    }
    # articolo a cinque livelli nella stessa pagina: stesso trattamento
    assert albero["1957"]["sezione"].startswith("Sezione V")


def test_cc_un_nuovo_capo_azzera_la_sezione():
    albero = leggi_sottopagina_cc(WIKITEXT_CC, "Libro IV", "Titolo III")

    assert albero["1703"]["capo"] == "Capo XXIII: Del mandato"
    assert "sezione" not in albero["1703"]


def test_cc_i_rimandi_nel_corpo_non_collocano_nulla():
    """Il difetto trovato il 2026-08-31: accettando anche le righe di corpo
    che cominciano per "Art. N", un rimando letto da una pagina che viene
    prima in ordine alfabetico rubava la collocazione all'articolo vero, e
    art. 1936 finiva senza `capo`."""
    albero = leggi_sottopagina_cc(WIKITEXT_CC, "Libro IV", "Titolo III")

    assert "1470" not in albero


def test_cc_libro_e_titolo_vengono_dal_nome_della_pagina():
    """Non compaiono nel wikitext: sono l'identita' della sottopagina."""
    albero = leggi_sottopagina_cc(WIKITEXT_CC, "Libro II", "Titolo IV")

    assert albero["1936"]["libro"] == "Libro II"
    assert albero["1936"]["titolo"] == "Titolo IV"


_cc_assenti = not list(SORGENTI.glob("codice_civile_Libro_*.wikitext"))
saltare_cc = pytest.mark.skipif(_cc_assenti,
                                reason="sottopagine del c.c. assenti (data/ non e' versionata)")


@saltare_cc
def test_sorgenti_vere_cc_la_fideiussione_ha_un_capo_proprio():
    """Al solo livello di TITOLO la fideiussione finirebbe in "Dei singoli
    contratti" con altri 516 articoli: e' il motivo per cui servono le
    sottopagine e non basta la pagina indice."""
    albero = carica_albero_cc()

    assert "FIDEIUSSIONE" in albero["1936"]["capo"].upper()
    assert "FIDEIUSSIONE" in albero["1957"]["capo"].upper()
    assert albero["1470"]["capo"] != albero["1936"]["capo"]


@saltare_cc
def test_sorgenti_vere_cc_copre_i_sei_libri():
    albero = carica_albero_cc()
    libri = {p["libro"] for p in albero.values() if "libro" in p}

    assert len(libri) == 6, libri
    assert len(albero) > 2900
