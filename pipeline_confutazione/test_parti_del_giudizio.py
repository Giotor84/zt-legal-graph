# -*- coding: utf-8 -*-
"""Chi e' creditore e chi debitore, letto dal testo e non assunto.

Ogni caso qui sotto viene da un provvedimento vero del corpus: le due
inversioni che questi test bloccano erano nel codice, e sono uscite
guardando i disaccordi con la tabella a mano, non ragionando a tavolino.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import parti_del_giudizio as pdg  # noqa: E402


# --- l'epigrafe -----------------------------------------------------------

def test_il_ruolo_si_prende_dal_marcatore_che_chiude_il_blocco():
    inte = ("promossa DA Parte_1 rappresentato dall'avv. Rossi appellante "
            "CONTRO Controparte_1 in persona del legale rappresentante appellata")

    ruoli = pdg.ruoli_delle_parti(inte)

    assert ruoli["Parte_1"]["ruoli"] == ["appellante"]
    assert ruoli["Controparte_1"]["ruoli"] == ["appellato"]


def test_una_parte_puo_avere_piu_ruoli_e_non_e_un_conflitto():
    """`appellata` in questo grado e `opposto` nel monitorio di primo grado
    descrivono la stessa parte in due momenti diversi."""
    inte = "DA Parte_1 appellante CONTRO Controparte_1 appellata, gia' opposto"

    ruoli = pdg.ruoli_delle_parti(inte)

    assert sorted(ruoli["Controparte_1"]["ruoli"]) == ["appellato", "opposto"]


def test_opposto_che_qualifica_il_decreto_non_e_un_ruolo_di_parte():
    """L'inversione peggiore: "il decreto ingiuntivo opposto" non nomina
    nessuno, ma letto come ruolo faceva CREDITORE la parte che gli stava
    accanto - cioe' proprio l'opponente."""
    inte = ("DA Parte_1 che propone opposizione avverso il decreto "
            "ingiuntivo opposto n. 462/2015 opponente")

    ruoli = pdg.ruoli_delle_parti(inte)

    assert ruoli["Parte_1"]["ruoli"] == ["opponente"], (
        "e' tornata l'inversione: 'opposto' aggettivo del decreto letto come parte")


def test_una_parte_troppo_lontana_dal_marcatore_non_gli_appartiene():
    inte = "DA Parte_1 " + ("procura e domicilio " * 200) + " appellante"

    ruoli = pdg.ruoli_delle_parti(inte)

    assert ruoli["Parte_1"]["ruoli"] == [], (
        "oltre la distanza massima in mezzo c'e' quasi sempre un'altra parte")


# --- il dispositivo -------------------------------------------------------

def test_chi_paga_e_chi_incassa_si_separano_anche_sul_dativo():
    """"condanna l'opposta al pagamento all'opponente delle spese": senza
    riconoscere il dativo finivano obbligate tutte e due le parti,
    compresa quella che aveva vinto."""
    disp = "Condanna Controparte_1 al pagamento a Parte_1 delle spese di giudizio"

    trovate = pdg.condanne(disp)

    assert trovate[0]["obbligati"] == ["Controparte_1"]
    assert trovate[0]["beneficiari"] == ["Parte_1"]


def test_la_condanna_alle_spese_non_e_una_condanna_a_pagare_un_debito():
    """Individua il soccombente. Confonderla con il debito significa dare
    del debitore a chiunque perda una causa."""
    disp = "Condanna Parte_1 alla rifusione delle spese di lite in favore di CP_1"

    trovate = pdg.condanne(disp)

    assert trovate[0]["spese"] is True


def test_rimborso_sta_con_le_spese_non_con_la_restituzione():
    """Misurato sui dispositivi del corpus: 307 volte su 422 "rimborso" e'
    accompagnato da "spese". Trattarlo come restituzione dell'indebito
    rovescerebbe il lato in tre casi su quattro."""
    disp = "condanna gli attori in opposizione al rimborso in favore della convenuta"

    trovate = pdg.condanne(disp)

    assert trovate[0]["spese"] is True
    assert trovate[0]["restituzione"] is False


def test_chi_restituisce_e_il_creditore_del_rapporto():
    """Il verso si rovescia rispetto all'intuizione: chi restituisce e' chi
    aveva incassato indebitamente."""
    disp = ("condanna Controparte_1 alla restituzione in favore di Parte_1 "
            "della somma di euro 12.000")

    parti = pdg.lati_delle_parti("DA Parte_1 attore CONTRO Controparte_1 convenuta", disp)

    assert parti["Controparte_1"]["lato"] == pdg.CREDITORE
    assert parti["Parte_1"]["lato"] == pdg.DEBITORE


# --- i criteri ------------------------------------------------------------

def test_nel_monitorio_il_ruolo_basta():
    """Chi ottiene il decreto e' il creditore ricorrente, chi lo subisce e'
    l'ingiunto. Non e' un'inferenza, e' la struttura del procedimento."""
    inte = "DA Parte_1 opponente CONTRO Controparte_1 opposta"

    parti = pdg.lati_delle_parti(inte, "")

    assert parti["Parte_1"]["lato"] == pdg.DEBITORE
    assert parti["Controparte_1"]["lato"] == pdg.CREDITORE
    assert parti["Parte_1"]["criteri"] == ["ruolo_nel_monitorio"]


def test_una_condanna_a_pagare_senza_monitorio_non_decide_il_lato():
    """La banca condannata a risarcire e' debitrice di QUELLA obbligazione
    e resta creditrice del rapporto. Senza un decreto ingiuntivo in causa
    non si sa quale delle due cose stia dicendo il dispositivo."""
    disp = "condanna Controparte_1 al pagamento in favore di Parte_1 di euro 5.000"

    parti = pdg.lati_delle_parti("DA Parte_1 attore CONTRO Controparte_1 convenuta", disp)

    assert parti["Controparte_1"]["lato"] is None
    assert parti["Controparte_1"]["solo_registrato"] == ["obbligazione_decisa_senza_monitorio"]


def test_con_il_monitorio_in_causa_la_condanna_a_pagare_decide():
    disp = ("revoca il decreto ingiuntivo e condanna Parte_1 al pagamento "
            "in favore di Controparte_1 della somma di euro 5.000")

    parti = pdg.lati_delle_parti("DA Parte_1 attore CONTRO Controparte_1 convenuta", disp)

    assert parti["Parte_1"]["lato"] == pdg.DEBITORE
    assert parti["Controparte_1"]["lato"] == pdg.CREDITORE


def test_soccombenza_e_direzione_insieme_danno_il_lato():
    """Presa da sola la condanna alle spese dice solo chi ha perso. Con la
    direzione del dispositivo i due fatti insieme danno il lato, e nessuno
    dei due e' un'inferenza."""
    disp = ("rigetta l'opposizione e condanna Parte_1 alle spese di lite")

    parti = pdg.lati_delle_parti("DA Parte_1 attore CONTRO Controparte_1 convenuta", disp)

    assert parti["Parte_1"]["lato"] == pdg.DEBITORE
    assert "soccombenza_e_direzione" in parti["Parte_1"]["criteri"]


def test_criteri_discordi_non_scelgono_un_lato():
    """Una controdeduzione presa dalla parte sbagliata e' un errore
    invisibile, e vale meno di un'astensione dichiarata."""
    inte = "DA Parte_1 opponente CONTRO Controparte_1 opposta"
    disp = ("revoca il decreto ingiuntivo e condanna Controparte_1 al pagamento "
            "in favore di Parte_1 della somma di euro 100")

    parti = pdg.lati_delle_parti(inte, disp)

    assert parti["Parte_1"]["lato"] is None
    assert parti["Parte_1"]["fiducia"] == "discordi"
    assert len(parti["Parte_1"]["prove"]) >= 2, "le prove di entrambi i criteri restano"


# --- la direzione ---------------------------------------------------------

def test_la_direzione_si_legge_dalle_formule_del_dispositivo():
    assert pdg.direzione("revoca il decreto ingiuntivo opposto")["verso"] == pdg.DEBITORE
    assert pdg.direzione("rigetta l'opposizione")["verso"] == pdg.CREDITORE


def test_due_formule_concordi_alzano_la_fiducia():
    esito = pdg.direzione("accoglie l'opposizione e revoca il decreto ingiuntivo")

    assert esito["verso"] == pdg.DEBITORE
    assert esito["fiducia"] == "concordi"


def test_formule_di_verso_opposto_si_dichiarano_miste():
    """Accade davvero: accoglimento parziale, o piu' decreti nella stessa
    causa. Dichiararlo misto e' l'unica lettura onesta."""
    esito = pdg.direzione("accoglie l'opposizione di Parte_1 e rigetta l'opposizione di Parte_2")

    assert esito["verso"] is None
    assert esito["fiducia"] == "misto"
    assert len(esito["prove"]) == 2


# --- risolvere come il modello ha chiamato la parte -----------------------

def test_lo_pseudonimo_e_una_chiave_non_un_nome_perduto():
    """Il corpus e' anonimizzato, ma "Parte_1" e' STABILE dentro il
    documento: e' risolvibile contro l'epigrafe dello stesso documento.
    Sono 1053 righe del corpus che sembravano perse."""
    parti = pdg.lati_delle_parti("DA Parte_1 opponente CONTRO CP_1 opposta", "")

    assert pdg.risolvi_parte("Parte_1", parti)["lato"] == pdg.DEBITORE


def test_il_ruolo_nel_monitorio_risponde_anche_senza_epigrafe():
    """"l'opponente" dice gia' tutto: e' l'ingiunto, e lo e' anche quando
    l'epigrafe lo chiama attore."""
    esito = pdg.risolvi_parte("l'opponente", {})

    assert esito["lato"] == pdg.DEBITORE
    assert esito["motivo"] == "dal_ruolo_nel_monitorio:opponente"


def test_un_ruolo_rivestito_da_parti_di_lato_diverso_resta_ambiguo():
    parti = {
        "Parte_1": {"ruoli": ["appellante"], "lato": "debitore", "fiducia": "x", "criteri": []},
        "Parte_2": {"ruoli": ["appellante"], "lato": "creditore", "fiducia": "x", "criteri": []},
    }

    assert pdg.risolvi_parte("gli appellanti", parti)["motivo"] == "ruolo_ambiguo:appellante"


def test_una_parte_vera_risponde_prima_della_chiave_di_lavoro():
    """Le voci `ruolo:` servono a portare una condanna espressa per ruolo
    fino alle parti che quel ruolo lo rivestono. Se rispondessero al posto
    loro, un dispositivo che condanna "l'opposta" verso "l'opponente"
    finirebbe per attribuire a entrambe lo stesso lato."""
    parti = {
        "Parte_1": {"ruoli": ["opponente"], "lato": "debitore", "fiducia": "x", "criteri": []},
        "ruolo:opponente": {"ruoli": ["opponente"], "lato": "creditore",
                            "fiducia": "x", "criteri": []},
    }

    assert pdg.risolvi_parte("l'opponente", parti)["lato"] == "debitore"


def test_una_parte_non_indicata_non_si_indovina():
    assert pdg.risolvi_parte("", {})["lato"] is None
    assert pdg.risolvi_parte("la banca", {})["motivo"] == "descrizione_non_riconosciuta"


# --- l'ancoraggio ---------------------------------------------------------

def test_ogni_prova_e_la_fetta_agli_offset_dichiarati():
    """Regola 4: la prova non e' una parafrasi, e' il testo a quegli
    offset, calcolati da Python."""
    inte = "DA Parte_1 rappresentato dall'avv. Rossi appellante"
    disp = "rigetta l'opposizione e condanna Parte_1 alle spese"

    registro = pdg.registro(inte, disp)

    sorgenti = {"intestazione": inte, "dispositivo": disp}
    prove = [p for v in registro["parti"].values() for p in v["prove"]]
    prove += registro["direzione"]["prove"]
    assert prove, "il caso deve produrre almeno una prova, altrimenti non prova niente"
    for prova in prove:
        testo = sorgenti[prova["campo"]]
        assert prova["verbatim"] == testo[prova["inizio"]:prova["fine"]]


# --- lo pseudonimo spezzato dal PDF ---------------------------------------

def _voce(lato):
    return {"ruoli": [], "lato": lato, "fiducia": "un_solo_criterio",
            "criteri": ["ruolo_nel_monitorio"], "prove": [], "solo_registrato": []}


def test_lo_pseudonimo_spezzato_e_lo_stesso_pseudonimo():
    """"Controp arte_1" e' 38 coppie da solo: lo spazio lo infila
    l'estrazione dal PDF a meta' parola, dove nel PDF c'era un a capo."""
    parti = {"Controparte_1": _voce("creditore")}

    assert pdg.risolvi_parte("la Controp arte_1", parti)["lato"] == "creditore"
    assert pdg.canonico("Controp arte_1") == "Controparte_1"


def test_lo_schema_largo_non_pesca_cio_che_non_e_un_nome():
    """Il suffisso `_<numero>` obbligatorio e' cio' che tiene stretto uno
    schema che accetta spazi in mezzo alle lettere. Senza, lettere
    separate da spazi combacerebbero con mezza pagina."""
    for testo in ("la parte opposta", "C P della societa'", "Parte prima",
                  "controparte processuale"):
        assert pdg.PSEUDONIMO.search(testo) is None, testo


def test_il_testo_non_si_riscrive_per_riparare_un_nome():
    """Gli offset delle prove sono calcolati sul testo (regola 4): si
    allarga lo schema, che legge il testo com'e', e si normalizza la sola
    chiave."""
    inte = "DA Controp arte_1 - opponente - CONTRO Parte_1 - opposto -"

    parti = pdg.lati_delle_parti(inte, "")

    assert "Controparte_1" in parti, "la chiave e' normalizzata"
    prova = parti["Controparte_1"]["prove"][0]
    assert prova["verbatim"] == inte[prova["inizio"]:prova["fine"]], (
        "la prova resta una fetta del testo ORIGINALE, spazio intruso incluso")


# --- l'eccezione attribuita a piu' parti ----------------------------------

def test_piu_parti_concordi_rispondono():
    parti = {"Parte_1": _voce("debitore"), "Parte_2": _voce("debitore")}

    esito = pdg.risolvi_parte("Parte_1 Parte_2 e Parte_3", parti)

    assert esito["lato"] is None, "Parte_3 non e' in epigrafe: non si indovina"
    assert esito["motivo"] == "pseudonimo_non_in_epigrafe"

    esito = pdg.risolvi_parte("Parte_1 e Parte_2", parti)
    assert esito["lato"] == "debitore"
    assert esito["motivo"] == "piu_parti_concordi"


def test_piu_parti_di_lati_diversi_non_decidono_per_la_prima():
    """Rispondere con il lato della prima parte nominata e' una scelta
    travestita da lettura, e sembra sicura quanto una lettura vera."""
    parti = {"Parte_1": _voce("debitore"), "Parte_2": _voce("creditore")}

    esito = pdg.risolvi_parte("Parte_1 e Parte_2", parti)

    assert esito["lato"] is None
    assert esito["motivo"] == "parti_di_lati_diversi"
    assert esito["parti"] == ["Parte_1", "Parte_2"]


def test_una_parte_senza_criteri_non_contraddice_le_altre():
    """Il silenzio non e' un dissenso: dice che di quella parte non
    risulta niente, non che sta dall'altro lato."""
    parti = {"Parte_1": _voce("debitore"),
             "Parte_2": dict(_voce(None), fiducia="nessun_criterio", criteri=[])}

    esito = pdg.risolvi_parte("Parte_1 e Parte_2", parti)

    assert esito["lato"] == "debitore"
