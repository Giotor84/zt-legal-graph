"""Le quattordici famiglie chiuse il 2026-09-03.

Scritte con un impianto comune, e per questo il primo blocco di test non
guarda una regola alla volta: guarda che l'impianto valga per TUTTE. Un
difetto in `_regola_per_allegazione` sarebbe un difetto in quattordici
famiglie insieme, ed e' il rischio che si accetta scrivendole cosi'.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import motore_regole as mr  # noqa: E402

TABELLA = mr._PER_ALLEGAZIONE


def _applica(famiglia, **campi) -> mr.RisultatoRegola:
    campi.setdefault("natura_rapporto", "conto_corrente")
    return mr.applica_regola(famiglia, mr.Precondizioni(**campi))


# --- l'impianto, su tutte e quattordici ---------------------------------

def test_ogni_famiglia_dell_enum_ha_una_regola():
    """Nessuna solleva piu' NotImplementedError. Una famiglia riconosciuta
    e senza regola nel dossier diventa 'manca la regola', che manda allo
    sviluppo: ora manda al fascicolo, che e' dove serve."""
    senza = [f.value for f in mr.Famiglia if f not in mr._REGISTRO]
    assert senza == [], senza


def test_la_generica_si_confuta_sempre_con_una_fonte():
    for famiglia in TABELLA:
        esito = _applica(famiglia, specificita_eccezione="generica")
        assert esito.fondata is False, famiglia
        assert esito.contro_argomento, famiglia
        assert esito.fonti, famiglia


def test_la_specifica_regge_sempre_e_non_porta_fonti():
    for famiglia in TABELLA:
        esito = _applica(famiglia, specificita_eccezione="specifica")
        assert esito.fondata is True, famiglia
        assert esito.contro_argomento is None and esito.fonti == [], famiglia


def test_l_ignota_non_decide_mai():
    for famiglia in TABELLA:
        esito = _applica(famiglia, specificita_eccezione="non_desumibile")
        assert esito.fondata is False and esito.contro_argomento is None, famiglia
        assert "NON trattare come 'eccezione infondata di default'" in esito.nota


def test_nessun_ramo_promette_una_confutazione_che_non_ha():
    """L'invariante di tutto il motore, verificata su ogni famiglia e ogni
    ramo insieme."""
    for famiglia in mr.Famiglia:
        for spec in ("generica", "specifica", "non_desumibile"):
            esito = _applica(famiglia, specificita_eccezione=spec)
            if esito.contro_argomento is None:
                assert esito.fonti == [], (famiglia, spec)


def test_nessuna_dichiara_un_consolidamento_mai_misurato():
    """Il corpus BDP non contiene massime verificate su queste materie:
    dichiarare un orientamento sarebbe una fonte inventata con l'aria di
    un dato."""
    for famiglia in TABELLA:
        for spec in ("generica", "specifica", "non_desumibile"):
            assert _applica(famiglia, specificita_eccezione=spec).consolidamento is None


# --- il contenuto: ogni voce deve dire le cose che promette -------------

def test_ogni_voce_ha_tutti_i_campi():
    for famiglia, voce in TABELLA.items():
        assert set(voce) == {"cosa_indicare", "contro", "fonti", "quota", "checklist"}, famiglia
        assert voce["fonti"], famiglia


def test_ogni_contro_argomento_nomina_almeno_una_delle_sue_fonti():
    """Un contro-argomento che cita articoli diversi da quelli che porta
    a supporto e' un contro-argomento senza fonti verificate."""
    for famiglia, voce in TABELLA.items():
        numeri = [f.citazione_breve.split()[1] for f in voce["fonti"]]
        assert any(n in voce["contro"] for n in numeri), (famiglia, numeri)


def test_ogni_quota_porta_la_sua_numerosita():
    """Una percentuale senza il numero di casi su cui e' calcolata e' la
    cosa che il progetto non pubblica."""
    for famiglia, voce in TABELLA.items():
        assert "casi" in voce["quota"], famiglia


def test_le_famiglie_con_pochi_casi_lo_dicono():
    """Cambiale e decadenza dal beneficio del termine hanno dodici casi
    decisi: la percentuale non deve essere presentata come se dicesse
    qualcosa."""
    for famiglia in (mr.Famiglia.CAMBIALE_TITOLO_ESECUTIVO,
                     mr.Famiglia.DECADENZA_BENEFICIO_TERMINE):
        assert "troppo pochi" in TABELLA[famiglia]["quota"]


def test_la_checklist_arriva_a_destinazione():
    nota = _applica(mr.Famiglia.PRESCRIZIONE, specificita_eccezione="specifica").nota
    assert "dies a quo" in nota and "atti interruttivi" in nota
    assert "28% dei 134 casi decisi" in nota


def test_la_qualifica_del_consumatore_avverte_che_il_dato_non_e_verificato():
    """E' il campo che il modello asserisce e nessun calcolo conferma: la
    regola che ci poggia sopra deve dirlo dove viene letta."""
    nota = _applica(mr.Famiglia.QUALIFICAZIONE_CONSUMATORE,
                    specificita_eccezione="specifica").nota
    assert "viene dal modello e non e' verificata" in nota


def test_la_ctu_distingue_la_consulenza_di_parte():
    """Contestare una CTP, contestare una CTU e chiederne una d'ufficio
    sono tre cose diverse, e la famiglia unica le assorbirebbe."""
    nota = _applica(mr.Famiglia.CONTESTAZIONE_CTU, specificita_eccezione="specifica").nota
    assert "CONSULENZA DI PARTE" in nota


# --- le due che non si decidono -----------------------------------------

def test_saldaconto_e_leasing_riconoscono_e_si_fermano():
    """Tre coppie e due coppie nel corpus: riconoscere e fermarsi e'
    l'unica cosa onesta, ed e' comunque meglio del silenzio."""
    for famiglia in (mr.Famiglia.SALDACONTO_ART_50_TUB, mr.Famiglia.LEASING):
        for spec in ("generica", "specifica", "non_desumibile"):
            esito = _applica(famiglia, specificita_eccezione=spec)
            assert esito.contro_argomento is None and esito.fonti == []
            assert "deliberatamente non decisa" in esito.nota


def test_il_saldaconto_nomina_la_precondizione_che_conterebbe():
    nota = _applica(mr.Famiglia.SALDACONTO_ART_50_TUB, fase_processuale="monitoria").nota
    assert "FASE del giudizio" in nota and "monitoria" in nota
