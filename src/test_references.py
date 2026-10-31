"""Test di references.py.

Il modulo non ne aveva: le sue forme erano fissate solo dai testi di
Normattiva su cui era stato scritto. Questi test fissano prima il
comportamento PREESISTENTE (guardia contro le regressioni), poi le forme
delle motivazioni aggiunte il 2026-08-30.

Le frasi sono copiate dalle 629 motivazioni BdP reali, non inventate:
ognuna corrisponde a un riferimento che prima si perdeva.
"""

import references
from references import _normalize_numero, _normalize_qualifier, estrai_riferimenti


def _uno(testo):
    """Il solo riferimento atteso nel testo, come (numero, codice)."""
    trovati = estrai_riferimenti(testo)
    assert len(trovati) == 1, f"attesi 1, trovati {len(trovati)}: {trovati}"
    return trovati[0].numero_target, trovati[0].codice_target


# --- Guardia sul comportamento preesistente ------------------------------
# Se una di queste cade, l'estensione del 2026-08-30 ha rotto qualcosa che
# funzionava, e il grafo degli articoli (5442 archi) ne risente.

def test_forma_canonica_codice_civile():
    assert _uno("ai sensi dell'art. 1957 c.c. il fideiussore") == ("1957", "codice_civile")


def test_forma_canonica_codice_procedura_civile():
    assert _uno("il termine dell'art. 645 c.p.c. decorre") == ("645", "codice_procedura_civile")


def test_forma_canonica_per_esteso():
    assert _uno("l'art. 2697 del codice civile") == ("2697", "codice_civile")


def test_forma_canonica_tub_con_punti():
    assert _uno("la certificazione ex art. 50 t.u.b. fa fede") == ("50", "tub")


def test_riferimento_senza_qualificatore_resta_senza():
    # Il caso che NON va indovinato: nessun codice nel testo, nessun codice
    # in uscita. È l'invariante su cui poggia la scelta di scartare i
    # riferimenti nudi (vedi bdp_archi_citazioni.py).
    assert _uno("si applica l'art. 1957 al caso di specie") == ("1957", None)


def test_e_seguenti_resta_un_solo_riferimento():
    (rif,) = estrai_riferimenti("gli artt. 1241 e seguenti c.c.")
    assert (rif.numero_target, rif.codice_target, rif.has_seguenti) == ("1241", "codice_civile", True)


def test_suffisso_con_spazio():
    assert _uno("deciso ex art. 281 sexies c.p.c.") == ("281-sexies", "codice_procedura_civile")


def test_suffisso_attaccato():
    # Igiene aggiunta nella stessa sessione: senza, non risolve su nulla.
    assert _uno("deciso ex art. 281sexies c.p.c.") == ("281-sexies", "codice_procedura_civile")


# --- Il ponte di sottoarticolazione ---------------------------------------
# Causa maggiore dei riferimenti persi: 1477 riferimenti nudi su 5680 hanno
# un ", comma N" fra il numero e il codice.

def test_ponte_comma_semplice():
    assert _uno("per effetto dell'art. 117, comma 3, del d.lgs. n. 385 del 1993") == ("117", "tub")


def test_ponte_comma_senza_virgola_finale():
    assert _uno("ex art. 1227, comma 1 c.c., in ogni caso") == ("1227", "codice_civile")


def test_ponte_comma_abbreviato():
    assert _uno("inammissibile ex art. 331, co. 2 c.p.c., per non aver") == ("331", "codice_procedura_civile")


def test_ponte_comma_e_lettera():
    assert _uno("violazione degli artt. 2, comma 2, lett. a) L. 287/1990") == ("2", "l_287_1990")


def test_ponte_lettera_per_esteso():
    assert _uno("contrasto con l'art. 2, comma 2, lettera a) della legge n. 287/1990") == ("2", "l_287_1990")


def test_ponte_su_piu_frammenti():
    assert _uno("l'art. 121, comma 1, lett. m) t.u.b. definisce") == ("121", "tub")


def test_il_ponte_non_scavalca_una_citazione_diversa():
    # La proprietà che rende il ponte sicuro: è un elenco chiuso di
    # frammenti, non testo libero. "e poi si applica" non è un frammento di
    # sottoarticolazione, quindi l'art. 5 NON deve prendersi il c.p.c.
    # dell'art. 645.
    trovati = estrai_riferimenti("l'art. 5 e poi si applica l'art. 645 c.p.c.")
    assert len(trovati) == 2
    assert (trovati[0].numero_target, trovati[0].codice_target) == ("5", None)
    assert (trovati[1].numero_target, trovati[1].codice_target) == ("645", "codice_procedura_civile")


def test_il_ponte_non_inventa_su_una_frase_qualunque():
    assert _uno("l'art. 3, in quanto norma generale, non rileva") == ("3", None)


# --- Grafie del codice non canoniche --------------------------------------

def test_tub_senza_punti():
    # 849 occorrenze: la singola forma più frequente fra quelle perse.
    assert _uno("la certificazione ex art. 50 TUB rilasciata dalla banca") == ("50", "tub")


def test_cod_civ_per_esteso():
    assert _uno("prescritti in via generale dall'art. 1264 cod. civ., ma non") == ("1264", "codice_civile")


def test_cod_civ_senza_spazi():
    assert _uno("Ai sensi dell'art. 2697 cod.civ., l'onere della prova") == ("2697", "codice_civile")


def test_cod_civ_senza_punti():
    assert _uno("ai sensi dell'art. 2043 cod civ, al risarcimento") == ("2043", "codice_civile")


def test_cod_proc_civ_per_esteso():
    assert _uno("giudizio di opposizione ex art. 645 cod. proc. civ.") == ("645", "codice_procedura_civile")


def test_cod_proc_civ_vince_su_cod_civ():
    # L'ordine delle alternative conta: "cod. civ." combacerebbe sul
    # prefisso di "cod. proc. civ." e attribuirebbe al codice civile una
    # citazione del codice di rito.
    assert _uno("a norma dell'art. 383 cod.proc.civ., il giudizio") == ("383", "codice_procedura_civile")


def test_cpc_senza_punti():
    assert _uno("rinviato ex art 352 cpc al 26/1/2026") == ("352", "codice_procedura_civile")


def test_cpc_con_punto_finale():
    assert _uno("soccombenza ex art. 91 cpc. Il giudizio si conclude") == ("91", "codice_procedura_civile")


def test_tub_citato_per_numero_di_decreto():
    assert _uno("i requisiti previsti dall'art. 58 del D.Lgs. 385/1993") == ("58", "tub")


def test_tub_citato_per_numero_di_decreto_esteso():
    assert _uno("la disciplina di cui all'art. 58 d.lgs. n. 385/1993, colui che") == ("58", "tub")


def test_dlgs_150_2011_non_confuso_con_385_1993():
    # Le due voci per numero di decreto convivono: quella preesistente non
    # deve essere assorbita da quella nuova.
    assert _uno("il rito dell'art. 14 del d.lgs. 150/2011") == ("14", "dlgs_150_2011")


# --- Rinvii fra codici diversi nei testi di Normattiva --------------------
# Non vengono dalle motivazioni ma dagli articoli, e sono i 12 casi che il
# ponte ripara nel grafo degli articoli: senza, il qualificatore andava
# perso, il riferimento veniva risolto sullo STESSO codice della fonte, e
# l'arco spariva perche' quell'articolo li' non esiste.

def test_rinvio_del_codice_della_crisi_al_codice_civile():
    assert _uno(
        "i crediti assistiti dal privilegio di cui all'articolo 2751-bis, n. 1, "
        "del codice civile, sono soddisfatti in denaro"
    ) == ("2751-bis", "codice_civile")


def test_rinvio_con_piu_commi_elencati():
    assert _uno(
        "in deroga all'articolo 2112, commi 1, 3 e 4, del codice civile"
    ) == ("2112", "codice_civile")


def test_rinvio_del_tub_al_codice_civile():
    assert _uno(
        "o di cui all'articolo 2483, comma 3, del codice civile nonche' la somma"
    ) == ("2483", "codice_civile")


def test_rinvio_del_dpr_602_al_codice_di_rito():
    assert _uno(
        "Nei casi previsti dall'art. 140, del codice di procedura civile, la notificazione"
    ) == ("140", "codice_procedura_civile")


# --- Normalizzatori --------------------------------------------------------

def test_normalize_numero_spazio_e_attaccato():
    assert _normalize_numero("129 bis") == "129-bis"
    assert _normalize_numero("125bis") == "125-bis"
    assert _normalize_numero("125-bis") == "125-bis"


def test_normalize_numero_non_tocca_un_numero_semplice():
    assert _normalize_numero("1957") == "1957"


def test_normalize_qualifier_ignora_maiuscole_e_spazi():
    assert _normalize_qualifier("  COD.  CIV. ") == "codice_civile"
    assert _normalize_qualifier("TUB") == "tub"


def test_normalize_qualifier_sconosciuto_e_none():
    assert _normalize_qualifier("codice della strada") is None
    assert _normalize_qualifier(None) is None


def test_ogni_chiave_della_mappa_e_normalizzata():
    # Una chiave scritta con una maiuscola o uno spazio doppio non verrebbe
    # mai trovata da _normalize_qualifier: sarebbe codice morto silenzioso.
    import re
    for chiave in references.CODE_QUALIFIER_MAP:
        assert chiave == re.sub(r"\s+", " ", chiave.strip().lower()), chiave
