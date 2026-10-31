"""
Verificatore di citazioni normative: dato (codice, numero, tema atteso), controlla
contro il grafo se la citazione esiste, se è in vigore, e se il suo contenuto reale
è in tema con quanto il modello ha affermato.

Uso diretto:
    ./.venv/Scripts/python.exe src/verify.py
lancia la demo sui casi già catalogati in Fase 1 del progetto (vedi
progetto-llm-locale-frontiera-STATO-ATTUALE-4.md) e stampa un riepilogo pass/fail.

Uso programmatico:
    from store import GraphStore
    from verify import verifica_citazione
    store = GraphStore.load()
    esito = verifica_citazione(store, "c.c.", "2946", "prescrizione ordinaria decennale")
"""

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))  # store.py resta condiviso in src/
from store import EmbeddingIndex, GraphStore, somiglianza_tema

SOGLIA_LESSICALE = 0.15  # sotto questa soglia di overlap, il tema è considerato "non in linea" (usata solo se manca l'indice semantico)

# Semantico: soglia sul RANK dell'articolo citato rispetto a tutto il corpus per
# quel tema, non sul punteggio di coseno assoluto. Tentato prima un punteggio
# assoluto (soglia 0.80) - scartato: peggiorava il risultato (9/13 invece di
# 10/13 lessicale) perché il coseno resta compresso in una fascia alta anche
# per coppie scorrelate, una soglia fissa non discrimina. Il rank invece separa
# nettamente i 13 casi noti: corrette quasi sempre rank 1-12, sbagliate rank
# 461-3929 (con un'eccezione a rank 23, istruttiva - vedi README). Soglia 20
# scelta con margine reale su entrambi i lati di quel divario osservato.
SOGLIA_RANK_SEMANTICO = 20


@dataclass
class EsitoVerifica:
    trovato: bool
    abrogato: bool | None
    citazione_breve: str | None
    rubrica: str | None
    tema_score_lessicale: float | None
    tema_score_semantico: float | None  # None se embeddings.npy non è stato costruito
    tema_rank_semantico: int | None  # posizione tra tutti gli articoli indicizzati, 1 = il più simile
    tema_in_linea: bool | None
    dettaglio: str


def verifica_citazione(
    store: GraphStore,
    codice: str,
    numero: str,
    tema_atteso: str | None = None,
    embedding_index: EmbeddingIndex | None = None,
) -> EsitoVerifica:
    art = store.trova(codice, numero)

    if art is None:
        return EsitoVerifica(
            trovato=False,
            abrogato=None,
            citazione_breve=None,
            rubrica=None,
            tema_score_lessicale=None,
            tema_score_semantico=None,
            tema_rank_semantico=None,
            tema_in_linea=None,
            dettaglio=(
                f"'{codice} {numero}' non trovato nel corpus (Codice Civile, Codice di "
                f"Procedura Civile, Codice della Crisi d'Impresa, TUB). Puo' essere una citazione "
                f"inventata, un refuso nel numero, o un riferimento a una legge fuori da questi "
                f"4 codici (non ancora coperta da questo GraphRAG)."
            ),
        )

    tema_score_lessicale = None
    tema_score_semantico = None
    tema_rank_semantico = None
    tema_in_linea = None
    if tema_atteso:
        tema_score_lessicale, _ = somiglianza_tema(tema_atteso, (art["rubrica"] or "") + " " + art["testo"])

        if embedding_index is not None:
            node_id = store._node_id_di(art)
            esito_sem = embedding_index.somiglianza_e_rank(tema_atteso, node_id)
            if esito_sem is not None:
                tema_score_semantico, tema_rank_semantico = esito_sem

        # Il rank semantico, quando disponibile, e' il segnale primario (vedi
        # nota sopra SOGLIA_RANK_SEMANTICO sul perche' rank e non punteggio
        # assoluto). Il lessicale resta sempre calcolato e riportato
        # (trasparenza, confrontabilita' con la versione precedente).
        if tema_rank_semantico is not None:
            tema_in_linea = tema_rank_semantico <= SOGLIA_RANK_SEMANTICO
        else:
            tema_in_linea = tema_score_lessicale >= SOGLIA_LESSICALE

    dettaglio_parti = [f"{art['citazione_breve']} = \"{art['rubrica']}\"."]
    if art["abrogato"]:
        dettaglio_parti.append("ATTENZIONE: articolo ABROGATO, non piu' in vigore.")
    if tema_atteso:
        punteggi = f"lessicale {tema_score_lessicale:.0%}"
        if tema_rank_semantico is not None:
            punteggi += f", rank semantico {tema_rank_semantico}/{len(embedding_index.node_ids)}"
        if tema_in_linea:
            dettaglio_parti.append(f"Tema atteso in linea con il contenuto reale ({punteggi}).")
        else:
            dettaglio_parti.append(
                f"SOSPETTO: il tema atteso ('{tema_atteso}') NON sembra in linea con il "
                f"contenuto reale dell'articolo ({punteggi})."
            )

    return EsitoVerifica(
        trovato=True,
        abrogato=art["abrogato"],
        citazione_breve=art["citazione_breve"],
        rubrica=art["rubrica"],
        tema_score_lessicale=tema_score_lessicale,
        tema_score_semantico=tema_score_semantico,
        tema_rank_semantico=tema_rank_semantico,
        tema_in_linea=tema_in_linea,
        dettaglio=" ".join(dettaglio_parti),
    )


@dataclass
class EsitoVerificaGiurisprudenza:
    trovato: bool
    verificabile: bool  # False se manca tipo/data (es. solo "Cass. n. X/anno" - le Massime BDP non hanno un numero, non cercabile)
    n_massime_trovate: int
    titoli: list[str]
    tema_in_linea: bool | None  # None se non verificabile o se manca tema_atteso
    dettaglio: str


def verifica_citazione_giurisprudenza(
    store,
    ufficio: str,
    tipo_provvedimento: str | None,
    data: str | None,
    numero_sentenza: str | None = None,
    tema_atteso: str | None = None,
) -> EsitoVerificaGiurisprudenza:
    """Verifica una citazione di giurisprudenza contro le Massime nel grafo -
    stesso principio del "doppio binario" già applicato agli articoli
    (vincola in generazione E verifica dopo), qui esteso alla giurisprudenza
    (gap dichiarato in redazione.py, chiuso da questa funzione +
    extract_citations.estrai_citazioni_giurisprudenza_da_testo)."""
    if tipo_provvedimento is None or data is None:
        return EsitoVerificaGiurisprudenza(
            trovato=False,
            verificabile=False,
            n_massime_trovate=0,
            titoli=[],
            tema_in_linea=None,
            dettaglio=(
                f"Citazione di '{ufficio}'"
                + (f", n. {numero_sentenza}" if numero_sentenza else "")
                + " non verificabile: manca tipo provvedimento e/o data. Le Massime BDP nel "
                "corpus non hanno un numero di sentenza indicizzato separatamente - senza "
                "tipo+data non c'è modo di cercarla nel grafo (non significa che sia inventata,"
                " solo che questo verificatore non può controllarla)."
            ),
        )

    massime = store.trova_massime(ufficio, tipo_provvedimento, data)
    if not massime:
        return EsitoVerificaGiurisprudenza(
            trovato=False,
            verificabile=True,
            n_massime_trovate=0,
            titoli=[],
            tema_in_linea=None,
            dettaglio=(
                f"'{ufficio}, {tipo_provvedimento} {data}' non trovata tra le Massime nel corpus "
                "- può essere una citazione inventata, un refuso nella data/ufficio, o una "
                "sentenza reale ma fuori dalle 185 Massime BDP raccolte (non è un corpus completo "
                "di tutta la giurisprudenza italiana)."
            ),
        )

    titoli = [m.get("titolo", "") for m in massime]
    tema_in_linea = None
    if tema_atteso:
        # Nessun layer semantico qui (a differenza degli articoli): confronto
        # lessicale semplice tra tema atteso e titolo+testo di OGNUNA delle
        # massime trovate - basta che UNA sia in tema (una stessa
        # citazione con più massime spesso copre principi diversi dello
        # stesso provvedimento, vedi nota in _build_lookup_massime).
        from store import somiglianza_tema
        tema_in_linea = False
        for m in massime:
            score, _ = somiglianza_tema(tema_atteso, (m.get("titolo") or "") + " " + (m.get("testo") or ""))
            if score >= SOGLIA_LESSICALE:
                tema_in_linea = True
                break

    dettaglio = f"Trovate {len(massime)} massima/e per '{ufficio}, {tipo_provvedimento} {data}': " + "; ".join(t[:80] for t in titoli)
    if tema_atteso:
        if tema_in_linea:
            dettaglio += ". Tema atteso in linea con almeno una massima trovata."
        else:
            dettaglio += f". SOSPETTO: nessuna delle massime trovate sembra in linea col tema atteso ('{tema_atteso}')."

    return EsitoVerificaGiurisprudenza(
        trovato=True,
        verificabile=True,
        n_massime_trovate=len(massime),
        titoli=titoli,
        tema_in_linea=tema_in_linea,
        dettaglio=dettaglio,
    )


# Casi dal catalogo Fase 1 (progetto-llm-locale-frontiera-STATO-ATTUALE-4.md).
# expected_ok=False -> il verificatore DEVE segnalare il problema (citazione
# inventata o fuori tema) perche' e' un caso di allucinazione gia' documentato.
# expected_ok=True -> citazione corretta, controllo positivo (il verificatore
# non deve gridare al lupo quando non c'e' nessun lupo).
CASI_FASE1 = [
    dict(
        descrizione="Priorita' tra ipoteche: citazione inventata 'art. 1224 c.c.'",
        codice="c.c.", numero="1224",
        tema_atteso="priorita' tra ipoteche sullo stesso immobile, grado ipotecario",
        expected_ok=False,
    ),
    dict(
        descrizione="Priorita' tra ipoteche: citazione inventata 'art. 1237 c.c.' (variante)",
        codice="c.c.", numero="1237",
        tema_atteso="priorita' tra ipoteche sullo stesso immobile, grado ipotecario",
        expected_ok=False,
    ),
    dict(
        descrizione="Priorita' tra ipoteche: citazione CORRETTA 'art. 2852 c.c.' (controllo positivo)",
        codice="c.c.", numero="2852",
        tema_atteso="priorita' tra ipoteche sullo stesso immobile, grado ipotecario",
        expected_ok=True,
    ),
    dict(
        descrizione="Prescrizione '5 anni' sui finanziamenti: citazione inventata 'art. 2943 c.c.'",
        codice="c.c.", numero="2943",
        tema_atteso="termine di prescrizione dei finanziamenti, durata del termine prescrizionale",
        expected_ok=False,
    ),
    dict(
        descrizione="Prescrizione ordinaria: citazione CORRETTA 'art. 2946 c.c.' (controllo positivo)",
        codice="c.c.", numero="2946",
        tema_atteso="termine di prescrizione ordinaria decennale",
        expected_ok=True,
    ),
    dict(
        descrizione="Sospensione esecuzione in procedure concorsuali: citazione inventata 'art. 119 c.c.'",
        codice="c.c.", numero="119",
        tema_atteso="sospensione dell'esecuzione forzata in caso di procedure concorsuali",
        expected_ok=False,
    ),
    dict(
        descrizione="Compensazione: citazione inventata 'art. 1287 c.c.'",
        codice="c.c.", numero="1287",
        tema_atteso="estinzione dei debiti per compensazione",
        expected_ok=False,
    ),
    dict(
        descrizione="Compensazione: citazione CORRETTA 'art. 1241 c.c.' (controllo positivo)",
        codice="c.c.", numero="1241",
        tema_atteso="estinzione dei debiti per compensazione",
        expected_ok=True,
    ),
    dict(
        descrizione="Surrogazione del fideiussore: citazione CORRETTA 'art. 1949 c.c.' (controllo positivo, gia' testato via SageMaker)",
        codice="c.c.", numero="1949",
        tema_atteso="il fideiussore che ha pagato subentra nei diritti del creditore verso il debitore",
        expected_ok=True,
    ),
    dict(
        descrizione="Regresso del fideiussore: citazione CORRETTA 'art. 1950 c.c.' (controllo positivo)",
        codice="c.c.", numero="1950",
        tema_atteso="il fideiussore che ha pagato ha regresso contro il debitore principale",
        expected_ok=True,
    ),
    dict(
        descrizione="Opposizione a decreto ingiuntivo: citazione GIUSTA ma FATTO NUMERICO sbagliato ('15 giorni' invece di 40)",
        codice="c.p.c.", numero="641",
        tema_atteso="termine per proporre opposizione a decreto ingiuntivo",
        expected_ok=True,  # la citazione e il tema sono giusti - il verificatore di citazioni
        # non cattura questo caso (e' un dato numerico dentro un articolo pertinente, non un
        # articolo sbagliato): serve un controllo dedicato, vedi nota nel report finale.
    ),
    # Casi TUB (aggiunto dopo il recepimento della Direttiva NPL 2021/2167 con
    # D.Lgs. 116/2024 - vedi progetto-llm-locale-frontiera-STATO-ATTUALE-4.md).
    dict(
        descrizione="Albo gestori crediti in sofferenza: citazione CORRETTA 'art. 114.5 TUB' (controllo positivo, normativa 2024)",
        codice="tub", numero="114.5",
        tema_atteso="albo pubblico dei gestori di crediti in sofferenza tenuto dalla Banca d'Italia",
        expected_ok=True,
    ),
    dict(
        descrizione="Albo gestori crediti in sofferenza: citazione PLAUSIBILE MA SBAGLIATA 'art. 106 TUB' (confusione con l'albo generico intermediari finanziari)",
        codice="tub", numero="106",
        tema_atteso="albo pubblico dei gestori di crediti in sofferenza tenuto dalla Banca d'Italia",
        expected_ok=False,
    ),
    # Casi sui 3 testi aggiunti nell'ampliamento del grafo (agosto 2026, vedi
    # README): stessa logica dei casi sopra, coppia corretto/plausibile-ma-sbagliato
    # scelta dentro lo stesso istituto o capo (non un confronto banale tra temi
    # lontani), per testare davvero la discriminazione del layer semantico.
    dict(
        descrizione="Annullabilita' provvedimento amministrativo: citazione CORRETTA 'art. 21-octies L. 241/1990' (controllo positivo)",
        codice="l_241_1990", numero="21-octies",
        tema_atteso="annullabilita' del provvedimento amministrativo per vizi di legittimita', violazione di legge, eccesso di potere o incompetenza",
        expected_ok=True,
    ),
    dict(
        descrizione="Annullabilita' provvedimento amministrativo: citazione PLAUSIBILE MA SBAGLIATA 'art. 21-quinquies L. 241/1990' (confusione con la revoca, istituto diverso)",
        codice="l_241_1990", numero="21-quinquies",
        tema_atteso="annullabilita' del provvedimento amministrativo per vizi di legittimita', violazione di legge, eccesso di potere o incompetenza",
        expected_ok=False,
    ),
    dict(
        descrizione="Termine per l'esecuzione forzata esattoriale: citazione CORRETTA 'art. 50 D.P.R. 602/1973' (controllo positivo)",
        codice="dpr_602_1973", numero="50",
        tema_atteso="termine entro cui l'agente della riscossione deve iniziare l'esecuzione forzata dopo la notifica della cartella di pagamento",
        expected_ok=True,
    ),
    dict(
        # FAIL atteso col layer semantico attivo (rank 11/5586, ben dentro la
        # soglia 20): stesso limite strutturale già documentato sopra
        # (SOGLIA_RANK_SEMANTICO) per istituti giuridici realmente vicini, non
        # un regressione - la cartella di pagamento (art. 25) e il termine per
        # l'esecuzione forzata (art. 50) sono fasi consecutive dello stesso
        # procedimento di riscossione, lessicalmente quasi indistinguibili.
        # Tenuto nella suite proprio perché istruttivo: mostra dove il solo
        # layer semantico NON basta e serve un controllo più mirato.
        descrizione="Termine per l'esecuzione forzata esattoriale: citazione PLAUSIBILE MA SBAGLIATA 'art. 25 D.P.R. 602/1973' (confusione con la notifica della cartella, atto diverso dal termine di esecuzione)",
        codice="dpr_602_1973", numero="25",
        tema_atteso="termine entro cui l'agente della riscossione deve iniziare l'esecuzione forzata dopo la notifica della cartella di pagamento",
        expected_ok=False,
    ),
    dict(
        descrizione="Revocatoria fallimentare: citazione CORRETTA 'art. 67 L. Fall.' (controllo positivo)",
        codice="rd_267_1942", numero="67",
        tema_atteso="azione revocatoria fallimentare degli atti a titolo oneroso, pagamenti e garanzie compiuti nel periodo sospetto",
        expected_ok=True,
    ),
    dict(
        # FAIL atteso (rank 12/5586), stesso motivo del caso D.P.R. 602/1973
        # sopra: art. 64 (atti a TITOLO GRATUITO) e art. 67 (atti a TITOLO
        # ONEROSO) sono nello stesso Capo, stesso lessico ("atti", "periodo
        # sospetto" ricorre in entrambi), ma regime di revocabilita' diverso
        # (il gratuito e' revocabile piu' facilmente, senza bisogno di provare
        # la scientia decoctionis) - un errore reale su questo punto
        # cambierebbe l'esito di una causa, non solo il numero d'articolo.
        # Caso tenuto per lo stesso motivo del precedente: il layer semantico
        # da solo non lo cattura, va saputo prima di fidarsi ciecamente.
        descrizione="Revocatoria fallimentare: citazione PLAUSIBILE MA SBAGLIATA 'art. 64 L. Fall.' (confusione con gli atti a titolo gratuito, fattispecie diversa)",
        codice="rd_267_1942", numero="64",
        tema_atteso="azione revocatoria fallimentare degli atti a titolo oneroso, pagamenti e garanzie compiuti nel periodo sospetto",
        expected_ok=False,
    ),
    # Casi sui 3 testi aggiunti nel secondo giro di ampliamento (agosto 2026):
    # L. 689/1981 e Costituzione, emersi dalle Massime BDP non ancora collegate.
    dict(
        descrizione="Opposizione a ordinanza-ingiunzione: citazione CORRETTA 'art. 22 L. 689/1981' (controllo positivo)",
        codice="l_689_1981", numero="22",
        tema_atteso="termine e modalita' per proporre opposizione all'ordinanza-ingiunzione dinanzi al giudice",
        expected_ok=True,
    ),
    dict(
        descrizione="Opposizione a ordinanza-ingiunzione: citazione PLAUSIBILE MA SBAGLIATA 'art. 18 L. 689/1981' (confusione con l'adozione dell'ordinanza-ingiunzione da parte dell'autorita', fase precedente e diversa dall'opposizione)",
        codice="l_689_1981", numero="18",
        tema_atteso="termine e modalita' per proporre opposizione all'ordinanza-ingiunzione dinanzi al giudice",
        expected_ok=False,
    ),
    dict(
        descrizione="Giusto processo: citazione CORRETTA 'art. 111 Cost.' (controllo positivo)",
        codice="costituzione", numero="111",
        tema_atteso="principio del giusto processo, contraddittorio tra le parti e ragionevole durata del processo",
        expected_ok=True,
    ),
    dict(
        descrizione="Giusto processo: citazione PLAUSIBILE MA SBAGLIATA 'art. 24 Cost.' (confusione con il diritto di azione e difesa in giudizio, istituto diverso)",
        codice="costituzione", numero="24",
        tema_atteso="principio del giusto processo, contraddittorio tra le parti e ragionevole durata del processo",
        expected_ok=False,
    ),
]


def esegui_demo():
    print("Carico il grafo...")
    store = GraphStore.load()
    print(f"Grafo caricato: {store.graph.number_of_nodes()} nodi, {store.graph.number_of_edges()} archi.\n")

    embedding_index = store.carica_embeddings()
    if embedding_index is None:
        print("ATTENZIONE: embeddings.npy non trovato - demo in modalita' solo lessicale.")
        print("Esegui prima ~/venvs/zt_legal_graph_ml/Scripts/python.exe src/build_embeddings.py\n")
    elif embedding_index._modello() is None:
        print(
            f"Indice semantico trovato ({len(embedding_index.node_ids)} articoli) ma "
            "sentence_transformers non e' installato in questo interprete - demo in "
            "modalita' solo lessicale. Rilancia con "
            "~/venvs/zt_legal_graph_ml/Scripts/python.exe per il confronto semantico.\n"
        )
        embedding_index = None
    else:
        print(f"Indice semantico caricato: {len(embedding_index.node_ids)} articoli embedded.\n")

    n_pass = 0
    for caso in CASI_FASE1:
        esito = verifica_citazione(store, caso["codice"], caso["numero"], caso["tema_atteso"], embedding_index)

        if not esito.trovato:
            rilevato_problema = True  # non trovato = comunque un problema rilevato
        elif esito.tema_in_linea is not None:
            rilevato_problema = not esito.tema_in_linea
        else:
            rilevato_problema = False

        # expected_ok=False vuol dire "questo e' un caso di allucinazione nota, il
        # verificatore deve rilevare un problema"; expected_ok=True vuol dire il
        # contrario (controllo positivo, il verificatore non deve falsi allarmi).
        atteso_problema = not caso["expected_ok"]
        esito_test = "PASS" if rilevato_problema == atteso_problema else "FAIL"
        n_pass += esito_test == "PASS"

        print(f"[{esito_test}] {caso['descrizione']}")
        print(f"       {esito.dettaglio}")
        print()

    print(f"Risultato: {n_pass}/{len(CASI_FASE1)} casi corretti.")


if __name__ == "__main__":
    esegui_demo()
