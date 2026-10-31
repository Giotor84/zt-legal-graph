# -*- coding: utf-8 -*-
"""Cosa deve reggere in `scarica_normattiva` e nel numero di articolo.

Il test che conta e'
`test_i_numeri_veri_dei_codici_nuovi_non_collidono`: la forma sbagliata
del numero non fa fallire niente - fa **sparire** articoli nella
deduplicazione per node_id, e il grafo esce piu' piccolo con l'aria di
essere completo. Sul solo codice del consumo ne sparivano 128.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import scarica_normattiva as sn
from parser import ARTICLE_HEADING_RE, parse_all

RADICE = Path(__file__).resolve().parents[1]
CARTELLA_RAW = RADICE / "data" / "raw"

_AKN = "{http://docs.oasis-open.org/legaldocml/ns/akn/3.0}"


def _articolo(eid: str, num: str, heading: str = "", corpo: str = "1. testo") -> ET.Element:
    art = ET.Element(f"{_AKN}article", {"eId": eid})
    ET.SubElement(art, f"{_AKN}num").text = num
    if heading:
        ET.SubElement(art, f"{_AKN}heading").text = heading
    par = ET.SubElement(art, f"{_AKN}paragraph")
    ET.SubElement(par, f"{_AKN}num").text = "1."
    ET.SubElement(ET.SubElement(par, f"{_AKN}content"), f"{_AKN}p").text = corpo
    return art


# --- il numero dell'articolo, che e' dove si perdono gli articoli ---

@pytest.mark.parametrize("eid, atteso", [
    ("art_5", "5"),
    ("art_67-bis", "67-bis"),
    ("art_67-vicies-semel", "67-vicies-semel"),   # codice del consumo
    ("art_35-novies.1", "35-novies.1"),           # TUF
    ("art_60-bis.4-bis", "60-bis.4-bis"),         # TUF
    ("art_190.1-bis", "190.1-bis"),               # TUF
    ("art_2409-terdecies", "2409-terdecies"),
])
def test_il_numero_viene_dall_eid(eid: str, atteso: str):
    """`eId` e' l'identificatore che l'atto si da'; `<num>` e' come viene
    stampato. Il TUF numera `35-novies.1` ... `.6` e leggendo lo stampato
    quei sei articoli collassavano in uno."""
    assert sn._numero_articolo(_articolo(eid, "Art. qualunque.")) == atteso


def test_senza_eid_si_ripiega_sul_numero_stampato():
    art = ET.Element(f"{_AKN}article")
    ET.SubElement(art, f"{_AKN}num").text = "Art. 12-bis."
    assert sn._numero_articolo(art) == "12-bis"


def test_un_articolo_senza_numero_non_inventa_niente():
    art = ET.Element(f"{_AKN}article")
    assert sn._numero_articolo(art) is None


# --- il modello del titolo in parser.py ---

@pytest.mark.parametrize("riga, numero", [
    ("### Art. 5. - Rubrica", "5"),
    ("### Art. 2946. - Prescrizione", "2946"),
    ("### Art. 129-bis.", "129-bis"),
    ("### Art. 2409-terdecies. - Competenza", "2409-terdecies"),
    ("### Art. 69-vicies-semel. - Rimozione", "69-vicies-semel"),
    ("### Art. 60-bis.4-bis.", "60-bis.4-bis"),
    ("### Art. 190.1-bis.", "190.1-bis"),
    ("### Art. 35-novies.6. - (( (Disposizioni applicabili). ))", "35-novies.6"),
])
def test_il_numero_di_un_titolo_e_tutto_il_numero(riga: str, numero: str):
    trovato = ARTICLE_HEADING_RE.match(riga)
    assert trovato is not None, riga
    assert trovato.group(1) == numero


def test_il_titolo_non_finisce_dentro_il_numero():
    """Il rischio del modello piu' largo: mangiarsi la rubrica. Il numero
    si ferma dove comincia uno spazio."""
    trovato = ARTICLE_HEADING_RE.match("### Art. 5. - Condizione di procedibilita'")
    assert trovato.group(1) == "5"
    assert trovato.group(2) == "- Condizione di procedibilita'"


# --- la conversione ---

def _atto(articoli: list[ET.Element]) -> str:
    radice = ET.Element(f"{_AKN}akomaNtoso")
    atto = ET.SubElement(radice, f"{_AKN}act")
    titolo = ET.SubElement(atto, f"{_AKN}docTitle")
    titolo.text = "Disposizioni di prova"
    corpo = ET.SubElement(atto, f"{_AKN}body")
    for a in articoli:
        corpo.append(a)
    return ET.tostring(radice, encoding="unicode")


_RIF = sn.Riferimenti(data_gu="19960309", codice_redazionale="096G0121",
                      urn="urn:nir:stato:legge:1996-03-07;108")


def test_il_markdown_prodotto_e_leggibile_dal_parser(tmp_path: Path):
    """Le due meta' devono combaciare: se il convertitore scrive una forma
    che `parser.py` non legge, il file finisce in data/raw e non entra nel
    grafo, senza che niente lo dica."""
    xml = _atto([_articolo("art_5", "Art. 5.", "Condizione di procedibilita'"),
                 _articolo("art_60-bis.4-bis", "Art. 60-bis.4-bis.")])
    markdown, quanti = sn.converti(xml, _RIF, "20260903")
    assert quanti == 2
    (tmp_path / "prova.md").write_text(markdown, encoding="utf-8")

    import parser as parser_modulo
    articoli = parser_modulo.parse_file(tmp_path / "prova.md", "prova")
    assert [a.numero for a in articoli] == ["5", "60-bis.4-bis"]
    assert articoli[0].rubrica == "Condizione di procedibilita'"


def test_il_frontmatter_porta_url_e_avviso(tmp_path: Path):
    """`parser.FRONTMATTER_URL_RE` pretende `url:`, e Normattiva pretende
    che si riporti l'avviso di non ufficialita'."""
    markdown, _ = sn.converti(_atto([_articolo("art_1", "Art. 1.")]), _RIF, "20260903")
    assert markdown.startswith("---")
    assert "\nurl: https://www.normattiva.it/uri-res/" in markdown
    assert "non hanno carattere di ufficialita'" in markdown


def test_un_atto_senza_articoli_e_un_errore_non_un_file_vuoto():
    """Un file vuoto scritto in data/raw sarebbe un buco colmato solo in
    apparenza."""
    with pytest.raises(sn.ScaricoFallito, match="nessun <article>"):
        sn.converti(_atto([]), _RIF, "20260903")


def test_una_risposta_html_non_viene_scambiata_per_xml():
    """Normattiva serve la pagina HTML con HTTP 200 quando manca la
    sessione: senza questo controllo il convertitore riceverebbe HTML e
    scriverebbe spazzatura."""
    class Apritore:
        def open(self, url, timeout=0):
            class R:
                @staticmethod
                def read():
                    return b"<!DOCTYPE html><html>...</html>"
            return R()

    with pytest.raises(sn.ScaricoFallito, match="non ha restituito XML"):
        sn.scarica_akn(_RIF, "20260903", Apritore())


# --- la registrazione, che e' il modo piu' facile di credere di aver finito ---

def test_un_file_non_registrato_viene_dichiarato():
    mancanti = sn.registrazione_mancante("una_legge_mai_vista_1999")
    assert len(mancanti) == 2
    assert any("parse_all" in m for m in mancanti)
    assert any("citazione_breve" in m for m in mancanti)


@pytest.mark.parametrize("sigla", ["l_108_1996", "dlgs_28_2010",
                                   "dlgs_206_2005", "dlgs_58_1998"])
def test_i_quattro_codici_nuovi_sono_registrati(sigla: str):
    assert sn.registrazione_mancante(sigla) == []


# --- l'invariante dichiarata nel docstring: la pipeline non va in rete ---

def test_nessun_modulo_della_pipeline_importa_lo_scaricatore():
    """Il docstring promette che questo attrezzo sta fuori dalla pipeline.
    Una promessa in un commento non e' un'invariante finche' non fallisce
    qualcosa."""
    colpevoli = []
    for cartella in ("src", "pipeline_confutazione"):
        for percorso in (RADICE / cartella).glob("*.py"):
            if percorso.name.startswith("test_") or percorso.name == "scarica_normattiva.py":
                continue
            if "scarica_normattiva" in percorso.read_text(encoding="utf-8"):
                colpevoli.append(percorso.name)
    assert colpevoli == [], "moduli che importano lo scaricatore: %s" % colpevoli


# --- sul reale: i file scaricati ---

@pytest.mark.skipif(not (CARTELLA_RAW / "dlgs_58_1998.md").exists(),
                    reason="i codici nuovi non sono su questa macchina")
def test_i_numeri_veri_dei_codici_nuovi_non_collidono():
    """Il test che conta. Una collisione di node_id non fa fallire nulla:
    `build_graph` deduplica e l'articolo sparisce. Con il modello vecchio
    del numero ne sparivano 128 sul solo codice del consumo."""
    import collections
    nuovi = {"l_108_1996", "dlgs_28_2010", "dlgs_206_2005", "dlgs_58_1998"}
    articoli = [a for a in parse_all(CARTELLA_RAW) if a.codice in nuovi]
    conta = collections.Counter(a.node_id for a in articoli)
    collisioni = {k: v for k, v in conta.items() if v > 1}
    assert collisioni == {}, collisioni
    assert len(articoli) == 877, len(articoli)


@pytest.mark.skipif(not (CARTELLA_RAW / "dlgs_28_2010.md").exists(),
                    reason="i codici nuovi non sono su questa macchina")
def test_le_norme_che_mancavano_ci_sono_e_sono_quelle_giuste():
    """Gli articoli su cui poggiano le eccezioni misurate come piu'
    frequenti: la condizione di procedibilita' della mediazione e il
    tasso soglia dell'usura."""
    per_id = {a.node_id: a for a in parse_all(CARTELLA_RAW)}
    mediazione = per_id["dlgs_28_2010::5"]
    assert "condizione di procedibilita'" in (mediazione.rubrica or "").lower()
    assert "mediazione" in mediazione.testo.lower()
    assert per_id["l_108_1996::2"].testo.lower().count("tasso") >= 1
    assert per_id["dlgs_206_2005::33"] is not None      # clausole vessatorie
    assert per_id["dlgs_58_1998::23"] is not None       # forma dei contratti


@pytest.mark.skipif(not (CARTELLA_RAW / "tub.md").exists(),
                    reason="i sorgenti non sono su questa macchina")
def test_l_articolo_del_tub_che_si_perdeva_ora_si_legge():
    """`69-vicies-semel` era letto come `69-vicies` e sovrascriveva
    l'omonimo: un articolo vero, sparito da sempre e da nessuno notato.
    Il grafo in carica non ce l'ha ancora - entrera' alla prossima
    ingestione."""
    per_id = {a.node_id: a for a in parse_all(CARTELLA_RAW)}
    assert "tub::69-vicies-semel" in per_id
    assert "tub::69-vicies" in per_id
    assert per_id["tub::69-vicies-semel"].rubrica is not None
