# -*- coding: utf-8 -*-
"""Il confronto fra i due metodi.

Cio' che i test difendono e' che il confronto resti NON circolare: nessuno
dei due metodi deve poter fare da riferimento all'altro, perche' chi fa da
riferimento vince per costruzione.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import confronta_metodi as cm  # noqa: E402


def _fase1(cartella: Path, stem: str, testi: list[str]) -> None:
    (cartella / (stem + "_01_estrazione.json")).write_text(json.dumps(
        {"eccezioni": [{"testo_letterale": t} for t in testi]},
        ensure_ascii=False), encoding="utf-8")


def _spazzata(cartella: Path, stem: str, testi: list[str]) -> None:
    righe = ["# x", "", "## Annotazione", ""]
    righe += ['%d. [prescrizione] "%s"' % (i, t) for i, t in enumerate(testi, 1)]
    (cartella / (stem + "_annotazione.md")).write_text(
        "\n".join(righe), encoding="utf-8")


def test_legge_le_voci_dei_due_formati(tmp_path):
    _fase1(tmp_path, "atto", ["la prima eccezione sollevata dall'opponente"])
    _spazzata(tmp_path, "atto", ["la prima eccezione sollevata dall'opponente",
                                 "la seconda eccezione, diversa dalla prima"])

    assert len(cm.voci_di_fase1(tmp_path)["atto"]) == 1
    assert len(cm.voci_della_spazzata(tmp_path)["atto"]) == 2


def test_l_appaiamento_e_quello_gia_usato_altrove():
    """Un criterio nuovo renderebbe questi numeri non paragonabili a quelli
    gia' misurati con lo stesso valutatore, e il confronto fra due metodi
    diventerebbe un confronto fra due metriche."""
    testo = "la fideiussione e' nulla per difetto di forma scritta"
    insieme, soli_a, soli_b = cm.appaia([testo], [testo])

    assert (insieme, soli_a, soli_b) == (1, [], [])


def test_cio_che_trova_uno_solo_finisce_da_una_parte_sola():
    a = ["la nullita' della clausola di capitalizzazione trimestrale"]
    b = ["il difetto di legittimazione attiva del cessionario"]

    insieme, soli_a, soli_b = cm.appaia(a, b)

    assert insieme == 0
    assert soli_a and soli_b, "ogni voce non appaiata deve restare visibile"


def test_la_citabilita_giudica_i_due_lati_con_lo_stesso_controllo(monkeypatch):
    """E' l'unico asse del confronto che non favorisce nessuno dei due: il
    controllo non sa da quale metodo venga la fetta. Se un giorno prendesse
    un argomento che dica la provenienza, il confronto smetterebbe di essere
    neutrale senza che nessun numero lo mostri."""
    visti = []

    def finto(base_url, fetta, **kwargs):
        visti.append(fetta)
        return {"categoria": "sta_in_piedi_da_sola", "motivo": "",
                "citabile": True, "azione": "passa"}

    monkeypatch.setattr(cm.citabilita, "valuta", finto)

    cm.profilo_citabilita("http://x", ["una fetta lunga a sufficienza"],
                          seed=1, temperature=0.0)

    assert visti == ["una fetta lunga a sufficienza"], (
        "alla citabilita' si passa la fetta e nient'altro")


def test_una_fetta_troppo_corta_si_dichiara_invece_di_sparire(monkeypatch):
    """Non chiamare il modello su una fetta di tre caratteri e' giusto, ma
    toglierla dal conto falserebbe le percentuali di entrambi i lati in
    silenzio."""
    monkeypatch.setattr(cm.citabilita, "valuta",
                        lambda *a, **k: {"categoria": "sta_in_piedi_da_sola"})

    categorie = cm.profilo_citabilita("http://x", ["ab", ""], seed=1,
                                      temperature=0.0)

    assert categorie == ["troppo_corta_per_giudicare"] * 2


def test_c_e_una_categoria_per_fetta_e_nello_stesso_ordine(monkeypatch):
    """Le categorie tornano appaiate alle fette, non aggregate: e' cio' che
    permette di rifare il confronto su un sottoinsieme degli atti senza
    rispendere una chiamata al modello per ogni fetta. Con un buco in mezzo
    l'accoppiamento slitterebbe e ogni giudizio finirebbe sulla fetta
    sbagliata, senza che nessun totale se ne accorga."""
    monkeypatch.setattr(cm.citabilita, "valuta", lambda base, f, **k: {
        "categoria": "frammento_sospeso" if "sospesa" in f
        else "sta_in_piedi_da_sola"})

    categorie = cm.profilo_citabilita(
        "http://x", ["una fetta intera che afferma", "ab",
                     "una fetta sospesa a meta'"], seed=1, temperature=0.0)

    assert categorie == ["sta_in_piedi_da_sola", "troppo_corta_per_giudicare",
                         "frammento_sospeso"]


def test_di_fase1_si_legge_il_campo_citabile_non_quello_dichiarato(tmp_path):
    """Il contratto dichiara `testo_letterale` NON citabile dalla 1.25: e'
    cio' che il modello DICE di aver citato, e l'ancoraggio per similarita'
    lo accetta fino a 0.95, quindi porta i caratteri di scaffolding del
    modello. Misurato su un atto reale: `testo_verbatim` combacia con la
    fetta agli offset 28 volte su 28, `testo_letterale` sbaglia su 11.

    Leggere quello sbagliato qui non rompe niente in modo visibile - rende
    il confronto ASIMMETRICO, testo dichiarato da un lato e testo ancorato
    dall'altro - e la citabilita' e' esattamente la grandezza che ne
    risente. E' successo davvero, e i numeri di §7.38 sono stati rifatti."""
    import json as _json
    (tmp_path / "atto_01_estrazione.json").write_text(_json.dumps(
        {"eccezioni": [{"testo_verbatim": "la fetta agli offset",
                        "testo_letterale": "'la fetta agli offset'"}]}),
        encoding="utf-8")

    assert cm.voci_di_fase1(tmp_path)["atto"] == ["la fetta agli offset"]
