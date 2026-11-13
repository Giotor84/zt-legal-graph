# -*- coding: utf-8 -*-
"""Il confronto fra le due annotazioni.

Cio' che difende e' il sistema di coordinate: le due misurano su testi
diversi (motivazione contro testo integrale), e confrontarle senza
convertire darebbe zero sovrapposizioni ovunque - non una misura bassa, una
misura sbagliata. E' lo stesso errore gia' pagato una volta, documentato in
`valuta_golden_eccezioni.carica_offset_base`.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import confronta_golden as cg  # noqa: E402

MOTIVAZIONE = ("L'opponente ha eccepito la prescrizione. Il motivo e' infondato. "
               "Ha inoltre dedotto l'anatocismo, che va accolto.")
INTEGRALE = "INTESTAZIONE E CONCLUSIONI DELLE PARTI. " + MOTIVAZIONE

DOCUMENTO_INTERA = {
    "documenti": [{
        "indice": 1, "node_id": "prov::1", "ufficio": "TRIBUNALE DI X", "area": "a",
        "eccezioni": [{"parte": "opponente", "esito": "rigettata",
                       "verbatim": "ha eccepito la prescrizione", "sintesi": "prescrizione"}],
    }]
}


def test_le_coordinate_si_convertono_prima_di_confrontare():
    base = INTEGRALE.index(MOTIVAZIONE)
    voci = cg.voci_della_lettura_intera(
        DOCUMENTO_INTERA, {"prov::1": MOTIVAZIONE}, {"prov::1": base})

    voce = voci["prov::1"][0]
    assert INTEGRALE[voce["inizio"]:voce["fine"]] == "ha eccepito la prescrizione", (
        "senza conversione la fetta cadrebbe nell'intestazione")


def test_cio_che_trova_solo_la_spazzata_e_il_punto_cieco():
    """E' il numero per cui esiste tutto il modulo: eccezioni su cui il
    golden set precedente non faceva misurare niente."""
    base = INTEGRALE.index(MOTIVAZIONE)
    intera = cg.voci_della_lettura_intera(
        DOCUMENTO_INTERA, {"prov::1": MOTIVAZIONE}, {"prov::1": base})
    anatocismo = INTEGRALE.index("dedotto l'anatocismo")
    prescrizione = INTEGRALE.index("ha eccepito la prescrizione")
    spazzata = {"prov::1": [
        {"offset_inizio": prescrizione, "offset_fine": prescrizione + 27,
         "verbatim": "ha eccepito la prescrizione", "esito": "rigettata"},
        {"offset_inizio": anatocismo, "offset_fine": anatocismo + 20,
         "verbatim": "dedotto l'anatocismo", "esito": "accolta"},
    ]}

    esito = cg.confronta(intera, spazzata)

    assert esito["totali"]["comuni"] == 1
    assert esito["totali"]["solo_spazzata"] == 1
    assert esito["totali"]["solo_intera"] == 0
    assert "anatocismo" in esito["trovate_solo_dalla_spazzata"][0]["verbatim"]


def test_i_provvedimenti_non_comuni_si_dichiarano_non_si_ignorano():
    """Confrontare insiemi diversi di documenti e riportare un totale unico
    darebbe una percentuale calcolata su basi diverse."""
    esito = cg.confronta({"prov::1": []}, {"prov::2": []})

    assert esito["provvedimenti_confrontati"] == 0
    assert esito["solo_nella_lettura_intera"] == ["prov::1"]
    assert esito["solo_nella_spazzata"] == ["prov::2"]
