"""
Parsing dei Markdown prodotti da normattiva2md in articoli strutturati.

Insidia scoperta ispezionando i file reali (non assumibile a priori): all'interno
dello stesso file possono convivere PIU' sequenze di numerazione che si sovrappongono:
- codice_civile.md: i 2 articoli del regio decreto di promulgazione (Art. 1, 2),
  le "Disposizioni sulla legge in generale" (Art. 1-31, le c.d. preleggi), e il
  Codice civile vero e proprio (Art. 1-2969ish) hanno TUTTI un "Art. 1" proprio.
- codice_procedura_civile.md: stessa cosa per i 3 articoli del decreto.
- codice_crisi_impresa.md: nessuna duplicazione, numerazione piatta e unica.

Senza tracciare la sezione "## " in cui ciascun articolo compare, una citazione
"art. 1 c.c." sarebbe ambigua tra 3 articoli diversi. Si traccia quindi la sezione
corrente e si marca come `is_main_body` solo la sezione il cui titolo contiene il
nome del codice (es. "CODICE CIVILE") - quella è il corpo principale, il significato
di default per una citazione "nuda" come "art. 2946 c.c.".
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

# Il numero di un articolo e' la cifra iniziale piu' QUALUNQUE sequenza di
# parti separate da trattino o punto: `67-vicies-semel`, `60-bis.4-bis`,
# `190.1-bis` sono un numero solo, non un numero piu' un pezzo di titolo.
#
# Fino al 2026-09-03 il modello ammetteva un trattino e un solo `.numero`
# finale (`([0-9]+(?:-[a-zA-Z]+)?(?:\.[0-9]+)?)`), che bastava per gli
# undici codici allora presenti. Aggiungendone quattro (usura, mediazione,
# codice del consumo, TUF) si e' visto che non basta: gli articoli in
# eccedenza collassavano su un numero gia' esistente e SPARIVANO nella
# deduplicazione per node_id di build_graph, senza che niente fallisse.
# Erano 128 sul solo codice del consumo.
#
# Il difetto non era solo nei codici nuovi: `tub::69-vicies-semel` e' un
# articolo vero del TUB che questa riga stava perdendo da sempre, letto come
# `69-vicies` e sovrascritto dall'omonimo. Il grafo in carica non ce l'ha.
#
# Misurato in ENTRAMBE le direzioni sui codici preesistenti: il parse dei
# soli codici vecchi da' 5868 node_id contro i 5867 del grafo, e la
# differenza e' esattamente quell'articolo recuperato - zero spariti.
ARTICLE_HEADING_RE = re.compile(r"^#+\s+Art\.\s+([0-9]+(?:[-.][a-zA-Z0-9]+)*)\.?\s*(.*)$")
SECTION_HEADING_RE = re.compile(r"^(#+)\s+(.*)$")
FRONTMATTER_URL_RE = re.compile(r"^url:\s*(.+)$", re.MULTILINE)

# Marcatore di sezione "corpo principale" per ciascun codice - il titolo "## "
# che contiene questa sottostringa è il corpo che si intende di default per una
# citazione nuda ("art. N c.c." senza ulteriori specificazioni).
MAIN_BODY_MARKERS = {
    "codice_civile": "CODICE CIVILE",
    "codice_procedura_civile": "CODICE DI PROCEDURA CIVILE",
    "codice_crisi_impresa": None,  # nessuna ambiguità in questo file, vedi sopra
    # Il TUB (decreto legislativo, non regio decreto) non ha il doppio-livello di
    # numerazione degli altri due codici storici: "Art. 1" del preambolo del
    # decreto È GIÀ il vero art. 1 del Testo Unico, verificato nessun duplicato.
    "tub": None,
    # L. 241/1990 e D.P.R. 602/1973: leggi/decreti senza decreto di promulgazione
    # con propria numerazione separata (verificato sul file reale: si passa
    # direttamente dal titolo alla prima sezione "## ", un'unica sequenza).
    "l_241_1990": None,
    "dpr_602_1973": None,
    # R.D. 267/1942 (Legge Fallimentare): stessa insidia del codice civile - il
    # decreto di promulgazione ha un proprio "Art. 1"/"Art. 2" (a livello "##",
    # non "###", ma ARTICLE_HEADING_RE non guarda il numero di # quindi va
    # comunque disambiguato) prima che inizi, sotto "## Allegati", il vero
    # corpo dell'"## DISCIPLINA DEL FALLIMENTO, DEL CONCORDATO PREVENTIVO...".
    "rd_267_1942": "DISCIPLINA DEL FALLIMENTO",
    # L. 689/1981 (depenalizzazione/sanzioni amministrative) e L. 287/1990
    # (antitrust): stessa verifica delle altre leggi (non decreti di
    # promulgazione) - unica sequenza di numerazione, nessuna ambiguita'.
    "l_689_1981": None,
    "l_287_1990": None,
    # Costituzione: numerazione unica art. 1-139 sotto "## PRINCIPI
    # FONDAMENTALI" e i vari Titoli - verificato nessuna ambiguita'. Le
    # disposizioni transitorie e finali (numerate in numeri romani, non
    # "Art. N") restano fuori dal parser, coerente con come ARTICLE_HEADING_RE
    # e' definito - gap minore, accettato.
    "costituzione": None,
    # D.Lgs. 150/2011 (riti speciali civili, es. opposizione a
    # ordinanza-ingiunzione): aggiunto 2026-08-19 per colmare il gap trovato
    # indagando il caso 10 (art. 22 L. 689/1981 e' un rinvio a questo decreto,
    # assente dal corpus fino ad ora - vedi README). Verificato sul file reale:
    # nessuna doppia numerazione (decreto legislativo semplice, come tub.md),
    # unica sequenza "Art. 1"..."Art. 41".
    "dlgs_150_2011": None,
    # Aggiunti il 2026-09-03 per colmare i buchi misurati sulle 3051
    # motivazioni del corpus (vedi STATO_PROGETTO §7.59). Sono tutti leggi o
    # decreti legislativi senza decreto di promulgazione a numerazione
    # propria, quindi un'unica sequenza e nessuna ambiguita'.
    # Verificato e non assunto: il parse dei quattro da' 877 articoli e 877
    # node_id distinti, zero collisioni. Sono elencati qui invece di
    # affidarsi al `.get()` che torna None: "corretto per assenza" e' il
    # difetto che `fori.grado_ufficio` ha gia' fatto pagare una volta.
    "l_108_1996": None,
    "dlgs_28_2010": None,
    "dlgs_206_2005": None,
    "dlgs_58_1998": None,
}


#: Pulizia dei marcatori Normattiva dal testo (trovata in una revisione
#: esterna, agosto 2026, verificata: 2459/5912 articoli - 42% - contenevano
#: marcatori di novellazione "((...))", 1188/5912 - 20% - note
#: "AGGIORNAMENTO (n) La L. ... ha disposto..." dentro il campo testo, fino
#: a 10484 caratteri di rumore in un solo articolo, art. 492 c.p.c.). Le
#: note di aggiornamento servono per la vigenza (tenute in `testo_raw`), non
#: per la ricerca - misurato un miglioramento netto sul retrieval pulendo,
#: mai un peggioramento.
def pulisci_testo(t: str) -> str:
    t = re.split(r"\bAGGIORNAMENTO\b", t, flags=re.IGNORECASE)[0]  # taglia le note in coda
    t = re.sub(r"\(\(\d+\)\)", " ", t)  # riferimenti a note tipo "((86))"
    t = re.sub(r"[()]{2}", " ", t)  # marcatori di novellazione "((" "))"
    return re.sub(r"\s+", " ", t).strip()


@dataclass
class Articolo:
    codice: str  # es. "codice_civile"
    numero: str  # es. "2946" o "129-bis"
    rubrica: str | None
    testo: str  # ripulito (pulisci_testo) - usato per retrieval/verifica
    testo_raw: str  # originale intatto (marcatori di novellazione, note di aggiornamento) - per consultazione/vigenza
    sezione: str  # titolo della sezione "## " in cui compare
    is_main_body: bool
    source_url: str
    abrogato: bool = False

    @property
    def node_id(self) -> str:
        # Il corpo principale non porta il nome sezione nell'id (è il caso comune,
        # meglio "codice_civile::2946" che "codice_civile::CODICE CIVILE::2946").
        if self.is_main_body:
            return f"{self.codice}::{self.numero}"
        return f"{self.codice}::{self.sezione}::{self.numero}"

    @property
    def citazione_breve(self) -> str:
        sigla = {
            "codice_civile": "c.c.",
            "codice_procedura_civile": "c.p.c.",
            "codice_crisi_impresa": "CCII",
            "tub": "TUB",
            "l_241_1990": "L. 241/1990",
            "dpr_602_1973": "D.P.R. 602/1973",
            "rd_267_1942": "L. Fall.",
            "l_689_1981": "L. 689/1981",
            "l_287_1990": "L. 287/1990",
            "costituzione": "Cost.",
            "dlgs_150_2011": "D.Lgs. 150/2011",
            "l_108_1996": "L. 108/1996",
            "dlgs_28_2010": "D.Lgs. 28/2010",
            "dlgs_206_2005": "Cod. Cons.",
            "dlgs_58_1998": "TUF",
        }.get(self.codice, self.codice)
        return f"art. {self.numero} {sigla}"


def _clean_title(raw: str) -> str | None:
    raw = raw.strip()
    raw = re.sub(r"^-\s*", "", raw)  # "Art. 1. - Ambito di applicazione"
    raw = raw.strip()
    m = re.match(r"^\(+(.*?)\)+\.?\s*$", raw)
    if m:
        raw = m.group(1)
    raw = raw.strip(" .")
    return raw or None


def parse_file(path: Path, codice: str) -> list[Articolo]:
    text = path.read_text(encoding="utf-8")

    url_match = FRONTMATTER_URL_RE.search(text)
    source_url = url_match.group(1).strip() if url_match else ""

    main_body_marker = MAIN_BODY_MARKERS.get(codice)
    lines = text.split("\n")

    articoli: list[Articolo] = []
    current_section = ""
    is_main_body = main_body_marker is None  # se non c'è ambiguità, tutto è "corpo"

    current_numero: str | None = None
    current_rubrica: str | None = None
    current_body_lines: list[str] = []
    current_is_main_body = is_main_body

    def flush():
        if current_numero is None:
            return
        testo_raw = "\n".join(current_body_lines).strip()
        # Articolo abrogato: la rubrica normattiva2md lo segnala esplicitamente
        # (es. "((ARTICOLO ABROGATO DALLA L. ...))"), niente corpo dopo il titolo.
        # Si tiene comunque come nodo (con marcatore) invece di scartarlo: per il
        # verificatore di citazioni è un'informazione diversa e più utile di un
        # semplice "articolo non trovato" - vuol dire "esisteva, ma non è più in vigore".
        abrogato = not testo_raw and current_rubrica is not None and "ABROGATO" in current_rubrica.upper()
        if not testo_raw and not abrogato:
            return  # titolo senza corpo per altri motivi (raro) - scartato, non abbastanza informazione
        testo_pulito = pulisci_testo(testo_raw) if testo_raw else ""
        articoli.append(
            Articolo(
                codice=codice,
                numero=current_numero,
                rubrica=current_rubrica,
                testo=testo_pulito or "[ARTICOLO ABROGATO]",
                testo_raw=testo_raw or "[ARTICOLO ABROGATO]",
                sezione=current_section,
                is_main_body=current_is_main_body,
                source_url=source_url,
                abrogato=abrogato,
            )
        )

    for line in lines:
        art_match = ARTICLE_HEADING_RE.match(line)
        if art_match:
            flush()
            current_numero = art_match.group(1)
            current_rubrica = _clean_title(art_match.group(2))
            current_body_lines = []
            current_is_main_body = is_main_body
            continue

        sec_match = SECTION_HEADING_RE.match(line)
        if sec_match and len(sec_match.group(1)) <= 2:  # solo "#"/"##", non i "###" articolo-livello
            flush()
            current_numero = None
            current_section = sec_match.group(2).strip()
            # BUG CORRETTO (trovato in una revisione esterna, agosto 2026):
            # "bool(main_body_marker) and ..." confondeva "nessun marcatore =
            # nessuna ambiguità, tutto è corpo" con "marcatore esplicito da
            # verificare" - per i 7 codici con marker=None (tub,
            # codice_crisi_impresa, l_241_1990, dpr_602_1973, l_689_1981,
            # l_287_1990, costituzione) bool(None)=False resettava
            # is_main_body a False in modo permanente alla prima intestazione
            # di sezione incontrata, invalidando il campo per l'intero
            # documento - verificato: prima del fix, TUB e Codice della Crisi
            # avevano 0/385 e 0/414 articoli con is_main_body=True. Ora: se
            # non c'è marcatore, la sezione non tocca is_main_body (resta
            # True per tutto il documento, il comportamento realmente voluto).
            if main_body_marker is not None:
                is_main_body = main_body_marker in current_section
            continue

        if current_numero is not None:
            current_body_lines.append(line)

    flush()
    return articoli


def parse_all(raw_dir: Path) -> list[Articolo]:
    codice_by_filename = {
        "codice_civile.md": "codice_civile",
        "codice_procedura_civile.md": "codice_procedura_civile",
        "codice_crisi_impresa.md": "codice_crisi_impresa",
        "tub.md": "tub",
        "l_241_1990.md": "l_241_1990",
        "dpr_602_1973.md": "dpr_602_1973",
        "rd_267_1942.md": "rd_267_1942",
        "l_689_1981.md": "l_689_1981",
        "l_287_1990.md": "l_287_1990",
        "costituzione.md": "costituzione",
        "dlgs_150_2011.md": "dlgs_150_2011",
        # Aggiunti il 2026-09-03 perche' erano i buchi misurati sulle 3051
        # motivazioni del corpus: sono le norme che i giudici citano di piu'
        # fra quelle che il grafo non aveva. Vedi STATO_PROGETTO §7.59.
        "l_108_1996.md": "l_108_1996",        # usura, citata dal 14,7%
        "dlgs_28_2010.md": "dlgs_28_2010",    # mediazione, dal 10,9%
        "dlgs_206_2005.md": "dlgs_206_2005",  # codice del consumo, dal 7,7%
        "dlgs_58_1998.md": "dlgs_58_1998",    # TUF, dal 7,5%
    }
    articoli: list[Articolo] = []
    for filename, codice in codice_by_filename.items():
        path = raw_dir / filename
        if not path.exists():
            continue
        articoli.extend(parse_file(path, codice))
    return articoli
