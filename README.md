# zt-legal-graph

[![tests](https://github.com/Giotor84/zt-legal-graph/actions/workflows/tests.yml/badge.svg)](https://github.com/Giotor84/zt-legal-graph/actions/workflows/tests.yml) [![license](https://img.shields.io/badge/license-source--available-orange)](LICENSE.md) ![python](https://img.shields.io/badge/python-3.12-blue)

**Comparse difensive per il creditore, 100% in locale, con ogni affermazione ancorata alla fonte.**

*English summary: a local-only (llama.cpp + GGUF) pipeline that reads the debtor's filing in an Italian civil case
(objection to an injunction, summons, writ), extracts the objections with grammar-constrained generation,
builds a dossier from a graph of Italian statutes as the only citable source, and drafts the reply. Every claim in
the output is anchored to `(source_id, start, end)` computed by Python, never by the model.*

## Cosa fa

Tre fasi, separate per contratto:

| fase | cosa | moduli principali |
|---|---|---|
| **1 · estrazione** | segmenta l'atto avversario, estrae le eccezioni con generazione vincolata da grammatiche GBNF, ancora ogni citazione al testo (rapidfuzz, soglie 0,95/0,80), recupera le estrazioni troncate, unisce le passate | `segmenta_atto`, `estrazione_atto`, `estrazione_eccezioni`, `localizza`, `unisci_estrazioni`, `validazione` |
| **2 · dossier** | regole di dominio (legittimazione del cessionario, vizi della fideiussione, anomalie contabili, competenza e rito), retrieval ibrido sul grafo normativo, citabilità con motivo esplicito quando una fonte non è citabile | `motore_regole`, `retrieval`, `citabilita`, `famiglie_grafo`, `ricerca_lessicale` |
| **3 · redazione** | bozza vincolata dallo schema, rendering; **nessun import verso grafo o store** (invariante architetturale) | `redazione`, `rendering`, `constrained_decoding` |

Il **grafo normativo** si costruisce da Normattiva (formato Akoma Ntoso), con alberatura dei codici, rinvii fra
articoli, versioni e una promozione a 8 controlli che boccia un grafo incoerente prima che vada in uso
(`scarica_normattiva`, `parser`, `build_graph`, `references`, `alberatura_codici`, `innesta_articoli`,
`promuovi_grafo`, `store`).

## Regole di progetto (vincolanti)

1. `contratti/` è la specifica: schemi JSON e grammatiche GBNF di ogni fase. Se il codice diverge, sbaglia il codice.
2. Ogni affermazione dell'output è ancorata a `(fonte_id, inizio, fine)` calcolata da Python. Mai dal modello.
3. La Fase 3 non importa né lo store né il grafo.
4. Nessun commit senza test verdi; tipizzazione completa.
5. Nessuna API esterna: modello locale con `llama-server` (llama.cpp mainline).

## Cosa **non** c'è in questo repository

- **Nessun dato**: né il grafo costruito, né sentenze, massime o atti di parte. Il grafo si ricostruisce da
  Normattiva con `src/scarica_normattiva.py` e `src/build_graph.py`.
- **Nessun orchestratore end-to-end**: nella versione di produzione la catena completa è legata a moduli
  di gestione del portafoglio e dei rintracci che restano privati. Qui ci sono le fasi come componenti,
  ciascuna con i suoi test.
- Nessuna analisi dei singoli magistrati.

## Avvio

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt     # versioni bloccate: cambiano gli embedding e quindi le soglie
.venv\Scripts\python -m pytest pipeline_confutazione src -q
```

Solo per i test (come la CI, senza torch): `pip install -r requirements-test.txt`.

Risultato sulla copia di pubblicazione: **473 test passati, 9 saltati** (i saltati richiedono un atto reale di
prova o il grafo costruito, che non sono inclusi).

Demo in un decimo di secondo, senza modello né grafo: ancoraggio delle citazioni con offset calcolati da Python e
riconoscimento dei conteggi di parte su un atto inventato.

```bash
python examples/demo_senza_modello.py
```

Per le fasi con il modello serve `llama-server` in ascolto su `127.0.0.1` con un GGUF (es. Qwen3-14B Q4_K_M) e il
grafo in `data/graph/`.

## Documentazione

`contratti/CONTRATTI_DATI.md` descrive ogni contratto, le soglie e le misure che le hanno fissate (in italiano).
Gli esiti citati come "atto reale di prova" vengono da un atto vero usato in sviluppo, che non è pubblicato.

## Limiti noti

- Diritto civile italiano, lato creditore: non è un sistema generico di RAG.
- Il grafo normativo va ricostruito da Normattiva prima dell'uso; le fasi con il modello richiedono `llama-server` e un GGUF.
- Nessun orchestratore end-to-end (vedi sopra): le fasi sono componenti con i loro test.
- Le soglie sono state misurate su un atto reale di prova non pubblicato: vanno ricontrollate sui propri atti.

## Progetti collegati

- [zt-batch-reader](https://github.com/Giotor84/zt-batch-reader) — open-core closed document extraction via calibrated first-token logprobs & deterministic rules (commercial 284B MoE add-on available)
- [zt-anchor](https://github.com/Giotor84/zt-anchor) — anchoring, abstention, blind-window backtest and frozen-holdout evaluation for document AI
- [zt-legal-analysis-core](https://github.com/Giotor84/zt-legal-analysis-core) — OCR cascade and rolling synthesis for case files larger than the context
- [zt-airgap](https://github.com/Giotor84/zt-airgap) — LLM pipelines without internet (SageMaker + Bedrock)
- [zt-memory](https://github.com/Giotor84/zt-memory) — local code-context engine + MCP server for air-gapped workflows
- Tutti i progetti: [github.com/Giotor84](https://github.com/Giotor84)

## Licenza (source-available)

Codice **source-available** (non open source OSI): gratuito per persone, studi e aziende sotto 100 persone e
1 M USD di ricavi annui con la [PolyForm Small Business License 1.0.0](LICENSE.md); per organizzazioni più
grandi (banche, servicer, grandi studi) o usi fuori soglia serve una [licenza commerciale](COMMERCIAL.md).
Contributi esterni soggetti a [CLA.md](CLA.md).

*Questo software produce bozze per professionisti del diritto: non sostituisce il giudizio dell'avvocato.*
