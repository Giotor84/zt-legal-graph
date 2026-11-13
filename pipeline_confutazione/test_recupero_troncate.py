# -*- coding: utf-8 -*-
"""Il recupero di una risposta troncata (contratto 1.34).

Cio' che questi test difendono e' il confine: si salva SOLO cio' che il
modello aveva gia' finito di scrivere. Un oggetto ricucito da Python
sarebbe un oggetto che il modello non ha emesso, e finirebbe in un atto
difensivo come se l'avesse emesso.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import estrazione_atto as ea  # noqa: E402
import llama_server_client  # noqa: E402


def _troncata(parziale: str) -> llama_server_client.RispostaTroncata:
    return llama_server_client.RispostaTroncata("limit", 4096, parziale)


def test_gli_oggetti_gia_chiusi_si_salvano():
    parziale = ('{"eccezioni_sollevate": [{"testo_letterale": "la prima"}, '
                '{"testo_letterale": "la seconda"}, {"testo_letter')

    fuori = ea.recupera_da_troncata(parziale)

    assert [e["testo_letterale"] for e in fuori["eccezioni_sollevate"]] == [
        "la prima", "la seconda"]


def test_l_oggetto_tagliato_a_meta_non_si_ricuce():
    """E' il punto dell'intero modulo. Un oggetto completato da Python
    sarebbe indistinguibile da uno emesso dal modello, e la regola 4 vale
    su cio' che il modello ha davvero prodotto."""
    parziale = ('{"eccezioni_sollevate": [{"testo_letterale": "la prima"}, '
                '{"testo_letterale": "la second')

    fuori = ea.recupera_da_troncata(parziale)

    assert len(fuori["eccezioni_sollevate"]) == 1
    assert "second" not in json.dumps(fuori)


def test_i_campi_interi_prima_del_taglio_restano():
    parziale = ('{"elementi_non_estraibili": ["un buco dichiarato"], '
                '"eccezioni_sollevate": [{"testo_letterale": "la prima"}, {"tes')

    fuori = ea.recupera_da_troncata(parziale)

    assert fuori["elementi_non_estraibili"] == ["un buco dichiarato"]
    assert len(fuori["eccezioni_sollevate"]) == 1


def test_niente_di_completo_niente_di_recuperato():
    """Senza questo, un parziale illeggibile diventerebbe un passaggio
    'riuscito' con zero elementi - che e' esattamente la confusione fra
    'non ha trovato nulla' e 'non e' riuscito a rispondere' che il campo
    passaggi_falliti esiste per evitare."""
    assert ea.recupera_da_troncata('{"eccezioni_sollevate": [{"tes') == {}
    assert ea.recupera_da_troncata("") == {}
    assert ea.recupera_da_troncata("non e' JSON") == {}


def test_non_serve_aggiornarla_quando_uno_schema_cambia():
    """Schema-agnostica di proposito: legge le chiavi che trova, non
    quelle che si aspetta. Uno schema nuovo non deve poter rendere muto il
    recupero senza che nessun test se ne accorga."""
    parziale = '{"campo_mai_visto_prima": [{"a": 1}, {"b": 2}, {"c'

    assert ea.recupera_da_troncata(parziale) == {
        "campo_mai_visto_prima": [{"a": 1}, {"b": 2}]}


def test_un_passaggio_recuperato_non_e_ne_riuscito_ne_fallito():
    """I due elenchi esistenti direbbero una cosa falsa in entrambi i
    versi: fra i riusciti nasconde che l'elenco e' tagliato, fra i falliti
    dice che non ha prodotto nulla mentre ha prodotto."""
    esiti = ea.EsitoEstrazione()

    fuori = ea._recupera_o_fallisci(
        _troncata('{"eccezioni_sollevate": [{"testo_letterale": "la prima"}, {"t'),
        "eccezioni_blocco_1", esiti)

    assert fuori is not None and len(fuori["eccezioni_sollevate"]) == 1
    assert esiti.passaggi_falliti == []
    assert len(esiti.passaggi_recuperati) == 1
    voce = esiti.passaggi_recuperati[0]
    assert voce["passaggio"] == "eccezioni_blocco_1"
    assert voce["motivo"] == "limit"
    assert voce["elementi"] == 1


def test_senza_niente_da_salvare_il_passaggio_resta_fallito():
    esiti = ea.EsitoEstrazione()

    fuori = ea._recupera_o_fallisci(_troncata('{"eccezioni_sollev'),
                                    "eccezioni_blocco_2", esiti)

    assert fuori is None
    assert esiti.passaggi_falliti == ["eccezioni_blocco_2"]
    assert esiti.passaggi_recuperati == []


def test_il_taglio_e_dichiarato_nei_buchi():
    """Un elenco tagliato che passa a valle senza dirlo e' peggio di un
    elenco perso: chi rivede conta le eccezioni e crede che siano tutte."""
    esiti = ea.EsitoEstrazione()
    ea._recupera_o_fallisci(
        _troncata('{"eccezioni_sollevate": [{"testo_letterale": "la prima"}, {"t'),
        "eccezioni_blocco_1", esiti)

    buchi = esiti.elementi_non_estraibili_totali()

    voci = [b for b in buchi if b["tipo"] == "passaggio_recuperato"]
    assert len(voci) == 1
    assert "TAGLIATO" in voci[0]["testo"]
    assert "eccezioni_blocco_1" in voci[0]["testo"]


def test_il_tipo_di_buco_e_nel_contratto():
    """Lezione della 1.30: il codice emetteva un tipo che il contratto non
    conosceva, e Fase 1 moriva in validazione a fine corsa su un atto su
    cinque - dopo aver speso l'intera estrazione."""
    schema = json.loads((Path(__file__).parents[1] / "contratti"
                         / "fase1_estrazione.schema.json").read_text(encoding="utf-8"))
    ammessi = schema["properties"]["buchi"]["items"]["properties"]["tipo"]["enum"]

    assert set(ea.TIPI_BUCO) <= set(ammessi)
    assert "passaggio_recuperato" in ammessi


@pytest.mark.parametrize("parziale", [
    '{"a": [1, 2, 3',
    '{"a": [{"b": [1, 2]}, {"b": [3',
    '{"a": "stringa intera", "b": [',
])
def test_non_solleva_mai_su_un_parziale_qualunque(parziale):
    """Il recupero gira dentro il gestore di un'eccezione: se sollevasse a
    sua volta, un passaggio troncato diventerebbe una corsa morta - il
    contrario di cio' per cui esiste."""
    assert isinstance(ea.recupera_da_troncata(parziale), dict)
