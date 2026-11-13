# -*- coding: utf-8 -*-
"""BUG-GRAFO-5: le tre popolazioni di archi, e la quarta che non c'e'.

Il test che conta e' `test_una_forma_nuova_non_passa_inosservata`. Tutti
i consumatori di archi usano `.get()` con un default, quindi una
popolazione nuova non fa fallire niente: fa solo uscire numeri piu'
piccoli, che sembrano giusti. E' l'unico modo in cui questo bug puo'
ancora fare danno.
"""

from __future__ import annotations

import popolazioni_archi as pa

#: Le tre forme come stanno nel grafo vero (censite il 2026-09-02).
FRA_ARTICOLI = {"tipo_arco": "cita", "has_seguenti": False}
DA_PROVVEDIMENTO = {
    "tipo_arco": "cita", "fonte_campo": "motivazione", "occorrenze": 5,
    "ancore": [{"inizio": 1174, "fine": 1185, "testo_verbatim": "art. 50 TUB"}],
    "data_provvedimento": "2026-02-03", "articolo_abrogato_oggi": False,
}
DA_MASSIMA = {"tipo_arco": "cita"}


# ------------------------------------------------- le tre che esistono

def test_le_tre_popolazioni_si_distinguono():
    assert pa.popolazione(FRA_ARTICOLI) == pa.FRA_ARTICOLI
    assert pa.popolazione(DA_PROVVEDIMENTO) == pa.DA_PROVVEDIMENTO
    assert pa.popolazione(DA_MASSIMA) == pa.DA_FONTE_ESTERNA


def test_l_ordine_del_riconoscimento_conta():
    """`fonte_campo` viene guardato per primo. Un arco di provvedimento ha
    anche `tipo_arco`, quindi chiedendo prima quello finirebbe fra le
    fonti esterne - e perderebbe le sue ancore."""
    assert "tipo_arco" in DA_PROVVEDIMENTO
    assert pa.popolazione(DA_PROVVEDIMENTO) == pa.DA_PROVVEDIMENTO


# ------------------------------------------------ la quarta che non c'e'

def test_una_forma_nuova_non_passa_inosservata():
    """Il danno residuo di questo bug non e' un errore: e' un conteggio
    piu' piccolo del vero, che nessuno mette in dubbio perche' e'
    plausibile. Il censimento e' l'unico posto in cui si vede."""
    quarta = {"peso": 0.7, "origine": "un produttore futuro"}
    assert pa.popolazione(quarta) == pa.SCONOSCIUTA
    conteggio = pa.censimento([("a", "b", quarta)])
    assert conteggio[pa.SCONOSCIUTA] == 1


def test_il_censimento_riporta_tutte_le_chiavi_anche_a_zero():
    """Una popolazione scomparsa e' un'informazione quanto una nuova: se
    la chiave sparisse dal risultato, un'ingestione che smette di produrre
    ancore si vedrebbe come un dizionario piu' corto, non come uno zero."""
    conteggio = pa.censimento([("a", "b", FRA_ARTICOLI)])
    assert set(conteggio) == {pa.FRA_ARTICOLI, pa.DA_PROVVEDIMENTO,
                              pa.DA_FONTE_ESTERNA, pa.SCONOSCIUTA}
    assert conteggio[pa.DA_PROVVEDIMENTO] == 0


def test_il_censimento_somma_a_quanti_archi_ha_ricevuto():
    archi = [("a", "b", FRA_ARTICOLI), ("c", "d", DA_PROVVEDIMENTO),
             ("e", "f", DA_MASSIMA), ("g", "h", {})]
    assert sum(pa.censimento(archi).values()) == len(archi)


def test_un_arco_senza_attributi_e_sconosciuto_non_e_un_articolo():
    """Il caso peggiore da confondere: un dizionario vuoto non e' una
    popolazione con i campi assenti, e' un arco di cui non si sa niente."""
    assert pa.popolazione({}) == pa.SCONOSCIUTA


# ------------------------------------------------------- i due criteri

def test_solo_gli_archi_di_motivazione_valgono_per_la_co_citazione():
    assert pa.e_citazione_in_motivazione(DA_PROVVEDIMENTO)
    assert not pa.e_citazione_in_motivazione(FRA_ARTICOLI)
    assert not pa.e_citazione_in_motivazione(DA_MASSIMA)


def test_una_citazione_dal_dispositivo_non_conta_come_motivazione():
    """Oggi non esiste - tutti e 3229 gli archi con `fonte_campo` valgono
    `motivazione` - quindi il filtro e' corretto e per ora inerte. Questo
    test descrive il giorno in cui smette di esserlo."""
    dal_dispositivo = dict(DA_PROVVEDIMENTO, fonte_campo="dispositivo")
    assert pa.popolazione(dal_dispositivo) == pa.DA_PROVVEDIMENTO
    assert not pa.e_citazione_in_motivazione(dal_dispositivo)


def test_le_ancore_le_ha_solo_il_provvedimento():
    assert pa.ha_ancore(DA_PROVVEDIMENTO)
    assert not pa.ha_ancore(FRA_ARTICOLI)
    assert not pa.ha_ancore(DA_MASSIMA)


def test_una_lista_di_ancore_vuota_non_conta_come_ancorata():
    """`ancore: []` e' un arco che le ancore le ha perse, non uno che le
    ha. La regola 4 non ci si puo' appoggiare in nessuno dei due casi, ma
    solo uno dei due e' un guasto da vedere."""
    assert not pa.ha_ancore(dict(DA_PROVVEDIMENTO, ancore=[]))
