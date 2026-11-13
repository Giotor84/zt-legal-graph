"""
Collega extract_citations.py (trova citazioni in un testo libero) e verify.py
(verifica una citazione contro il grafo) in un'unica funzione: dato il testo
di una risposta generata dal modello, estrae tutte le citazioni normative che
contiene e le verifica una per una, usando la frase che le contiene come tema
atteso (la stessa cosa che farebbe un revisore umano).

Questo è il pezzo che chiude il circuito a doppio binario: fino ad ora il
modello (Ollama su SageMaker) e il verificatore (verify.py) esistevano come
componenti separati, mai collegati a una risposta reale del modello.

Uso diretto (demo su generazioni reali già salvate, non richiede l'istanza
SageMaker attiva):
    ~/venvs/zt_legal_graph_ml/Scripts/python.exe src/pipeline.py

Uso live (quando l'istanza SageMaker è attiva, dentro il notebook Studio):
    from pipeline import verifica_risposta
    from store import GraphStore
    store = GraphStore.load()
    embedding_index = store.carica_embeddings()
    risposta_modello = ...  # output di requests.post(OLLAMA_HOST_URL + "/api/generate", ...)
    report = verifica_risposta(risposta_modello, store, embedding_index)
"""

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
# store.py resta condiviso in src/ (usato anche dagli script di costruzione
# del corpus, non solo da questa pipeline) - non spostato qui insieme al
# resto quando la pipeline e' stata riorganizzata in pipeline_confutazione/.
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from extract_citations import (
    CitazioneGiurisprudenzaTrovata,
    CitazioneTrovata,
    estrai_citazioni_da_testo,
    estrai_citazioni_giurisprudenza_da_testo,
)
from store import EmbeddingIndex, GraphStore
from verify import EsitoVerifica, EsitoVerificaGiurisprudenza, verifica_citazione, verifica_citazione_giurisprudenza


@dataclass
class RigaReport:
    citazione: CitazioneTrovata
    esito: EsitoVerifica


@dataclass
class RigaReportGiurisprudenza:
    citazione: CitazioneGiurisprudenzaTrovata
    esito: EsitoVerificaGiurisprudenza


def verifica_risposta(
    testo: str,
    store: GraphStore,
    embedding_index: EmbeddingIndex | None = None,
) -> list[RigaReport]:
    citazioni = estrai_citazioni_da_testo(testo)
    righe = []
    for c in citazioni:
        esito = verifica_citazione(store, c.codice, c.numero, c.contesto, embedding_index)
        righe.append(RigaReport(citazione=c, esito=esito))
    return righe


def verifica_risposta_giurisprudenza(testo: str, store: GraphStore) -> list[RigaReportGiurisprudenza]:
    """Come verifica_risposta(), ma per citazioni di giurisprudenza - chiude
    il gap dichiarato in redazione.py (nessun controllo testuale sulla
    giurisprudenza generata, solo il vincolo dello schema in generazione).
    Funzione separata, non fusa con verifica_risposta(): formati ed esiti
    diversi (EsitoVerificaGiurisprudenza ha n_massime_trovate/titoli, non
    ha rank semantico), un chiamante che vuole entrambe le chiama entrambe
    (vedi redazione.py)."""
    citazioni = estrai_citazioni_giurisprudenza_da_testo(testo)
    righe = []
    for c in citazioni:
        esito = verifica_citazione_giurisprudenza(store, c.ufficio, c.tipo_provvedimento, c.data, c.numero_sentenza, c.contesto)
        righe.append(RigaReportGiurisprudenza(citazione=c, esito=esito))
    return righe


def estrai_da_atto_controparte(
    store: GraphStore, embedding_index: EmbeddingIndex | None, testo_controparte: str
) -> tuple[list[RigaReport], list[RigaReportGiurisprudenza]]:
    """Legge le citazioni (normative E di giurisprudenza) fatte da
    controparte in un atto e le verifica una per una - utile di per sé,
    indipendentemente dalla redazione di una replica: sapere se le
    citazioni di controparte sono corrette o deboli è già informazione
    strategica.

    Spostata qui da redazione.py il 2026-08-20 (split retrieval/
    generazione vincolata): richiede lo store, e la Fase 3 non deve avere
    alcun percorso di import verso il grafo. Di questo modulo era gia' una
    composizione di due sole funzioni, quindi qui non aggiunge una
    dipendenza nuova - la toglie a redazione.py.

    Un atto di controparte reale userà probabilmente citazioni di
    giurisprudenza nel formato forense standard ("Cass. n. X/anno", senza
    data) più spesso del formato ufficio+tipo+data che il nostro modello
    produce - queste risulteranno "non verificabili" (le Massime BDP non
    hanno un numero di sentenza indicizzato), non silenziosamente perse:
    vedi EsitoVerificaGiurisprudenza.verificabile.

    Scope dichiarato di questo primo giro: solo le citazioni, non
    l'argomento di controparte."""
    return (
        verifica_risposta(testo_controparte, store, embedding_index),
        verifica_risposta_giurisprudenza(testo_controparte, store),
    )


def stampa_report(righe: list[RigaReport]) -> None:
    if not righe:
        print("Nessuna citazione normativa trovata nel testo.")
        return

    for r in righe:
        c, e = r.citazione, r.esito
        bandiera = "[OK]" if (e.trovato and e.tema_in_linea in (True, None)) else "[SOSPETTO]"
        nota_codice = " (codice non esplicito nel testo, assunto Codice Civile)" if c.codice_inferito else ""
        print(f"{bandiera} \"art. {c.numero}\" ({c.codice}){nota_codice}")
        print(f"   contesto: {c.contesto[:150]}")
        print(f"   {e.dettaglio}")
        print()


def stampa_report_giurisprudenza(righe: list[RigaReportGiurisprudenza]) -> None:
    if not righe:
        print("Nessuna citazione di giurisprudenza trovata nel testo.")
        return

    for r in righe:
        c, e = r.citazione, r.esito
        if not e.verificabile:
            bandiera = "[NON VERIFICABILE]"
        elif e.trovato and e.tema_in_linea in (True, None):
            bandiera = "[OK]"
        else:
            bandiera = "[SOSPETTO]"
        print(f"{bandiera} \"{c.ufficio}, {c.tipo_provvedimento or '?'} {c.data or c.numero_sentenza or '?'}\"")
        print(f"   contesto: {c.contesto[:150]}")
        print(f"   {e.dettaglio}")
        print()


if __name__ == "__main__":
    # Demo su generazioni REALI già salvate (fase1_risultati_*.json) - non
    # casi costruiti a mano come CASI_FASE1 in verify.py, proprio le frasi
    # generate dal modello nei test già fatti. Trovate ispezionando i file:
    # tutte le citazioni esplicite trovate in fase1_risultati_completo.json e
    # fase1_risultati_pruned_quantized.json (dominio diritto_italiano) erano
    # sbagliate - dato onesto, non selezionato per far bella figura. L'unico
    # controllo positivo qui sotto è costruito (non da una generazione reale),
    # segnalato esplicitamente.
    ESEMPI = [
        (
            "REALE (fase1_risultati_completo.json)",
            "### 1. **Sospensione dell'esecuzione (art. 119 c.c.)**\n"
            "Quando è aperta una procedura concorsuale (ad esempio, un fallimento), "
            "l'esecuzione individuale nei confronti del debitore viene sospesa.",
        ),
        (
            "REALE (fase1_risultati_completo.json)",
            "Sta facendo valere un diritto di compensazione previsto dal Codice Civile "
            "italiano (art. 1287 e ss. del Codice Civile), che consente al debitore di "
            "far sì che il proprio debito venga estinto mediante il pagamento di un "
            "credito che gli spetta verso lo stesso creditore.",
        ),
        (
            "REALE (fase1_risultati_pruned_quantized.json)",
            "La cessione del credito non produce effetti nei confronti del debitore se "
            "non viene comunicata. Secondo il codice civile italiano (art. 1274 c.c.), "
            "il cessionario (nuovo creditore) non può esigere il pagamento fino alla notifica.",
        ),
        (
            "REALE (fase1_risultati_pruned_quantized.json)",
            "Un pagamento parziale effettuato spontaneamente dal debitore interrompe il "
            "periodo di prescrizione per il credito residuo. Questo è un principio "
            "consolidato dal Codice Civile italiano (art. 2946 c.c.).",
        ),
        (
            "COSTRUITO per controllo positivo, non da una generazione reale",
            "Il fideiussore che ha pagato il debito è surrogato nei diritti che il "
            "creditore aveva contro il debitore principale, ai sensi dell'art. 1949 c.c.",
        ),
    ]

    print("Carico il grafo...")
    store = GraphStore.load()
    embedding_index = store.carica_embeddings()
    if embedding_index is not None and embedding_index._modello() is None:
        print("sentence_transformers non disponibile in questo interprete - solo lessicale.\n")
        embedding_index = None
    elif embedding_index is not None:
        print("Layer semantico attivo.\n")

    for fonte, testo in ESEMPI:
        print(f"===== {fonte} =====")
        print(f'"{testo[:100]}..."\n')
        righe = verifica_risposta(testo, store, embedding_index)
        stampa_report(righe)
        print()
