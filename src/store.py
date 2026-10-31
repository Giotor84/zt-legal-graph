"""Caricamento del grafo costruito da build_graph.py e ricerca per citazione.

Due livelli di retrieval: lookup esatto per (codice, numero) - sempre
disponibile, base del verificatore di citazioni - e, se build_embeddings.py è
stato eseguito, un indice semantico (classe EmbeddingIndex sotto) per
confrontare un "tema atteso" in linguaggio naturale col contenuto reale
dell'articolo, oltre al semplice overlap lessicale di somiglianza_tema().
"""

import pickle
import re
import unicodedata
from pathlib import Path

import networkx as nx

GRAPH_DIR = Path(__file__).parent.parent / "data" / "graph"

#: Il modello con cui e' stato costruito l'indice dei SEGMENTI di
#: provvedimento, e la soglia 0,856 che lo accompagna. Non si tocca senza
#: ricostruire quell'indice E rifare la calibrazione della soglia.
EMBEDDING_MODEL_BASE = "intfloat/multilingual-e5-small"

#: Il modello con cui e' costruito l'indice degli ARTICOLI, riaddestrato
#: sul linguaggio dei provvedimenti il 2026-09-03 (vedi
#: `addestra_embedding.py` e STATO_PROGETTO §7.60). Se non e' sul disco si
#: ripiega sul modello base: chi clona il repository senza i dati deve
#: poter comunque far girare la suite.
MODELLO_ARTICOLI_ADDESTRATO = Path(__file__).parent.parent / "data" / "modelli" / "e5-small-giuridico"
EMBEDDING_MODEL_ARTICOLI = (str(MODELLO_ARTICOLI_ADDESTRATO)
                            if MODELLO_ARTICOLI_ADDESTRATO.exists()
                            else EMBEDDING_MODEL_BASE)

#: NON esiste piu' un modello "del progetto". Ce n'erano due indici e una
#: costante sola: misurato il 2026-09-03, interrogare l'indice dei
#: segmenti con il modello degli articoli fa crollare il punteggio massimo
#: da 0,910 a 0,489 e porta a ZERO i segmenti sopra soglia - la quota di
#: giurisprudenza si sarebbe svuotata a ogni query senza che niente
#: fallisse. Il nome resta come alias del modello base per i chiamanti
#: vecchi, ma il modello va scelto per INDICE.
EMBEDDING_MODEL_NAME = EMBEDDING_MODEL_BASE

CODICE_ALIASES = {
    "c.c.": "codice_civile",
    "cc": "codice_civile",
    "codice civile": "codice_civile",
    "c.p.c.": "codice_procedura_civile",
    "cpc": "codice_procedura_civile",
    "codice di procedura civile": "codice_procedura_civile",
    "c.c.i.": "codice_crisi_impresa",
    "ccii": "codice_crisi_impresa",
    "codice della crisi d'impresa": "codice_crisi_impresa",
    "codice della crisi": "codice_crisi_impresa",
    "tub": "tub",
    "t.u.b.": "tub",
    "testo unico bancario": "tub",
    "l. 241/1990": "l_241_1990",
    "legge 241/1990": "l_241_1990",
    "l_241_1990": "l_241_1990",
    "d.p.r. 602/1973": "dpr_602_1973",
    "dpr 602/1973": "dpr_602_1973",
    "dpr_602_1973": "dpr_602_1973",
    "l. fall.": "rd_267_1942",
    "l.fall.": "rd_267_1942",
    "legge fallimentare": "rd_267_1942",
    "r.d. 267/1942": "rd_267_1942",
    "rd_267_1942": "rd_267_1942",
    "l. 689/1981": "l_689_1981",
    "legge 689/1981": "l_689_1981",
    "l_689_1981": "l_689_1981",
    "l. 287/1990": "l_287_1990",
    "legge 287/1990": "l_287_1990",
    "l_287_1990": "l_287_1990",
    "cost.": "costituzione",
    "costituzione": "costituzione",
    "d.lgs. 150/2011": "dlgs_150_2011",
    "dlgs 150/2011": "dlgs_150_2011",
    "d.lgs. 1 settembre 2011, n. 150": "dlgs_150_2011",
    "dlgs_150_2011": "dlgs_150_2011",
    # --- Le quattro fonti innestate il 2026-09-04.
    "t.u.f.": "dlgs_58_1998",
    "tuf": "dlgs_58_1998",
    "testo unico della finanza": "dlgs_58_1998",
    "d.lgs. 58/1998": "dlgs_58_1998",
    "dlgs 58/1998": "dlgs_58_1998",
    "dlgs_58_1998": "dlgs_58_1998",
    "codice del consumo": "dlgs_206_2005",
    "d.lgs. 206/2005": "dlgs_206_2005",
    "dlgs 206/2005": "dlgs_206_2005",
    "dlgs_206_2005": "dlgs_206_2005",
    "d.lgs. 28/2010": "dlgs_28_2010",
    "dlgs 28/2010": "dlgs_28_2010",
    "dlgs_28_2010": "dlgs_28_2010",
    "legge 108/1996": "l_108_1996",
    "l. 108/1996": "l_108_1996",
    "l. 108/96": "l_108_1996",
    "legge antiusura": "l_108_1996",
    "l_108_1996": "l_108_1996",
}

#: I nomi interni ammessi da `trova`. E' una lista CHIUSA, e va tenuta
#: allineata alle fonti che il grafo contiene: il 2026-09-04 quattro leggi
#: erano state innestate come nodi, il lookup le conteneva, e `trova` le
#: rifiutava all'ingresso perche' il loro nome non era qui. Nessun errore,
#: nessun arco: 1284 citazioni di sentenze restavano senza bersaglio e il
#: grafo sembrava semplicemente non averne.
CODICI_INTERNI = (
    "codice_civile",
    "codice_procedura_civile",
    "codice_crisi_impresa",
    "tub",
    "l_241_1990",
    "dpr_602_1973",
    "rd_267_1942",
    "l_689_1981",
    "l_287_1990",
    "costituzione",
    "dlgs_150_2011",
    "dlgs_58_1998",
    "dlgs_206_2005",
    "dlgs_28_2010",
    "l_108_1996",
)

# Normalizzazioni per citazioni di giurisprudenza (Massime) - usate sia da
# store.py (indicizzazione) sia da extract_citations.py (estrazione da testo
# libero), stessa funzione per garantire che i due lati combacino sempre.

_MESI_ITALIANI = {
    "gennaio": "01", "febbraio": "02", "marzo": "03", "aprile": "04",
    "maggio": "05", "giugno": "06", "luglio": "07", "agosto": "08",
    "settembre": "09", "ottobre": "10", "novembre": "11", "dicembre": "12",
}


def normalizza_ufficio(raw: str) -> str:
    """"Trib. Ancona" / "Tribunale di Ancona" -> "tribunale di ancona";
    "Corte d'Appello di Firenze" / "Corte di Appello di Firenze" / "C. App.
    Firenze" -> "corte di appello di firenze"; "Cass." / "Corte di
    Cassazione" -> "corte di cassazione" (nessuna sede, è unica). Permissivo
    di proposito: la stessa citazione compare in forme diverse tra un atto
    di controparte, il testo generato dal modello, e i dati BDP - meglio
    sovra-normalizzare che perdere un match valido per una differenza di
    formattazione."""
    s = unicodedata.normalize("NFKD", raw or "").encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"\s+", " ", s.strip().lower())
    s = s.replace("'", " ").replace(".", " ")
    s = re.sub(r"\s+", " ", s).strip()

    if re.match(r"^cass\b|^corte (di )?cassazione|^corte suprema di cassazione", s):
        return "corte di cassazione"

    m = re.match(r"^(?:c\s*app|corte (?:d|di) appello)\s*(?:di\s*)?(.*)$", s)
    if m:
        sede = m.group(1).strip()
        return f"corte di appello di {sede}".strip()

    # "tribunale" prima di "trib" nell'alternanza: "trib" e' un prefisso di
    # "tribunale", provato per primo mangerebbe solo quello e lascerebbe
    # "unale di bologna" nel gruppo del nome sede - bug trovato testando su
    # "TRIBUNALE DI BOLOGNA" prima di fidarsi della regex.
    m = re.match(r"^(?:tribunale|trib)\s*(?:di\s*)?(.*)$", s)
    if m:
        sede = m.group(1).strip()
        return f"tribunale di {sede}".strip()

    return s


def normalizza_tipo_provvedimento(raw: str) -> str:
    """"sent." / "sentenza" / "SENTENZA" -> "sentenza"; stesso per
    ordinanza/decreto - un solo valore normalizzato per confronto."""
    s = re.sub(r"\s+", " ", (raw or "").strip().lower()).rstrip(".")
    if s.startswith("sent"):
        return "sentenza"
    if s.startswith("ord"):
        return "ordinanza"
    if s.startswith("decr"):
        return "decreto"
    return s


def normalizza_data(raw: str) -> str:
    """Accetta "30/11/2023", "30.11.2023", "30-11-2023", "30 novembre 2023"
    - normalizza sempre a "DD/MM/YYYY" (stesso formato usato nei dati BDP
    già nel grafo, vedi bdp_integra_grafo.py)."""
    s = (raw or "").strip()

    m = re.match(r"^(\d{1,2})\s*[/.\-]\s*(\d{1,2})\s*[/.\-]\s*(\d{4})$", s)
    if m:
        gg, mm, aaaa = m.groups()
        return f"{int(gg):02d}/{int(mm):02d}/{aaaa}"

    m = re.match(r"^(\d{1,2})\s+([a-zàèéìòù]+)\s+(\d{4})$", s.lower())
    if m:
        gg, mese_nome, aaaa = m.groups()
        mese_num = _MESI_ITALIANI.get(mese_nome)
        if mese_num:
            return f"{int(gg):02d}/{mese_num}/{aaaa}"

    return s


class GraphStore:
    def __init__(self, graph: nx.MultiDiGraph):
        self.graph = graph
        self._lookup = self._build_lookup()
        self._lookup_massime = self._build_lookup_massime()

    @classmethod
    def load(cls) -> "GraphStore":
        with open(GRAPH_DIR / "grafo.gpickle", "rb") as f:
            graph = pickle.load(f)
        return cls(graph)

    def _build_lookup(self) -> dict[tuple[str, str], str]:
        # Nodi Articolo (i soli esistenti finora) non hanno mai avuto un
        # campo tipo_nodo esplicito - retrocompatibile: assente o
        # "articolo" = Articolo, "massima" = nodo di giurisprudenza
        # aggiunto da bdp_integra_grafo.py, va saltato qui (schema
        # diverso, niente codice/numero/is_main_body).
        lookup = {}
        for node_id, data in self.graph.nodes(data=True):
            if data.get("tipo_nodo", "articolo") != "articolo":
                continue
            key = (data["codice"], data["numero"])
            if key not in lookup or data["is_main_body"]:
                lookup[key] = node_id
        return lookup

    def _build_lookup_massime(self) -> dict[tuple[str, str, str], list[str]]:
        """Lookup per (ufficio normalizzato, tipo_provvedimento normalizzato,
        data normalizzata) -> LISTA di node_id, non un singolo match: una
        stessa sentenza produce spesso più massime distinte (stesso
        ufficio+tipo+data, principi di diritto diversi) - verificato sui
        dati reali (es. due massime CORTE DI APPELLO DI PERUGIA, SENTENZA,
        19/10/2022), non un'ipotesi."""
        lookup: dict[tuple[str, str, str], list[str]] = {}
        for node_id, data in self.graph.nodes(data=True):
            if data.get("tipo_nodo") != "massima":
                continue
            chiave = (
                normalizza_ufficio(data.get("ufficio", "")),
                normalizza_tipo_provvedimento(data.get("tipo_provvedimento", "")),
                normalizza_data(data.get("data", "")),
            )
            lookup.setdefault(chiave, []).append(node_id)
        return lookup

    def trova_massime(self, ufficio: str, tipo_provvedimento: str, data: str) -> list[dict]:
        """Ritorna TUTTE le massime che combaciano con (ufficio, tipo
        provvedimento, data) citati - può essere più di una (vedi nota in
        _build_lookup_massime), lista vuota se nessuna trovata (citazione
        non presente nel corpus, non necessariamente inventata: potrebbe
        essere una sentenza reale ma fuori dalle 185 massime BDP raccolte)."""
        chiave = (normalizza_ufficio(ufficio), normalizza_tipo_provvedimento(tipo_provvedimento), normalizza_data(data))
        node_ids = self._lookup_massime.get(chiave, [])
        return [dict(self.graph.nodes[nid]) for nid in node_ids]

    @staticmethod
    def normalizza_codice(sigla: str) -> str | None:
        key = re.sub(r"\s+", " ", sigla.strip().lower())
        return CODICE_ALIASES.get(key)

    @staticmethod
    def normalizza_numero(numero: str) -> str:
        return re.sub(r"\s+", "-", numero.strip())

    def trova(self, codice: str, numero: str) -> dict | None:
        """codice può essere il nome interno ("codice_civile") o una sigla comune
        ("c.c.", "cc", ecc.) - normalizzato automaticamente."""
        codice_norm = codice if codice in CODICI_INTERNI else self.normalizza_codice(codice)
        if codice_norm is None:
            return None
        node_id = self._lookup.get((codice_norm, self.normalizza_numero(numero)))
        if node_id is None:
            return None
        return dict(self.graph.nodes[node_id])

    def citanti(self, codice: str, numero: str) -> list[dict]:
        """Articoli che citano quello dato (archi entranti)."""
        art = self.trova(codice, numero)
        if art is None:
            return []
        node_id = f"{art['codice']}::{art['numero']}" if art["is_main_body"] else f"{art['codice']}::{art['sezione']}::{art['numero']}"
        return [dict(self.graph.nodes[u]) for u, _ in self.graph.in_edges(node_id)]

    def citati_da(self, codice: str, numero: str) -> list[dict]:
        """Articoli citati da quello dato (archi uscenti)."""
        art = self.trova(codice, numero)
        if art is None:
            return []
        node_id = f"{art['codice']}::{art['numero']}" if art["is_main_body"] else f"{art['codice']}::{art['sezione']}::{art['numero']}"
        return [dict(self.graph.nodes[v]) for _, v in self.graph.out_edges(node_id)]

    def _node_id_di(self, art: dict) -> str:
        return f"{art['codice']}::{art['numero']}" if art["is_main_body"] else f"{art['codice']}::{art['sezione']}::{art['numero']}"

    def carica_embeddings(self) -> "EmbeddingIndex | None":
        """None se embeddings.npy non è stato ancora costruito (build_embeddings.py) -
        il chiamante deve saper degradare al solo confronto lessicale in quel caso."""
        emb_path = GRAPH_DIR / "embeddings.npy"
        idx_path = GRAPH_DIR / "embeddings_index.json"
        if not emb_path.exists() or not idx_path.exists():
            return None
        return EmbeddingIndex.load(emb_path, idx_path)


class IndiceDiUnAltroModello(RuntimeError):
    """L'indice e' stato costruito con un modello e interrogato con un altro."""


def percorso_modello_dichiarato(emb_path: Path) -> Path:
    """Il file che dice con quale modello e' nato un indice."""
    return emb_path.with_name(emb_path.stem + "_modello.json")


def leggi_modello_dichiarato(emb_path: Path) -> str | None:
    """Il modello dichiarato accanto all'indice, o None se non dichiarato."""
    import json

    percorso = percorso_modello_dichiarato(emb_path)
    if not percorso.exists():
        return None
    return json.loads(percorso.read_text(encoding="utf-8")).get("modello")


def scrivi_modello_dichiarato(emb_path: Path, nome_modello: str) -> Path:
    """Dichiara il modello accanto all'indice appena costruito."""
    import json

    percorso = percorso_modello_dichiarato(emb_path)
    percorso.write_text(json.dumps({"modello": nome_modello}, ensure_ascii=False),
                        encoding="utf-8")
    return percorso


class EmbeddingIndex:
    """Wrapper sugli embedding precalcolati (build_embeddings.py) + il modello
    per codificare al volo il testo di query (il "tema atteso" del verificatore,
    che non è mai stato visto in anticipo, quindi non può essere precalcolato).

    Import di sentence_transformers/numpy fatto qui dentro, non in cima al
    modulo: così store.py resta usabile per il solo confronto lessicale anche
    in un ambiente senza quelle dipendenze (vedi nota in build_embeddings.py sul
    perché sono in un venv separato su questa macchina)."""

    def __init__(self, embeddings, node_ids: list[str],
                 nome_modello: str | None = None):
        import numpy as np

        self._np = np
        self.embeddings = embeddings  # (n, d) normalizzato, coseno = dot product
        self.node_ids = node_ids
        self._row_by_node_id = {nid: i for i, nid in enumerate(node_ids)}
        self._model = None  # lazy: caricato solo alla prima query effettiva
        #: il modello va con l'INDICE, non con il progetto: due indici
        #: diversi possono essere nati da due modelli diversi, ed e'
        #: esattamente il caso di oggi (articoli riaddestrato, segmenti
        #: base).
        self.nome_modello = nome_modello or EMBEDDING_MODEL_ARTICOLI

    @classmethod
    def load(cls, emb_path: Path, idx_path: Path,
             nome_modello: str | None = None) -> "EmbeddingIndex":
        """Carica l'indice, e controlla di sapere con quale modello e' nato.

        Accanto al `.npy` si scrive un `<nome>_modello.json` che dichiara
        il modello che lo ha costruito. Se c'e' e non combacia, si alza
        un errore: interrogare un indice con un modello diverso da quello
        che lo ha prodotto **non fallisce da solo** - restituisce
        punteggi bassi e plausibili. Misurato il 2026-09-03 sull'indice
        dei segmenti: massimo da 0,910 a 0,489 e zero risultati sopra la
        soglia, con la pipeline che continuava a girare.

        Un indice senza il file di dichiarazione e' un indice vecchio: si
        accetta, perche' rifiutarlo bloccherebbe chi ha dati anteriori a
        questa modifica, ma il controllo diventa attivo appena l'indice
        viene ricostruito.
        """
        import json

        import numpy as np

        embeddings = np.load(emb_path)
        with open(idx_path, encoding="utf-8") as f:
            node_ids = json.load(f)
        modello = nome_modello or EMBEDDING_MODEL_ARTICOLI
        dichiarato = leggi_modello_dichiarato(emb_path)
        if dichiarato is not None and dichiarato != modello:
            raise IndiceDiUnAltroModello(
                "l'indice %s e' stato costruito con %r, ma lo si vuole "
                "interrogare con %r. Un indice interrogato dal modello "
                "sbagliato non da' errore: da' punteggi bassi e credibili. "
                "Ricostruire l'indice, oppure passare nome_modello."
                % (emb_path.name, dichiarato, modello))
        return cls(embeddings, node_ids, nome_modello=modello)

    def _modello(self):
        """None se sentence_transformers non è installato nell'interprete che sta
        girando (es. lanciato da .venv invece di ~/venvs/zt_legal_graph_ml) - la
        degradazione al solo confronto lessicale deve restare pulita, non un
        traceback, così verify.py gira comunque da qualunque dei due ambienti."""
        if self._model is None and self._model is not False:
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(self.nome_modello)
            except ImportError:
                self._model = False  # marcatore "tentato e non disponibile", non ritentare ad ogni chiamata
        return self._model or None

    def somiglianza_e_rank(self, query_text: str, node_id: str) -> tuple[float, int] | None:
        """Similarità coseno E posizione in classifica (1 = il più simile in
        assoluto nell'intero corpus) tra una query in linguaggio naturale e un
        articolo specifico. None se l'articolo non è indicizzato O se
        sentence_transformers non è disponibile in questo interprete Python.

        Il rank, non il punteggio assoluto, è la base della decisione nel
        verificatore - vedi nota in verify.py sul perché: con questo modello,
        su testo giuridico italiano breve, il coseno resta compresso in una
        fascia alta (~0.78-0.94) anche per coppie di testo completamente
        scorrelate, quindi una soglia fissa sul punteggio non discrimina bene.
        Il rank invece si è mostrato pulito nei test empirici: le citazioni
        corrette finiscono quasi sempre in top-12, quelle sbagliate ben oltre
        top-400 (con un'eccezione istruttiva, vedi README/documento di stato)."""
        row = self._row_by_node_id.get(node_id)
        if row is None:
            return None
        modello = self._modello()
        if modello is None:
            return None
        query_vec = modello.encode(
            "query: " + query_text, convert_to_numpy=True, normalize_embeddings=True
        )
        scores = self.embeddings @ query_vec
        score = float(scores[row])
        rank = int((scores > score).sum()) + 1
        return score, rank

    def top_k(self, query_text: str, k: int) -> list[tuple[str, float]] | None:
        """I k node_id più simili alla query, per il retrieval "vero" (prima della
        generazione) usato dal constrained decoding - a differenza di
        somiglianza_e_rank(), che valuta UN articolo specifico già noto, questo
        restituisce l'insieme dei candidati senza sapere in anticipo quale sia
        quello giusto. None se sentence_transformers non è disponibile."""
        modello = self._modello()
        if modello is None:
            return None
        query_vec = modello.encode(
            "query: " + query_text, convert_to_numpy=True, normalize_embeddings=True
        )
        scores = self.embeddings @ query_vec
        top_idx = self._np.argsort(-scores)[:k]
        return [(self.node_ids[i], float(scores[i])) for i in top_idx]


def _normalizza_parole(text: str) -> set[str]:
    text = text.lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    # parole di 4+ lettere: filtro grezzo per scartare articoli/preposizioni/congiunzioni
    return {w for w in text.split() if len(w) >= 4}
    # Nota: niente stemming/lemmatizzazione qui. Un tentativo di troncamento al
    # prefisso ("ipoteche"/"ipoteca" -> stesso prefisso) risolveva un falso
    # negativo ma ne apriva uno nuovo altrove (collisione "debiti"/"debitore"
    # su un caso scorrelato, vedi git history) - un patch lessicale sposta il
    # problema invece di risolverlo. Il limite strutturale (bag-of-words non
    # coglie sinonimi né distingue "stesso ambito lessicale" da "stesso punto
    # specifico") va risolto con un layer semantico vero, non con euristiche
    # sui suffissi - vedi README, sezione limiti.


def somiglianza_tema(tema_atteso: str, testo_articolo: str) -> tuple[float, set[str]]:
    """Overlap grezzo per parole normalizzate tra il tema atteso e il testo reale
    dell'articolo. Non è un embedding semantico (nessun modello coinvolto, gira
    all'istante su CPU) - cattura bene i casi netti del catalogo Fase 1 (overlap
    vicino a zero per una citazione totalmente inventata), non sostituisce una
    vera ricerca semantica per sfumature più sottili. Vedi README."""
    parole_tema = _normalizza_parole(tema_atteso)
    parole_articolo = _normalizza_parole(testo_articolo)
    if not parole_tema:
        return 0.0, set()
    overlap = parole_tema & parole_articolo
    return len(overlap) / len(parole_tema), overlap
