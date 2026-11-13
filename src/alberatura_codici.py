"""L'albero dei codici: quale articolo sta sotto quale Libro/Titolo/Capo/Sezione.

## Perche' esiste

Il grafo aveva 5867 articoli PIATTI: `sezione` valeva "CODICE DI PROCEDURA
CIVILE" per tutti e 1032 gli articoli del c.p.c. Il grafo poteva dire cosa
un articolo DICE (la rubrica) ma non dove sta nel codice - e quindi non
poteva distinguere una norma che definisce un atto (art. 650, "Opposizione
tardiva", nel Capo sul procedimento d'ingiunzione) da una che ne regola la
forma (art. 125, "Contenuto e sottoscrizione degli atti di parte", fra le
disposizioni generali sugli atti processuali).

Senza quella distinzione, ricavare il TIPO DI ATTO dal grafo e' impossibile
e resta un lavoro da lista scritta a mano. Con essa, e' il codice a dirlo.

## Da dove viene il dato, e perche' non da Normattiva

**Normattiva non pubblica l'albero.** Verificato alla fonte il 2026-08-30
(STATO_PROGETTO §7.24): l'Akoma Ntoso del c.p.c. e' fatto di 1056 `<doc>`
in fila dentro `<attachment>`, uno per articolo, con zero `<book>`,
`<title>`, `<chapter>`, `<section>`. Non e' un difetto dell'export -
riscaricato e riconvertito con `normattiva2md` v2.1.15, esce identico.

Viene da **it.wikisource.org**, il cui wikitext porta l'albero come livelli
di heading, scaricato una volta sola e conservato in
`data/raw/wikisource/`. Da qui in poi tutto offline: questo modulo non va
mai in rete.

Si prende SOLO l'albero. Il TESTO degli articoli resta quello di Normattiva
(`data/raw/*.md`), che e' vigente: le pagine Wikisource sono ferme al 2010 e
il loro testo non riflette le riforme.

## Due formati nella stessa fonte

I libri I e II scrivono gli articoli come heading di quinto livello
(`=====Art. 1 (rubrica)=====`), i libri III e IV come righe di testo
(`Art. 633 Condizioni di ammissibilita'`). Entrambi vanno riconosciuti:
saltare i secondi lascia fuori l'intero processo di esecuzione e i
procedimenti speciali, cioe' proprio gli articoli 615, 617, 633, 645, 650
da cui dipende il tipo di atto.

## Le due provenienze, mai confuse

- `wikisource`: la collocazione e' letta dalla fonte. 887 articoli su 955.
- `adiacenza_numerica`: DEDOTTA. Un articolo introdotto da una riforma
  (127-ter, 171-bis, 281-decies, 473-bis...) non c'e' in una pagina ferma
  al 2010, ma un articolo *bis*/*ter* e' per costruzione un inserimento
  nello stesso capo dell'articolo che estende, quindi eredita la sua
  collocazione. 57 articoli. E' un'inferenza, non una lettura, e il campo
  `fonte` lo dice: chi costruisce una citazione su una collocazione dedotta
  deve poterlo sapere senza rileggere questo file.

Gli articoli che non si collocano NON ricevono il campo `alberatura`:
l'assenza e' piu' onesta di un valore nullo. Sono 11 sul c.p.c. (art. 78,
732, e la sezione sull'arbitrato 834-838-quinquies).

Uso:
    python src/alberatura_codici.py                      # riepilogo
    python src/alberatura_codici.py --json out.json      # l'albero come dati
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parent.parent
SORGENTI = ROOT / "data" / "raw" / "wikisource"

#: I libri del c.p.c. su Wikisource, in ordine. Il nome del file e' costruito
#: da qui, non elencato a parte: un file mancante deve essere un errore
#: rumoroso, non un libro saltato in silenzio.
LIBRI_CPC = ("primo", "secondo", "terzo", "quarto")

#: Suffissi ordinali di numerazione. Gli stessi di references.py, ma qui
#: servono a RICONOSCERE il numero nel wikitext, non a normalizzarlo dopo:
#: ripetuti apposta invece di importati, perche' le due liste possono
#: divergere legittimamente (Wikisource usa anche "undecies"/"duodecies"/
#: "terdecies", che nei testi degli atti non compaiono mai).
_SUFFISSI = (r"(?:[\-\s]?(?:bis|ter|quater|quinquies|sexies|septies|octies"
             r"|novies|decies|undecies|duodecies|terdecies))")

_INTESTAZIONE = re.compile(r"^(={1,6})\s*(.+?)\s*\1\s*$")
#: Articolo come heading (libri I e II).
_ARTICOLO_INTESTAZIONE = re.compile(r"^Art\.?\s*([0-9]+" + _SUFFISSI + r"?)\b", re.I)
#: Articolo come riga di testo (libri III e IV). Il prefisso opzionale
#: ''...'' assorbe il marcatore corsivo di Wikisource per gli abrogati.
_ARTICOLO_RIGA = re.compile(r"^\s*(?:''.{0,14}?''\s*)?Art\.?\s*([0-9]+" + _SUFFISSI + r"?)\b", re.I)
#: Marcatori wiki da togliere dai titoli dei livelli.
_RUMORE_WIKI = re.compile(r"''|\[abrogato\]|\{\{[^}]*\}\}")

#: I livelli dell'albero, per profondita' di heading. Wikisource usa
#: `=Libro=`, `==Titolo==`, `===Capo===`, `====Sezione====`.
_NOME_LIVELLO = {1: "libro", 2: "titolo", 3: "capo", 4: "sezione"}

FONTE_LETTA = "wikisource"
FONTE_DEDOTTA = "adiacenza_numerica"


def normalizza_numero(grezzo: str) -> str:
    """"281 decies" -> "281-decies", minuscolo. Stessa forma dei nodi del
    grafo, altrimenti la mappatura non aggancia nulla."""
    return re.sub(r"\s+", "-", grezzo.strip()).lower()


def numero_base(numero: str) -> str:
    """"171-ter" -> "171". La radice su cui poggia l'adiacenza numerica."""
    return re.match(r"(\d+)", numero).group(1)


def _titolo_pulito(grezzo: str) -> str:
    return _RUMORE_WIKI.sub("", grezzo).strip()


def leggi_wikitext(testo: str) -> dict[str, dict[str, str]]:
    """Da un libro in wikitext a {numero_articolo: {libro, titolo, capo,
    sezione}}. Il primo collocamento di un articolo vince: se un numero
    ricompare (rimandi, note), non si sovrascrive la sua posizione."""
    albero: dict[str, dict[str, str]] = {}
    corrente: dict[int, str] = {}
    for riga in testo.splitlines():
        intestazione = _INTESTAZIONE.match(riga.strip())
        if intestazione:
            livello = len(intestazione.group(1))
            titolo = _titolo_pulito(intestazione.group(2))
            articolo = _ARTICOLO_INTESTAZIONE.match(titolo)
            if articolo and livello >= 4:
                # E' un articolo scritto come heading (libri I e II), non un
                # livello dell'albero: colloca e NON toccare il contesto.
                albero.setdefault(normalizza_numero(articolo.group(1)), dict(corrente_nominato(corrente)))
                continue
            for profondita in [p for p in corrente if p >= livello]:
                corrente.pop(profondita)
            corrente[livello] = titolo
            continue
        articolo = _ARTICOLO_RIGA.match(riga)
        if articolo:
            albero.setdefault(normalizza_numero(articolo.group(1)), dict(corrente_nominato(corrente)))
    return albero


def corrente_nominato(corrente: dict[int, str]) -> dict[str, str]:
    """Da {profondita': titolo} a {libro/titolo/capo/sezione: titolo}. I
    livelli oltre il quarto (rari, sotto-sezioni) sono scartati: il nome
    non c'e' e inventarlo renderebbe il campo non confrontabile."""
    return {_NOME_LIVELLO[p]: t for p, t in sorted(corrente.items()) if p in _NOME_LIVELLO}


def carica_albero_cpc(sorgenti: Path = SORGENTI) -> dict[str, dict[str, str]]:
    albero: dict[str, dict[str, str]] = {}
    for libro in LIBRI_CPC:
        percorso = sorgenti / f"codice_procedura_civile_libro_{libro}.wikitext"
        if not percorso.is_file():
            raise FileNotFoundError(
                f"manca {percorso}. Le sorgenti Wikisource si scaricano una volta sola "
                f"(vedi {sorgenti / 'LEGGIMI.md'}); questo modulo non va in rete."
            )
        for numero, posizione in leggi_wikitext(percorso.read_text(encoding="utf-8")).items():
            albero.setdefault(numero, posizione)
    return albero


#: Codice civile. Le sorgenti sono 53 SOTTOPAGINE, una per titolo
#: (`Codice_civile/Libro IV/Titolo III`), non quattro pagine per libro come
#: il c.p.c.: la pagina indice `Codice_civile` porta solo gli intervalli di
#: articoli per titolo, e al livello di TITOLO la fideiussione finirebbe in
#: "Dei singoli contratti" insieme ad altri 516 articoli - inutile per
#: qualificare alcunche'. Il CAPO sta solo nelle sottopagine, e li' art. 1936
#: risulta "Capo XXII: Della fideiussione".
#:
#: Perche' un lettore diverso da quello del c.p.c.: nelle sottopagine il
#: LIVELLO dell'heading non e' il livello dell'albero. Libro e titolo non
#: compaiono affatto (sono l'identita' della pagina), il capo e' `==`, la
#: sezione `===`, e gli articoli stanno a `====` in certe pagine e a
#: `=====` in altre - il c.c. non e' uniforme. Classificare per LIVELLO qui
#: sbaglia; si classifica per PREFISSO del testo, che la fonte scrive
#: sempre per esteso ("Capo I: ...", "Sezione II: ...", "Art. 1470 ...").
_PREFISSO_CAPO = re.compile(r"^Capo\b", re.I)
_PREFISSO_SEZIONE = re.compile(r"^Sezione\b", re.I)

#: `Codice_civile/Libro IV/Titolo III` -> codice_civile_Libro_IV_Titolo_III
_NOME_SOTTOPAGINA = re.compile(
    r"^codice_civile_(Libro_[IVX]+)_(Titolo_[IVX]+(?:-bis)?)\.wikitext$", re.I)


def leggi_sottopagina_cc(testo: str, libro: str, titolo: str) -> dict[str, dict[str, str]]:
    """Da una sottopagina del c.c. a {numero: {libro, titolo, capo, sezione}}.

    `libro` e `titolo` arrivano dal nome del file: nella pagina non ci sono,
    perche' sono la pagina. Capo e sezione si riconoscono dal prefisso, non
    dal livello (vedi la nota sopra). I `§` (partizioni interne di un capo)
    non hanno posto nello schema a quattro livelli e si scartano invece di
    essere spacciati per sezioni."""
    albero: dict[str, dict[str, str]] = {}
    capo = sezione = None
    for riga in testo.splitlines():
        intestazione = _INTESTAZIONE.match(riga.strip())
        # SOLO gli heading, a differenza del c.p.c.: nel c.c. gli articoli
        # sono scritti come heading in tutte le sottopagine (2978 su 2990
        # misurati), e le poche righe di corpo che cominciano per "Art. N"
        # sono RIMANDI ad altri articoli - spesso di un altro titolo. Con
        # `setdefault`, un rimando letto da una pagina che viene prima in
        # ordine alfabetico ruberebbe la collocazione all'articolo vero:
        # e' cosi' che art. 1936 risultava senza `capo`.
        if not intestazione:
            continue
        etichetta = _titolo_pulito(intestazione.group(2))
        articolo = _ARTICOLO_INTESTAZIONE.match(etichetta)
        if articolo:
            albero.setdefault(normalizza_numero(articolo.group(1)),
                              _posizione_cc(libro, titolo, capo, sezione))
        elif _PREFISSO_CAPO.match(etichetta):
            capo, sezione = etichetta, None
        elif _PREFISSO_SEZIONE.match(etichetta):
            sezione = etichetta
    return albero


def _posizione_cc(libro: str, titolo: str, capo: str | None, sezione: str | None) -> dict[str, str]:
    posizione = {"libro": libro, "titolo": titolo}
    if capo:
        posizione["capo"] = capo
    if sezione:
        posizione["sezione"] = sezione
    return posizione


def carica_albero_cc(sorgenti: Path = SORGENTI) -> dict[str, dict[str, str]]:
    """L'albero del codice civile dalle sottopagine per titolo.

    Il titolo leggibile ("Titolo III: Dei singoli contratti") non sta nella
    sottopagina: sta nella pagina indice, che qui non si rilegge. Si tiene
    l'identificatore della pagina ("Libro IV", "Titolo III"), che e' stabile
    e verificabile contro la fonte; l'indice leggibile prodotto da --indice
    serve proprio a controllarlo a mano."""
    albero: dict[str, dict[str, str]] = {}
    sottopagine = sorted(sorgenti.glob("codice_civile_Libro_*.wikitext"))
    if not sottopagine:
        raise FileNotFoundError(
            f"nessuna sottopagina del c.c. in {sorgenti}. Si scaricano una volta sola "
            f"(vedi {sorgenti / 'LEGGIMI.md'}); questo modulo non va in rete."
        )
    for percorso in sottopagine:
        nome = _NOME_SOTTOPAGINA.match(percorso.name)
        if not nome:
            continue
        libro = nome.group(1).replace("_", " ")
        titolo = nome.group(2).replace("_", " ")
        for numero, posizione in leggi_sottopagina_cc(
                percorso.read_text(encoding="utf-8"), libro, titolo).items():
            albero.setdefault(numero, posizione)
    return albero


def colloca(numeri: set[str], albero: dict[str, dict[str, str]]) -> tuple[dict[str, dict], list[str]]:
    """Colloca gli articoli richiesti. Ritorna ({numero: alberatura},
    non_collocati). Ogni alberatura porta `fonte`: letta o dedotta."""
    collocati: dict[str, dict] = {}
    non_collocati: list[str] = []
    for numero in numeri:
        chiave = numero.lower()
        if chiave in albero:
            collocati[numero] = {**albero[chiave], "fonte": FONTE_LETTA}
            continue
        base = numero_base(chiave)
        if base != chiave and base in albero:
            collocati[numero] = {**albero[base], "fonte": FONTE_DEDOTTA,
                                 "dedotta_da": f"art. {base}"}
            continue
        non_collocati.append(numero)
    return collocati, non_collocati


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sorgenti", type=Path, default=SORGENTI)
    parser.add_argument("--json", type=Path, default=None, help="Scrive l'albero come JSON")
    parser.add_argument("--indice", type=Path, default=None,
                        help="Scrive l'indice leggibile (libri/titoli/capi) per la verifica a mano")
    parser.add_argument("--codice", choices=("cpc", "cc"), default="cpc",
                        help="quale codice leggere: cpc (quattro pagine per libro) o cc (53 sottopagine per titolo)")
    args = parser.parse_args()

    carica = carica_albero_cc if args.codice == "cc" else carica_albero_cpc
    albero = carica(args.sorgenti)
    print(f"articoli collocati dalle sorgenti: {len(albero)}")
    for livello in ("libro", "titolo", "capo", "sezione"):
        distinti = {p[livello] for p in albero.values() if livello in p}
        print(f"  {livello:8s} distinti: {len(distinti)}")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(albero, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nalbero scritto in {args.json}")

    if args.indice:
        # L'indice serve a una persona che deve controllare la fonte: e'
        # l'unico modo di validare Wikisource senza rileggere 955 articoli.
        righe, visto = [], set()
        for numero, posizione in sorted(albero.items(), key=lambda kv: (int(numero_base(kv[0])), kv[0])):
            chiave = tuple(posizione.get(l, "") for l in ("libro", "titolo", "capo", "sezione"))
            if chiave in visto:
                continue
            visto.add(chiave)
            righe.append(f"{'':2s}a partire da art. {numero:12s} "
                         + " > ".join(x for x in chiave if x))
        args.indice.parent.mkdir(parents=True, exist_ok=True)
        args.indice.write_text("\n".join(righe) + "\n", encoding="utf-8")
        print(f"indice leggibile scritto in {args.indice} ({len(righe)} righe)")


if __name__ == "__main__":
    main()
