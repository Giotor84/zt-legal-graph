"""Ordine di rendering dei motivi, calcolato da Python (contratto 1.27).

## Perche' non lo chiede piu' al modello

Fino alla 1.26 l'ordine era il campo `ordine_motivi` della Fase 3-bis: il
modello riceveva i riassunti e doveva restituire una PERMUTAZIONE completa
degli `eccezione_id`. Il tetto di contratto era `maxItems: 15`.

Misurato sul batch del 2026-08-30 (45 atti, non stimato): **24 atti su 45
hanno piu' di 15 motivi** - mediana 17, massimo 59. Il tetto respingeva
l'input e fermava la corsa DOPO che Fase 2 e Fase 3 avevano gia' fatto il
loro lavoro. Alzarlo non e' la soluzione: una passata generativa che deve
emettere una permutazione completa degrada gia' a K=20-30 e fallisce a
K=50, omettendo candidati (RLPO, arXiv 2601.07449), e i modelli hanno un
bias posizionale forte che favorisce gli elementi in testa (arXiv
2604.03642). A K=56 la permutazione sarebbe stata respinta dal controllo
11 quasi ogni volta: costo pieno di una chiamata, risultato nullo.

Non era un problema di lunghezza dell'uscita: misurato sul tokenizzatore
del server, 56 id costano **293 token** contro un `n_predict` di 1536.
Il vincolo era la capacita' del modello, non il budget.

## Cosa fa al suo posto

L'ordine di un atto difensivo non e' gusto: e' rito. Prima le pregiudiziali
di rito, poi le preliminari di merito, poi il merito. E' una regola
processuale, quindi calcolabile - la stessa logica per cui il tipo di atto
e' uscito dal modello nella 1.26.

L'ordinamento e' STABILE: dentro lo stesso rango si conserva l'ordine del
dossier, che e' l'ordine in cui le eccezioni compaiono nell'atto di
controparte. Nessun criterio nascosto, e due corse sugli stessi motivi
danno lo stesso ordine senza dipendere dal campionamento.

## Da dove viene il rango (1.28: dal grafo, non da una tabella)

La prima versione di questo modulo aveva `RANGO_PER_FAMIGLIA`, una tabella
scritta a mano: nove famiglie, ciascuna assegnata al rito o al merito da
chi scriveva il codice. Non c'era bisogno di inventarla, perche' il grafo
lo dice gia': **il rango di un'eccezione e' l'alberatura degli articoli a
cui si aggancia**. Il codice di rito e' rito, il capo della prescrizione e'
preliminare di merito, il resto e' merito - e sta scritto sul nodo, non in
una nostra opinione.

Il calcolo vive in `famiglie_grafo.py`, che legge i profili prodotti da
`src/profili_famiglia.py`; qui resta solo l'ORDINAMENTO, che del rango non
sa nient'altro che la priorita'.

I motivi il cui rango non e' ricavabile NON vengono collocati a caso:
finiscono in coda con `non_classificato` e l'elenco viene restituito al
chiamante perche' lo dichiari.
"""

from __future__ import annotations

#: I ranghi, nell'ordine in cui vanno esposti nell'atto. L'indice in questa
#: tupla E' la priorita': non esiste un secondo criterio di ordinamento.
RANGHI: tuple[str, ...] = (
    "rito",                    # pregiudiziali di rito: si decidono prima di tutto
    "preliminare_di_merito",   # prescrizione, decadenza, giudicato
    "merito",                  # il merito della pretesa
    "non_classificato",        # rango non ricavabile dal grafo: in coda, dichiarato
)

NON_CLASSIFICATO = "non_classificato"


def ordina(motivi: list[dict]) -> dict:
    """Ordina i motivi per rango processuale, stabile dentro il rango.

    `motivi` sono i motivi dell'atto: serve `eccezione_id` e `rango`, che il
    chiamante ha gia' calcolato dal grafo (`famiglie_grafo.classifica`).
    Questo modulo non decide nessun rango: ordina e basta, ed e' cio' che
    gli permette di non sapere niente ne' del grafo ne' delle famiglie.
    Ritorna:

        {"ordine": [eccezione_id, ...],        # permutazione di TUTTI gli id
         "rango_per_motivo": {id: rango},
         "non_classificati": [id, ...]}        # da dichiarare, non da nascondere

    L'esito del motivo (trattato, astensione, errore tecnico) NON entra
    nell'ordinamento: un'eccezione preliminare resta preliminare anche se
    non siamo riusciti a confutarla, e retrocederla in coda perche' ci
    siamo astenuti darebbe all'ordine un significato che non ha.
    """
    posizione_rango = {nome: indice for indice, nome in enumerate(RANGHI)}
    rango_per_motivo = {m["eccezione_id"]: (m.get("rango") or NON_CLASSIFICATO)
                        for m in motivi}
    sconosciuti = {r for r in rango_per_motivo.values() if r not in posizione_rango}
    if sconosciuti:
        raise ValueError(
            f"rango non previsto dal contratto: {sorted(sconosciuti)} - "
            f"i ranghi ammessi sono {list(RANGHI)}")

    # `enumerate` come secondo criterio e' cio' che rende l'ordinamento
    # stabile: a parita' di rango vince chi compare prima nel dossier,
    # cioe' nell'atto di controparte.
    ordinati = sorted(
        enumerate(motivi),
        key=lambda coppia: (posizione_rango[rango_per_motivo[coppia[1]["eccezione_id"]]], coppia[0]),
    )
    return {
        "ordine": [m["eccezione_id"] for _, m in ordinati],
        "rango_per_motivo": rango_per_motivo,
        "non_classificati": [i for i, r in rango_per_motivo.items() if r == NON_CLASSIFICATO],
    }


#: Ampiezza della finestra della passata conflitti e passo di scorrimento.
#: La sovrapposizione (FINESTRA - PASSO) serve perche' due motivi adiacenti
#: nell'ordine finale non finiscano sempre a cavallo di due finestre diverse
#: e quindi non vengano mai confrontati.
FINESTRA = 8
PASSO = 4


def finestre(ordine: list[str]) -> list[list[str]]:
    """Le finestre scorrevoli su cui gira la ricerca dei conflitti.

    Con meno di due motivi non c'e' nessuna coppia: lista vuota, e il
    chiamante salta la passata (stessa prescrizione del contratto per
    `< 2 motivi`). L'ultima finestra e' ancorata alla fine invece che
    troncata, cosi' anche gli ultimi motivi vengono confrontati con
    qualcuno.
    """
    if len(ordine) < 2:
        return []
    if len(ordine) <= FINESTRA:
        return [list(ordine)]

    blocchi = []
    inizio = 0
    while inizio + FINESTRA < len(ordine):
        blocchi.append(list(ordine[inizio:inizio + FINESTRA]))
        inizio += PASSO
    blocchi.append(list(ordine[-FINESTRA:]))
    return blocchi


def coppie_esaminate(blocchi: list[list[str]]) -> set[frozenset[str]]:
    """Le coppie non ordinate che almeno una finestra ha messo insieme.

    Serve a dichiarare la COPERTURA: una coppia mai finita nella stessa
    finestra non e' stata esaminata, e non averla segnalata non significa
    che non ci sia un conflitto. Tacerlo sarebbe un silenzio, che e'
    esattamente cio' che il contratto vieta."""
    coppie: set[frozenset[str]] = set()
    for blocco in blocchi:
        for i, primo in enumerate(blocco):
            for secondo in blocco[i + 1:]:
                coppie.add(frozenset((primo, secondo)))
    return coppie


def copertura(ordine: list[str], blocchi: list[list[str]]) -> dict:
    """Quante coppie sono state davvero guardate, su quante ne esistono."""
    totali = len(ordine) * (len(ordine) - 1) // 2
    return {
        "finestre": len(blocchi),
        "coppie_esaminate": len(coppie_esaminate(blocchi)),
        "coppie_totali": totali,
    }
