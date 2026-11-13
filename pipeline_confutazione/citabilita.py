# -*- coding: utf-8 -*-
"""Una fetta di testo DICE qualcosa, o esiste soltanto?

## Il buco che colma

La regola 4 impone che ogni affermazione dell'atto finale sia ancorata a
`(fonte_id, inizio, fine)` calcolata da Python. `localizza` garantisce che
il testo citato **esista** nel documento, carattere per carattere, e lo fa
bene: e' il controllo su cui poggia tutta la pipeline.

Non esiste nessun controllo che il testo citato **dica** qualcosa.

    "ha censurato la statuizione del"

Trentuno caratteri, si ancora perfettamente, supera ogni verifica
automatica del progetto, e non afferma nulla. In un atto depositato sarebbe
una citazione formalmente ineccepibile e completamente muta. Misurato: sei
frammenti cosi' nel golden set del 2026-08-30, e due nell'uscita di Fase 1
dopo il contratto 1.31 (§7.35, §7.36).

## Perche' non e' un'euristica

Due tentativi automatici, entrambi falliti e misurati in §7.36:

- **"scegli la piu' lunga"**: concorda 19 su 19 col giudizio umano e non
  significa nulla, perche' l'annotatore che vince e' anche sistematicamente
  piu' lungo - le due spiegazioni sono indistinguibili. E comunque la
  pipeline ha UNA fetta davanti, non due;
- **"la fetta si interrompe a meta'"** (finisce in minuscola, su una parola
  che regge cio' che segue, con i puntini): trova 7 delle 10 fette note come
  non citabili, ma da' **9 falsi allarmi su 31** citabili - il 29%, e su
  fette da 122 a 644 caratteri che finiscono con un punto e virgola.

La ragione del secondo fallimento e' la sola cosa che conta qui: **la
troncatura sintattica non e' l'incompletezza semantica**. Cio' che rende
inutilizzabile "ha censurato la statuizione del" non e' come finisce, e'
che non predica nulla. Un test sulla forma della coda non puo' vederlo, e
nessun test sulla forma potra'.

## La forma della domanda

Tre categorie mutuamente esclusive, tutte descrizioni POSITIVE di che cosa
la fetta e'. Nessuna e' un "non va bene": e' la forma che ha raddrizzato
quattro classificazioni prima di questa (`golden_esaustivo.NATURE`,
`VOCI_CHE_SOSTENGONO`, `golden_esaustivo_atti.NATURE`, il filtro di Fase 1
nel contratto 1.31), e ogni volta il difetto era lo stesso: cio' che non ha
una casella finisce nella casella sbagliata.

Il `motivo` esce PRIMA della decisione. Con la decodifica vincolata i campi
escono nell'ordine dello schema, e con la decisione per prima il modello
decide e poi razionalizza - misurato, non temuto: la prima versione del
terzo stadio della spazzata respinse 8 candidati su 8 mentre i suoi stessi
`motivo` dicevano il contrario.

Nessuna istruzione del tipo "nel dubbio rispondi X": una soglia scritta nel
prompt non e' una soglia calibrata, e' un pollice sulla bilancia.

## Cosa NON fa

Non giudica se la fetta sia un'eccezione - quello e' un altro giudizio, e
tenerli separati e' il punto: un frammento troncato puo' riferirsi a
un'eccezione verissima e restare incitabile. Non tocca gli offset, non
riancora, non accorcia ne' allunga nulla: dice solo se cio' che gli e'
stato dato regge da solo.
"""

from __future__ import annotations

import sys
from pathlib import Path

CARTELLA = Path(__file__).parent
if str(CARTELLA) not in sys.path:
    sys.path.insert(0, str(CARTELLA))

import llama_server_client  # stesso pacchetto, import diretto

VERSIONE_MODULO = "1.0"

#: Le tre categorie. Solo la prima e' citabile.
#:
#: `dipende_dal_contesto` non e' un doppione della seconda ed e' il motivo
#: per cui le categorie sono tre e non due: "l'eccezione e' fondata e va
#: accolta" e' una frase grammaticalmente intera che non dice QUALE
#: eccezione. Non si interrompe a meta' - nessun controllo sulla forma la
#: segnalerebbe - e citata da sola non significa niente. Senza una casella
#: propria finirebbe fra le citabili, che e' il difetto piu' pericoloso dei
#: due: passa inosservata.
CATEGORIE = (
    "sta_in_piedi_da_sola",
    "frammento_sospeso",
    "dipende_dal_contesto",
)

CITABILE = "sta_in_piedi_da_sola"

#: Che cosa FARE di ciascuna categoria, e non e' la stessa cosa per le due
#: non citabili. Misurato sui 41 giudizi umani del 2026-09-01:
#:
#:   frammento_sospeso     prende 4 delle 10 fette cattive
#:                         e boccia 1 delle 31 buone   ->  3% di falsi allarmi
#:   dipende_dal_contesto  prende 4 delle 10 cattive
#:                         e boccia 6 delle 31 buone   -> 19% di falsi allarmi
#:
#: Trattarle insieme butta via quella buona per colpa dell'altra: il 23% di
#: falsi allarmi complessivo viene quasi tutto dalla seconda. Quindi la
#: prima BLOCCA e la seconda SEGNALA - che e' poi la politica che questo
#: progetto applica gia' altrove (dichiarare invece di troncare, contratto
#: 1.30): dove il giudizio non e' netto non si cancella niente, si dice.
#:
#: LIMITE DICHIARATO: 41 casi, e questa divisione e' stata scelta DOPO aver
#: visto quei numeri. Il 3% e' quindi ottimistico e va riverificato su fette
#: nuove prima di fidarsene come soglia.
AZIONE = {
    "sta_in_piedi_da_sola": "passa",
    "frammento_sospeso": "blocca",
    "dipende_dal_contesto": "segnala",
}

SCHEMA = {
    "type": "object",
    "properties": {
        "motivo": {"type": "string", "maxLength": 300},
        "categoria": {"enum": list(CATEGORIE)},
    },
    "required": ["motivo", "categoria"],
    "additionalProperties": False,
}

SISTEMA = (
    "Sei un giurista che controlla le citazioni di un atto giudiziario "
    "italiano prima del deposito. Rispondi solo con il JSON richiesto."
)


def costruisci_prompt(fetta: str) -> str:
    """La fetta si mostra DA SOLA, senza il testo intorno.

    Gli esempi nel prompt sono INVENTATI, non presi dai campioni verificati
    a mano: mettere in esempio una frase del banco di prova la farebbe
    indovinare per costruzione, e il numero che ne uscirebbe non
    misurerebbe piu' il controllo.

    Mostrare il contesto renderebbe la domanda impossibile: con il periodo
    intero davanti anche "ha censurato la statuizione del" si capisce
    benissimo, ed e' esattamente cio' che non deve succedere. La domanda e'
    se la fetta regga QUANDO IL CONTESTO NON C'E' - che e' la condizione in
    cui si trova un giudice che legge la citazione nell'atto."""
    return "\n".join([
        "Questa frase sta per essere citata testualmente in un atto "
        "giudiziario. Il giudice che la leggera' NON avra' davanti il "
        "documento da cui e' presa: leggera' solo queste parole.",
        "",
        "--- frase ---",
        fetta,
        "--- fine ---",
        "",
        "Prima, in `motivo`, scrivi in una riga che cosa questa frase "
        "afferma, oppure che cosa le manca per affermare qualcosa.",
        "",
        "Poi scegli in `categoria`:",
        "",
        "- `sta_in_piedi_da_sola`: afferma qualcosa di compiuto. Chi la "
        "legge capisce che cosa si sostiene. Puo' cominciare o finire a "
        "meta' di un periodo piu' lungo, puo' finire con una virgola o un "
        "punto e virgola: cio' che conta e' che dica qualcosa, non come sia "
        "tagliata;",
        "- `frammento_sospeso`: si interrompe prima di affermare. Resta un "
        "pezzo di frase che introduce qualcosa e non arriva a dirlo - "
        "\"il convenuto ha contestato la determinazione del\", \"rilevando "
        "che la banca avrebbe indebitamente\";",
        "- `dipende_dal_contesto`: la frase usa un RIMANDO esplicito a "
        "qualcosa che qui non c'e' - \"tale eccezione e' fondata\", \"la "
        "domanda di cui sopra va respinta\", \"ne consegue quanto detto\", "
        "\"il primo motivo e' infondato\". Il segnale sono le parole che "
        "puntano altrove: tale, detto, predetto, di cui sopra, il primo/il "
        "secondo, ne consegue.",
        "",
        "ATTENZIONE, e' l'errore piu' facile: una citazione NON deve "
        "raccontare tutta la causa. Non serve che nomini la parte che "
        "solleva la questione, ne' il contratto, ne' le date, ne' il numero "
        "del decreto. \"il tasso pattuito supera la soglia di usura vigente "
        "al momento della stipula\" "
        "afferma benissimo qualcosa e va in `sta_in_piedi_da_sola`, anche se "
        "non dice chi la solleva ne' in quale causa. `dipende_dal_contesto` "
        "e' solo per i rimandi espliciti, non per cio' che una frase "
        "semplicemente non ha bisogno di dire.",
    ])


def valuta(base_url: str, fetta: str, *, seed: int = 1234,
           temperature: float = 0.0) -> dict:
    """La categoria di UNA fetta. Ritorna {categoria, motivo, citabile}.

    Una risposta fuori vocabolario diventa `dipende_dal_contesto`: e' la
    categoria non citabile piu' cauta, e un modello che risponde fuori
    schema non sta dando un giudizio di cui fidarsi. Non e' un pollice sulla
    bilancia nel prompt - li' le tre vie restano pari - e' cosa fare quando
    un giudizio non c'e'."""
    prompt = llama_server_client.costruisci_prompt_chatml(
        SISTEMA, costruisci_prompt(fetta), pensiero_attivo=False)
    risposta = llama_server_client.completa_json(
        base_url, prompt, SCHEMA, n_predict=384,
        temperature=temperature, seed=seed)
    categoria = risposta.get("categoria")
    if categoria not in CATEGORIE:
        categoria = "dipende_dal_contesto"
    return {
        "categoria": categoria,
        "motivo": (risposta.get("motivo") or "").strip(),
        "citabile": categoria == CITABILE,
        "azione": AZIONE[categoria],
    }
