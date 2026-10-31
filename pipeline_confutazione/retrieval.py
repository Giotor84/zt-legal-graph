"""
UNICO MODULO CHE CONOSCE LO SCHEMA DEL GRAFO - punto di riapertura per la
migrazione al versionamento temporale.

Nessun altro modulo della pipeline legge `store.graph.nodes[...]`, i nomi
dei campi dei nodi (`testo`/`motivazione`/`dispositivo`/`rubrica`/`ufficio`/
`data`/`codice`/`numero`/...) o interroga l'indice di embedding. Quando il
grafo diventa versionato, si riaprono le IMPLEMENTAZIONI qui dentro: le
firme pubbliche e i chiamanti restano invariati per costruzione, perche'
gli accessori nascono gia' con il parametro temporale (`data`), oggi
ignorato.

Importato SOLO dalla Fase 2 (assembla_report). La Fase 3 (redazione.py,
constrained_decoding.py) non ha alcun percorso di import verso questo
modulo ne' verso lo store - invariante architetturale verificato
staticamente da test_import_grafo_isolato.py, non affidato alla
disciplina.

Contenuto spostato da constrained_decoding.py (2026-08-20, split
retrieval/generazione vincolata) senza modifiche di comportamento, salvo
gli accessori nuovi e le marcature dei bug noti del grafo.

--- Perche' la riformulazione della query vive qui ---

Risolto il problema di recall gia' segnalato come aperto (art. 2852 c.c.,
risposta corretta per un caso reale di priorita' tra ipoteche, a rank
648-759 su un prompt narrativo realistico - fuori da qualunque K
praticabile). Riformulare la stessa domanda in parole chiave dirette porta
lo stesso identico articolo da rank 759 a rank 4 (query di prova: "grado
ipoteca priorita' tra creditori ipotecari sullo stesso immobile", stessa
sostanza del prompt narrativo, zero fatti/numeri). La riformulazione
serve e resta.

**Le due conclusioni che accompagnavano quell'esperimento erano
sbagliate, e il 2026-09-03 sono state smentite da una misura.** Qui si
leggeva: «NON e' un limite del modello di embedding ne' un problema
risolvibile con retrieval lessicale (bag-of-words dava 0% di overlap,
rank 4771 - anche peggio del semantico)». Erano tratte da UNA query.
Su 1200 passaggi di motivazione con verita' di riferimento presa dal
grafo (`valuta_retrieval.py`):

- la ricerca lessicale **non** e' peggiore: e' piu' del doppio della
  semantica (R@20 32,1% contro 14,6%);
- il modello di embedding **e'** il limite: `multilingual-e5-small`, 118M
  parametri, generico, e' la strategia peggiore fra quelle provate -
  peggio di una lista fissa che non legge nemmeno la domanda (48,7%).

Lezione, e vale oltre questo modulo: un esperimento su un caso solo
produce una spiegazione plausibile e la fissa in un commento, dove poi
indirizza il lavoro per settimane. Il difetto non era l'esperimento -
era chiamare "causa isolata sperimentalmente" cio' che era n=1.

`riformula_query_di_ricerca()` e' una chiamata LLM e quindi NON puo' stare
dentro la Fase 2, che il contratto vincola a "solo Python, zero LLM": e'
un passo 1-bis dell'orchestratore, fra Fase 1 e Fase 2 (vedi
CONTRATTI_DATI.md). Vive qui perche' e' logicamente parte del retrieval e
perche' il suo unico chiamante e' l'entry point.

--- Bug noti del grafo che attraversano questo modulo ---

- BUG-GRAFO-3: 244 articoli abrogati sono ancora nell'indice di retrieval,
  quindi `candidati_per_prompt` puo' restituirli come candidati citabili.
- BUG-GRAFO-4: 36 valori di `citazione_breve` non sono univoci, quindi
  `citazione_breve` non e' utilizzabile come chiave (il contratto lo dice
  gia' come principio: l'identita' e' `fonte_id`/`node_id`).
- BUG-GRAFO-6: il parser BDP lascia `collegio` vuoto e `numero_rg`
  mancante, quindi la citazione breve di un provvedimento puo' degradare.

Vedi le marcature puntuali sotto e il riepilogo finale della pipeline.
"""

from __future__ import annotations

import hashlib
import pickle
import sys
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))  # store.py resta condiviso in src/
import llama_server_client
import ricerca_lessicale
from store import EmbeddingIndex, GraphStore

#: Indice per parole e graduatoria di citazione, costruiti una volta per
#: grafo. La chiave e' l'identita' dell'oggetto grafo: una corsa ne usa
#: uno solo, e ricostruire l'indice a ogni eccezione costerebbe 0,2s per
#: nulla. Non e' una cache di correttezza - il contenuto dipende solo dal
#: grafo - e' una cache di lavoro.
_INDICI_LESSICALI: dict[int, tuple["ricerca_lessicale.IndiceLessicale", list[str]]] = {}


def _lessicale_e_graduatoria(store: GraphStore, node_ids: Sequence[str]):
    chiave = id(store.graph)
    presente = _INDICI_LESSICALI.get(chiave)
    if presente is None:
        indice = ricerca_lessicale.indice_dal_grafo(store.graph, node_ids)
        frequenze = ricerca_lessicale.frequenza_di_citazione(store.graph)
        graduatoria = ricerca_lessicale.graduatoria_per_frequenza(frequenze, set(node_ids))
        presente = (indice, graduatoria)
        _INDICI_LESSICALI[chiave] = presente
    return presente

#: Default dei dati, allineato a `store.GRAPH_DIR` - ma NON importato da
#: li': i percorsi devono poter arrivare dalla riga di comando, e una
#: costante importata sarebbe un default travestito da vincolo.
CARTELLA_DATI_DEFAULT = Path(__file__).parent.parent / "data" / "graph"
#: Grafo di riferimento: contiene i provvedimenti integrali con
#: testo_integrale/motivazione segmentabili, numero_sentenza,
#: stato_verifica e motivazione_certa sui nodi, e numero_rg in formato
#: NUM/ANNO.
#:
#: Qui c'era "grafo_con_provvedimenti_integrali.gpickle" fino al 2026-08-30,
#: cioe' un file che NON ESISTE dal 2026-08-20, quando fu promosso a
#: grafo.gpickle. `carica_grafo` solleva FileNotFoundError se il file non
#: c'e': il default era percio' un percorso morto, e OGNI Fase 2 lanciata
#: senza `--grafo` esplicito falliva in partenza. Non se n'era accorto
#: nessuno perche' le corse recenti sono tutte `--solo-fase1`, che il grafo
#: non lo apre.
#: Anche la nota che diceva "il precedente (grafo.gpickle) e' in
#: data/graph/archivio/" era sbagliata due volte: grafo.gpickle e' il file
#: IN CARICA, non il precedente, e `data/graph/archivio/` non esiste (vedi
#: CLAUDE.md bug 6, corretto nella stessa sessione; i backup stanno in
#: C:\zt_legal_graph_backup\graph\).
NOME_GRAFO_DEFAULT = "grafo.gpickle"
NOME_EMBEDDINGS_DEFAULT = "embeddings.npy"
NOME_EMBEDDINGS_SEGMENTI_DEFAULT = "embeddings_segmenti_provvedimenti.npy"

#: Soglia di rilevanza assoluta per l'INDICE SEGMENTI. DECISIONE
#: OPERATIVA, non costante misurata: vedi CONTRATTI_DATI.md, sezione
#: "Criterio di rilevanza". Calibrazione del 2026-08-20, n=20 per lato:
#: rumore max 0.8554, segnale min 0.8547, sovrapposizione 0.0008. A questo
#: valore nessuna query fuori dominio passa e se ne perde una di dominio
#: ("opposizione all'esecuzione"), che e' comportamento corretto - il
#: corpus di Ancona non copre quella materia.
#:
#: Sull'INDICE PRINCIPALE una soglia analoga NON esiste e non va cercata:
#: alla stessa calibrazione, 19 query di dominio su 20 cadevano sotto il
#: massimo del rumore, e il punteggio piu' alto dell'intero esperimento
#: era una query fuori dominio. La' il criterio e' la verifica di
#: pertinenza a valle.
SOGLIA_SEGMENTI_DEFAULT = 0.8560

#: Quota per indice. Mai un ordinamento unico: alla calibrazione la
#: mediana del RUMORE sull'indice principale (0.8804) e' risultata piu'
#: alta del minimo del SEGNALE sui segmenti (0.8547), quindi fondere i due
#: elenchi per punteggio metterebbe sistematicamente il rumore dell'uno
#: sopra il segnale dell'altro.
QUOTA_PRINCIPALE_DEFAULT = 4
QUOTA_SEGMENTI_DEFAULT = 2


# ------------------------------------------------------------------ caricamento


class IndiceSegmenti:
    """L'indice dei segmenti di provvedimento.

    Non e' un `EmbeddingIndex`: quello assume che `embeddings_index.json`
    sia una lista di `node_id` (stringhe), mentre qui ogni voce e' un
    oggetto `{node_id, indice_segmento, offset_inizio, offset_fine,
    motivazione_certa, stato_verifica}`. Gli offset sono cio' che rende un
    segmento ritagliabile come estratto con la tripla corretta, e i due
    campi di verifica sono quelli del controllo 15 - a livello di SEGMENTO,
    piu' fine di quello per nodo.

    Ogni risultato porta il punteggio: e' il criterio di rilevanza (soglia
    assoluta) a deciderne l'ammissione, quindi il chiamante deve poterlo
    vedere."""

    def __init__(self, embeddings, voci: list[dict], modello=None):
        import numpy as np

        self._np = np
        self.embeddings = embeddings
        self.voci = voci
        self._modello_condiviso = modello

    @classmethod
    def carica(cls, percorso_embeddings: Path, modello=None) -> "IndiceSegmenti | None":
        import json as _json

        indice_json = percorso_embeddings.with_name(percorso_embeddings.stem + "_index.json")
        if not percorso_embeddings.is_file() or not indice_json.is_file():
            return None
        import numpy as np

        return cls(np.load(percorso_embeddings),
                   _json.loads(indice_json.read_text(encoding="utf-8")), modello)

    def _modello(self):
        if self._modello_condiviso is None:
            from sentence_transformers import SentenceTransformer
            from store import EMBEDDING_MODEL_NAME

            self._modello_condiviso = SentenceTransformer(EMBEDDING_MODEL_NAME)
        return self._modello_condiviso

    def similarita(self, query: str):
        """La somiglianza fra la query e OGNI riga della matrice, nell'ordine
        delle righe.

        Serve allo strato vettoriale della classificazione
        (`famiglie_grafo.famiglia_da_vettori`), che vota sui vicini e ha
        bisogno del vettore intero, non dei primi k: il quorum si conta sui
        5 piu' vicini, ma quali siano i 5 lo decide lui.

        Stesso prefisso "query: " del resto del progetto: e' il formato che
        il modello e5 richiede, e usarne uno diverso qui produrrebbe
        punteggi non confrontabili con quelli della calibrazione."""
        vettore = self._modello().encode("query: " + query, convert_to_numpy=True,
                                          normalize_embeddings=True)
        return self.embeddings @ vettore

    def top_k(self, query: str, k: int) -> list[dict]:
        """I k segmenti piu' simili, ciascuno con punteggio e offset."""
        punteggi = self.similarita(query)
        migliori = self._np.argsort(-punteggi)[:k]
        return [{**self.voci[i], "score": float(punteggi[i])} for i in migliori]


def carica_grafo(percorso_grafo: Path, percorso_embeddings: Path | None = None
                  ) -> tuple[GraphStore, EmbeddingIndex | None]:
    """Carica grafo ed embedding da percorsi ESPLICITI.

    Non usa `GraphStore.load()` ne' `store.carica_embeddings()`: quelle
    leggono da `store.GRAPH_DIR`, una costante di modulo, e store.py non
    e' modificabile in questo lavoro. Si usa invece l'API pubblica che i
    percorsi li accetta - `GraphStore(graph)` e `EmbeddingIndex.load(emb,
    idx)` - il che evita sia di toccare store.py sia di scriverne la
    costante da fuori (monkeypatch che funzionerebbe, e che sarebbe
    invisibile a chiunque legga store.py dopo).

    `data/graph/` contiene una dozzina di gpickle di backup
    (`grafo_pre_bankit_backup`, `grafo_con_direzione`, ...): quale sia
    quello buono e' una decisione dell'operatore, non un default da
    indovinare in silenzio - per questo il percorso arriva da fuori.

    L'indice degli embedding e' opzionale: `None` se non indicato o non
    presente. Chi ne ha bisogno (la Fase 2) deve fallire rumorosamente,
    non degradare - vedi `esegui_fase2`."""
    if not percorso_grafo.is_file():
        raise FileNotFoundError(
            f"grafo non trovato: {percorso_grafo}. Indicarlo con --grafo, oppure "
            f"metterlo in {CARTELLA_DATI_DEFAULT / NOME_GRAFO_DEFAULT}"
        )
    with percorso_grafo.open("rb") as file:
        grafo = pickle.load(file)
    store = GraphStore(grafo)

    indice = None
    if percorso_embeddings is not None:
        indice_json = percorso_embeddings.with_name(
            percorso_embeddings.stem + "_index.json")
        if percorso_embeddings.is_file() and indice_json.is_file():
            indice = EmbeddingIndex.load(percorso_embeddings, indice_json)
    return store, indice


def candidati_segmenti(indice: "IndiceSegmenti | None", store: GraphStore, query: str,
                        soglia: float, quota: int) -> list[dict]:
    """Segmenti di provvedimento sopra soglia, gia' filtrati dal controllo
    15 e con gli offset per ritagliarli.

    **Se nessun segmento supera la soglia la quota resta VUOTA**: non si
    riempie con l'indice principale. Le due scale non sono confrontabili
    (vedi QUOTA_SEGMENTI_DEFAULT), e sostituire materiale sopra soglia con
    materiale di un altro indice significherebbe far passare per pertinente
    cio' che la soglia ha appena escluso."""
    if indice is None:
        return []
    ammessi = []
    for voce in indice.top_k(query, quota * 4):
        if len(ammessi) >= quota:
            break
        if voce["score"] < soglia:
            break  # ordinati per punteggio: sotto soglia il resto lo e' pure
        if voce["stato_verifica"] != STATO_VERIFICA_CITABILE or not voce["motivazione_certa"]:
            continue  # controllo 15, a livello di segmento
        citabile, _ = citabile_automaticamente(store, voce["node_id"])
        if not citabile:
            continue  # controllo 15, a livello di nodo
        ammessi.append(voce)
    return ammessi


def identita_grafo(store: GraphStore, percorso_grafo: Path) -> dict:
    """Il blocco `meta.esecuzione.grafo`: cosa e' stato davvero caricato.

    Sta qui e non nell'orchestratore perche' e' l'unico punto che sa come
    si conta un nodo - e perche' quando il grafo sara' versionato questa
    e' una delle funzioni che dovranno dire ANCHE quale versione."""
    return {
        "percorso": str(percorso_grafo),
        "sha256": _sha256_file(percorso_grafo),
        "n_nodi": store.graph.number_of_nodes(),
    }


def _sha256_file(percorso: Path) -> str | None:
    if not percorso.is_file():
        return None
    digestore = hashlib.sha256()
    with percorso.open("rb") as file:
        for blocco in iter(lambda: file.read(1024 * 1024), b""):
            digestore.update(blocco)
    return digestore.hexdigest()


# ------------------------------------------------------------------ retrieval


def candidati_per_prompt(store: GraphStore, embedding_index: EmbeddingIndex,
                         query_di_ricerca: str, k: int = 20, *,
                         usa_semantico: bool = True) -> list[dict]:
    """Retrieval vero: data una query di ricerca (vedi
    riformula_query_di_ricerca - NON necessariamente il prompt narrativo
    originale dell'utente, la cui lunghezza/stile diluisce il segnale
    semantico, verificato empiricamente, non assunto), i k nodi più
    pertinenti per similarità semantica - articoli di codice O
    giurisprudenza reale (Massime, paragrafi Banca d'Italia - da agosto
    2026 indicizzati anche loro, vedi build_embeddings.py; i Provvedimenti
    integrali restano esclusi dal retrieval, stesso motivo li'
    documentato).
    Ordine di rilevanza preservato (primo = più simile).

    # BUG-GRAFO-3: 244 articoli abrogati sono ancora presenti nell'indice
    # di embedding, quindi possono comparire qui come candidati citabili.
    # NON filtrati in silenzio: filtrarli richiederebbe leggere l'attributo
    # `abrogato` dei nodi e decidere al posto dell'avvocato che un articolo
    # abrogato non serve mai (falso: la versione vigente all'epoca dei
    # fatti e' esattamente cio' che la migrazione temporale dovra' gestire).
    # Il chiamante li vede nel dossier e la pipeline li segnala nel
    # riepilogo finale.

    --- Dal 2026-09-03 non e' piu' solo semantico, ed e' una misura a
    dirlo, non un'intuizione ---

    `valuta_retrieval.py` misura questa funzione contro una verita' di
    riferimento che non abbiamo scritto noi: i 15.889 archi
    provvedimento -> articolo del grafo, cioe' quale norma il giudice ha
    citato scrivendo quel passaggio. Su 1200 passaggi di provvedimenti
    tenuti fuori dal calcolo delle frequenze:

        strategia                     R@1    R@5   R@20    MRR
        vettoriale (quella di ieri)  3,6%   8,3%  14,6%  0,058
        BM25 (parole)                8,4%  18,8%  32,1%  0,135
        frequenza di citazione       4,4%  18,7%  48,7%  0,120
        RRF parole+frequenza        23,5%  42,3%  60,5%  0,321   <- oggi
        RRF vett+parole+frequenza   16,5%  26,2%  41,1%  0,214

    La ricerca semantica era la strategia PEGGIORE fra quelle provate -
    peggio di una lista fissa che non legge nemmeno la domanda - e
    aggiungerla alla fusione la peggiorava (60,5% -> 41,1%). Non era un
    segnale debole da pesare di meno: era rumore. Il modello era
    `multilingual-e5-small`, 118M parametri, generico, mai addestrato su
    italiano giuridico.

    --- Poi il modello e' stato riaddestrato, ed e' cambiato tutto ---

    Il 2026-09-03, con `addestra_embedding.py`, sulle stesse coppie del
    grafo e con i provvedimenti di prova tenuti fuori (§7.60). Stessi
    1200 casi, stesso metro:

        denso riaddestrato (da solo)   22,2%  42,3%  61,2%  0,317
        RRF parole+frequenza           23,5%  42,3%  60,5%  0,321
        RRF denso+parole+frequenza     33,2%  56,7%  76,8%  0,442   <- oggi

    Da solo il modello riaddestrato **pareggia l'intera fusione
    precedente**; insieme la porta a 76,8% di R@20. Il criterio per
    accettarlo era stato dichiarato PRIMA di addestrare.

    Quindi `usa_semantico` torna a `True` di default. Resta un
    interruttore perche' il confronto fra le due configurazioni deve
    poter essere rifatto senza modificare il codice.

    **Attenzione a quale modello.** `embedding_index` deve essere quello
    degli ARTICOLI, costruito col modello riaddestrato. L'indice dei
    SEGMENTI e' un altro, costruito col modello base, e la sua soglia
    0,856 e' tarata su quello: interrogarlo con il modello sbagliato non
    da' errore, da' punteggi bassi e credibili - misurato, il massimo
    scende da 0,910 a 0,489 e nessun segmento passa la soglia.
    `EmbeddingIndex.load` ora se ne accorge e alza `IndiceDiUnAltroModello`.

    Il `score` restituito NON e' piu' una similarita' coseno: e' il
    punteggio RRF, che vale solo a ordinare. Nessun consumatore gli
    applica una soglia (verificato: l'unica soglia del modulo, 0,856, sta
    su `candidati_segmenti`, che e' un altro indice e non e' toccato)."""
    node_ids = list(embedding_index.node_ids)
    indice_parole, graduatoria = _lessicale_e_graduatoria(store, node_ids)

    strategie = [ricerca_lessicale.strategia_lessicale(indice_parole),
                 ricerca_lessicale.strategia_costante(graduatoria)]
    if usa_semantico:
        def semantica(query: str, quanti: int) -> list[str]:
            esito = embedding_index.top_k(query, quanti)
            if esito is None:
                raise RuntimeError(
                    "Layer semantico non disponibile in questo interprete "
                    "(serve il venv zt_legal_graph_ml).")
            return [node_id for node_id, _ in esito]

        strategie.insert(0, semantica)

    fusione = ricerca_lessicale.fondi(*strategie)
    return [_candidato(store, node_id, punteggio)
            for node_id, punteggio in _con_punteggio(fusione, query_di_ricerca, k)]


def _con_punteggio(fusione, query: str, k: int) -> list[tuple[str, float]]:
    """I node_id fusi, con il punteggio RRF accanto.

    `fondi` restituisce i soli node_id perche' e' la forma che serve alla
    misura; qui serve anche il punteggio, che il dossier mostra fra gli
    spunti. Si ricava dalla posizione, che e' esattamente cio' su cui RRF
    si basa: nessun secondo calcolo, nessuna seconda verita'."""
    ordinati = list(fusione(query, k))
    return [(node_id, 1.0 / (ricerca_lessicale.K_RRF + posizione))
            for posizione, node_id in enumerate(ordinati, 1)]


def candidato_da_node_id(store: GraphStore, node_id: str, score: float = 1.0) -> dict:
    """Costruisce un candidato (stessa forma di quelli restituiti da
    candidati_per_prompt) a partire da un node_id GIA' NOTO, non da
    retrieval semantico - per iniettare nella Fase 2 le fonti che il
    motore delle regole (motore_regole.py) ha verificato esistere nel
    grafo (Fase 2a), che altrimenti dipenderebbero dalla fortuna del
    retrieval per essere offerte come citabili. score=1.0 di default:
    non e' un punteggio di similarita' semantica, e' un segnale "fonte
    raccomandata con certezza dalla regola", va in cima se ordinato per
    punteggio insieme ai candidati veri del retrieval."""
    return _candidato(store, node_id, score)


def _candidato(store: GraphStore, node_id: str, score: float) -> dict:
    """Forma unica del candidato - un solo punto in cui i nomi dei campi
    del grafo compaiono, cosi' la migrazione temporale ne riapre uno solo."""
    nodo = dict(store.graph.nodes[node_id])
    tipo_nodo = nodo.get("tipo_nodo", "articolo")
    candidato = {
        "node_id": node_id,
        "tipo_nodo": tipo_nodo,
        "citazione_breve": _citazione_breve(tipo_nodo, nodo),
        "descrizione": _descrizione_per_schema(tipo_nodo, nodo),
        "score": score,
    }
    if tipo_nodo == "articolo":
        candidato["codice"] = nodo["codice"]
        candidato["numero"] = nodo["numero"]
    return candidato


# ------------------------------------------------------------------ accessori (firme gia' temporali)


def testo_di_fonte(store: GraphStore, node_id: str, data: str | None = None) -> str:
    """Testo citabile di un nodo del grafo - la base su cui la Fase 2
    taglia gli `estratti` del dossier, e quindi la base degli offset
    (fonte_id, inizio, fine) promessi dal contratto finale.

    data: criterio temporale di risoluzione della versione ("testo
    vigente al <data>"), formato ISO YYYY-MM-DD. **IGNORATO OGGI**: il
    grafo e' mono-versione, esiste un solo testo per nodo. Il parametro
    nasce qui apposta perche' alla migrazione cambi solo il CORPO di
    questa funzione, mai la sua firma ne' i chiamanti - il contratto
    prevede gia' i campi `data_vigenza`/`data_criterio_risoluzione` in
    `fase2_dossier.schema.json`, nullable finche' questo parametro resta
    inerte.

    Ritorna stringa vuota se il nodo non ha nessuno dei campi testuali
    noti: e' il chiamante a decidere se sia un'astensione o un errore,
    non questo accessore.

    # BUG-GRAFO-2: ~42% dei testi degli articoli e' contaminato da
    # marcatori di novellazione Normattiva, che finiscono percio' dentro
    # gli estratti e dentro il controllo di identita' testuale
    # `estratto.testo == testo_fonte[inizio:fine]`. Il controllo resta
    # coerente (confronta il testo del grafo con se stesso), ma
    # l'estratto mostrato all'avvocato puo' contenere rumore: segnalato
    # nel riepilogo finale, non ripulito qui (ripulirlo sposterebbe gli
    # offset rispetto al testo del nodo e romperebbe l'ancoraggio)."""
    nodo = store.graph.nodes[node_id]
    return nodo.get("testo") or nodo.get("motivazione") or nodo.get("dispositivo") or ""


#: Il testo INTEGRALE dei 244 articoli abrogati del grafo, tutti e 244.
#: Non e' un prefisso e non e' una nota dentro un testo vero: e' l'unico
#: contenuto del campo `testo`, 19 caratteri, misurato il 2026-09-02.
SEGNAPOSTO_ABROGATO = "[ARTICOLO ABROGATO]"


def motivo_non_citabile(store: GraphStore, node_id: str) -> str | None:
    """Perche' questo nodo non puo' reggere una citazione, o None se puo'.

    BUG-GRAFO-3, misurato il 2026-09-02 e diverso da come era descritto.
    I 244 articoli abrogati **non contengono la norma abrogata**: il campo
    `testo` e' lungo 19 caratteri su tutti e 244, minimo mediana e massimo,
    e vale esattamente `SEGNAPOSTO_ABROGATO`. Non c'e' nessun testo storico
    da preservare.

    Cambia due cose rispetto alla nota che `candidati_per_prompt` porta da
    sempre. La prima: l'argomento "la versione vigente all'epoca dei fatti
    e' esattamente cio' che la migrazione temporale dovra' gestire" resta
    giusto in principio e **non si applica a questi nodi**, perche' quella
    versione qui non e' scritta da nessuna parte. La seconda: il guasto non
    e' "citare una norma abrogata come se fosse in vigore" - e' che
    l'estratto ritagliato da un nodo simile riporta alla lettera
    `[ARTICOLO ABROGATO]` dentro l'atto, con i suoi offset regolari e il
    controllo di identita' testuale soddisfatto.

    Ci si arriva davvero, non in teoria: `GraphStore._build_lookup` fa
    vincere il nodo `is_main_body` sulle omonimie (ed e' giusto cosi',
    e' la risposta agli articoli 1-36 che collidono con le preleggi -
    BUG-GRAFO-4), e per 230 dei 244 abrogati il vincitore e' proprio lo
    stub. `store.trova("c.c.", "3")` restituisce oggi il segnaposto.

    **Il controllo guarda il testo, non il flag, e non e' un dettaglio.**
    I nodi con il segnaposto sono **265**, non 244: 21 hanno
    `abrogato=False` pur avendo `[ARTICOLO ABROGATO]` come unico testo
    (art. 17, 155, 342-bis, 342-ter c.c. fra gli altri). Il verso e' solo
    quello - zero nodi hanno `abrogato=True` con un testo vero - quindi
    il flag non e' rumore casuale: **sotto-dichiara**. Fidarsi di lui ne
    avrebbe lasciati passare 21.

    Non filtra il retrieval e non riscrive il grafo (vincolo 2): dice il
    motivo, e chi chiama decide. In Fase 2 quel motivo finisce in
    `fonti_scartate`, che il contratto tiene apposta per le astensioni
    esplicite - nessun campo nuovo, nessun bump di versione."""
    nodo = store.graph.nodes[node_id]
    testo = testo_di_fonte(store, node_id)
    if not testo.strip():
        return ("nodo risolto nel grafo ma senza testo citabile (nessun campo "
                "testo/motivazione/dispositivo popolato) - non produce estratti")
    if testo.strip() == SEGNAPOSTO_ABROGATO:
        return ("articolo ABROGATO e senza testo nel grafo: il campo `testo` vale "
                f"{SEGNAPOSTO_ABROGATO!r} e nient'altro, quindi ogni estratto "
                "ritagliato da qui citerebbe quel segnaposto invece della norma "
                "(BUG-GRAFO-3)")
    if nodo.get("abrogato"):
        # Abrogato ma CON testo: non e' questo il caso oggi (0 su 244), e
        # non e' compito di questa funzione decidere per l'avvocato che una
        # norma abrogata non serva mai - la versione vigente all'epoca dei
        # fatti e' spesso esattamente quella che serve. Passa, e chi rende
        # la fonte lo segnala (verify.py lo fa gia').
        return None
    return None


def citazione_breve_di_fonte(store: GraphStore, node_id: str, data: str | None = None) -> str:
    """Citazione di visualizzazione di un nodo del grafo.

    data: come in testo_di_fonte - ignorato oggi, criterio di risoluzione
    della versione dopo la migrazione (la citazione di un articolo
    versionato dira' quale versione, oggi non c'e' niente da dire).

    # BUG-GRAFO-4: 36 valori di citazione_breve non sono univoci nel
    # grafo. Questa stringa serve SOLO al rendering: usarla come chiave
    # e' un errore, l'identita' di una fonte e' node_id/fonte_id (vedi
    # CONTRATTI_DATI.md, principio 2). L'unico punto della pipeline che
    # la usa ancora come chiave e' assembla_report.risolvi_fonte, dove e'
    # marcato e dichiarato."""
    nodo = store.graph.nodes[node_id]
    return _citazione_breve(nodo.get("tipo_nodo", "articolo"), dict(nodo))


_SIGLA_CODICE = {
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
}


def _citazione_breve(tipo_nodo: str, nodo: dict) -> str:
    """Formato di citazione leggibile per tipo di nodo - diverso per
    costruzione da un articolo di codice ("art. N sigla") a un precedente
    giurisprudenziale ("Ufficio, tipo data" o "Ufficio, R.G. N/anno"), per
    rispecchiare come si cita davvero nella prassi forense.

    Nota sul formato Massima (primo giro, raffinabile): usa ufficio + tipo
    provvedimento + data, non un numero di sentenza specifico - il dato
    strutturato disponibile dalle Massime BDP non lo include separatamente
    (solo `tipo_provvedimento` e `data`), a differenza dei Provvedimenti
    integrali che hanno un vero numero di R.G.

    Resta accessibile come `_citazione_breve(tipo_nodo, nodo)` per
    assembla_report.risolvi_fonte, che confronta la citazione di OGNI
    massima durante una scansione lineare e ha gia' i dati del nodo in
    mano: passare da citazione_breve_di_fonte() la costringerebbe a un
    secondo lookup per nodo senza guadagno."""
    if tipo_nodo == "articolo":
        sigla = _SIGLA_CODICE.get(nodo["codice"], nodo["codice"])
        return f"art. {nodo['numero']} {sigla}"
    if tipo_nodo == "massima":
        ufficio = (nodo.get("ufficio") or "").title()
        tipo_prov = (nodo.get("tipo_provvedimento") or "provvedimento").lower()
        data = nodo.get("data") or ""
        return f"{ufficio}, {tipo_prov} {data}".strip()
    if tipo_nodo == "bankit_disposizione":
        return nodo.get("citazione_breve", "Disposizioni di vigilanza Banca d'Italia")
    if tipo_nodo == "provvedimento":
        # Allineato al grafo di riferimento
        # (grafo_con_provvedimenti_integrali.gpickle, 2026-08-20):
        # `numero_rg` e' ora UN SOLO campo in formato "NUM/ANNO"
        # ("100/2026", "200-1/2025") e `anno_rg` NON esiste piu'. La
        # versione precedente concatenava i due campi separati e su questo
        # grafo produceva "Ufficio, R.G. 100/2026/" - numero giusto, slash
        # spurio, anno vuoto.
        #
        # BUG-GRAFO-6 e' RISOLTO in questo grafo: numero_rg popolato 41/41,
        # collegio 41/41 (lista di {nome, ruolo}). Restava vero sul grafo
        # precedente, ora archiviato.
        #
        # Si preferisce il numero di SENTENZA quando c'e' (38/41): e' la
        # forma con cui un avvocato cita davvero un provvedimento. Il
        # numero di R.G. resta come ripiego - identifica il fascicolo, non
        # la decisione.
        ufficio = (nodo.get("ufficio") or "").title()
        numero_sentenza = (nodo.get("numero_sentenza") or "").strip()
        if numero_sentenza:
            return f"{ufficio}, sent. {numero_sentenza}".strip()
        numero_rg = (nodo.get("numero_rg") or "").strip()
        if numero_rg:
            return f"{ufficio}, R.G. {numero_rg}".strip()
        return f"{ufficio} (estremi non disponibili)".strip()
    return nodo.get("citazione_breve") or nodo.get("identificativo") or "(citazione senza formato noto)"


#: Valore di `stato_verifica` che consente la citazione automatica.
#: Qualunque altro valore (oggi solo `estremi_incerti`) e' bloccante.
STATO_VERIFICA_CITABILE = "verificato"


def estremi_provvedimento(store: GraphStore, node_id: str) -> dict:
    """Estremi identificativi di un provvedimento, per il match per numero
    e per la diagnostica.

    `numero_rg` arriva come "NUM/ANNO" e viene spezzato qui: il match per
    numero richiede ufficio + numero + anno INSIEME, perche' "130/2026" da
    solo collide fra uffici diversi - e con 39 provvedimenti su 41 dello
    stesso ufficio, una collisione fra uffici e' esattamente il caso che
    passerebbe inosservato."""
    nodo = store.graph.nodes[node_id]
    numero_sentenza = (nodo.get("numero_sentenza") or "").strip()
    numero_rg = (nodo.get("numero_rg") or "").strip()
    numero, _, anno = numero_sentenza.partition("/")
    numero_rg_num, _, anno_rg = numero_rg.partition("/")
    return {
        "ufficio": (nodo.get("ufficio") or "").strip(),
        "sentenza_numero": numero.strip() or None,
        "sentenza_anno": anno.strip() or None,
        "rg_numero": numero_rg_num.strip() or None,
        "rg_anno": anno_rg.strip() or None,
    }


def citabile_automaticamente(store: GraphStore, node_id: str) -> tuple[bool, str | None]:
    """`(True, None)` se il nodo puo' entrare negli `estratti_citabili`,
    `(False, motivo)` altrimenti.

    Controllo n. 15. `stato_verifica` e `motivazione_certa` esistono nel
    grafo dal 2026-08-20 e finora non li leggeva nessuno: un provvedimento
    con gli estremi incerti o la motivazione non certa poteva finire fra le
    fonti citabili come qualunque altro. Non sono un'etichetta
    informativa - sono la dichiarazione che quel testo non e' affidabile
    abbastanza da metterlo in un atto.

    Restano interrogabili dal RETRIEVAL: servono a far vedere all'avvocato
    che il materiale esiste. E' la citazione automatica che e' bloccata,
    non la visibilita'."""
    nodo = store.graph.nodes.get(node_id)
    if nodo is None:
        return False, f"node_id {node_id!r} assente dal grafo"

    stato = nodo.get("stato_verifica")
    if stato is not None and stato != STATO_VERIFICA_CITABILE:
        return False, (f"stato_verifica = {stato!r}: gli estremi identificativi del provvedimento "
                        "non sono stati verificati, quindi la citazione non e' difendibile in atti")

    if nodo.get("motivazione_certa") is False:
        return False, ("motivazione_certa = False: non e' certo quale parte del testo sia la "
                        "motivazione, quindi un estratto ritagliato da qui potrebbe citare come "
                        "principio di diritto una porzione che non lo e'")
    return True, None


def _descrizione_per_schema(tipo_nodo: str, nodo: dict) -> str:
    """Riga descrittiva mostrata al modello nel prompt di sistema
    (constrained_decoding.costruisci_prompt_di_sistema) - equivalente
    della rubrica per un articolo, ma per tipo di nodo (un articolo ha una
    rubrica secca, una massima ha invece un titolo/principio di diritto,
    un paragrafo Banca d'Italia il proprio titolo di sezione)."""
    if tipo_nodo == "articolo":
        return nodo.get("rubrica") or "(senza rubrica)"
    if tipo_nodo == "massima":
        return nodo.get("titolo") or "(senza titolo)"
    if tipo_nodo == "bankit_disposizione":
        return (nodo.get("testo") or "")[:150]
    if tipo_nodo == "provvedimento":
        return (nodo.get("dispositivo") or "")[:150]
    return "(senza descrizione)"


# ------------------------------------------------------------------ riformulazione (passo 1-bis, LLM)


SISTEMA_RIFORMULAZIONE = (
    "Riscrivi il TESTO DELL'ECCEZIONE che l'utente scrivera' come una breve query di ricerca "
    "per una banca dati normativa: SOLO i concetti e gli istituti giuridici "
    "chiave (5-12 parole), senza fatti del caso, numeri, nomi o narrazione. "
    "Il testo dell'eccezione e' la fonte primaria: leggilo davvero, la query deve riflettere "
    "DAVVERO cosa dice, non un'etichetta generica. "
    "Se ricevi anche un 'suggerimento di materia', trattalo come un'ipotesi di un classificatore "
    "automatico che puo' sbagliare, MAI come un fatto: usalo solo se conferma quello che leggi nel "
    "testo. Se il testo parla di tutt'altro (es. il suggerimento dice 'prescrizione' ma il testo "
    "parla di tassi usurari), ignora il suggerimento e riformula sul testo. "
    "Rispondi con la sola query, nient'altro."
)

#: Schema minimo per vincolare la riformulazione a UNA stringa breve.
#: Prima di questo (fino al 2026-08-24) la chiamata era testo libero con
#: n_predict=1024 e ragionamento attivo: misurato su 15 chiamate reali,
#: 1/15 troncata a 3911 caratteri (il blocco <think> da solo aveva
#: riempito il budget, la query vera non e' mai stata scritta) per un
#: campo che il sistema chiede in 5-12 parole. maxLength=200 lascia
#: margine oltre il caso peggiore osservato senza aprire di nuovo il
#: budget a un paragrafo.
SCHEMA_RIFORMULAZIONE = {
    "type": "object",
    "additionalProperties": False,
    "required": ["query"],
    "properties": {
        "query": {"type": "string", "minLength": 1, "maxLength": 200},
    },
}


def riformula_query_di_ricerca(base_url: str, prompt_utente: str, timeout: int = llama_server_client.TIMEOUT_DEFAULT_SECONDI,
                                seed: int | None = None) -> str:
    """Chiamata LLM che riscrive un prompt narrativo in una query di
    ricerca per il retrieval - vedi nota nel docstring del modulo sul
    perche' serve: un prompt "caso sintetico" (fatti, numeri, narrazione)
    diluisce il segnale semantico rispetto al testo tecnico e breve degli
    articoli, verificato sperimentalmente (rank 759 -> rank 4 per lo
    stesso identico articolo, stessa sostanza della domanda, solo
    riformulata).

    E' un passo 1-bis dell'ORCHESTRATORE, non della Fase 2: la Fase 2 e'
    vincolata dal contratto a "solo Python, zero LLM" e riceve la query
    gia' riformulata come dato (vedi costruisci_dossier). La query usata e
    quella originale finiscono nel dossier, cosi' un dossier resta
    riproducibile a distanza di mesi.

    Testata dal vivo la prima volta (2026-08-18, pod RunPod, Ollama, modello
    prosa potato Q4_K_M): trovato un bug reale con num_predict=64 - il
    modello e' un modello "ragionante" che scrive un blocco
    <think>...</think> prima della risposta vera, e 64 token troncavano quel
    blocco a META', prima che la query vera venisse mai scritta.

    Vincolata a schema dal 2026-08-24 (prima era testo libero, n_predict=1024,
    ragionamento attivo): sulla corsa reale di prova, 1/15 chiamate e'
    arrivata a 3911 caratteri prima di troncare - il blocco <think> da solo
    aveva riempito tutto il budget, la query vera (attesa in 5-12 parole)
    non e' mai stata scritta. Il ragionamento non ha piu' senso con un
    budget cosi' stretto: PENSIERO SPENTO qui (a differenza di Fase 1/3,
    dove n_predict e' largo abbastanza da poterselo permettere), e lo
    schema impone una sola stringa fino a 200 caratteri - margine oltre il
    caso peggiore atteso, non un paragrafo.

    n_predict alzato da 80 a 150 lo stesso giorno: non per il troncamento
    (mai avvenuto con lo schema vincolato, 0/14 su una corsa reale) ma per
    dare al modello lo spazio di LEGGERE il testo dell'eccezione e il
    suggerimento di materia insieme prima di scegliere - 80 bastava per
    scrivere la query ma non per "pensare senza pensare": con lo schema
    vincolato non c'e' un blocco <think> separato, la deliberazione (quale
    parte del testo conta, se il suggerimento e' pertinente) accade dentro
    gli stessi token della risposta. Serve margine per la decisione, non
    liberta' di ragionare a briglia sciolta - il ragionamento resta spento."""
    prompt = llama_server_client.costruisci_prompt_chatml(SISTEMA_RIFORMULAZIONE, prompt_utente, pensiero_attivo=False)
    # temperature=0.0, non 0.1 (contratto 1.23): stessa misura di
    # estrazione_atto._passata - su output vincolato da json_schema la
    # temperatura residua non aggiunge diversita' utile, spinge verso
    # cicli degeneri. Misurato su Fase 1 (10/10 esecuzioni deterministiche
    # e sbagliate a 0.1, 10/10 deterministiche e giuste a 0.0), non
    # ripetuto qui su questa chiamata specifica - stesso principio,
    # stesso motore GBNF.
    generato = llama_server_client.completa_json(
        base_url, prompt, SCHEMA_RIFORMULAZIONE, n_predict=150, temperature=0.0, timeout=timeout, seed=seed,
    )
    return generato["query"].strip()


def rispondi_con_citazioni_verificate(
    store: GraphStore, embedding_index: EmbeddingIndex,
    base_url: str, prompt_utente: str, k: int = 20,
) -> dict:
    """Orchestratore a due stadi (retrieval riformulato + generazione
    vincolata) - il pezzo che chiude il Passo 3ter dopo la scoperta del
    problema di recall: PRIMA riformula il prompt narrativo in una query di
    ricerca (riformula_query_di_ricerca), POI usa quella query - non il
    prompt originale - per il retrieval dei candidati, POI genera la
    risposta vincolata mostrando al modello il prompt utente COMPLETO
    (la riformulazione serve solo a pescare bene, non sostituisce la
    domanda vera nella generazione).

    Resta qui e NON in constrained_decoding.py: tocca lo store, quindi e'
    codice di Fase 2 per l'invariante architetturale (regola 3 di
    Claude.md). Non e' parte della pipeline di confutazione a tre fasi -
    e' l'interrogazione a domanda singola, mantenuta per il confronto
    vincolato/libero (test_confronto_vincolato_libero.py).

    Testata end-to-end dal vivo su Ollama il 2026-08-18 (18 casi del
    catalogo di allucinazioni note, 0/18 ha reso disponibile la citazione
    storicamente sbagliata tra i candidati - vedi README). Migrata a
    llama-server con quella modifica, non ancora ritestata dal vivo su
    quell'API."""
    import constrained_decoding

    query_di_ricerca = riformula_query_di_ricerca(base_url, prompt_utente)
    candidati = candidati_per_prompt(store, embedding_index, query_di_ricerca, k=k)
    risposta = constrained_decoding.genera_vincolato(base_url, prompt_utente, candidati)
    return {
        "query_di_ricerca_usata": query_di_ricerca,
        "candidati": candidati,
        "risposta": risposta,
    }


if __name__ == "__main__":
    # Smoke test locale, nessuna chiamata a llama-server - solo retrieval,
    # gira in CPU sul venv zt_legal_graph_ml.
    import constrained_decoding

    store = GraphStore.load()
    embedding_index = store.carica_embeddings()
    if embedding_index is None or embedding_index._modello() is None:
        raise SystemExit("Serve il layer semantico (venv zt_legal_graph_ml) per questo smoke test.")

    prompt_prova = (
        "Caso sintetico: un immobile è gravato da due ipoteche, la prima di "
        "100.000 euro e la seconda di 40.000 euro, iscritte da due creditori "
        "diversi. In caso di vendita all'asta a 90.000 euro, spiega in termini "
        "generali il criterio di priorità nella distribuzione del ricavato."
    )
    # Riformulazione scritta a mano per questo smoke test (non generata da
    # riformula_query_di_ricerca, che richiede llama-server, non disponibile
    # qui) - stessa sostanza del prompt narrativo sopra, zero
    # fatti/numeri/narrazione. Dimostra l'effetto della riformulazione sul
    # retrieval anche senza rete: la risposta giusta (art. 2852 c.c., "Grado
    # dell'ipoteca") passa da rank 759 (prompt narrativo) a rank 4 (query
    # riformulata) - vedi nota nel docstring del modulo.
    query_riformulata_prova = "grado ipoteca priorità tra creditori ipotecari sullo stesso immobile"

    def _e_target(c: dict) -> bool:
        return c.get("codice") == "codice_civile" and c.get("numero") == "2852"

    print("=== Retrieval col prompt narrativo originale (K=20) ===")
    candidati = candidati_per_prompt(store, embedding_index, prompt_prova, k=20)
    for c in candidati:
        print(f"  [{c['tipo_nodo']:18s}] {c['citazione_breve']:28s} score={c['score']:.3f}  {c['descrizione'][:60]}")
    print(f"  -> art. 2852 c.c. (risposta corretta) nei top-20? {'SI' if any(_e_target(c) for c in candidati) else 'NO'}")

    print("\n=== Retrieval con query riformulata (K=20) ===")
    candidati_rif = candidati_per_prompt(store, embedding_index, query_riformulata_prova, k=20)
    for c in candidati_rif[:8]:
        print(f"  [{c['tipo_nodo']:18s}] {c['citazione_breve']:28s} score={c['score']:.3f}  {c['descrizione'][:60]}")
    print(f"  -> art. 2852 c.c. (risposta corretta) nei top-20? {'SI' if any(_e_target(c) for c in candidati_rif) else 'NO'}")

    schema = constrained_decoding.costruisci_schema(candidati_rif)
    print(f"\nSchema JSON costruito, enum con {len(schema['properties']['citazioni_pertinenti']['items']['enum'])} valori ammessi (candidati + astensione).")
