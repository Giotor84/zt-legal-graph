# -*- coding: utf-8 -*-
"""Il controllo di citabilita'.

Cio' che i test difendono e' la FORMA della domanda, non le risposte del
modello: la forma e' l'unica cosa che il codice controlla, e quattro volte
su quattro in questo progetto il difetto stava li' - una casella mancante,
un pollice sulla bilancia nel prompt, la decisione emessa prima del motivo.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import citabilita  # noqa: E402


def _server(categoria="sta_in_piedi_da_sola", motivo="", grezza=None):
    def completa_json(base_url, prompt, schema, **kwargs):
        assert schema is citabilita.SCHEMA
        if grezza is not None:
            return grezza
        return {"motivo": motivo, "categoria": categoria}

    return completa_json


def test_una_fetta_che_afferma_e_citabile(monkeypatch):
    monkeypatch.setattr(citabilita.llama_server_client, "completa_json",
                        _server("sta_in_piedi_da_sola"))

    esito = citabilita.valuta("http://x", "la fideiussione e' nulla per "
                                          "difetto di forma scritta")

    assert esito["citabile"] is True
    assert esito["categoria"] == "sta_in_piedi_da_sola"


def test_un_frammento_sospeso_non_e_citabile(monkeypatch):
    monkeypatch.setattr(citabilita.llama_server_client, "completa_json",
                        _server("frammento_sospeso"))

    assert citabilita.valuta("http://x", "ha censurato la statuizione del")["citabile"] is False


def test_una_frase_intera_che_rimanda_altrove_non_e_citabile(monkeypatch):
    """E' il caso per cui le categorie sono tre e non due: "tale eccezione e'
    fondata" e' grammaticalmente completa, nessun controllo sulla forma la
    segnalerebbe, e citata da sola non dice di che cosa parli. Senza una
    casella propria finirebbe fra le citabili - il difetto piu' pericoloso
    dei due, perche' passa inosservato."""
    monkeypatch.setattr(citabilita.llama_server_client, "completa_json",
                        _server("dipende_dal_contesto"))

    assert citabilita.valuta("http://x", "tale eccezione e' fondata")["citabile"] is False


def test_una_risposta_fuori_vocabolario_non_diventa_citabile(monkeypatch):
    """Un modello che risponde fuori schema non sta dando un giudizio di cui
    fidarsi, e la fetta finirebbe in un atto depositato. Si cade sulla
    categoria non citabile piu' cauta."""
    monkeypatch.setattr(citabilita.llama_server_client, "completa_json",
                        _server(grezza={"motivo": "boh", "categoria": "forse"}))

    esito = citabilita.valuta("http://x", "una fetta qualsiasi")

    assert esito["citabile"] is False
    assert esito["categoria"] in citabilita.CATEGORIE


def test_il_motivo_esce_prima_della_decisione():
    """Con la decodifica vincolata i campi escono nell'ordine dello schema.
    Con la decisione per prima il modello decide e poi razionalizza: e'
    successo davvero, e il terzo stadio della spazzata respinse 8 candidati
    su 8 mentre i suoi stessi `motivo` dicevano il contrario."""
    campi = list(citabilita.SCHEMA["properties"])

    assert campi.index("motivo") < campi.index("categoria")


def test_nessuna_categoria_e_una_via_di_uscita_che_costa_meno():
    """Le tre categorie sono descrizioni positive di che cosa la fetta E'.
    Un'istruzione tipo "nel dubbio rispondi X" non e' una soglia calibrata:
    e' un pollice sulla bilancia, e ha gia' prodotto un rifiuto su 8 casi
    su 8."""
    prompt = citabilita.costruisci_prompt("una frase")

    for categoria in citabilita.CATEGORIE:
        assert categoria in prompt, "%s non e' offerta come risposta" % categoria
    for pollice in ("nel dubbio", "Nel dubbio", "se non sei sicuro",
                    "in caso di incertezza"):
        assert pollice not in prompt


def test_la_fetta_si_giudica_senza_il_testo_intorno():
    """Col periodo intero davanti anche "ha censurato la statuizione del" si
    capisce benissimo - ed e' esattamente cio' che non deve succedere. La
    domanda e' se la fetta regga QUANDO IL CONTESTO NON C'E', che e' la
    condizione del giudice che legge la citazione nell'atto."""
    fetta = "una frase qualunque da controllare"
    prompt = citabilita.costruisci_prompt(fetta)

    assert prompt.count(fetta) == 1, "la fetta compare una volta sola"
    assert "NON avra' davanti il documento" in prompt


def test_il_taglio_a_meta_di_un_periodo_non_e_di_per_se_un_difetto():
    """Il difetto misurato dell'euristica precedente: 9 falsi allarmi su 31
    su fette da 122 a 644 caratteri che finivano con un punto e virgola e
    che l'avvocato ha giudicato citabili. Il prompt deve dirlo, altrimenti
    il modello rifa' lo stesso errore della regex."""
    prompt = citabilita.costruisci_prompt("x")

    assert "a meta' di un periodo piu' lungo" in prompt
    assert "non come sia tagliata" in prompt


def test_una_citazione_non_deve_raccontare_tutta_la_causa():
    """Il difetto misurato della prima versione: 10 falsi allarmi su 31, quasi
    tutti `dipende_dal_contesto`, e i `motivo` del modello dicevano "non
    specifica chi la solleva", "non indica il contesto". La definizione era
    ambigua e il modello l'ha letta come "non descrive tutta la causa" - cosa
    vera di qualunque citazione.

    `dipende_dal_contesto` deve valere per i RIMANDI ESPLICITI, non per cio'
    che una frase semplicemente non ha bisogno di dire."""
    prompt = citabilita.costruisci_prompt("x")

    for rimando in ("tale", "di cui sopra", "ne consegue"):
        assert rimando in prompt, "il rimando %r non e' nominato" % rimando
    assert "NON deve raccontare tutta la causa" in prompt
    assert "non dice chi la solleva" in prompt


def test_nessun_esempio_del_prompt_viene_dai_campioni_verificati():
    """Mettere in esempio una frase del banco di prova la fa indovinare per
    costruzione, e il punteggio che ne esce non misura piu' il controllo:
    misura quanto bene si copia.

    E' successo davvero mentre questo modulo veniva scritto - due dei sette
    esempi erano frasi dei campioni 2 e 3 - e non era evidente finche' non
    lo si e' cercato apposta."""
    import json
    import re
    from pathlib import Path

    cartella = Path(__file__).parent / "verifica_umana"
    if not cartella.is_dir():
        return
    campioni = " ".join(
        " ".join(json.dumps(json.loads(f.read_text(encoding="utf-8")),
                            ensure_ascii=False).split())
        for f in cartella.glob("*.json")).lower()

    esempi = re.findall(r'"([^"]{20,})"', citabilita.costruisci_prompt("x"))
    assert esempi, "il prompt non contiene esempi: il test non misura nulla"

    sporchi = [e for e in esempi if e.lower()[:30] in campioni]
    assert not sporchi, (
        "esempi del prompt presi dai campioni verificati a mano: %s" % sporchi)


def test_le_due_categorie_non_citabili_non_portano_alla_stessa_azione():
    """Misurato sui 41 giudizi umani: `frammento_sospeso` boccia 1 delle 31
    fette buone (3%), `dipende_dal_contesto` ne boccia 6 (19%). Trattarle
    insieme butta via quella netta per colpa dell'altra - il 23% di falsi
    allarmi complessivo viene quasi tutto dalla seconda.

    Quindi la prima blocca e la seconda segnala, che e' la politica gia'
    applicata altrove nel progetto: dove il giudizio non e' netto non si
    cancella niente, si dichiara."""
    assert citabilita.AZIONE["frammento_sospeso"] == "blocca"
    assert citabilita.AZIONE["dipende_dal_contesto"] == "segnala"
    assert citabilita.AZIONE[citabilita.CITABILE] == "passa"
    assert set(citabilita.AZIONE) == set(citabilita.CATEGORIE), (
        "una categoria senza azione lascerebbe il chiamante a inventarsela")


def test_ogni_categoria_ha_un_azione(monkeypatch):
    for categoria in citabilita.CATEGORIE:
        monkeypatch.setattr(citabilita.llama_server_client, "completa_json",
                            _server(categoria))
        esito = citabilita.valuta("http://x", "una fetta")
        assert esito["azione"] in ("passa", "blocca", "segnala")
        assert esito["citabile"] == (esito["azione"] == "passa")
