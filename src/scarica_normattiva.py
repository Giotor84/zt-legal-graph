# -*- coding: utf-8 -*-
"""Scarica un atto da Normattiva e lo scrive nel formato di `data/raw/`.

## Questo script VA IN RETE, e per questo sta fuori dalla pipeline

`data/raw/wikisource/LEGGIMI.md` dichiara il principio: «da qui in poi
tutto offline: nessuno script del progetto va in rete». Il principio
resta. Questo modulo e' un attrezzo di **acquisizione**, si lancia a mano
come si e' lanciato a mano il download di Wikisource, e **nessun modulo
della pipeline lo importa** - un test lo verifica.

Prima esisteva solo la procedura a mano, non scritta da nessuna parte:
gli undici `.md` di `data/raw/` sono stati costruiti cosi' e nessuno
sapeva piu' come rifarlo. Ora si sa.

## Perche' serve, e quanto vale

`STATO_PROGETTO §3.2` punto 1 e `§7.58`: il corpus normativo ha buchi
proprio dove i giudici citano di piu'. Misurato il 2026-09-03 sulle 3051
motivazioni del corpus:

    usura           l. 108/1996     14,7% dei provvedimenti   ASSENTE
    mediazione      d.lgs. 28/2010  10,9%                     ASSENTE
    cod. consumo    d.lgs. 206/2005  7,7%                     ASSENTE
    TUF             d.lgs. 58/1998   7,5%                     ASSENTE

Il retrieval, rifatto il 2026-09-03, ora trova la norma giusta il 60,5%
delle volte contro il 14,6% - ma **non puo' trovare cio' che non c'e'**.
Su una query di mediazione restituisce articoli ragionevoli e nessuno
pertinente, perche' la norma pertinente non e' nel grafo. Questi buchi
sono, oggi, l'ostacolo piu' grande.

## Come si prende il testo, e perche' cosi'

Dall'export **Akoma Ntoso** di Normattiva (`caricaAKN`), che e' XML
strutturato: articoli, commi, lettere. Non dalla pagina HTML, dove la
stessa informazione va indovinata dalla grafica.

L'export **richiede una sessione**: chiamato a freddo restituisce una
pagina HTML invece dell'XML, in silenzio e con HTTP 200. Si apre prima la
pagina dell'atto per prendere i cookie. E' la ragione per cui un tentativo
ingenuo sembra funzionare e produce spazzatura: il controllo che l'uscita
cominci per `<?xml` non e' pignoleria.

Il testo che si ottiene e' quello **vigente alla data richiesta**, ed e'
il motivo per cui l'albero viene da Wikisource e il testo da qui: le
pagine di Wikisource sono ferme al 2010.

## Uso

    python src/scarica_normattiva.py --urn "urn:nir:stato:legge:1996-03-07;108" \\
                                     --sigla l_108_1996

Poi vanno registrati il file e la sigla in `parser.parse_all` e in
`Articolo.citazione_breve`, altrimenti il file resta sul disco e non
entra nel grafo: `--controlla-registrazione` lo verifica e lo dice.
"""

from __future__ import annotations

import argparse
import datetime
import http.cookiejar
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

RADICE = Path(__file__).resolve().parents[1]
CARTELLA_RAW = RADICE / "data" / "raw"

BASE = "https://www.normattiva.it"
#: L'avviso che Normattiva chiede di riportare, gia' presente in tutti i
#: file di `data/raw/`. Si copia alla lettera: e' una condizione d'uso.
AVVISO_LEGALE = ('I testi presenti nella banca dati "Normattiva" non hanno '
                 "carattere di ufficialita'. L'unico testo ufficiale e' quello "
                 "pubblicato sulla Gazzetta Ufficiale Italiana.")

_AKN = "{http://docs.oasis-open.org/legaldocml/ns/akn/3.0}"

#: Un'attesa fra una richiesta e l'altra. Normattiva e' un servizio
#: pubblico e questo attrezzo scarica pochi atti a mano: non c'e' nessuna
#: ragione di andare piu' in fretta di cosi'.
PAUSA = 1.0


class ScaricoFallito(RuntimeError):
    """L'atto non e' stato ottenuto in forma utilizzabile."""


@dataclass(frozen=True)
class Riferimenti:
    """Cio' che identifica un atto negli endpoint di Normattiva."""

    data_gu: str
    codice_redazionale: str
    urn: str

    @property
    def url_atto(self) -> str:
        return f"{BASE}/uri-res/N2Ls?{self.urn}"

    def url_akn(self, data_vigenza: str) -> str:
        return (f"{BASE}/do/atto/caricaAKN?dataGU={self.data_gu}"
                f"&codiceRedaz={self.codice_redazionale}&dataVigenza={data_vigenza}")


def _apritore():
    """Un client con i cookie: senza sessione l'export AKN torna HTML."""
    barattolo = http.cookiejar.CookieJar()
    apritore = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(barattolo))
    apritore.addheaders = [
        ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"),
        ("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
    ]
    return apritore


def riferimenti_da_urn(urn: str, apritore=None, timeout: int = 45) -> tuple[Riferimenti, object]:
    """Legge dataGU e codiceRedazionale dalla pagina dell'atto.

    Restituisce anche l'apritore, perche' la sessione appena aperta e'
    quella che l'export pretende: rifarne una nuova rimetterebbe il
    problema che questa funzione ha appena risolto.
    """
    apritore = apritore or _apritore()
    pagina = apritore.open(f"{BASE}/uri-res/N2Ls?{urn}", timeout=timeout).read()
    testo = pagina.decode("utf-8", "replace")
    trovato = re.search(r"caricaAKN\?dataGU=(\d{8})&(?:amp;)?codiceRedaz=([A-Za-z0-9]+)", testo)
    if trovato is None:
        raise ScaricoFallito(
            "nella pagina di %r non c'e' il collegamento all'export AKN: "
            "l'URN e' sbagliato, oppure Normattiva ha cambiato pagina" % urn)
    return Riferimenti(data_gu=trovato.group(1),
                       codice_redazionale=trovato.group(2), urn=urn), apritore


def scarica_akn(riferimenti: Riferimenti, data_vigenza: str,
                apritore=None, timeout: int = 60) -> str:
    """L'XML Akoma Ntoso dell'atto, vigente alla data indicata."""
    apritore = apritore or _apritore()
    grezzo = apritore.open(riferimenti.url_akn(data_vigenza), timeout=timeout).read()
    testo = grezzo.decode("utf-8", "replace")
    if not testo.lstrip().startswith("<?xml"):
        raise ScaricoFallito(
            "l'export non ha restituito XML ma %d byte di altro (quasi certamente "
            "la pagina HTML che Normattiva serve senza sessione). Aprire prima "
            "la pagina dell'atto con lo STESSO apritore." % len(testo))
    return testo


# ------------------------------------------------------------------ conversione


def _testo_disteso(elemento: ET.Element) -> str:
    """Tutto il testo sotto un elemento, con gli spazi normalizzati.

    I riferimenti (`<ref>`) diventano il loro testo: il collegamento non
    serve, il testo citabile si'. Gli offset di ancoraggio si calcolano
    poi sul markdown, quindi qui l'unica cosa che conta e' che il testo
    esca completo e nell'ordine giusto.
    """
    pezzi = ["".join(elemento.itertext())]
    return re.sub(r"[ \t]+", " ", " ".join(pezzi)).strip()


def _numero_articolo(articolo: ET.Element) -> str | None:
    """`Art. 12-bis.` -> `12-bis`; `Art. 67-vicies-semel.` -> `67-vicies-semel`.

    Il suffisso si prende com'e', **senza elencare gli ordinali latini**.
    Il primo tentativo li elencava (bis, ter, ... decies) e su 242
    articoli del codice del consumo ne collassava 128: `67-undecies`,
    `67-duodecies`, `67-terdecies` finivano tutti su `67`, e siccome il
    node_id e' `codice::numero` sarebbero spariti nella
    deduplicazione di `build_graph`, in silenzio.

    I suffissi veri, letti dal sorgente e non immaginati, arrivano a
    `-duodevicies`, `-vicies-semel`, `-viciesbis`, e compaiono sia con il
    trattino sia senza (`-septies-decies` e `-septiesdecies` nello stesso
    atto). Qualunque elenco sarebbe stato incompleto: e' proprio il caso
    in cui un vocabolario chiuso e' la scelta sbagliata, al contrario di
    `fori.grado_ufficio` dove i valori possibili sono due.

    Il numero si legge dall'attributo **`eId`** (`art_35-novies.1`), che e'
    l'identificatore che l'atto si da' da solo, non dal testo di `<num>`
    che e' come l'articolo viene STAMPATO. Sono due cose diverse e il TUF
    lo dimostra: numera `35-novies.1` ... `35-novies.6`, cioe' una parte
    numerica dopo il suffisso latino, e leggendo il testo stampato quei
    sei articoli collassavano tutti su `35-novies`. `<num>` resta come
    ripiego per gli atti in cui l'`eId` manca.
    """
    grezzo = articolo.get("eId") or ""
    trovato = re.match(r"art_(.+)$", grezzo, re.IGNORECASE)
    if trovato is None:
        num = articolo.find(f"{_AKN}num")
        if num is None:
            return None
        testo = re.sub(r"\s+", " ", "".join(num.itertext())).strip()
        trovato = re.match(r"Art(?:icolo)?\.?\s*(\d+(?:[-\s][A-Za-z]+)*(?:\.\d+)?)",
                           testo, re.IGNORECASE)
        if trovato is None:
            return None
    return re.sub(r"\s+", "-", trovato.group(1).strip()).lower()


def _rubrica(articolo: ET.Element) -> str:
    intestazione = articolo.find(f"{_AKN}heading")
    if intestazione is None:
        return ""
    return _testo_disteso(intestazione)


def _corpo(articolo: ET.Element) -> list[str]:
    """I commi dell'articolo, gia' come righe di markdown."""
    righe: list[str] = []
    commi = articolo.findall(f"{_AKN}paragraph")
    if not commi:
        testo = _testo_disteso(articolo)
        # tolto il "Art. N." iniziale, che diventa il titolo
        testo = re.sub(r"^Art\.\s*\S+\.?\s*", "", testo).strip()
        return [testo] if testo else []
    for comma in commi:
        numero = comma.find(f"{_AKN}num")
        etichetta = _testo_disteso(numero) if numero is not None else ""
        contenuto = comma.find(f"{_AKN}content")
        testo = _testo_disteso(contenuto) if contenuto is not None else _testo_disteso(comma)
        if etichetta and testo.startswith(etichetta):
            testo = testo[len(etichetta):].strip()
        righe.append(f"{etichetta} {testo}".strip() if etichetta else testo)
    return [r for r in righe if r]


def converti(xml: str, riferimenti: Riferimenti, data_vigenza: str) -> tuple[str, int]:
    """Dall'Akoma Ntoso al markdown di `data/raw/`, e quanti articoli.

    Il formato di arrivo non e' una scelta: e' quello che `parser.py` sa
    leggere - frontmatter con `url:`, poi `### Art. N. - Rubrica`.
    """
    radice = ET.fromstring(xml)
    titolo_elemento = radice.find(f".//{_AKN}docTitle")
    titolo = (_testo_disteso(titolo_elemento) if titolo_elemento is not None
              else riferimenti.urn)

    righe = [
        "---",
        f"legal_notice: {AVVISO_LEGALE}",
        f"url: {riferimenti.url_atto}",
        f"url_xml: {riferimenti.url_akn(data_vigenza)}",
        f"dataGU: {riferimenti.data_gu}",
        f"codiceRedaz: {riferimenti.codice_redazionale}",
        f"dataVigenza: {data_vigenza}",
        "---",
        "",
        f"# {titolo}",
        "",
    ]

    quanti = 0
    for articolo in radice.iter(f"{_AKN}article"):
        numero = _numero_articolo(articolo)
        if numero is None:
            continue
        rubrica = _rubrica(articolo)
        righe.append(f"### Art. {numero}." + (f" - {rubrica}" if rubrica else ""))
        righe.append("")
        for comma in _corpo(articolo):
            righe.append(comma)
            righe.append("")
        quanti += 1

    if quanti == 0:
        raise ScaricoFallito(
            "l'XML non contiene nessun <article> riconoscibile: l'atto e' "
            "vuoto oppure usa una struttura che questo convertitore non legge")
    return "\n".join(righe).rstrip() + "\n", quanti


# ------------------------------------------------------------------ registrazione


def registrazione_mancante(sigla: str) -> list[str]:
    """Cosa manca perche' il file entri davvero nel grafo.

    Scaricare non basta e non fallisce: il file resta in `data/raw/` e
    `parse_all` semplicemente non lo apre, senza dire niente. E' il modo
    piu' facile di credere di aver colmato un buco.
    """
    sorgente = (RADICE / "src" / "parser.py").read_text(encoding="utf-8")
    mancanti = []
    if f'"{sigla}.md": "{sigla}"' not in sorgente:
        mancanti.append(f"parser.parse_all: manca la riga '\"{sigla}.md\": \"{sigla}\",'")
    if f'"{sigla}":' not in sorgente.split("def citazione_breve")[-1]:
        mancanti.append(f"Articolo.citazione_breve: manca la sigla per '{sigla}'")
    return mancanti


def main(argv: Sequence[str] | None = None) -> int:
    oggi = datetime.date.today().strftime("%Y%m%d")
    parser = argparse.ArgumentParser(
        description="Scarica un atto da Normattiva nel formato di data/raw/.",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    parser.add_argument("--urn", required=True,
                        help='es. "urn:nir:stato:legge:1996-03-07;108"')
    parser.add_argument("--sigla", required=True,
                        help="nome del file e del codice, es. l_108_1996")
    parser.add_argument("--data-vigenza", default=oggi,
                        help="AAAAMMGG; default oggi (%s)" % oggi)
    parser.add_argument("--cartella", type=Path, default=CARTELLA_RAW)
    parser.add_argument("--sovrascrivi", action="store_true")
    argomenti = parser.parse_args(argv)

    destinazione = argomenti.cartella / f"{argomenti.sigla}.md"
    if destinazione.exists() and not argomenti.sovrascrivi:
        print(f"{destinazione} esiste gia': usare --sovrascrivi per rifarlo",
              file=sys.stderr)
        return 2

    print(f"cerco {argomenti.urn} ...", flush=True)
    riferimenti, apritore = riferimenti_da_urn(argomenti.urn)
    print(f"  dataGU={riferimenti.data_gu} codiceRedaz={riferimenti.codice_redazionale}")
    print("scarico l'Akoma Ntoso ...", flush=True)
    xml = scarica_akn(riferimenti, argomenti.data_vigenza, apritore)
    markdown, quanti = converti(xml, riferimenti, argomenti.data_vigenza)

    argomenti.cartella.mkdir(parents=True, exist_ok=True)
    destinazione.write_text(markdown, encoding="utf-8")
    print(f"scritto {destinazione}: {quanti} articoli, {len(markdown)} caratteri")

    mancanti = registrazione_mancante(argomenti.sigla)
    if mancanti:
        print("\nIL FILE NON ENTRA ANCORA NEL GRAFO. Manca:")
        for voce in mancanti:
            print(f"  - {voce}")
        return 1
    print("registrazione in parser.py: presente")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
