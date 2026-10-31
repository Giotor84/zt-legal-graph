"""
Test di estrazione_eccezioni.py - le correzioni degli 8 difetti misurati
nell'audit del 2026-08-25 sul campione di 206 coppie/38 provvedimenti.

Nessuna chiamata di rete: le funzioni pure (verbatim, dedup, filtri di
classe, parte_normalizzata, log-odds) sono testate isolate; l'orchestrazione
di estrai_provvedimento e' testata con llama_server_client.completa_json e
conta_token monkeypatchati, cosi' la suite resta verde senza llama-server
acceso (stesso principio di conftest.py per le corse dal vivo).
"""

from __future__ import annotations

import sys
from pathlib import Path

CARTELLA = Path(__file__).parent
sys.path.insert(0, str(CARTELLA))

import estrazione_eccezioni as ee
import llama_server_client


# --------------------------------------------------------------- [1] verbatim + elisione


def test_verbatim_e_sempre_una_slice_del_testo_integrale() -> None:
    testo = "Il fideiussore eccepisce la nullita' della garanzia omnibus per difetto di forma."
    inizio, fine = 4, 15
    assert ee.calcola_verbatim(testo, inizio, fine) == testo[inizio:fine]


def test_elisione_ereditata_da_fonte_vs_inventata_dal_modello() -> None:
    """Scoperta del 2026-08-25 (altra sessione, riverificata): la
    pseudonimizzazione a monte lascia '[...]' letterali nel testo_integrale
    stesso. Il modello che li copia fedelmente non sta 'inventando'
    un'elisione - va distinto da quando lo fa lui, anche se la decisione di
    scarto (contiene_elisione_esplicita) resta identica in entrambi i casi."""
    testo_integrale = "CP_6\n[...]l settimo motivo censura la sentenza impugnata nella parte in cui ha rilevato la soccombenza."
    testo_modello_ereditato = "[...]l settimo motivo censura la sentenza impugnata nella parte in cui ha rilevato la soccombenza."
    assert ee.elisione_ereditata_da_fonte(testo_modello_ereditato, testo_integrale) is True

    testo_modello_inventato = "il giudice ha [...] rigettato la domanda per i motivi sopra esposti"
    assert ee.elisione_ereditata_da_fonte(testo_modello_inventato, testo_integrale) is False

    # nessun '[...]' nel testo del modello: non applicabile, non ereditato
    assert ee.elisione_ereditata_da_fonte("un testo del tutto normale", testo_integrale) is False


def test_elisione_esplicita_rilevata_solo_con_parentesi_quadre() -> None:
    assert ee.contiene_elisione_esplicita("ha rigettato l'eccezione [...] rilevando che") is True
    assert ee.contiene_elisione_esplicita("un testo del tutto normale.") is False
    assert ee.contiene_elisione_esplicita(None) is False
    assert ee.contiene_elisione_esplicita("") is False


def test_ratio_con_elisione_non_scarta_la_coppia_solo_la_ratio(monkeypatch) -> None:
    """Difetto [1]: la ratio con "[...]" va trattata come assente, non deve
    far sparire l'intera coppia (l'eccezione resta valida)."""
    motivazione = "L'appellante eccepisce la nullita' del contratto. La censura non coglie nel segno [...] per le ragioni gia' esposte."
    testo_integrale = "PREMESSA\n" + motivazione

    def finto_completa_json(base_url, prompt, schema, n_predict, temperature, repeat_penalty, timeout, seed=None):
        return {
            "coppie": [{
                "eccezione_letterale": "L'appellante eccepisce la nullita' del contratto.",
                "parte_che_la_solleva": "l'appellante",
                "esito": "rigettata",
                "ratio_letterale": "La censura non coglie nel segno [...] per le ragioni gia' esposte.",
            }],
            "elementi_non_estraibili": [],
        }

    monkeypatch.setattr(llama_server_client, "conta_token", lambda base_url, testo, timeout=60: 10)
    monkeypatch.setattr(llama_server_client, "completa_json", finto_completa_json)

    provv = {"node_id": "n1", "motivazione": motivazione, "testo_integrale": testo_integrale}
    esito = ee.estrai_provvedimento("http://x", provv, n_ctx=16384)

    assert len(esito.coppie) == 1
    coppia = esito.coppie[0]
    assert coppia["ratio_letterale"] is None
    assert coppia["ratio_scartata_motivo"] == "elisione_esplicita_ratio"
    assert coppia["classificazione_dato"] == "strategico"
    assert coppia["eccezione_verbatim"] == testo_integrale[coppia["offset_inizio"]:coppia["offset_fine"]]


# --------------------------------------------------------------- [2] dedup per span (IoU)


def _coppia(node_id, inizio, fine, corrispondenza="normalizzata", similarita=0.9):
    return {
        "node_id": node_id,
        "offset_inizio": inizio,
        "offset_fine": fine,
        "eccezione_corrispondenza": corrispondenza,
        "eccezione_similarita": similarita,
        "eccezione_letterale": f"testo[{inizio}:{fine}]",
    }


def test_dedup_tiene_la_corrispondenza_piu_esatta() -> None:
    coppie = [
        _coppia("n1", 11712, 11981, corrispondenza="fuzzy", similarita=0.96),
        _coppia("n1", 11712, 11984, corrispondenza="normalizzata"),
        _coppia("n1", 11712, 11981, corrispondenza="esatta"),
    ]
    tenute, scartate = ee.deduplica_per_span(coppie)
    assert len(tenute) == 1
    assert tenute[0]["eccezione_corrispondenza"] == "esatta"
    assert len(scartate) == 2
    assert all(s["motivo_scarto"] == "duplicato_span" for s in scartate)


def test_dedup_non_fonde_span_sotto_soglia_iou() -> None:
    coppie = [_coppia("n1", 0, 100), _coppia("n1", 90, 300)]  # IoU basso: 10/300
    tenute, scartate = ee.deduplica_per_span(coppie, soglia_iou=0.8)
    assert len(tenute) == 2
    assert scartate == []


def test_dedup_e_per_provvedimento_non_globale() -> None:
    """Stesso span, provvedimenti diversi: non sono duplicati."""
    coppie = [_coppia("n1", 100, 200), _coppia("n2", 100, 200)]
    tenute, scartate = ee.deduplica_per_span(coppie)
    assert len(tenute) == 2
    assert scartate == []


# --------------------------------------------------------------- [3] falsi positivi per classe


def test_soggetto_organo_giudicante() -> None:
    assert ee.soggetto_e_organo_giudicante("il Collegio") is True
    assert ee.soggetto_e_organo_giudicante("il CTU") is True
    assert ee.soggetto_e_organo_giudicante("il consulente d'ufficio") is True
    assert ee.soggetto_e_organo_giudicante("l'appellante") is False
    assert ee.soggetto_e_organo_giudicante("") is False


def test_formula_conclusiva_o_dispositivo() -> None:
    assert ee.e_formula_conclusiva_o_dispositivo("Piaccia all'Ecc.ma Corte di Appello, ogni contraria istanza...") is True
    assert ee.e_formula_conclusiva_o_dispositivo("- dichiarare inammissibile l'appello formulato;") is True
    assert ee.e_formula_conclusiva_o_dispositivo("rigettare l'appello e confermare la sentenza impugnata") is True
    assert ee.e_formula_conclusiva_o_dispositivo("L'appellante eccepisce la nullita' del contratto") is False


def test_riferimento_a_motivo_senza_contenuto() -> None:
    assert ee.e_riferimento_a_motivo_senza_contenuto("il secondo motivo") is True
    assert ee.e_riferimento_a_motivo_senza_contenuto("il quarto motivo") is True
    assert ee.e_riferimento_a_motivo_senza_contenuto("il primo ed il terzo motivo di impugnazione") is True
    # con contenuto proprio, non solo il rimando: non deve scattare
    assert ee.e_riferimento_a_motivo_senza_contenuto("il secondo motivo, con cui si censura la mancata prova del credito") is False


def test_verdetto_senza_contenuto() -> None:
    assert ee.e_verdetto_senza_contenuto("I motivi sono fondati.") is True
    assert ee.e_verdetto_senza_contenuto("Il motivo è infondato.") is True
    assert ee.e_verdetto_senza_contenuto("L'appellante eccepisce la nullita' del contratto per difetto di forma.") is False


def test_istanza_istruttoria() -> None:
    assert ee.e_istanza_istruttoria("la rimessione della controversia in istruttoria e lo svolgimento di una consulenza tecnica d'ufficio.") is True
    assert ee.e_istanza_istruttoria("l'ammissione di CTU sulla debenza degli interessi") is True
    assert ee.e_istanza_istruttoria("la nullita' parziale dei contratti di fideiussione") is False


def test_classifica_falso_positivo_none_per_eccezione_genuina() -> None:
    assert ee.classifica_falso_positivo(
        "la carenza di titolarita' del diritto di credito", "l'appellante",
    ) is None


# --------------------------------------------------------------- [4] parte_normalizzata


def test_parte_normalizzata_vocabolario_chiuso() -> None:
    casi = {
        "l'appellante": "appellante",
        "l’appellante": "appellante",  # apostrofo curvo
        "gli appellanti": "appellante",
        "l'appellato": "appellato",
        "l’appellata": "appellato",
        "il ricorrente": "ricorrente",
        "il resistente": "resistente",
        "l'opponente": "opponente",
        "l'opposto": "opposto",
        "il terzo chiamato": "terzo",
    }
    for grezza, attesa in casi.items():
        assert ee.normalizza_parte(grezza) == attesa, grezza

    # segnaposto di pseudonimizzazione e valori non mappabili: non_determinabile,
    # mai un valore nuovo inventato
    for non_mappabile in ("Parte_1", "CP_3", "Controparte_2", "la convenuta", "", None):
        assert ee.normalizza_parte(non_mappabile) == "non_determinabile"


def test_parte_normalizzata_sempre_nel_vocabolario_chiuso_dichiarato() -> None:
    for grezza in ("l'appellante", "Parte_9", "il Collegio", "boh", ""):
        assert ee.normalizza_parte(grezza) in ee.PARTE_VOCABOLARIO_CHIUSO


# --------------------------------------------------------------- [5] indipendenza dei contatori


def test_verifica_contatori_indipendenti_rileva_coincidenza_numerica() -> None:
    scartate = [{"motivo_scarto": "non_ancorata"}] * 61
    coppie = [{"eccezione_corrispondenza": "fuzzy"}] * 61 + [{"eccezione_corrispondenza": "esatta"}] * 100
    esito = ee.verifica_contatori_indipendenti(scartate, coppie)
    assert esito["coppie_scartate_non_ancorate"] == 61
    assert esito["coppie_ancorate_fuzzy"] == 61
    assert esito["coincidono"] is True
    assert esito["liste_disgiunte_per_costruzione"] is True


def test_verifica_contatori_indipendenti_numeri_diversi() -> None:
    scartate = [{"motivo_scarto": "non_ancorata"}] * 40
    coppie = [{"eccezione_corrispondenza": "fuzzy"}] * 12
    esito = ee.verifica_contatori_indipendenti(scartate, coppie)
    assert esito["coincidono"] is False


# --------------------------------------------------------------- [6] contrasto log-odds


def test_contrasto_log_odds_e_deterministico_a_parita_di_seed() -> None:
    testo_per_nodo = {
        "n1": "premessa lunga. " * 20 + "il fideiussore eccepisce la nullita' della fideiussione per difetto di forma scritta. " * 3,
    }
    coppie = [{"node_id": "n1", "offset_inizio": 330}, {"node_id": "n1", "offset_inizio": 420}]

    r1 = ee.contrasto_log_odds(coppie, testo_per_nodo, seed=42)
    r2 = ee.contrasto_log_odds(coppie, testo_per_nodo, seed=42)
    assert r1 == r2


def test_contrasto_log_odds_denominatore_e_solo_le_ancorate() -> None:
    """Difetto [6]: il contrasto usa SOLO le coppie con un contesto reale
    (ancorate), niente frequenza grezza su un denominatore piu' grande."""
    testo_per_nodo = {"n1": "x" * 500}
    coppie = [{"node_id": "n1", "offset_inizio": 200}, {"node_id": "sconosciuto", "offset_inizio": 10}]
    # non deve sollevare per il node_id assente da testo_per_nodo
    risultato = ee.contrasto_log_odds(coppie, testo_per_nodo, seed=1)
    assert isinstance(risultato, list)


# --------------------------------------------------------------- [7] motivazione nulla: percorso esplicito


def test_motivazione_nulla_e_un_percorso_esplicito_non_un_eccezione(monkeypatch) -> None:
    chiamato = False

    def non_dovrebbe_essere_chiamato(*a, **k):
        nonlocal chiamato
        chiamato = True
        raise AssertionError("non deve chiamare il server per un provvedimento senza motivazione")

    monkeypatch.setattr(llama_server_client, "conta_token", non_dovrebbe_essere_chiamato)
    monkeypatch.setattr(llama_server_client, "completa_json", non_dovrebbe_essere_chiamato)

    provv = {"node_id": "n1", "motivazione": None, "testo_integrale": "qualcosa"}
    esito = ee.estrai_provvedimento("http://x", provv, n_ctx=16384)

    assert chiamato is False
    assert esito.processabile is False
    assert esito.motivo_non_processabile == "motivazione_nulla_nel_grafo"
    assert esito.coppie == []
    assert esito.scartate == []


def test_schema_identico_segmentato_e_non_segmentato(monkeypatch) -> None:
    """Difetto [7]: stesso schema di output sui due percorsi - stessa
    funzione di costruzione del record indipendentemente da quanti blocchi
    genera _costruisci_blocchi."""
    testo_breve = "L'appellante eccepisce la nullita' del contratto per difetto di forma scritta."
    testo_integrale = "INTESTAZIONE\n" + testo_breve

    def finto_completa_json(base_url, prompt, schema, n_predict, temperature, repeat_penalty, timeout, seed=None):
        return {
            "coppie": [{
                "eccezione_letterale": "L'appellante eccepisce la nullita' del contratto per difetto di forma scritta.",
                "parte_che_la_solleva": "l'appellante",
                "esito": "accolta",
                "ratio_letterale": None,
            }],
            "elementi_non_estraibili": [],
        }

    monkeypatch.setattr(llama_server_client, "completa_json", finto_completa_json)

    # percorso NON segmentato: token contati sotto budget
    monkeypatch.setattr(llama_server_client, "conta_token", lambda base_url, testo, timeout=60: 10)
    provv = {"node_id": "n1", "motivazione": testo_breve, "testo_integrale": testo_integrale}
    esito_non_segmentato = ee.estrai_provvedimento("http://x", provv, n_ctx=16384)

    # percorso segmentato: forzo il conteggio token sopra budget cosi'
    # _costruisci_blocchi entra in gioco (un solo segmento naturale, quindi
    # un solo blocco comunque - basta a esercitare il ramo, la parita' di
    # schema e' cio' che si verifica)
    monkeypatch.setattr(llama_server_client, "conta_token", lambda base_url, testo, timeout=60: 10**9)
    esito_segmentato = ee.estrai_provvedimento("http://x", provv, n_ctx=16384)

    assert esito_non_segmentato.segmentato is False
    assert esito_segmentato.segmentato is True
    assert len(esito_non_segmentato.coppie) == 1
    assert len(esito_segmentato.coppie) == 1
    assert set(esito_non_segmentato.coppie[0].keys()) == set(esito_segmentato.coppie[0].keys())
    # anche l'ancoraggio deve combaciare: stesso testo, stessi offset
    assert esito_non_segmentato.coppie[0]["offset_inizio"] == esito_segmentato.coppie[0]["offset_inizio"]
    assert esito_non_segmentato.coppie[0]["offset_fine"] == esito_segmentato.coppie[0]["offset_fine"]


# --------------------------------------------------------------- invarianti generali


def test_invariante_somma_emesse_e_scartate_uguale_generate(monkeypatch) -> None:
    motivazione = (
        "L'appellante eccepisce la nullita' del contratto per difetto di forma scritta. "
        "Il Collegio ritiene la censura infondata. "
        "il secondo motivo. "
        "Piaccia all'Ecc.ma Corte di Appello accogliere il gravame."
    )
    testo_integrale = "INTESTAZIONE\n" + motivazione

    def finto_completa_json(base_url, prompt, schema, n_predict, temperature, repeat_penalty, timeout, seed=None):
        return {
            "coppie": [
                {
                    "eccezione_letterale": "L'appellante eccepisce la nullita' del contratto per difetto di forma scritta.",
                    "parte_che_la_solleva": "l'appellante",
                    "esito": "accolta",
                    "ratio_letterale": None,
                },
                {
                    "eccezione_letterale": "il secondo motivo.",
                    "parte_che_la_solleva": "l'appellante",
                    "esito": "non_esaminata",
                    "ratio_letterale": None,
                },
                {
                    "eccezione_letterale": "Piaccia all'Ecc.ma Corte di Appello accogliere il gravame.",
                    "parte_che_la_solleva": "l'appellante",
                    "esito": "non_esaminata",
                    "ratio_letterale": None,
                },
                {
                    "eccezione_letterale": "testo mai presente nella motivazione, non ancorabile",
                    "parte_che_la_solleva": "l'appellante",
                    "esito": "non_chiaro",
                    "ratio_letterale": None,
                },
            ],
            "elementi_non_estraibili": [],
        }

    monkeypatch.setattr(llama_server_client, "conta_token", lambda base_url, testo, timeout=60: 10)
    monkeypatch.setattr(llama_server_client, "completa_json", finto_completa_json)

    provv = {"node_id": "n1", "motivazione": motivazione, "testo_integrale": testo_integrale}
    esito = ee.estrai_provvedimento("http://x", provv, n_ctx=16384)

    assert esito.coppie_generate_dal_modello == 4
    assert len(esito.coppie) + len(esito.scartate) == esito.coppie_generate_dal_modello
    motivi = {s["motivo_scarto"] for s in esito.scartate}
    assert "riferimento_a_motivo_senza_contenuto" in motivi
    assert "formula_conclusiva_o_dispositivo" in motivi
    assert "non_ancorata" in motivi


def test_ogni_coppia_citabile_ha_verbatim_ancorato_su_eccezione_e_ratio(monkeypatch) -> None:
    motivazione = "L'appellante eccepisce la nullita' del contratto. Il motivo e' fondato perche' manca la forma scritta."
    testo_integrale = "INTESTAZIONE\n" + motivazione

    def finto_completa_json(base_url, prompt, schema, n_predict, temperature, repeat_penalty, timeout, seed=None):
        return {
            "coppie": [{
                "eccezione_letterale": "L'appellante eccepisce la nullita' del contratto.",
                "parte_che_la_solleva": "l'appellante",
                "esito": "accolta",
                "ratio_letterale": "Il motivo e' fondato perche' manca la forma scritta.",
            }],
            "elementi_non_estraibili": [],
        }

    monkeypatch.setattr(llama_server_client, "conta_token", lambda base_url, testo, timeout=60: 10)
    monkeypatch.setattr(llama_server_client, "completa_json", finto_completa_json)

    provv = {"node_id": "n1", "motivazione": motivazione, "testo_integrale": testo_integrale}
    esito = ee.estrai_provvedimento("http://x", provv, n_ctx=16384)

    assert len(esito.coppie) == 1
    c = esito.coppie[0]
    assert c["classificazione_dato"] == "citabile"
    assert c["eccezione_verbatim"] == testo_integrale[c["offset_inizio"]:c["offset_fine"]]
    assert c["ratio_verbatim"] == testo_integrale[c["ratio_offset_inizio"]:c["ratio_offset_fine"]]
    assert "[...]" not in c["eccezione_verbatim"]
    assert "[...]" not in c["ratio_verbatim"]


# --------------------------------------------------------------- estrai_corpus


def test_estrai_corpus_meta_e_invariante_su_corpus_misto(monkeypatch) -> None:
    """Un provvedimento processabile + uno a motivazione nulla: la corsa
    intera non deve saltare il secondo silenziosamente (difetto [7]), e
    l'invariante emesse+scartate==generate deve valere sul totale."""
    motivazione = "L'appellante eccepisce la nullita' del contratto per difetto di forma scritta."
    testo_integrale = "INTESTAZIONE\n" + motivazione

    def finto_completa_json(base_url, prompt, schema, n_predict, temperature, repeat_penalty, timeout, seed=None):
        return {
            "coppie": [{
                "eccezione_letterale": motivazione,
                "parte_che_la_solleva": "l'appellante",
                "esito": "accolta",
                "ratio_letterale": None,
            }],
            "elementi_non_estraibili": [],
        }

    monkeypatch.setattr(llama_server_client, "conta_token", lambda base_url, testo, timeout=60: 10)
    monkeypatch.setattr(llama_server_client, "completa_json", finto_completa_json)
    monkeypatch.setattr(llama_server_client, "proprieta_server", lambda base_url, timeout=30: {"modello": "finto", "n_ctx": 16384})

    provvedimenti = [
        {"node_id": "n1", "motivazione": motivazione, "testo_integrale": testo_integrale},
        {"node_id": "n2", "motivazione": None, "testo_integrale": "solo dispositivo, niente motivazione"},
    ]
    risultato = ee.estrai_corpus("http://x", provvedimenti, n_ctx=16384)

    assert risultato["meta"]["provvedimenti_totali_nel_grafo"] == 2
    assert risultato["meta"]["provvedimenti_processati"] == 1
    assert len(risultato["meta"]["provvedimenti_non_processabili"]) == 1
    assert risultato["meta"]["provvedimenti_non_processabili"][0]["node_id"] == "n2"
    assert risultato["meta"]["esecuzione"]["temperature_per_passo"]["eccezioni_coppie"] == 0.0
    assert risultato["meta"]["esecuzione"]["cache_prompt"] is False
    assert len(risultato["coppie"]) + len(risultato["scartate"]) == risultato["meta"]["coppie_generate_dal_modello"]


def test_il_seed_arriva_al_client(monkeypatch):
    """Regressione: senza `seed` nel payload llama-server usa il proprio
    default (4294967295 = casuale a ogni richiesta) e ogni corsa e' un
    campione diverso. E' il bug di estrazione_atto.py del 2026-08-24, che
    qui ha prodotto 206 / 176 / 408 coppie sullo stesso corpus. Il test
    controlla il PASSAGGIO del parametro, non la riproducibilita' (quella
    si misura solo dal vivo, server riavviato - protocollo sezione 4)."""
    visti = []

    def finto_completa_json(base_url, prompt, schema, n_predict, temperature,
                             repeat_penalty, timeout, seed=None):
        visti.append(seed)
        return {"coppie": [], "elementi_non_estraibili": []}

    monkeypatch.setattr(llama_server_client, "conta_token", lambda base_url, testo, timeout=60: 10)
    monkeypatch.setattr(llama_server_client, "completa_json", finto_completa_json)

    provv = {"node_id": "n1", "motivazione": "Il motivo e' infondato.",
             "testo_integrale": "Il motivo e' infondato."}

    ee.estrai_provvedimento("http://x", provv, n_ctx=16384)
    assert visti == [ee.SEED], "il seed di default del modulo non arriva al client"

    ee.estrai_provvedimento("http://x", provv, n_ctx=16384, seed=99)
    assert visti[-1] == 99, "il seed esplicito del chiamante non arriva al client"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
