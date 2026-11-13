"""L'atto porta conteggi, o contesta e basta.

Il modulo esiste per impedire UN errore: che la regola delle anomalie
contabili scriva in un atto depositato che l'avversario non ha prodotto
cifre, mentre le ha prodotte. I test difendono quell'errore e la
direzione in cui la funzione deve sbagliare quando sbaglia.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import conteggi_di_parte as cdp  # noqa: E402
import motore_regole as mr  # noqa: E402


# --- cosa riconosce -----------------------------------------------------

def test_una_perizia_di_parte_con_un_saldo():
    """Caso sintetico di perizia di parte con saldo rideterminato."""
    testo = ("L'odierna attrice faceva sottoporre l'intero rapporto a perizia "
             "econometrica dalla quale si evinceva che il saldo effettivo in favore "
             "della correntista ammonta ad euro 150.000,00 alla data di chiusura.")
    esito = cdp.cerca(testo)
    assert esito.trovati
    assert esito.riscontri[0].importo.startswith("150") or "150" in esito.riscontri[0].importo


def test_un_ricalcolo_con_un_tasso():
    testo = ("Si dovra' procedere al ricalcolo degli interessi come previsto "
             "dall'art. 117 co. 7 TUB, essendo stato applicato un tasso del 24,375% "
             "in luogo di quello legale.")
    assert cdp.nell_atto(testo)


def test_l_importo_puo_precedere_la_parola():
    """La cifra puo' stare prima del richiamo al conteggio: la finestra
    guarda da entrambi i lati."""
    assert cdp.nell_atto("La somma di euro 12.500,00 risulta dal prospetto allegato.")


# --- cosa NON deve riconoscere -----------------------------------------

def test_la_sola_somma_ingiunta_non_e_un_conteggio():
    """Misurato: 44 atti su 52 contengono un importo, perche' c'e' dentro
    la somma ingiunta. Un segnale vero all'85% non e' un segnale."""
    testo = ("Con decreto ingiuntivo n. 123/2024 il Tribunale ingiungeva il pagamento "
             "di euro 352.918,74 oltre interessi e spese. Si propone opposizione.")
    assert not cdp.nell_atto(testo)


def test_chiedere_una_CTU_non_e_un_conteggio_allegato():
    """E' il contrario: chiedere al giudice una consulenza contabile e'
    semmai la prova che i conteggi la parte non li ha fatti."""
    testo = ("Si chiede disporsi CTU tecnico-contabile per ricostruire i rapporti di "
             "conto corrente e determinare l'importo complessivamente dovuto, pari a "
             "euro 100.000,00 secondo la prospettazione attorea.")
    esito = cdp.cerca(testo)
    assert not any("ctu" in r.parola.lower() for r in esito.riscontri)


def test_un_numero_tondo_senza_decimali_non_e_un_importo():
    """`art. 1283`, `n. 2024`, `l. 108/1996`: un atto e' pieno di numeri
    che non sono somme. I decimali sono obbligatori."""
    assert not cdp.nell_atto("Il conteggio di cui all'art. 1283 c.c. e alla legge 108 "
                             "del 1996, richiamato nel prospetto n. 7 del 2024.")


def test_una_parola_di_ricalcolo_senza_cifre_non_basta():
    assert not cdp.nell_atto("Si contesta il conteggio operato dalla banca, del tutto "
                             "arbitrario e privo di fondamento.")


def test_una_cifra_lontana_dalla_parola_non_basta():
    """Oltre la finestra la vicinanza smette di voler dire qualcosa."""
    lontano = "x" * (cdp.FINESTRA + 200)
    assert not cdp.nell_atto("Si allega perizia di parte." + lontano + "euro 1.000,00")


def test_un_testo_vuoto_non_e_un_errore():
    assert not cdp.nell_atto("")
    assert cdp.cerca("").riscontri == []


# --- la spiegazione, che finisce in una nota per un umano ---------------

def test_la_spiegazione_positiva_cita_il_passaggio():
    esito = cdp.cerca("dalla perizia di parte risulta un saldo di euro 150.000,00")
    assert "L'atto porta dei conteggi" in esito.perche()
    assert "150.000,00" in esito.perche()


def test_la_spiegazione_negativa_non_dice_che_non_ce_ne_sono():
    """`False` vuol dire "non se ne sono trovati", non "non ce ne sono".
    Una funzione che cerca su un testo non puo' dire di piu', e una nota
    che dicesse di piu' verrebbe letta come una prova."""
    perche = cdp.cerca("Si contesta genericamente il saldo.").perche()
    assert "Non e' la prova che non ce ne siano" in perche


# --- l'effetto sulla regola, che e' il motivo per cui il modulo esiste --

def test_con_i_conteggi_nell_atto_la_regola_non_confuta_piu():
    """Il ramo di sicurezza. Senza, sull'atto ALFA sette contestazioni
    sarebbero state confutate sostenendo che l'avversario non ha prodotto
    cifre, con a pagina 14 una perizia che ne quantifica 150.000,00."""
    senza = mr.applica_regola(mr.Famiglia.ANOMALIE_CONTABILI, mr.Precondizioni(
        natura_rapporto="conto_corrente", specificita_eccezione="generica",
        conteggi_nell_atto=False))
    con = mr.applica_regola(mr.Famiglia.ANOMALIE_CONTABILI, mr.Precondizioni(
        natura_rapporto="conto_corrente", specificita_eccezione="generica",
        conteggi_nell_atto=True))
    assert senza.contro_argomento and senza.fonti
    assert con.contro_argomento is None and con.fonti == []
    assert "NON confutare prima di averla fatta" in con.nota


def test_il_ramo_di_sicurezza_non_tocca_gli_altri():
    """Vale solo dove il contro-argomento afferma l'assenza di cifre. Se
    l'eccezione e' gia' documentata o gia' indecidibile, i conteggi
    nell'atto non cambiano nulla."""
    for campi in ({"conteggi_allegati": True},
                  {"specificita_eccezione": "specifica"},
                  {"specificita_eccezione": "non_desumibile"}):
        a = mr.applica_regola(mr.Famiglia.ANOMALIE_CONTABILI,
                              mr.Precondizioni(natura_rapporto="conto_corrente", **campi))
        b = mr.applica_regola(mr.Famiglia.ANOMALIE_CONTABILI,
                              mr.Precondizioni(natura_rapporto="conto_corrente",
                                               conteggi_nell_atto=True, **campi))
        assert a == b, f"{campi}: il ramo di sicurezza non doveva intervenire"
