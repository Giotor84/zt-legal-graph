"""Test della variante a due passate di estrazione_eccezioni.py.

File separato da test_estrazione_eccezioni.py perche' la variante ha una
storia sua: e' stata aggiunta il 2026-08-30 sulla diagnosi di Piccioli et
al. 2026 (arXiv 2607.03325), e cio' che questi test proteggono e' che resti
INTERCAMBIABILE con la passata unica - stessi filtri, stesso record, stesso
comportamento sui casi limite. Se le due divergono, il confronto sul golden
set smette di misurare la resa dell'estrazione e comincia a misurare la
differenza fra due schemi.

Nessuna chiamata di rete: llama_server_client e' sostituito da monkeypatch.
"""

import estrazione_eccezioni as ee
import llama_server_client

MOTIVAZIONE = (
    "L'appellante eccepisce la nullita' del contratto per difetto di forma scritta. "
    "Il Collegio ritiene la censura infondata perche' il documento reca la sottoscrizione. "
    "L'appellato eccepisce la tardivita' del gravame. "
    "Tale eccezione resta assorbita."
)
INTEGRALE = "INTESTAZIONE\n" + MOTIVAZIONE
PROVV = {"node_id": "n1", "motivazione": MOTIVAZIONE, "testo_integrale": INTEGRALE}

ECC_1 = "L'appellante eccepisce la nullita' del contratto"
ECC_2 = "L'appellato eccepisce la tardivita' del gravame"
RATIO_1 = "il documento reca la sottoscrizione"


def _senza_segmentazione(monkeypatch):
    monkeypatch.setattr(llama_server_client, "conta_token", lambda base_url, testo, timeout=60: 10)


def _finto(questioni, dettagli):
    """Finto server: la chiamata con SCHEMA_CENSIMENTO risponde con l'elenco,
    quelle con SCHEMA_DETTAGLIO consumano `dettagli` nell'ordine."""
    rimasti = list(dettagli)

    def finto(base_url, prompt, schema, n_predict, temperature, repeat_penalty, timeout, seed=None):
        if schema is ee.SCHEMA_CENSIMENTO:
            return {"questioni": list(questioni), "elementi_non_estraibili": []}
        assert schema is ee.SCHEMA_DETTAGLIO
        return rimasti.pop(0)

    return finto


# --- Intercambiabilita' con la passata unica ------------------------------

def test_stesso_schema_di_record_della_passata_unica(monkeypatch) -> None:
    _senza_segmentazione(monkeypatch)
    monkeypatch.setattr(llama_server_client, "completa_json", _finto(
        [{"eccezione_letterale": ECC_1, "parte_che_la_solleva": "l'appellante"}],
        [{"esito": "rigettata", "ratio_letterale": RATIO_1}],
    ))
    due = ee.estrai_provvedimento_due_passate("http://x", PROVV, n_ctx=16384)

    def finto_unico(base_url, prompt, schema, n_predict, temperature, repeat_penalty, timeout, seed=None):
        return {"coppie": [{"eccezione_letterale": ECC_1,
                            "parte_che_la_solleva": "l'appellante",
                            "esito": "rigettata",
                            "ratio_letterale": RATIO_1}],
                "elementi_non_estraibili": []}

    monkeypatch.setattr(llama_server_client, "completa_json", finto_unico)
    unica = ee.estrai_provvedimento("http://x", PROVV, n_ctx=16384)

    assert len(due.coppie) == len(unica.coppie) == 1
    assert set(due.coppie[0]) == set(unica.coppie[0])
    assert due.coppie[0]["offset_inizio"] == unica.coppie[0]["offset_inizio"]
    assert due.coppie[0]["eccezione_verbatim"] == unica.coppie[0]["eccezione_verbatim"]
    assert due.coppie[0]["classificazione_dato"] == unica.coppie[0]["classificazione_dato"] == "citabile"


def test_gli_offset_sono_sul_testo_integrale_come_nella_passata_unica(monkeypatch) -> None:
    # Il frame degli offset e' quello del testo_integrale, non della
    # motivazione: un errore qui rende incomparabili estrazione e golden set
    # (e' successo davvero, vedi valuta_golden_eccezioni.carica_offset_base).
    _senza_segmentazione(monkeypatch)
    monkeypatch.setattr(llama_server_client, "completa_json", _finto(
        [{"eccezione_letterale": ECC_1, "parte_che_la_solleva": "l'appellante"}],
        [{"esito": "rigettata", "ratio_letterale": None}],
    ))
    (coppia,) = ee.estrai_provvedimento_due_passate("http://x", PROVV, n_ctx=16384).coppie
    assert INTEGRALE[coppia["offset_inizio"]:coppia["offset_fine"]] == coppia["eccezione_verbatim"]
    assert coppia["offset_inizio"] >= len("INTESTAZIONE\n")


def test_applica_gli_stessi_filtri_della_passata_unica(monkeypatch) -> None:
    """Una questione vuota e una non ancorabile vanno scartate con gli stessi
    motivi, non passare perche' arrivano da un percorso diverso."""
    _senza_segmentazione(monkeypatch)
    monkeypatch.setattr(llama_server_client, "completa_json", _finto(
        [{"eccezione_letterale": "", "parte_che_la_solleva": "l'appellante"},
         {"eccezione_letterale": "una frase che nella motivazione non compare affatto",
          "parte_che_la_solleva": "l'appellante"}],
        [{"esito": "rigettata", "ratio_letterale": None}],
    ))
    esito = ee.estrai_provvedimento_due_passate("http://x", PROVV, n_ctx=16384)

    motivi = {s["motivo_scarto"] for s in esito.scartate}
    assert esito.coppie == []
    assert "vuoto_o_placeholder" in motivi
    assert "non_ancorata" in motivi
    assert esito.coppie_generate_dal_modello == 2


def test_motivazione_nulla_non_chiama_il_server(monkeypatch) -> None:
    def non_dovrebbe(*a, **k):
        raise AssertionError("nessuna chiamata attesa")

    monkeypatch.setattr(llama_server_client, "conta_token", non_dovrebbe)
    monkeypatch.setattr(llama_server_client, "completa_json", non_dovrebbe)
    esito = ee.estrai_provvedimento_due_passate(
        "http://x", {"node_id": "n1", "motivazione": None, "testo_integrale": "x"}, n_ctx=16384)
    assert esito.processabile is False
    assert esito.motivo_non_processabile == "motivazione_nulla_nel_grafo"


# --- Struttura delle chiamate --------------------------------------------

def test_una_chiamata_di_dettaglio_per_questione(monkeypatch) -> None:
    _senza_segmentazione(monkeypatch)
    schemi = []

    def finto(base_url, prompt, schema, n_predict, temperature, repeat_penalty, timeout, seed=None):
        schemi.append(schema)
        if schema is ee.SCHEMA_CENSIMENTO:
            return {"questioni": [
                {"eccezione_letterale": ECC_1, "parte_che_la_solleva": "l'appellante"},
                {"eccezione_letterale": ECC_2, "parte_che_la_solleva": "l'appellato"},
            ], "elementi_non_estraibili": []}
        return {"esito": "assorbita", "ratio_letterale": None}

    monkeypatch.setattr(llama_server_client, "completa_json", finto)
    esito = ee.estrai_provvedimento_due_passate("http://x", PROVV, n_ctx=16384)

    assert schemi.count(ee.SCHEMA_CENSIMENTO) == 1
    assert schemi.count(ee.SCHEMA_DETTAGLIO) == 2
    assert len(esito.coppie) == 2


def test_il_dettaglio_riceve_la_questione_e_la_parte(monkeypatch) -> None:
    # Il prompt di dettaglio deve isolare UNA questione, altrimenti la
    # seconda passata rifa' il lavoro della prima e non serve a nulla.
    _senza_segmentazione(monkeypatch)
    prompt_dettaglio = []

    def finto(base_url, prompt, schema, n_predict, temperature, repeat_penalty, timeout, seed=None):
        if schema is ee.SCHEMA_CENSIMENTO:
            return {"questioni": [{"eccezione_letterale": ECC_1,
                                   "parte_che_la_solleva": "l'appellante"}],
                    "elementi_non_estraibili": []}
        prompt_dettaglio.append(prompt)
        return {"esito": "rigettata", "ratio_letterale": None}

    monkeypatch.setattr(llama_server_client, "completa_json", finto)
    ee.estrai_provvedimento_due_passate("http://x", PROVV, n_ctx=16384)

    (p,) = prompt_dettaglio
    assert ECC_1 in p
    assert "l'appellante" in p
    assert ECC_2 not in p.split("---")[-1]


def test_il_seed_arriva_a_entrambe_le_passate(monkeypatch) -> None:
    _senza_segmentazione(monkeypatch)
    semi = []

    def finto(base_url, prompt, schema, n_predict, temperature, repeat_penalty, timeout, seed=None):
        semi.append(seed)
        if schema is ee.SCHEMA_CENSIMENTO:
            return {"questioni": [{"eccezione_letterale": ECC_1,
                                   "parte_che_la_solleva": "l'appellante"}],
                    "elementi_non_estraibili": []}
        return {"esito": "rigettata", "ratio_letterale": None}

    monkeypatch.setattr(llama_server_client, "completa_json", finto)
    ee.estrai_provvedimento_due_passate("http://x", PROVV, n_ctx=16384, seed=4242)
    assert semi == [4242, 4242]


# --- Casi limite ----------------------------------------------------------

def test_un_dettaglio_troncato_non_perde_la_questione(monkeypatch) -> None:
    """La questione e' gia' stata censita: se la seconda chiamata fallisce
    entra comunque, senza esito accertato. Buttarla renderebbe la variante a
    due passate PIU' fragile della passata unica proprio dove dovrebbe
    esserlo meno."""
    _senza_segmentazione(monkeypatch)

    def finto(base_url, prompt, schema, n_predict, temperature, repeat_penalty, timeout, seed=None):
        if schema is ee.SCHEMA_CENSIMENTO:
            return {"questioni": [{"eccezione_letterale": ECC_1,
                                   "parte_che_la_solleva": "l'appellante"}],
                    "elementi_non_estraibili": []}
        raise llama_server_client.RispostaTroncata("troncata", 512, "{")

    monkeypatch.setattr(llama_server_client, "completa_json", finto)
    esito = ee.estrai_provvedimento_due_passate("http://x", PROVV, n_ctx=16384)

    assert len(esito.coppie) == 1
    assert esito.coppie[0]["esito"] == "non_chiaro"
    assert esito.coppie[0]["ratio_stato_ancora"] == "nessuna_ratio"
    assert esito.passaggi_falliti == ["blocco_1_dettaglio_1"]


def test_censimento_fallito_non_solleva(monkeypatch) -> None:
    _senza_segmentazione(monkeypatch)

    def finto(base_url, prompt, schema, n_predict, temperature, repeat_penalty, timeout, seed=None):
        raise llama_server_client.RispostaTroncata("troncata", 512, "{")

    monkeypatch.setattr(llama_server_client, "completa_json", finto)
    esito = ee.estrai_provvedimento_due_passate("http://x", PROVV, n_ctx=16384)

    assert esito.coppie == []
    assert esito.passaggi_falliti == ["blocco_1_censimento"]


def test_censimento_vuoto_non_chiama_il_dettaglio(monkeypatch) -> None:
    _senza_segmentazione(monkeypatch)
    dettagli = []

    def finto(base_url, prompt, schema, n_predict, temperature, repeat_penalty, timeout, seed=None):
        if schema is ee.SCHEMA_CENSIMENTO:
            return {"questioni": [], "elementi_non_estraibili": ["nulla di deciso in questo brano"]}
        dettagli.append(prompt)
        return {"esito": "non_chiaro", "ratio_letterale": None}

    monkeypatch.setattr(llama_server_client, "completa_json", finto)
    esito = ee.estrai_provvedimento_due_passate("http://x", PROVV, n_ctx=16384)

    assert dettagli == []
    assert esito.coppie == []
    assert esito.elementi_non_estraibili == ["[blocco_1] nulla di deciso in questo brano"]


def test_lo_schema_di_censimento_non_chiede_esito_ne_ratio() -> None:
    # E' il punto dell'intera variante: la passata 1 deve produrre voci
    # CORTE. Se le si riaggiungessero i campi lunghi, tornerebbe a essere
    # una passata unica con un giro in piu'.
    campi = ee.SCHEMA_CENSIMENTO["properties"]["questioni"]["items"]["properties"]
    assert set(campi) == {"eccezione_letterale", "parte_che_la_solleva"}
    assert campi["eccezione_letterale"]["maxLength"] < \
        ee.SCHEMA_COPPIE["properties"]["coppie"]["items"]["properties"]["eccezione_letterale"]["maxLength"]
    assert ee.SCHEMA_CENSIMENTO["properties"]["questioni"]["maxItems"] > \
        ee.SCHEMA_COPPIE["properties"]["coppie"]["maxItems"]
