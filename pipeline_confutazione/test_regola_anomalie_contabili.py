"""La regola delle anomalie contabili - famiglia 4.

Sull'atto ALFA e' la famiglia di dieci contestazioni su ventuno, e nessuna
altra ne vale piu' di due: e' l'unico ramo che, scritto, sposti quel
dossier.

I test difendono una cosa sopra le altre: che i due segnali non vengano
sommati. `conteggi_allegati` e' un fatto, `specificita` e' un giudizio del
modello, e nella corsa ALFA quel giudizio ha marcato "specifica" un
frammento troncato a meta' periodo. Una regola che li mediasse
deciderebbe su un dato inventato meta' delle volte.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import motore_regole as mr  # noqa: E402

FAMIGLIA = mr.Famiglia.ANOMALIE_CONTABILI


def _applica(**campi) -> mr.RisultatoRegola:
    campi.setdefault("natura_rapporto", "conto_corrente")
    return mr.applica_regola(FAMIGLIA, mr.Precondizioni(**campi))


# --- il ramo che confuta ------------------------------------------------

def test_generica_e_senza_conteggi_si_confuta():
    esito = _applica(specificita_eccezione="generica", conteggi_allegati=False)
    assert esito.fondata is False
    assert esito.contro_argomento
    assert "art. 2697 c.c." in [f.citazione_breve for f in esito.fonti]


def test_le_fonti_esistono_nel_grafo_con_la_rubrica_giusta():
    """Verificate il 2026-09-02 per numero E per rubrica. Il test non
    apre il grafo - il motore non deve avere dipendenze - ma fissa le
    citazioni brevi esatte: se qualcuno le cambia, `risolvi_fonte` smette
    di trovarle e la regola esce in astensione senza che nulla lo
    spieghi."""
    esito = _applica(specificita_eccezione="generica")
    assert [f.citazione_breve for f in esito.fonti] == [
        "art. 2697 c.c.", "art. 115 c.p.c.", "art. 210 c.p.c.", "art. 191 c.p.c."]
    ruoli = {f.citazione_breve: f.ruolo for f in esito.fonti}
    assert ruoli["art. 2697 c.c."] == "principale"
    assert ruoli["art. 191 c.p.c."] == "subordinato"


def test_il_contro_argomento_nomina_l_inerzia_probatoria():
    """E' il cuore dell'argomento: esibizione e CTU sono poteri
    discrezionali, non rimedi alla prova che la parte non ha offerto."""
    esito = _applica(specificita_eccezione="generica")
    assert "discrezionali" in esito.contro_argomento
    assert "inerzia probatoria" in esito.contro_argomento


def test_nessun_consolidamento_dichiarato_senza_massime():
    """Il corpus BDP non ha massime verificate su questo punto. Un
    consolidamento dichiarato e mai misurato sarebbe una fonte inventata
    con l'aria di un dato."""
    assert _applica(specificita_eccezione="generica").consolidamento is None


# --- il ramo in cui l'eccezione regge -----------------------------------

def test_con_i_conteggi_l_eccezione_regge():
    esito = _applica(specificita_eccezione="specifica", conteggi_allegati=True)
    assert esito.fondata is True
    assert esito.contro_argomento is None
    assert esito.fonti == []


def test_i_conteggi_vincono_anche_se_il_modello_dice_generica():
    """Un fatto batte un giudizio. Se un conteggio c'e', l'argomento
    della contestazione generica non si applica, comunque il modello
    abbia etichettato il passaggio."""
    esito = _applica(specificita_eccezione="generica", conteggi_allegati=True)
    assert esito.fondata is True


def test_quando_regge_la_nota_indica_i_terreni_alternativi():
    """Un'eccezione che regge senza indicazione di dove andare e' un
    vicolo cieco: la regola deve dire cosa resta da percorrere."""
    nota = _applica(conteggi_allegati=True).nota
    assert "riconvenzionale" in nota
    assert "art. 1832 c.c." in nota
    assert "Nessuno dei tre e' automatizzato" in nota


# --- i due rami che non decidono, e perche' sono due --------------------

def test_specifica_senza_conteggi_non_decide():
    """I due segnali non concordano e la regola non decide su quello
    debole. Non e' un'eccezione infondata di default."""
    esito = _applica(specificita_eccezione="specifica", conteggi_allegati=False)
    assert esito.fondata is False
    assert esito.contro_argomento is None
    assert "non concordano" in esito.nota
    assert "NON trattare come infondata di default" in esito.nota


def test_specificita_ignota_non_decide():
    esito = _applica(specificita_eccezione="non_desumibile", conteggi_allegati=False)
    assert esito.fondata is False
    assert esito.contro_argomento is None
    assert "non determinata dall'estrazione" in esito.nota


def test_i_due_rami_che_non_decidono_dicono_cose_diverse():
    """Uno manda a guardare se i conteggi ci sono; l'altro manda a
    rileggere il passaggio. Se dessero la stessa nota, chi la legge non
    saprebbe cosa fare."""
    incoerente = _applica(specificita_eccezione="specifica").nota
    ignoto = _applica(specificita_eccezione="non_desumibile").nota
    assert incoerente != ignoto
    assert "consulenza di parte" in incoerente
    assert "rileggere il passaggio" in ignoto


# --- l'invariante che vale per ogni regola del motore -------------------

def test_nessun_ramo_promette_una_confutazione_che_non_ha():
    """L'invariante violata dal dossier ALFA: un contro-argomento nullo e
    delle fonti non possono coesistere, perche' a valle diventerebbe un
    esito `confutabile` senza confutazione."""
    for campi in ({"specificita_eccezione": "generica"},
                  {"specificita_eccezione": "specifica"},
                  {"specificita_eccezione": "non_desumibile"},
                  {"conteggi_allegati": True}):
        esito = _applica(**campi)
        if esito.contro_argomento is None:
            assert esito.fonti == [], (
                f"{campi}: fonti senza contro-argomento - a valle diventa "
                "'confutabile' senza confutazione")


def test_la_natura_del_rapporto_non_cambia_l_esito():
    """Il discrimine di questa famiglia e' la specificita', non la natura
    del rapporto: il rapporto qui e' sempre bancario. Se un giorno la
    natura contasse, questo test va riscritto - non cancellato."""
    esiti = {_applica(specificita_eccezione="generica", natura_rapporto=n).fondata
             for n in ("conto_corrente", "apertura_credito_cc", "mutuo",
                       "finanziamento_rateale", "altro", "non_desumibile")}
    assert esiti == {False}


def test_la_famiglia_e_registrata():
    assert FAMIGLIA in mr._REGISTRO
