"""I profili di famiglia, ricavati dal grafo invece che scritti a mano.

## Perche' esiste

Fino al contratto 1.27 due decisioni giuridiche vivevano in tabelle scritte
a mano dentro il codice:

- `classificazione._KEYWORD_PER_FAMIGLIA`: nove famiglie decise a priori e
  riconosciute per sottostringa sul testo dell'eccezione. Sul batch reale
  (45 atti, 983 eccezioni) lasciava **442 eccezioni su 983 - il 45% -
  senza famiglia**;
- `ordine_motivi.RANGO_PER_FAMIGLIA`: la collocazione di ciascuna famiglia
  nel rito o nel merito, cioe' l'ordine dell'atto.

Il grafo quelle informazioni le ha gia', e piu' precise di chi le ha
scritte a mano:

- **le famiglie** sono le comunita' di co-citazione fra articoli
  (`famiglie_da_cocitazione.py`, misurate su 775 provvedimenti): due
  articoli che i giudici citano nella stessa motivazione appartengono allo
  stesso discorso giuridico, e nessuno gliel'ha detto;
- **il rango processuale** e' l'alberatura dell'articolo: un articolo del
  codice di rito e' rito, il capo della prescrizione e' preliminare di
  merito, il resto e' merito. Non e' un'opinione, e' dove sta scritto;
- **la natura del rapporto** e' la sezione del c.c.: "Dell'apertura di
  credito bancario", "Delle operazioni bancarie in conto corrente", "Del
  mutuo", "Della fideiussione". Il codice civile nomina gli istituti, non
  serve indovinarli da un modello.

Questo modulo li mette insieme in un artefatto statico,
`data/famiglie/profili_famiglia.json`, che il runtime legge senza mai
aprire il grafo - cosi' `--solo-fase1 --batch` continua a girare dove il
grafo non c'e', che e' l'invariante su cui poggia il golden set.

## Cosa NON fa

Non nomina le famiglie e non ne fissa i confini: le comunita' sono
candidate, il nome e la regola restano giudizio giuridico (STATO_PROGETTO
§7.5). Il profilo porta con se' il **vocabolario del grafo** - `materia` e
`parola_chiave` delle massime che citano quegli articoli - proprio perche'
l'etichetta venga da li' e non da questo file.

Non tocca il grafo, non tocca `motore_regole.py`, non chiama nessun
modello. Sola lettura.

Uso:
    python src/profili_famiglia.py --grafo data/graph/grafo.gpickle
"""

from __future__ import annotations

import argparse
import collections
import json
import pickle
import sys
from pathlib import Path

from popolazioni_archi import e_citazione_in_motivazione  # BUG-GRAFO-5

sys.path.insert(0, str(Path(__file__).parent))
from famiglie_da_cocitazione import (SOGLIA_COPPIA, articoli_per_provvedimento,
                                     comunita, grafo_cocitazione)

ROOT = Path(__file__).parent.parent
GRAFO_DEFAULT = ROOT / "data" / "graph" / "grafo.gpickle"
USCITA_DEFAULT = ROOT / "data" / "famiglie" / "profili_famiglia.json"

#: I ranghi processuali, nell'ordine in cui vanno esposti in un atto.
RITO = "rito"
PRELIMINARE = "preliminare_di_merito"
MERITO = "merito"
NON_CLASSIFICATO = "non_classificato"

#: Il capo del c.c. che contiene la prescrizione. Non e' una parola chiave
#: sul testo: e' il capo dell'alberatura, letto da Wikisource e scritto sui
#: nodi da arricchisci_alberatura.py.
_CAPO_PRESCRIZIONE = "Della prescrizione"


def rango_di_articolo(dati: dict) -> str:
    """Il rango processuale di UN articolo, dalla sua collocazione.

    Regola, in tre righe e tutte verificabili sul nodo:

    - codice di procedura civile -> `rito`. E' il codice del processo: un
      articolo che sta li' disciplina come si sta in giudizio, non chi ha
      ragione;
    - capo della prescrizione (c.c. Libro VI) -> `preliminare_di_merito`.
      La prescrizione si decide prima del merito e lo assorbe;
    - tutto il resto (c.c., TUB, leggi speciali) -> `merito`.

    Un articolo senza `codice` non e' un articolo e non da' rango.
    """
    codice = dati.get("codice")
    if not codice:
        return NON_CLASSIFICATO
    if codice == "codice_procedura_civile":
        return RITO
    alberatura = dati.get("alberatura") or {}
    if _CAPO_PRESCRIZIONE in (alberatura.get("capo") or ""):
        return PRELIMINARE
    return MERITO


def istituto_di_articolo(dati: dict) -> str | None:
    """L'istituto nominato dall'alberatura: la sezione se c'e', altrimenti
    il capo. E' il testo del codice civile, non una nostra etichetta -
    "Sezione III: Dell'apertura di credito bancario" lo dice il c.c.

    None per gli articoli senza alberatura (TUB e leggi speciali, che su
    Wikisource non ci sono - vedi STATO_PROGETTO): l'assenza e' piu' onesta
    di un valore inventato.
    """
    alberatura = dati.get("alberatura") or {}
    etichetta = alberatura.get("sezione") or alberatura.get("capo")
    if not etichetta:
        return None
    # "Capo XXII: Della fideiussione" -> "Della fideiussione"
    return etichetta.split(":", 1)[-1].strip()


def chiave(dati: dict) -> str:
    """L'identita' di un articolo indipendente dal node_id, che cambia
    formato fra i codici: `codice::numero`."""
    return f"{dati.get('codice')}::{dati.get('numero')}"


def vocabolario_delle_massime(grafo, articoli: set[str]) -> dict:
    """`materia` e `parola_chiave` delle massime che citano questi
    articoli. E' il vocabolario del CORPUS, l'unico legittimato a dare un
    nome alla comunita': se le massime che citano 1957 e 1938 parlano di
    fideiussione, quella comunita' si chiama cosi' perche' lo dice il
    corpus, non perche' lo abbiamo deciso noi."""
    materie: collections.Counter = collections.Counter()
    chiavi: collections.Counter = collections.Counter()
    for origine, destinazione in grafo.edges():
        if destinazione not in articoli:
            continue
        dati = grafo.nodes[origine]
        if dati.get("tipo_nodo") != "massima":
            continue
        if dati.get("materia"):
            materie[dati["materia"]] += 1
        for parola in dati.get("parola_chiave") or []:
            chiavi[parola] += 1
    return {"materia": materie.most_common(3), "parola_chiave": chiavi.most_common(8)}


#: Quante parole distintive tenere per comunita'. Non e' una manopola per
#: ottenere il risultato voluto: e' un taglio sulla coda, e le prime sono
#: quelle che il log-odds separa nettamente.
PAROLE_PER_COMUNITA = 40

#: Sotto questa frequenza documentale globale una parola e' un accidente
#: del singolo provvedimento (un nome proprio, un refuso dell'OCR), non
#: lessico del dominio.
MINIMO_DOCUMENTI = 5

#: Quota MINIMA di motivazioni della comunita' in cui la parola deve
#: comparire. Senza questa soglia il log-odds premia le parole rarissime e
#: concentrate: la prima misura (senza) restituiva "corrispondendo",
#: "parrebbe", "anagrafica" - idiosincrasie di singole sentenze, non
#: lessico di una famiglia. Con la soglia restituisce i termini che quella
#: comunita' usa DAVVERO e le altre no.
QUOTA_MINIMA_DENTRO = 0.25

_PAROLA = __import__("re").compile(r"[a-zà-ÿ]{4,}")


def _parole(testo: str) -> set[str]:
    """Le parole di un testo, in forma confrontabile. Insieme e non lista:
    conta se una parola c'e', non quante volte - una motivazione lunga
    ripete gli stessi termini e peserebbe piu' di una corta senza dire
    nulla di piu'."""
    return set(_PAROLA.findall((testo or "").lower()))


def lessico_per_comunita(grafo, per_provvedimento: dict[str, set[str]],
                          membri_per_comunita: list[set[str]]) -> list[list[tuple[str, float]]]:
    """Le parole con cui i giudici scrivono di ciascuna comunita'.

    Sostituisce le parole chiave scritte a mano in
    `classificazione._KEYWORD_PER_FAMIGLIA`: qui non le sceglie nessuno -
    si prendono le motivazioni dei provvedimenti che citano almeno DUE
    articoli della comunita' (uno solo puo' essere un richiamo di
    passaggio) e si misura quali parole vi compaiono piu' che nel resto del
    corpus, con un log-odds smorzato.

    E' la stessa idea del `contrasto_log_odds` gia' usato per le eccezioni
    estratte dai provvedimenti: il corpus dice il proprio lessico, noi non
    lo indoviniamo.
    """
    import math

    testi = {}
    for node_id in per_provvedimento:
        dati = grafo.nodes[node_id]
        testi[node_id] = _parole(dati.get("motivazione") or "")

    documenti_globali: collections.Counter = collections.Counter()
    for parole in testi.values():
        documenti_globali.update(parole)
    totale = max(1, len(testi))

    lessici = []
    for membri in membri_per_comunita:
        dentro = [n for n, citati in per_provvedimento.items() if len(citati & membri) >= 2]
        if not dentro:
            lessici.append([])
            continue
        locali: collections.Counter = collections.Counter()
        for node_id in dentro:
            locali.update(testi.get(node_id, ()))

        punteggi = []
        for parola, quante in locali.items():
            if documenti_globali[parola] < MINIMO_DOCUMENTI:
                continue
            if quante < QUOTA_MINIMA_DENTRO * len(dentro):
                continue
            dentro_p = (quante + 0.5) / (len(dentro) + 1)
            fuori = documenti_globali[parola] - quante
            fuori_p = (fuori + 0.5) / (totale - len(dentro) + 1)
            punteggi.append((parola, math.log(dentro_p / fuori_p)))
        punteggi.sort(key=lambda x: -x[1])
        lessici.append([(p, round(v, 3)) for p, v in punteggi[:PAROLE_PER_COMUNITA] if v > 0])
    return lessici


#: Quota che il rango piu' frequente deve raggiungere perche' la comunita'
#: ne abbia uno. Sotto, la comunita' e' mista - come la 2, che tiene
#: insieme la prescrizione e la procedura d'appello - e dire che e' "di
#: merito" o "di rito" sarebbe una scelta, non una lettura.
QUOTA_RANGO_DOMINANTE = 0.6


def _rango_dominante(articoli: list[dict]) -> str:
    """Il rango della comunita', se ne ha uno. Serve alle eccezioni che non
    citano nessuna norma: la comunita' la trova il lessico, e da li' si
    risale al rango senza dover indovinare."""
    conteggi = collections.Counter(a["rango"] for a in articoli)
    primo, quante = conteggi.most_common(1)[0]
    if quante >= QUOTA_RANGO_DOMINANTE * len(articoli):
        return primo
    return NON_CLASSIFICATO


def sha256_file(percorso: Path) -> str:
    """sha256 di un file, a blocchi: il grafo pesa 40 MB e non va letto
    tutto in memoria per un'impronta."""
    import hashlib

    impronta = hashlib.sha256()
    with open(percorso, "rb") as f:
        for blocco in iter(lambda: f.read(1 << 20), b""):
            impronta.update(blocco)
    return impronta.hexdigest()


#: Quota degli articoli "di comunita'" che devono stare nella stessa
#: comunita' perche' un provvedimento possa ETICHETTARE i propri segmenti.
#: Stessa soglia del golden set (src/golden_dal_grafo.py), e per la stessa
#: ragione: sotto, la sentenza tratta piu' discorsi e l'etichetta sarebbe
#: una media di cose diverse.
SOGLIA_PUREZZA = 0.6
MINIMO_ARTICOLI_PUREZZA = 2


def etichette_dei_segmenti(grafo, comunita_per_articolo: dict[str, int],
                            indice_segmenti: list[dict] | None) -> dict[str, int]:
    """Per ogni segmento di motivazione indicizzato, la comunita' del suo
    provvedimento - quando quel provvedimento e' PURO.

    E' cio' che permette alla classificazione di usare l'assonanza
    vettoriale senza ricalcolare niente: gli embedding dei segmenti
    esistono gia' (`embeddings_segmenti_provvedimenti.npy`), qui si
    aggiunge solo l'etichetta. La chiave e' l'indice di riga nella
    matrice, in forma di stringa perche' JSON non ha chiavi intere.

    Misurato (965 eccezioni del golden set, ESCLUSO il provvedimento
    d'origine dai vicini): il voto dei 5 vicini con quorum 4 da' precisione
    0,646 su copertura 0,345, contro 0,523 su 0,602 del lessico. Nessuno
    dei due domina - ma **dove concordano la precisione e' 0,804**, ed e'
    quello il motivo per cui questo strato esiste.
    """
    if not indice_segmenti:
        return {}
    articoli_per_prov: dict[str, set[str]] = collections.defaultdict(set)
    for origine, destinazione, dati in grafo.edges(data=True):
        if not e_citazione_in_motivazione(dati):
            continue
        nodo = grafo.nodes[destinazione]
        chiave = f"{nodo.get('codice')}::{nodo.get('numero')}"
        if chiave in comunita_per_articolo:
            articoli_per_prov[origine].add(chiave)

    puri: dict[str, int] = {}
    for provvedimento, articoli in articoli_per_prov.items():
        if len(articoli) < MINIMO_ARTICOLI_PUREZZA:
            continue
        conteggi = collections.Counter(comunita_per_articolo[a] for a in articoli)
        dominante, quante = conteggi.most_common(1)[0]
        if quante / len(articoli) >= SOGLIA_PUREZZA:
            puri[provvedimento] = dominante

    return {str(i): puri[voce["node_id"]]
            for i, voce in enumerate(indice_segmenti) if voce["node_id"] in puri}


def costruisci_profili(grafo, soglia: int = SOGLIA_COPPIA,
                        sha256_grafo: str | None = None,
                        indice_segmenti: list[dict] | None = None) -> dict:
    """L'artefatto completo: le comunita' con i loro articoli, il rango e
    l'istituto di ciascun articolo, e il vocabolario del corpus."""
    per_provvedimento = articoli_per_provvedimento(grafo)
    cocitazione = grafo_cocitazione(per_provvedimento, soglia)
    comunita_trovate = comunita(cocitazione)

    articoli: dict[str, dict] = {}
    for node_id, dati in grafo.nodes(data=True):
        if not dati.get("codice"):
            continue
        articoli[node_id] = {
            "chiave": chiave(dati),
            "codice": dati["codice"],
            "numero": str(dati.get("numero")),
            "rango": rango_di_articolo(dati),
            "istituto": istituto_di_articolo(dati),
        }

    ordinate = sorted(comunita_trovate, key=len, reverse=True)
    lessici = lessico_per_comunita(grafo, per_provvedimento, ordinate)

    profili = []
    comunita_per_articolo: dict[str, int] = {}
    for indice, membri in enumerate(ordinate):
        dentro = [articoli[n] for n in membri if n in articoli]
        if not dentro:
            continue
        for voce in dentro:
            comunita_per_articolo[voce["chiave"]] = indice
        quanti_provvedimenti = sum(
            1 for citati in per_provvedimento.values() if len(citati & membri) >= 2)
        profili.append({
            "comunita": indice,
            "n_articoli": len(dentro),
            "provvedimenti_che_la_usano": quanti_provvedimenti,
            "articoli": sorted(a["chiave"] for a in dentro),
            "ranghi": dict(collections.Counter(a["rango"] for a in dentro)),
            "rango_dominante": _rango_dominante(dentro),
            "istituti": [i for i, _ in collections.Counter(
                a["istituto"] for a in dentro if a["istituto"]).most_common(6)],
            "lessico": lessici[indice],
            "vocabolario_del_corpus": vocabolario_delle_massime(grafo, set(membri)),
        })

    # Quante motivazioni citano ciascun articolo. Serve a distinguere
    # l'articolo che IDENTIFICA una lite da quello che compare ovunque:
    # famiglie_da_cocitazione lo dice gia' in prosa - artt. 641-650,
    # 281-sexies, 91/96 c.p.c. "compaiono ovunque proprio perche' non
    # distinguono nulla" - e qui diventa un numero, cosi' il runtime puo'
    # pesarli invece di doverli elencare a mano.
    citazioni: collections.Counter = collections.Counter()
    for citati in per_provvedimento.values():
        for node_id in citati:
            if node_id in articoli:
                citazioni[articoli[node_id]["chiave"]] += 1

    return {
        "meta": {
            "grafo_nodi": grafo.number_of_nodes(),
            "grafo_archi": grafo.number_of_edges(),
            "provvedimenti_con_articoli": len(per_provvedimento),
            "soglia_coppia": soglia,
            # L'impronta del grafo da cui questi profili sono usciti. Serve
            # a far dire alla pipeline "sto usando profili di un altro
            # grafo" invece di lavorare in silenzio su una classificazione
            # vecchia: e' un artefatto DERIVATO, e un derivato senza
            # l'identita' della sorgente non e' verificabile.
            "sha256_grafo": sha256_grafo,
            "avviso": (
                "Le comunita' sono CANDIDATE: nome, confini e regola restano "
                "giudizio giuridico (STATO_PROGETTO §7.5). Il rango e l'istituto "
                "sono invece letti dall'alberatura dei nodi, non decisi qui."
            ),
        },
        "rango_per_articolo": {a["chiave"]: a["rango"] for a in articoli.values()},
        "istituto_per_articolo": {a["chiave"]: a["istituto"]
                                   for a in articoli.values() if a["istituto"]},
        "provvedimenti_per_articolo": dict(citazioni),
        "comunita_per_segmento": etichette_dei_segmenti(
            grafo, comunita_per_articolo, indice_segmenti),
        "comunita_per_articolo": comunita_per_articolo,
        "comunita": profili,
    }


def _indice_segmenti(percorso_grafo: Path) -> list[dict] | None:
    """L'indice dei segmenti di provvedimento, cercato accanto al grafo.
    None se non c'e': l'etichettatura dei segmenti e' un di piu', non un
    requisito, e senza indice il resto dei profili si costruisce lo
    stesso."""
    accanto = Path(percorso_grafo).parent / "embeddings_segmenti_provvedimenti_index.json"
    try:
        return json.loads(accanto.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def rigenera(percorso_grafo: Path, uscita: Path = USCITA_DEFAULT,
             soglia: int = SOGLIA_COPPIA) -> dict:
    """Rigenera i profili da un grafo su disco. Chiamata da
    `promuovi_grafo.py` subito dopo una promozione riuscita: i profili
    sono un DERIVATO del grafo, e lasciarli indietro significherebbe
    classificare le eccezioni con le comunita' di un corpus che non
    esiste piu'. Ritorna il riepilogo scritto."""
    with open(percorso_grafo, "rb") as f:
        grafo = pickle.load(f)
    profili = costruisci_profili(grafo, soglia, sha256_file(percorso_grafo),
                                 _indice_segmenti(percorso_grafo))
    uscita.parent.mkdir(parents=True, exist_ok=True)
    uscita.write_text(json.dumps(profili, ensure_ascii=False, indent=1), encoding="utf-8")
    return profili


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--grafo", type=Path, default=GRAFO_DEFAULT)
    parser.add_argument("--uscita", type=Path, default=USCITA_DEFAULT)
    parser.add_argument("--soglia", type=int, default=SOGLIA_COPPIA)
    argomenti = parser.parse_args()

    with open(argomenti.grafo, "rb") as f:
        grafo = pickle.load(f)

    profili = costruisci_profili(grafo, argomenti.soglia, sha256_file(argomenti.grafo),
                                 _indice_segmenti(argomenti.grafo))

    argomenti.uscita.parent.mkdir(parents=True, exist_ok=True)
    argomenti.uscita.write_text(
        json.dumps(profili, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"{len(profili['comunita'])} comunita' da {profili['meta']['provvedimenti_con_articoli']} "
          f"provvedimenti con articoli agganciati")
    for c in profili["comunita"]:
        materia = c["vocabolario_del_corpus"]["materia"]
        print(f"  comunita {c['comunita']}: {c['n_articoli']} articoli, "
              f"{c['provvedimenti_che_la_usano']} provvedimenti, ranghi {c['ranghi']}")
        if materia:
            print(f"      materia dal corpus: {materia}")
        if c["istituti"]:
            print(f"      istituti: {', '.join(c['istituti'][:4])}")
    print(f"\nScritto in {argomenti.uscita}")


if __name__ == "__main__":
    main()
