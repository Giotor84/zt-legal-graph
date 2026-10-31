"""La legittimazione del cessionario - famiglia 3.

E' la famiglia con piu' materiale nel corpus (393 coppie, 279 decise, il
40,5% accolte) e la sola in cui l'avversario vince quattro volte su
dieci. La regola non confuta mai, e il primo gruppo di test difende
esattamente quello: una regola che qui producesse un contro-argomento
starebbe affermando di aver prodotto documenti che nessuno ha guardato.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import cessione_del_credito as cdc  # noqa: E402
import motore_regole as mr  # noqa: E402

FAMIGLIA = mr.Famiglia.LEGITTIMAZIONE_CESSIONARIO


def _applica(**campi) -> mr.RisultatoRegola:
    campi.setdefault("natura_rapporto", "conto_corrente")
    campi.setdefault("creditore_e_cessionario", True)
    return mr.applica_regola(FAMIGLIA, mr.Precondizioni(**campi))


# --- l'invariante della famiglia: qui non si confuta --------------------

def test_nessun_ramo_produce_un_contro_argomento():
    """Il fatto che deciderebbe - cosa abbiamo prodotto - sta nel nostro
    fascicolo, non nell'atto e non nel corpus. Un contro-argomento
    scritto senza saperlo affermerebbe documenti mai guardati."""
    for campi in ({"creditore_e_cessionario": False},
                  {"contestata_solo_gazzetta": True},
                  {"contestata_solo_gazzetta": True, "cessioni_plurime": True},
                  {}):
        esito = _applica(**campi)
        assert esito.contro_argomento is None, campi
        assert esito.fonti == [], campi


def test_non_si_cita_niente_nemmeno_l_art_58():
    """Il corpus contiene un'autorita' AVVERSA su questo punto e il
    retrieval non ha l'annotazione di direzione: la regola non propone
    fonti, cosi' non c'e' nulla che possa essere scambiato per supporto."""
    assert _applica(contestata_solo_gazzetta=True).fonti == []


# --- i tre rami ---------------------------------------------------------

def test_senza_cessione_la_regola_non_si_aggancia():
    esito = _applica(creditore_e_cessionario=False)
    assert esito.fondata is False
    assert "non si aggancia" in esito.nota
    assert "non e' un giudizio di infondatezza" in esito.nota.lower()


def test_la_contestazione_sulla_sola_gazzetta_fa_reggere_l_eccezione():
    esito = _applica(contestata_solo_gazzetta=True)
    assert esito.fondata is True
    assert "40,5%" in esito.nota


def test_quando_regge_la_nota_elenca_i_tre_documenti():
    """Un'eccezione che regge senza dire cosa serve e' un vicolo cieco."""
    nota = _applica(contestata_solo_gazzetta=True).nota
    assert "contratto di cessione" in nota
    assert "specifico credito" in nota
    assert "NOSTRO FASCICOLO" in nota


def test_le_cessioni_plurime_aggiungono_l_avvertimento_sull_autorita_avversa():
    con = _applica(contestata_solo_gazzetta=True, cessioni_plurime=True).nota
    senza = _applica(contestata_solo_gazzetta=True).nota
    assert "Trib. Bologna" in con and "Trib. Bologna" not in senza
    assert "non e' una fonte a supporto" in con


def test_forma_della_contestazione_ignota_non_decide():
    esito = _applica(contestata_solo_gazzetta=False)
    assert esito.fondata is False
    assert "non risulta COME sia contestata" in esito.nota
    assert "quattro volte su dieci" in esito.nota


# --- il rilevatore sul testo dell'atto ----------------------------------

def test_riconosce_le_forme_reali_degli_atti():
    """Tutte e quattro vengono da atti veri di `atti_input/`."""
    for testo in (
        "in tema di cessione dei crediti la pubblicazione nella Gazzetta Ufficiale "
        "non e' sufficiente a dimostrare la titolarita' del credito",
        "si e' semplicemente limitata a produrre l'avviso di cessione pubblicato "
        "sulla Gazzetta Ufficiale",
        "E' pacifico che, in mancanza di produzione del contratto di cessione, la "
        "titolarita' del credito ceduto non e' provata",
        "non potendo valere quale valido titolo il solo avviso pubblicato sulla "
        "Gazzetta Ufficiale, parte II, n. 7 del 16.01.2020, relativo alla cessione",
    ):
        assert cdc.cerca(testo).contestata_solo_gazzetta, testo[:50]


def test_un_atto_che_non_parla_di_cessione_non_produce_nulla():
    esito = cdc.cerca("Si contesta il saldo del conto corrente e l'anatocismo.")
    assert not esito.parla_di_cessione
    assert not esito.contestata_solo_gazzetta
    assert "non contesta la cessione" in esito.perche()


def test_parlare_di_cessione_non_basta():
    """42 atti su 52 nominano la cessione, 13 portano l'allegazione
    specifica: il primo dato da solo non discrimina niente."""
    esito = cdc.cerca("L'opposta agisce quale cessionaria del credito in forza di "
                      "cessione in blocco ex art. 58 TUB.")
    assert esito.parla_di_cessione
    assert not esito.contestata_solo_gazzetta


def test_le_cessioni_plurime_si_riconoscono():
    esito = cdc.cerca("La pubblicazione in Gazzetta Ufficiale non prova la titolarita', "
                      "trattandosi peraltro di cessioni successive fra piu' veicoli.")
    assert esito.contestata_solo_gazzetta and esito.cessioni_plurime
    assert "catena di cessioni" in esito.perche()


def test_la_spiegazione_negativa_non_dichiara_un_assenza():
    perche = cdc.cerca("cessione in blocco ex art. 58 TUB").perche()
    assert "Non e' la prova che non ci sia" in perche


def test_l_aggravante_non_viene_mostrata_al_posto_della_contestazione():
    """`cessioni_plurime` da solo non e' la contestazione: e' la sua
    aggravante, e nella nota non deve prendere il posto del riscontro che
    conta."""
    esito = cdc.cerca("Si tratta peraltro di cessioni successive. La cessionaria non ha "
                      "prodotto il contratto di cessione.")
    assert esito.riscontri[0].tipo != "cessioni_plurime"


def test_la_famiglia_e_registrata():
    assert FAMIGLIA in mr._REGISTRO
