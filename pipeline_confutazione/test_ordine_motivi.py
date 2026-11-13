"""Ordine dei motivi calcolato da Python, e finestre della ricerca conflitti
(contratto 1.27).

Il punto di questi test non e' che l'ordine sia "bello": e' che sia una
PERMUTAZIONE di tutti i motivi, sempre, e che cio' che non e' stato
esaminato risulti come non esaminato. Sono le due proprieta' che la
passata generativa non riusciva a garantire su 56 motivi, ed erano il
motivo per cui la corsa moriva.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import ordine_motivi  # noqa: E402
import validazione  # noqa: E402
from ordine_motivi import NON_CLASSIFICATO, copertura, finestre, ordina  # noqa: E402


def _motivo(eccezione_id: str, rango: str = "merito", esito: str = "trattata") -> dict:
    """Il rango arriva gia' calcolato dal grafo (famiglie_grafo): questo
    modulo ordina e basta, non classifica."""
    return {"eccezione_id": eccezione_id, "rango": rango, "esito": esito,
            "riassunto": "riassunto di prova"}


# --- l'ordine ------------------------------------------------------------

def test_il_rito_precede_il_merito_qualunque_sia_l_ordine_di_ingresso():
    motivi = [_motivo("X01", "merito"),
              _motivo("X02", "preliminare_di_merito"),
              _motivo("X03", "rito")]

    assert ordina(motivi)["ordine"] == ["X03", "X02", "X01"]


def test_dentro_lo_stesso_rango_vince_l_ordine_dell_atto():
    """Stabilita': a parita' di rango si conserva l'ordine del dossier, che
    e' quello in cui le eccezioni compaiono nell'atto di controparte.
    Senza questo, due corse identiche potrebbero rendere in ordini diversi."""
    motivi = [_motivo("X05", "merito"), _motivo("X02", "merito"), _motivo("X09", "merito")]

    assert ordina(motivi)["ordine"] == ["X05", "X02", "X09"]


def test_l_esito_non_sposta_un_motivo():
    """Un'eccezione preliminare resta preliminare anche se non siamo
    riusciti a confutarla: retrocederla darebbe all'ordine un significato
    che non ha."""
    motivi = [_motivo("X01", "merito", esito="trattata"),
              _motivo("X02", "preliminare_di_merito", esito="errore_tecnico")]

    assert ordina(motivi)["ordine"] == ["X02", "X01"]


def test_un_rango_non_ricavabile_finisce_in_coda_e_viene_dichiarato():
    """Sul batch reale il rango non si ricava per 325 eccezioni su 983: una
    quota cosi' alta non puo' essere collocata in silenzio."""
    motivi = [_motivo("X01", NON_CLASSIFICATO),
              _motivo("X02", None),
              _motivo("X03", "preliminare_di_merito")]

    esito = ordina(motivi)

    assert esito["ordine"] == ["X03", "X01", "X02"]
    assert esito["non_classificati"] == ["X01", "X02"]
    assert esito["rango_per_motivo"]["X02"] == NON_CLASSIFICATO


def test_un_rango_inventato_e_un_errore_non_una_coda():
    """Se un giorno arrivasse un rango che il contratto non prevede, questo
    modulo lo direbbe invece di metterlo in fondo come se fosse un caso
    non classificato: sono due cose diverse."""
    import pytest

    with pytest.raises(ValueError, match="rango non previsto"):
        ordina([_motivo("X01", "pregiudiziale_inventata"), _motivo("X02", "merito")])


def test_l_ordine_e_sempre_una_permutazione_esatta():
    """La proprieta' che il modello sbagliava. Qui vale per costruzione, e
    il test serve a impedire che una riscrittura futura la perda."""
    motivi = [_motivo(f"X{i:02d}", "merito" if i % 3 else NON_CLASSIFICATO)
              for i in range(1, 57)]

    ordine = ordina(motivi)["ordine"]

    assert sorted(ordine) == sorted(m["eccezione_id"] for m in motivi)
    assert len(ordine) == len(set(ordine)) == 56


def test_nessun_motivo_viene_perso_quando_nessuna_famiglia_e_nota():
    motivi = [_motivo("X01", None), _motivo("X02", None)]  # rango assente = non classificato

    esito = ordina(motivi)

    assert esito["ordine"] == ["X01", "X02"]
    assert esito["non_classificati"] == ["X01", "X02"]


# --- le finestre ---------------------------------------------------------

def test_sotto_i_due_motivi_non_c_e_nessuna_finestra():
    """Senza almeno una coppia non esiste nessun conflitto possibile: il
    contratto prescrive di saltare la passata, non di eseguirla."""
    assert finestre(["X01"]) == []
    assert finestre([]) == []


def test_pochi_motivi_stanno_in_una_finestra_sola():
    ordine = [f"X{i:02d}" for i in range(1, 7)]

    assert finestre(ordine) == [ordine]


def test_le_finestre_coprono_ogni_motivo_e_l_ultima_e_ancorata_in_fondo():
    """Troncare l'ultima finestra lascerebbe gli ultimi motivi senza
    nessuno con cui essere confrontati."""
    ordine = [f"X{i:02d}" for i in range(1, 57)]

    blocchi = finestre(ordine)

    assert all(len(b) == ordine_motivi.FINESTRA for b in blocchi)
    assert set().union(*blocchi) == set(ordine)
    assert blocchi[-1] == ordine[-ordine_motivi.FINESTRA:]


def test_le_finestre_si_sovrappongono():
    """Senza sovrapposizione due motivi adiacenti nell'ordine finale
    potrebbero non essere mai confrontati fra loro."""
    ordine = [f"X{i:02d}" for i in range(1, 25)]

    blocchi = finestre(ordine)

    assert set(blocchi[0]) & set(blocchi[1]), "finestre consecutive senza motivi in comune"


def test_la_copertura_dichiara_le_coppie_non_guardate():
    """Su 56 motivi le coppie sono 1540 e le finestre ne vedono una
    frazione: il numero va dichiarato, perche' 'nessun conflitto
    segnalato' non vuol dire 'nessun conflitto'."""
    ordine = [f"X{i:02d}" for i in range(1, 57)]
    blocchi = finestre(ordine)

    esito = copertura(ordine, blocchi)

    assert esito["coppie_totali"] == 56 * 55 // 2
    assert 0 < esito["coppie_esaminate"] < esito["coppie_totali"]
    assert esito["finestre"] == len(blocchi)


def test_con_una_finestra_sola_la_copertura_e_totale():
    ordine = ["X01", "X02", "X03"]

    esito = copertura(ordine, finestre(ordine))

    assert esito["coppie_esaminate"] == esito["coppie_totali"] == 3


def test_una_finestra_scartata_non_conta_come_esaminata():
    """La copertura si calcola sulle finestre RIUSCITE: se una chiamata
    viene troncata, le sue coppie non sono state guardate."""
    ordine = [f"X{i:02d}" for i in range(1, 25)]
    blocchi = finestre(ordine)

    tutte = copertura(ordine, blocchi)
    meno_una = copertura(ordine, blocchi[1:])

    assert meno_una["coppie_esaminate"] < tutte["coppie_esaminate"]


# --- il controllo 11, nella forma nuova ----------------------------------

def test_un_conflitto_di_un_motivo_con_se_stesso_e_rifiutato():
    conflitti = [{"tra": ["X01", "X01"], "tipo": "contraddizione", "descrizione": "d"}]

    rifiuto = validazione.controllo_11_conflitti_coerenza(conflitti, ["X01", "X02"])

    assert rifiuto and "non confligge con se stesso" in rifiuto


def test_un_conflitto_fuori_dalla_finestra_e_rifiutato():
    conflitti = [{"tra": ["X01", "X99"], "tipo": "sovrapposizione", "descrizione": "d"}]

    rifiuto = validazione.controllo_11_conflitti_coerenza(conflitti, ["X01", "X02"])

    assert rifiuto and "X99" in rifiuto


def test_un_conflitto_regolare_passa_e_la_lista_vuota_pure():
    conflitti = [{"tra": ["X01", "X02"], "tipo": "subordinazione", "descrizione": "d"}]

    assert validazione.controllo_11_conflitti_coerenza(conflitti, ["X01", "X02"]) is None
    assert validazione.controllo_11_conflitti_coerenza([], ["X01", "X02"]) is None


# --- il tetto che fermava la corsa ---------------------------------------

def test_il_contratto_non_ferma_piu_un_atto_da_56_motivi():
    """Regressione diretta sul guasto misurato: `maxItems: 15` respingeva
    l'input e uccideva la corsa su 24 atti su 45, dopo che Fase 2 e Fase 3
    avevano gia' lavorato."""
    ingresso = {
        "obiettivo": "rigetto dell'opposizione",
        "motivi": [{"eccezione_id": f"X{i:02d}", "esito": "trattata",
                     "famiglia": "anomalie_contabili", "riassunto": "r"} for i in range(1, 57)],
    }

    validazione.valida_sotto_schema(validazione.SCHEMA_COERENZA, "input", ingresso, "prova")


def test_lo_schema_runtime_non_chiede_piu_un_ordine():
    """Se `ordine_motivi` tornasse nello schema di uscita, il modello
    tornerebbe a doverne generare uno - ed e' esattamente cio' che la 1.27
    ha tolto."""
    import constrained_decoding

    schema = constrained_decoding.costruisci_schema_coerenza(["X01", "X02", "X03"])

    assert set(schema["properties"]) == {"conflitti"}
    assert schema["properties"]["conflitti"]["items"]["properties"]["tra"]["items"]["enum"] == \
        ["X01", "X02", "X03"]
