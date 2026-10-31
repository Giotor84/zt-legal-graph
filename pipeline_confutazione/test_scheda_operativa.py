"""La scheda operativa: il documento che si legge per decidere.

I test guardano una cosa sola, da angoli diversi: che il documento non
possa far credere di avere in mano piu' di quello che c'e'. E' il difetto
che aveva il dossier ALFA - due esiti `confutabile` senza confutazione - e
un documento in italiano lo rende piu' facile, non piu' difficile: nessuno
rilegge il JSON per controllare la prosa.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import motore_regole  # noqa: E402
import scheda_operativa as so  # noqa: E402


#: Una famiglia SENZA regola e una CON regola, scelte dal registro vero a
#: ogni esecuzione. Scriverle a mano le fa marcire: `anomalie_contabili`
#: era l'esempio di "famiglia senza regola" in tre test, e il giorno in
#: cui la regola e' stata scritta i tre sono falliti tutti insieme
#: dicendo la cosa sbagliata (un difetto nella scheda, invece che il
#: proprio esempio diventato obsoleto).
#: Dal 2026-09-03 il motore copre TUTTE le famiglie dell'enum, quindi il
#: ripiego e' un valore fuori enum: il ramo "manca la regola" resta
#: raggiungibile - una famiglia nuova nasce sempre senza - e va difeso.
SENZA_REGOLA = next((f.value for f in motore_regole.Famiglia
                     if f not in motore_regole._REGISTRO
                     and f.value != "non_riconosciuta"),
                    "famiglia_senza_regola")
CON_REGOLA = next(f.value for f in motore_regole._REGISTRO)


def _esito(eid: str, stato: str, famiglia: str | None = None,
           contro: str | None = None) -> dict:
    return {"eccezione_id": eid, "stato": stato, "famiglia": famiglia,
            "contro_argomento": contro, "estratti_citabili": [], "nota": "",
            "motivo_astensione": None, "motivo_errore": None}


def _dossier(esiti: list[dict]) -> dict:
    return {"esiti": esiti, "obiettivo": "", "fatti_di_causa": "",
            "fonti": [], "estratti": [], "fonti_scartate": []}


# --- le cause si deducono dalla struttura, non dal testo ----------------

def test_famiglia_senza_regola_e_famiglia_senza_fatto_sono_due_cose_diverse():
    """Entrambe escono `astensione` dal dossier, ed e' giusto. Ma una si
    risolve scrivendo codice e l'altra leggendo l'atto: se la scheda le
    unisce, l'avvocato non sa a chi passare la pratica."""
    senza_regola = so.causa_di(_esito("X01", "astensione", SENZA_REGOLA))
    senza_fatto = so.causa_di(_esito("X02", "astensione", CON_REGOLA))
    assert senza_regola == so.CAUSA_REGOLA_ASSENTE
    assert senza_fatto == so.CAUSA_FATTO_MANCANTE


def test_la_copertura_si_chiede_al_registro_vero():
    """Non a un elenco tenuto a mano qui dentro, che diverge il giorno in
    cui qualcuno scrive una regola nuova."""
    for famiglia in motore_regole._REGISTRO:
        assert so._famiglia_coperta(famiglia.value)
    assert not so._famiglia_coperta("famiglia_che_non_esiste")


def test_un_esito_senza_famiglia_e_non_riconosciuto():
    assert so.causa_di(_esito("X01", "astensione")) == so.CAUSA_NON_RICONOSCIUTA


def test_un_guasto_non_diventa_un_astensione():
    """L'astensione e' il sistema che funziona e rifiuta di argomentare;
    l'errore tecnico e' il sistema rotto. Il contratto vieta di
    collassarli, e la scheda e' l'ultimo posto in cui potrebbero
    ricollassare."""
    assert so.causa_di(_esito("X01", "errore_tecnico", "prescrizione")) == so.CAUSA_GUASTO


def test_l_eccezione_che_regge_non_e_un_limite_nostro():
    assert so.causa_di(_esito("X01", "eccezione_fondata", "prescrizione")) == so.CAUSA_RETTA


# --- il verdetto in testa non puo' promettere piu' del vero -------------

def test_zero_risposte_lo_dice_in_testa():
    testo = so.rendi(_dossier([_esito("X%02d" % i, "astensione", "anomalie_contabili")
                               for i in range(1, 22)]))
    prima_riga = testo.split("## In una riga")[1].split("##")[0]
    assert "nessuna ha prodotto una risposta utilizzabile" in prima_riga
    assert "21 contestazioni" in prima_riga


def test_le_risposte_pronte_si_contano_solo_se_lo_sono():
    testo = so.rendi(_dossier([
        _esito("X01", "confutabile", "incompletezza_estratti_conto", "perche' si"),
        _esito("X02", "astensione", "anomalie_contabili")]))
    assert "**1 hanno una risposta pronta" in testo


def test_un_dossier_vuoto_non_e_una_buona_notizia():
    """Zero contestazioni non vuol dire che l'atto non contesti nulla:
    quasi sempre vuol dire che la lettura e' andata storta."""
    assert "qualcosa e' andato storto in lettura" in so.rendi(_dossier([]))


# --- le cause si raggruppano, le azioni si ordinano ---------------------

def test_quindici_astensioni_uguali_sono_una_riga():
    esiti = [_esito("X%02d" % i, "astensione", SENZA_REGOLA) for i in range(1, 16)]
    testo = so.rendi(_dossier(esiti))
    assert testo.count("Manca la regola per questa materia") == 1
    assert "15 contestazioni" in testo


def test_le_azioni_sono_ordinate_per_quanto_sbloccano():
    esiti = ([_esito("X%02d" % i, "astensione", "anomalie_contabili") for i in range(1, 11)]
             + [_esito("X11", "astensione", "prescrizione")])
    azioni = so.azioni(so.raggruppa(esiti))
    assert [a["quante"] for a in azioni] == [10, 1]
    assert "anomalie contabili" in azioni[0]["cosa"]


def test_ogni_limite_ha_la_sua_azione():
    """Un limite senza il 'per farlo servirebbe' e' una lamentela."""
    for famiglia, atteso in ((SENZA_REGOLA, "sviluppo"),
                             (CON_REGOLA, "lettura dell'atto"),
                             (None, "lettura dell'atto")):
        azioni = so.azioni(so.raggruppa([_esito("X01", "astensione", famiglia)]))
        assert len(azioni) == 1 and azioni[0]["chi"] == atteso


# --- niente vocabolario interno nel documento ---------------------------

def test_ogni_famiglia_del_contratto_ha_un_nome_in_italiano():
    """Una famiglia nuova senza il suo nome fa fallire QUI, non compare
    con l'underscore in mezzo in un documento per l'avvocato."""
    mancanti = [f.value for f in motore_regole.Famiglia
                if f.value not in so.IN_ITALIANO]
    assert not mancanti, f"famiglie senza nome in italiano: {mancanti}"


def test_il_documento_non_contiene_nomi_di_campo():
    esiti = [_esito("X01", "astensione", "anomalie_contabili"),
             _esito("X02", "confutabile", "incompletezza_estratti_conto", "perche'"),
             _esito("X03", "astensione", None)]
    testo = so.rendi(_dossier(esiti))
    for interno in ("anomalie_contabili", "incompletezza_estratti_conto",
                    "motivo_astensione", "estratti_citabili", "eccezione_id",
                    "contro_argomento", "famiglia_probabile"):
        assert interno not in testo, f"vocabolario interno nel documento: {interno}"


def test_gli_stati_interni_non_compaiono():
    """`astensione` non dice a un avvocato che cosa e' successo."""
    testo = so.rendi(_dossier([_esito("X01", "astensione", "prescrizione")]))
    assert "astensione" not in testo and "non_classificata" not in testo


# --- cio' che non e' stato guardato si dice, in fondo -------------------

def test_la_fase3_non_eseguita_si_dichiara():
    testo = so.rendi(_dossier([_esito("X01", "astensione", "prescrizione")]),
                     fase3_eseguita=False)
    assert "non e' stata prodotta" in testo
    testo_con = so.rendi(_dossier([_esito("X01", "astensione", "prescrizione")]),
                         fase3_eseguita=True)
    assert "non e' stata prodotta" not in testo_con


def test_i_passaggi_non_collocati_si_contano():
    estrazione = {"struttura": {}, "buchi": [
        {"tipo": "ancoraggio_non_riuscito", "testo": "X03 ..."},
        {"tipo": "ancoraggio_non_riuscito", "testo": "X04 ..."},
        {"tipo": "tetto_array", "testo": "altro"}]}
    testo = so.rendi(_dossier([_esito("X01", "astensione", "prescrizione")]), estrazione)
    assert "**2 passaggi**" in testo
    assert "non sono stati giudicati affatto" in testo


def test_la_qualifica_del_fideiussore_dichiarata_va_verificata():
    """Una persona fisica che garantisce non e' per cio' solo un
    consumatore, e nella corsa ALFA quella qualifica veniva dal modello
    senza che nulla la confermasse."""
    estrazione = {"buchi": [], "struttura": {"qualita_parti": {
        "fideiussore_presente": True, "qualita_fideiussore": "consumatore"}}}
    testo = so.rendi(_dossier([_esito("X01", "astensione", "prescrizione")]), estrazione)
    assert "non verificata da nessun calcolo" in testo


def test_niente_avviso_quando_la_qualifica_non_e_stata_dedotta():
    estrazione = {"buchi": [], "struttura": {"qualita_parti": {
        "fideiussore_presente": True, "qualita_fideiussore": "non_desumibile"}}}
    testo = so.rendi(_dossier([_esito("X01", "astensione", "prescrizione")]), estrazione)
    assert "Da verificare a mano" not in testo


def test_la_scheda_esce_anche_senza_estrazione():
    """Una corsa fermata presto deve produrre qualcosa di leggibile, non
    un errore."""
    testo = so.rendi(_dossier([_esito("X01", "astensione", "prescrizione")]), None)
    assert testo.startswith("# Scheda operativa")
