"""
Estrazione (eccezione della parte -> esito -> ratio) dalle MOTIVAZIONI dei
provvedimenti integrali gia' nel grafo (grafo.gpickle, nodi
tipo_nodo=='provvedimento'). Costruisce il catalogo delle famiglie DAI DATI -
non popola motore_regole.py, non scrive nel grafo, non assegna famiglie:
solo estrae, ancora, filtra e deduplica.

Promosso da lavoro/nucleo_estrazione.py dopo l'audit del 2026-08-25 sul
campione di 206 coppie/38 provvedimenti (8 difetti misurati, tutti corretti
qui - vedi il docstring di ogni funzione per il difetto che risolve).

Riusa l'infrastruttura di Fase 1, sola lettura:
- llama_server_client.completa_json/proprieta_server/conta_token (questo
  modulo vive ORA in pipeline_confutazione/, import diretto - completa()
  impone gia' cache_prompt=False su OGNI chiamata, quindi non serve piu' il
  client HTTP diretto che lavoro/nucleo_estrazione.py si era dovuto scrivere
  a mano: la duplicazione era necessaria solo finche' questo modulo era
  scratch fuori dal pacchetto).
- localizza.localizza per l'ancoraggio (stessa procedura normativa di
  CONTRATTI_DATI.md, zero soglie proprie).
- segmenta_provvedimenti.segmenta_motivazione (src/) per i confini di
  frase quando una motivazione supera il contesto in una sola chiamata.

VINCOLI (task 2026-08-25): non tocca motore_regole.py, il grafo, src/,
nessuna assegnazione di famiglie. Non e' Fase 3: puo' leggere il grafo
(pickle diretto, mai src/store.py) perche' l'invariante "Fase 3 non importa
mai store/grafo" riguarda solo redazione.py/constrained_decoding.py - questo
modulo non e' nel percorso di redazione di un atto.
"""

from __future__ import annotations

import json
import pickle
import random
import re
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

RADICE = Path(__file__).parent.parent
if str(RADICE / "src") not in sys.path:
    sys.path.insert(0, str(RADICE / "src"))

import llama_server_client  # stesso pacchetto, import diretto
import localizza  # stesso pacchetto, import diretto
import segmenta_provvedimenti  # noqa: E402  (src/, sola lettura)

GRAPH_PATH = RADICE / "data" / "graph" / "grafo.gpickle"

VERSIONE_MODULO = "2.0"  # promosso da lavoro/nucleo_estrazione.py, 8 difetti corretti

# --------------------------------------------------------------- schema/prompt

ESITI_VALIDI = ("accolta", "rigettata", "assorbita", "non_esaminata", "non_chiaro")

SCHEMA_COPPIE = {
    "type": "object",
    "properties": {
        "coppie": {
            "type": "array",
            "maxItems": 20,
            "items": {
                "type": "object",
                "properties": {
                    "eccezione_letterale": {
                        "type": "string",
                        "maxLength": 2500,
                        "description": (
                            "Il passaggio, il piu' possibile letterale, in cui il testo RIPORTA "
                            "l'eccezione/domanda sollevata da una parte - copiato, non riassunto. "
                            "MAI '[...]' o '...' per indicare un'omissione: se il passaggio e' "
                            "lungo, copiane una parte piu' breve ma SENZA buchi."
                        ),
                    },
                    "parte_che_la_solleva": {
                        "type": "string",
                        "maxLength": 80,
                        "description": "Come il testo chiama la parte (es. 'l'appellante', 'l'opponente', 'la convenuta') - copia il termine usato, non inventarne uno.",
                    },
                    "esito": {"type": "string", "enum": list(ESITI_VALIDI)},
                    "ratio_letterale": {
                        "type": ["string", "null"],
                        "maxLength": 2500,
                        "description": (
                            "Il passaggio letterale in cui il giudice MOTIVA quella decisione, "
                            "copiato dal testo. null se il testo non fornisce una motivazione "
                            "specifica per quel punto. MAI '[...]' o '...' per indicare "
                            "un'omissione, con le stesse regole di eccezione_letterale."
                        ),
                    },
                },
                "required": ["eccezione_letterale", "parte_che_la_solleva", "esito", "ratio_letterale"],
            },
        },
        "elementi_non_estraibili": {
            "type": "array",
            "items": {"type": "string", "maxLength": 200},
            "maxItems": 10,
            "description": "Cosa non e' stato possibile determinare con certezza in questo blocco - campo obbligatorio, mai vuoto per omissione.",
        },
    },
    "required": ["coppie", "elementi_non_estraibili"],
}

PROMPT_COPPIE = (
    "Leggi il seguente brano, tratto dalla MOTIVAZIONE di un provvedimento giudiziario "
    "italiano (non e' l'atto di una parte: qui e' il giudice che riassume cosa le parti "
    "hanno eccepito o chiesto, e decide).\n\n"
    "Per OGNI eccezione, domanda o motivo di impugnazione sollevato da una parte che il "
    "testo discute, estrai QUATTRO cose:\n"
    "1. eccezione_letterale: il passaggio in cui il testo riporta l'eccezione della "
    "parte, copiato ESCLUSIVAMENTE con le parole del testo, carattere per carattere. "
    "NON racchiuderlo fra virgolette. NON usare '[...]' o puntini di sospensione per "
    "segnalare che hai saltato una parte. NON accorciare sostituendo parole con '...' o "
    "'[...]' in mezzo: se il passaggio e' lungo, copiane una parte piu' breve ma "
    "INTERA, senza buchi indicati in nessun modo.\n"
    "2. parte_che_la_solleva: il termine con cui il testo chiama quella parte (es. "
    "'l'appellante', 'l'opponente', 'la convenuta', 'il ricorrente') - copia il termine "
    "usato nel testo, non inventarne uno.\n"
    "3. esito: come il giudice ha deciso quel punto - 'accolta' se il giudice da' "
    "ragione alla parte su quel punto, 'rigettata' se la respinge nel merito, "
    "'assorbita' se il giudice dichiara la questione assorbita/superata da altra "
    "decisione senza esaminarla nel merito, 'non_esaminata' se il testo non dice come "
    "e' andata a finire quel punto specifico, 'non_chiaro' se non riesci a determinarlo "
    "con sicurezza.\n"
    "4. ratio_letterale: il passaggio in cui il giudice MOTIVA quella decisione, copiato "
    "con le stesse regole del punto 1 (letterale, non parafrasato, mai '[...]' o '...'). "
    "Se il giudice non da' una motivazione specifica per quel punto (es. lo dichiara "
    "assorbito senza spiegare perche'), scrivi null - non inventare una motivazione che "
    "il testo non contiene.\n\n"
    "Non classificare le eccezioni in categorie giuridiche: elencale soltanto, cosi' come "
    "il testo le presenta.\n\n"
    "Se in questo brano non c'e' NESSUNA eccezione o domanda discussa (es. e' solo "
    "l'intestazione, lo svolgimento del processo senza discussione, o il dispositivo), "
    "restituisci coppie: [] (lista VUOTA) - NON un oggetto con i campi vuoti o con "
    "puntini di sospensione al posto del testo. Un oggetto con campi vuoti non e' una "
    "risposta valida: se non c'e' nulla da estrarre, la lista deve restare vuota.\n\n"
    "Testo:\n{testo}"
)

# --------------------------------------------------------------- due passate
#
# Variante di estrazione in DUE passate, aggiunta il 2026-08-30. La passata
# unica sopra chiede al modello, per ogni eccezione, quattro campi insieme -
# fra cui due passaggi letterali che possono valere centinaia di caratteri
# l'uno. Su una motivazione lunga con molte questioni, il costo in token di
# ogni voce e' alto e la lista si accorcia: il modello ne emette poche e
# lunghe invece di molte e brevi.
#
# La diagnosi non e' nostra. E' quella di Piccioli et al. 2026 (King's
# College / Bologna / EUI, arXiv 2607.03325) su 330.000 sentenze delle
# commissioni tributarie italiane, che hanno dovuto spezzare l'estrazione
# esattamente cosi': "il modello aveva un intervallo di lunghezza di output
# preferito e, sui provvedimenti che richiedevano output piu' lunghi,
# l'approccio a prompt unico produceva output troppo concisi e QUESTIONI
# MANCANTI". Lo stesso lavoro indica l'omissione (non l'errore) come modo di
# fallimento dominante, e il nostro §7.11 e §7.16 descrivono lo stesso
# fenomeno.
#
# Passata 1 (censimento): solo "quali questioni ci sono e chi le solleva".
# Nessuna motivazione del giudice, nessun esito. Ogni voce costa poche
# decine di caratteri, quindi ne entrano molte.
# Passata 2 (dettaglio): una chiamata per questione, sullo STESSO blocco, per
# ricavarne esito e ratio.
#
# I candidati prodotti passano poi per _processa_coppia(), cioe' per gli
# stessi otto filtri della passata unica: il confronto fra le due strade
# misura la resa dell'estrazione, non due regimi di controllo diversi.

SCHEMA_CENSIMENTO = {
    "type": "object",
    "properties": {
        "questioni": {
            "type": "array",
            # 30 e non 20: qui ogni voce e' corta, quindi il tetto puo' essere
            # piu' alto senza avvicinarsi al limite di output. Resta un tetto:
            # la lezione di 1.22 (alzare maxItems senza alzare n_predict) vale
            # ancora, ed e' il motivo per cui non e' illimitato.
            "maxItems": 30,
            "items": {
                "type": "object",
                "properties": {
                    # 1200 e non 600: la prima stesura chiedeva un passaggio
                    # BREVE, e la corsa di prova ha mostrato che era un
                    # errore. Un verbatim corto o non si ancora in modo
                    # univoco (2 questioni su 2 scartate su un provvedimento
                    # reale: "violazione dell'art. 2697 c.c." compare due
                    # volte nella stessa motivazione -> ancora_ambigua) o
                    # invita il modello a riscrivere invece di copiare
                    # ("violenza dell'art. 58 TUB" al posto di "violazione").
                    # Il risparmio della passata 1 viene dal NON chiedere la
                    # ratio, non dall'accorciare l'eccezione.
                    "eccezione_letterale": {
                        "type": "string",
                        "maxLength": 1200,
                        "description": (
                            "Il passaggio, il piu' possibile letterale, in cui il testo RIPORTA "
                            "l'eccezione/domanda sollevata da una parte - copiato, non riassunto. "
                            "Abbastanza lungo da individuare UN SOLO punto del testo: se una frase "
                            "breve potrebbe riferirsi a due punti diversi, copiane una piu' lunga. "
                            "MAI '[...]' o '...' per indicare un'omissione."
                        ),
                    },
                    "parte_che_la_solleva": {
                        "type": "string",
                        "maxLength": 80,
                        "description": "Come il testo chiama la parte (es. 'l'appellante', 'l'opponente', 'la convenuta') - copia il termine usato, non inventarne uno.",
                    },
                },
                "required": ["eccezione_letterale", "parte_che_la_solleva"],
            },
        },
        "elementi_non_estraibili": {
            "type": "array",
            "items": {"type": "string", "maxLength": 200},
            "maxItems": 10,
            "description": "Cosa non e' stato possibile determinare con certezza in questo blocco - campo obbligatorio, mai vuoto per omissione.",
        },
    },
    "required": ["questioni", "elementi_non_estraibili"],
}

PROMPT_CENSIMENTO = (
    "Leggi il seguente brano, tratto dalla MOTIVAZIONE di un provvedimento giudiziario "
    "italiano (non e' l'atto di una parte: qui e' il giudice che riassume cosa le parti "
    "hanno eccepito o chiesto, e decide).\n\n"
    "Il tuo compito e' UNO SOLO: fare l'ELENCO COMPLETO delle eccezioni, domande e motivi "
    "di impugnazione sollevati dalle PARTI di cui il brano parla. Non devi dire come sono "
    "andati a finire, ne' perche': solo elencarli.\n\n"
    "Per ognuno indica DUE cose:\n"
    "1. eccezione_letterale: il passaggio in cui il testo riporta quella questione, "
    "copiato ESCLUSIVAMENTE con le parole del testo, carattere per carattere. Deve "
    "essere abbastanza lungo da individuare UN SOLO punto del testo: se una frase "
    "breve potrebbe riferirsi a due punti diversi del documento, copiane una piu' "
    "lunga. NON riscriverlo con parole tue nemmeno in parte: una sola parola cambiata "
    "rende il passaggio inutilizzabile. NON racchiuderlo fra virgolette. NON usare "
    "'[...]' o puntini di sospensione: se il passaggio e' lungo, copiane una parte "
    "piu' breve ma INTERA, senza buchi.\n"
    "2. parte_che_la_solleva: il termine con cui il testo chiama quella parte (es. "
    "'l'appellante', 'l'opponente', 'la convenuta', 'il ricorrente') - copia il termine "
    "usato nel testo, non inventarne uno.\n\n"
    "Elencale TUTTE, comprese quelle che il giudice dichiara tardive, assorbite o non "
    "esaminate: anche quelle sono questioni sollevate da una parte. Non elencare invece "
    "i passaggi in cui e' il GIUDICE a ragionare per conto proprio, ne' le formule di "
    "rito, ne' la liquidazione delle spese quando nessuna parte l'abbia contestata.\n\n"
    "Non classificare le questioni in categorie giuridiche: elencale soltanto, cosi' come "
    "il testo le presenta.\n\n"
    "Se in questo brano non c'e' NESSUNA questione sollevata da una parte, restituisci "
    "questioni: [] (lista VUOTA) - non un oggetto con i campi vuoti.\n\n"
    "Testo:\n{testo}"
)

SCHEMA_DETTAGLIO = {
    "type": "object",
    "properties": {
        "esito": {"type": "string", "enum": list(ESITI_VALIDI)},
        "ratio_letterale": {
            "type": ["string", "null"],
            "maxLength": 2500,
            "description": (
                "Il passaggio letterale in cui il giudice MOTIVA quella decisione, "
                "copiato dal testo. null se il testo non fornisce una motivazione "
                "specifica per quel punto. MAI '[...]' o '...' per indicare un'omissione."
            ),
        },
    },
    "required": ["esito", "ratio_letterale"],
}

PROMPT_DETTAGLIO = (
    "Leggi il seguente brano, tratto dalla MOTIVAZIONE di un provvedimento giudiziario "
    "italiano.\n\n"
    "Testo:\n{testo}\n\n"
    "---\n"
    "In quel testo, {parte} ha sollevato questa questione:\n"
    "\"{questione}\"\n\n"
    "Rispondi SOLO su questa questione, ignorando tutte le altre presenti nel testo.\n\n"
    "1. esito: come il giudice ha deciso QUESTO punto - 'accolta' se il giudice da' "
    "ragione alla parte su questo punto, 'rigettata' se lo respinge nel merito, "
    "'assorbita' se il giudice lo dichiara assorbito/superato da altra decisione senza "
    "esaminarlo nel merito, 'non_esaminata' se il testo non dice come e' andato a finire "
    "questo punto specifico, 'non_chiaro' se non riesci a determinarlo con sicurezza.\n"
    "2. ratio_letterale: il passaggio in cui il giudice MOTIVA questa decisione, copiato "
    "ESCLUSIVAMENTE con le parole del testo, carattere per carattere, senza virgolette e "
    "senza '[...]' o puntini di sospensione. Se il giudice non da' una motivazione "
    "specifica per questo punto (es. lo dichiara assorbito senza spiegare perche'), "
    "scrivi null - non inventare una motivazione che il testo non contiene."
)

#: Tetto di output della passata 2. Molto piu' basso di RISERVA_OUTPUT_TOKEN
#: perche' la risposta e' un esito piu' un passaggio: non c'e' una lista da
#: riempire, e un tetto alto qui inviterebbe soltanto a scrivere di piu'.
RISERVA_OUTPUT_DETTAGLIO_TOKEN = 1536


#: stessa lezione di estrazione_atto.py: a temperatura bassa (qui 0.0, greedy
#: puro) senza penalita' di ripetizione il modello puo' degenerare in loop.
REPEAT_PENALTY = 1.3
TEMPERATURA = 0.0
#: seed fissato e passato ESPLICITAMENTE a ogni chiamata. Non e' una
#: precauzione: llama-server senza `seed` nel payload usa il proprio default
#: (4294967295 = seed casuale a ogni richiesta), e completa_json lo inoltra
#: solo se il chiamante lo passa. E' lo stesso bug di estrazione_atto.py
#: (trovato 2026-08-24: tre corse identiche -> 29, 15, 14 eccezioni) e qui
#: ha prodotto lo stesso profilo (206 / 176 / 408 coppie sullo stesso
#: corpus). Senza, nessun confronto prima/dopo e' interpretabile.
SEED = 1234  # stesso default di esegui_pipeline.py --seed
CACHE_PROMPT = False  # imposto da llama_server_client.completa() su OGNI chiamata (invariato qui)

RISERVA_OUTPUT_TOKEN = 6144
RISERVA_PROMPT_TOKEN = 1000
MARGINE_TOKEN = 500
CHAR_PER_TOKEN_PRUDENTE = 3.0  # sottostima apposta: meglio un blocco piu' piccolo del necessario che uno che tronca

#: Difetto [2]: soglia di sovrapposizione oltre la quale due span dello
#: stesso provvedimento sono la STESSA eccezione riletta due volte, non due
#: eccezioni diverse. 0.8, non 1.0: il caso reale misurato nell'audit
#: (stesso offset_inizio, fine che varia di 3 caratteri su ~270) ha IoU
#: ben sopra 0.8; un IoU piu' basso rischierebbe di fondere due eccezioni
#: adiacenti ma distinte.
SOGLIA_IOU_DUPLICATO = 0.8

#: Difetto [4]: vocabolario CHIUSO per parte_normalizzata. Chi non mappa va
#: in non_determinabile - mai un valore nuovo inventato qui.
PARTE_VOCABOLARIO_CHIUSO = (
    "appellante", "appellato", "ricorrente", "resistente",
    "opponente", "opposto", "terzo", "non_determinabile",
)


# --------------------------------------------------------------- grafo


def carica_provvedimenti() -> list[dict]:
    """Tutti i nodi tipo_nodo=='provvedimento', SENZA pre-filtrare quelli a
    motivazione nulla (difetto [7]: l'esclusione va gestita come percorso
    esplicito in estrai_provvedimento, non come filtro silenzioso qui)."""
    with open(GRAPH_PATH, "rb") as f:
        grafo = pickle.load(f)
    provvedimenti = []
    for node_id, dati in grafo.nodes(data=True):
        if dati.get("tipo_nodo") == "provvedimento":
            provvedimenti.append({"node_id": node_id, **dati})
    return provvedimenti


# --------------------------------------------------------------- [4] parte_normalizzata

_APOSTROFI_CURVI = "‘’ʼ´′"


def _normalizza_apostrofo(testo: str) -> str:
    for c in _APOSTROFI_CURVI:
        testo = testo.replace(c, "'")
    return testo


_PARTE_PATTERN: tuple[tuple[str, "re.Pattern"], ...] = (
    ("appellante", re.compile(r"appellant[ei]", re.I)),
    ("appellato", re.compile(r"appellat[aeio]", re.I)),
    ("ricorrente", re.compile(r"ricorrent[ei]", re.I)),
    ("resistente", re.compile(r"resistent[ei]", re.I)),
    ("opponente", re.compile(r"opponent[ei]", re.I)),
    ("opposto", re.compile(r"oppost[aeio]", re.I)),
    ("terzo", re.compile(r"\bterz[oai]\b", re.I)),
)


def normalizza_parte(grezza: str) -> str:
    """Difetto [4]: mappa parte_che_la_solleva su un vocabolario CHIUSO di 8
    valori. Segnaposto di pseudonimizzazione (Parte_1, CP_3, Controparte_2),
    l'organo giudicante, e qualunque variante non prevista finiscono in
    non_determinabile - MAI un valore nuovo. Il campo grezzo resta
    disponibile accanto (mai perso).

    L'apostrofo curvo/dritto (oggi "l'appellante" contato due volte, 31+17)
    e' risolto qui a monte, normalizzando ENTRAMBE le forme prima del
    confronto - il pattern cerca solo lo stelo lessicale (appellant[ei]),
    indifferente a cosa lo precede."""
    if not grezza:
        return "non_determinabile"
    testo = _normalizza_apostrofo(grezza).lower()
    for etichetta, pattern in _PARTE_PATTERN:
        if pattern.search(testo):
            return etichetta
    return "non_determinabile"


# --------------------------------------------------------------- [3] falsi positivi per classe

_ORGANO_PATTERN = re.compile(
    r"\b(corte|tribunale|collegio|giudice|giudicante|g\.\s?u\.|ctu|"
    r"consulente\s+tecnico|consulente\s+(?:d['’]|di\s+)ufficio)\b",
    re.I,
)


def soggetto_e_organo_giudicante(parte_grezza: str) -> bool:
    """Difetto [3], classe 1: il soggetto dichiarato e' l'organo decidente o
    il suo ausiliario tecnico - per definizione non sollevano eccezioni, le
    decidono o le valutano. Filtro su parte_che_la_solleva (CHI il modello
    dice che parla), non sul testo dell'eccezione: un CTU o un giudice
    possono comparire come soggetto grammaticale di una frase che il
    modello ha comunque classificato come "eccezione discussa" - e' un
    errore di classe, si riconosce da chi e' indicato come parte."""
    if not parte_grezza:
        return False
    testo = _normalizza_apostrofo(parte_grezza).lower()
    return bool(_ORGANO_PATTERN.search(testo))


_VERBI_PETITUM = (
    "dichiarare", "rigettare", "respingere", "confermare", "condannare",
    "accertare", "disporre", "ordinare", "revocare", "annullare",
    "riformare", "accogliere",
)
_PETITUM_APERTURA = re.compile(
    r"^\W*(?:[-–—•\d.\)]+\s*)*(" + "|".join(_VERBI_PETITUM) + r")\b",
    re.I,
)
_FORMULA_PIACCIA = re.compile(r"\bpiaccia\b|\bvoglia\s+l['’]?\s*ecc", re.I)


def e_formula_conclusiva_o_dispositivo(testo: str) -> bool:
    """Difetto [3], classe 2: formule del PETITUM (le conclusioni delle
    parti, spesso trascritte in motivazione com'erano nell'atto: "Piaccia
    all'Ecc.ma Corte...", o un elenco puntato di richieste che apre con un
    verbo all'infinito tipico delle conclusioni - dichiarare, rigettare,
    confermare...) non sono un'eccezione DISCUSSA dal giudice: sono la
    domanda della parte riportata com'e', non l'argomento su cui il
    giudice si e' pronunciato. Pattern sulla STRUTTURA (apertura della
    frase), non su una lista di frasi viste nel campione."""
    testo = (testo or "").strip()
    if not testo:
        return False
    if _FORMULA_PIACCIA.search(testo):
        return True
    return bool(_PETITUM_APERTURA.match(testo))


_ORDINALI = ("primo", "secondo", "terzo", "quarto", "quinto", "sesto", "settimo", "ottavo", "nono", "decimo")
_MOTIVO_SOSTANTIVI = ("motivo", "motivi", "censura", "censure", "doglianza", "doglianze", "gravame", "profilo", "profili")

_RIFERIMENTO_MOTIVO_VUOTO = re.compile(
    r"^\W*(il|lo|la|i|gli|le|un|uno|una)\s+"
    r"(" + "|".join(_ORDINALI) + r")"
    r"(\s+ed?\s+(il|lo|la|i|gli|le)\s+(" + "|".join(_ORDINALI) + r"))?"
    r"\s+(" + "|".join(_MOTIVO_SOSTANTIVI) + r")"
    r"(\s+di\s+\w+)?\W*$",
    re.I,
)


def e_riferimento_a_motivo_senza_contenuto(testo: str) -> bool:
    """Difetto [3], classe 3: la frase e' SOLO un rimando numerato a un
    motivo/censura ("il secondo motivo", "il primo ed il terzo motivo di
    impugnazione") - un'etichetta di sezione, non un'eccezione con un
    contenuto proprio. Si ancora comunque nell'atto, ma non dice nulla su
    COSA si eccepisce: non e' citabile come argomento."""
    return bool(_RIFERIMENTO_MOTIVO_VUOTO.match((testo or "").strip()))


_SOGGETTI_VERDETTO = ("motivo", "motivi", "censura", "censure", "doglianza", "doglianze", "gravame", "appello", "ricorso", "eccezione", "eccezioni")
_ESITI_AGGETTIVI = ("fondat", "infondat", "assorbit", "inammissibil", "ammissibil", "accolt", "respint", "riget")

_VERDETTO_SENZA_CONTENUTO = re.compile(
    r"^\W*(il|lo|la|i|gli|le)?\s*"
    r"(" + "|".join(_SOGGETTI_VERDETTO) + r")\s+"
    r"(sono|è|risulta(?:no)?)\s+"
    r"(" + "|".join(_ESITI_AGGETTIVI) + r")\w*\W*$",
    re.I,
)


def e_verdetto_senza_contenuto(testo: str) -> bool:
    """Difetto [3], classe 4: la frase e' SOLO il verdetto del giudice su un
    punto ("I motivi sono fondati."), non l'eccezione stessa - il giudice
    che riassume l'esito, non la parte che argomenta. Filtro strutturale
    sul predicato (soggetto processuale + copula + aggettivo di esito),
    non sulla frase esatta vista nel campione."""
    return bool(_VERDETTO_SENZA_CONTENUTO.match((testo or "").strip()))


_ISTANZA_ISTRUTTORIA = re.compile(
    r"^\W*(la|lo|l['’]|le|una|un)?\s*"
    r"(rimessione|svolgimento|ammissione|nomina|espletamento|richiesta)\b"
    r"[^.]{0,60}?"
    r"\b(istruttori[ao]|consulenza\s+tecnica\s+(?:d['’]|di\s+)ufficio|c\.t\.u\.|ctu|prova\s+testimoniale)\b",
    re.I,
)


def e_istanza_istruttoria(testo: str) -> bool:
    """Difetto [3], classe 5: il testo e' una RICHIESTA di un mezzo
    istruttorio (CTU, prova testimoniale, rimessione in istruttoria), non
    un'eccezione o un motivo di merito - e' una domanda processuale sul
    COME accertare i fatti, non un argomento su cosa e' giusto o dovuto."""
    return bool(_ISTANZA_ISTRUTTORIA.search((testo or "")))


def classifica_falso_positivo(eccezione_testo: str, parte_grezza: str) -> str | None:
    """Difetto [3]: un solo punto di ingresso per le 5 classi di falso
    positivo sistematico misurate nell'audit (non casi isolati - vedi ogni
    funzione sopra). Ritorna il motivo (stringa stabile, usata come chiave
    in 'scartate') o None se il testo passa tutti i filtri."""
    if soggetto_e_organo_giudicante(parte_grezza):
        return "soggetto_organo_giudicante_o_ctu"
    if e_formula_conclusiva_o_dispositivo(eccezione_testo):
        return "formula_conclusiva_o_dispositivo"
    if e_riferimento_a_motivo_senza_contenuto(eccezione_testo):
        return "riferimento_a_motivo_senza_contenuto"
    if e_verdetto_senza_contenuto(eccezione_testo):
        return "verdetto_senza_contenuto"
    if e_istanza_istruttoria(eccezione_testo):
        return "istanza_istruttoria"
    return None


# --------------------------------------------------------------- [1] elisione e verbatim


def contiene_elisione_esplicita(testo: str | None) -> bool:
    """Difetto [1]: il testo del modello contiene "[...]" - va scartato A
    MONTE comunque: localizza() non lo ancorerebbe mai come 'ancorata'
    (ellissi interna, vedi localizza._ancora_con_omissione e
    _ELLISSI_INTERNA, che tratta "[...]" come qualunque sequenza di 3+
    punti) qualunque sia l'origine del "[...]" - una citazione con un buco
    dichiarato in mezzo non e' MAI un intervallo unico di
    (fonte_id, inizio, fine), per contratto. Verificato sui 23 casi della
    ri-corsa 2026-08-25: 0/23 sarebbero stati 'ancorata' senza questo
    scarto a monte - e' un taglio diagnostico anticipato, non un cambio di
    esito.

    Questo controllo NON distingue la CAUSA (vedi
    elisione_ereditata_da_fonte) - non serve per decidere se scartare (la
    decisione e' la stessa in entrambi i casi), solo per la diagnostica in
    'scartate'."""
    return bool(testo) and "[...]" in testo


def elisione_ereditata_da_fonte(testo_modello: str, testo_integrale: str, contesto: int = 25) -> bool:
    """Distingue le due cause DIVERSE di "[...]" nel testo del modello
    (chiesto esplicitamente dopo la scoperta indipendente, 2026-08-25):

    - EREDITATA dalla fonte: `testo_integrale` contiene GIA' lo stesso
      "[...]" nello stesso punto (verificato: la pipeline di
      pseudonimizzazione a monte lascia 152 "[...]" letterali su 32/41
      provvedimenti, quasi sempre subito dopo un segnaposto come
      "Parte_1"/"CP_3" - non un'invenzione del modello, che qui e' stato
      fedele al sorgente compreso il suo buco).
    - INVENTATA dal modello: nessun "[...]" della fonte in quel punto - il
      modello ha scelto di abbreviare un passaggio che nella fonte e'
      continuo.

    Sui 23 scarti di eccezione della ri-corsa 2026-08-25: 8 ereditate
    (tutte dallo stesso provvedimento degenere, R.G. 00009530/2024 - vedi
    §7 del report), 15 inventate. La decisione di scarto (vedi
    contiene_elisione_esplicita) resta identica in entrambi i casi: questa
    funzione serve SOLO a etichettare la causa in 'scartate', non a
    cambiare cosa viene tenuto."""
    i = testo_modello.find("[...]")
    if i == -1:
        return False
    intorno = testo_modello[max(0, i - contesto):i + 5 + contesto]
    return intorno in testo_integrale


def calcola_verbatim(testo_integrale: str, inizio: int, fine: int) -> str:
    """Difetto [1]: l'unico testo CITABILE in un atto - ricalcolato da
    Python dal testo_integrale del nodo agli offset registrati, mai preso
    dall'output del modello. eccezione_letterale/ratio_letterale restano
    nel record solo come "cosa ha detto il modello", mai come fonte di
    citazione (vedi META_AVVISO_USO_DATI)."""
    return testo_integrale[inizio:fine]


META_AVVISO_USO_DATI = (
    "CITABILE in un atto: SOLO eccezione_verbatim/ratio_verbatim, ricalcolati da Python da "
    "testo_integrale[offset_inizio:offset_fine] del nodo dichiarato - mai da eccezione_letterale/"
    "ratio_letterale, che sono l'output del modello (puo' differire dal testo reale: virgolette, "
    "puntini finali, parole ricomposte) e NON sono citabili. STRATEGICO (classificazione_dato != "
    "'citabile'): pattern di come un ufficio decide, frequenza, argomenti - mai in un atto, solo "
    "per memoria di analisi interna."
)


# --------------------------------------------------------------- [2] dedup per span (IoU)

_RANGO_CORRISPONDENZA = {"esatta": 0, "normalizzata": 1, "fuzzy": 2}


def _iou(a: tuple[int, int], b: tuple[int, int]) -> float:
    inizio = max(a[0], b[0])
    fine = min(a[1], b[1])
    intersezione = max(0, fine - inizio)
    if intersezione == 0:
        return 0.0
    unione = (a[1] - a[0]) + (b[1] - b[0]) - intersezione
    return intersezione / unione if unione else 0.0


def deduplica_per_span(coppie: list[dict], soglia_iou: float = SOGLIA_IOU_DUPLICATO) -> tuple[list[dict], list[dict]]:
    """Difetto [2]: dedup per (node_id, sovrapposizione di span), non per
    stringa - il dedup sulla stringa non vede due span quasi identici che
    differiscono per un frammento agrammaticale ("sollevata ha" contro
    "sollevato da ha"), che sono lo stesso punto dell'atto riletto due
    volte, non due eccezioni diverse.

    Fra un gruppo che si sovrappone oltre soglia_iou, tiene la
    corrispondenza piu' esatta (esatta > normalizzata > fuzzy), a parita'
    di rango la similarita' piu' alta, a parita' di similarita' l'indice
    piu' basso (stabile). Ritorna (tenute, scartate) - le scartate portano
    motivo_scarto e lo span del duplicato tenuto, mai silenziosamente
    sparite."""
    per_nodo: dict[str, list[int]] = {}
    for i, c in enumerate(coppie):
        per_nodo.setdefault(c["node_id"], []).append(i)

    def chiave_qualita(i: int) -> tuple:
        c = coppie[i]
        rango = _RANGO_CORRISPONDENZA.get(c.get("eccezione_corrispondenza"), 99)
        sim = c.get("eccezione_similarita")
        sim = sim if sim is not None else 1.0
        return (rango, -sim, i)

    scartato_come_duplicato_di: dict[int, int] = {}
    for _node_id, indici in per_nodo.items():
        indici_ordinati = sorted(indici, key=chiave_qualita)
        tenuti_di_questo_nodo: list[int] = []
        for i in indici_ordinati:
            span_i = (coppie[i]["offset_inizio"], coppie[i]["offset_fine"])
            duplicato_di = None
            for j in tenuti_di_questo_nodo:
                span_j = (coppie[j]["offset_inizio"], coppie[j]["offset_fine"])
                if _iou(span_i, span_j) >= soglia_iou:
                    duplicato_di = j
                    break
            if duplicato_di is None:
                tenuti_di_questo_nodo.append(i)
            else:
                scartato_come_duplicato_di[i] = duplicato_di

    tenute = [coppie[i] for i in range(len(coppie)) if i not in scartato_come_duplicato_di]
    scartate = [
        {
            **coppie[i],
            "motivo_scarto": "duplicato_span",
            "duplicato_di_offset": [coppie[j]["offset_inizio"], coppie[j]["offset_fine"]],
        }
        for i, j in scartato_come_duplicato_di.items()
    ]
    return tenute, scartate


# --------------------------------------------------------------- blocchi (solo per motivazioni troppo lunghe)


def _costruisci_blocchi(motivazione: str, testo_integrale: str, node_id: str, budget_token_input: int) -> list[str]:
    """Divide la motivazione in blocchi CONTIGUI (nessuna sovrapposizione,
    nessun buco) usando i confini di frase di segmenta_provvedimenti - non
    per indicizzare, solo per stare dentro il contesto. L'ancoraggio a
    valle cerca sempre nella motivazione INTERA, non nel singolo blocco
    (difetto [7]: percorso segmentato e non segmentato producono lo STESSO
    schema perche' condividono lo stesso codice di ancoraggio/costruzione
    record a valle di questa funzione - solo l'INPUT al modello cambia)."""
    segmenti = segmenta_provvedimenti.segmenta_motivazione(node_id, motivazione, testo_integrale)
    if not segmenti:
        return [motivazione] if motivazione.strip() else []

    budget_char = int(budget_token_input * CHAR_PER_TOKEN_PRUDENTE)
    offset_base = testo_integrale.index(motivazione)

    blocchi: list[str] = []
    inizio_blocco_locale = segmenti[0].offset_inizio - offset_base
    fine_blocco_locale = segmenti[0].offset_fine - offset_base

    for seg in segmenti[1:]:
        s_inizio = seg.offset_inizio - offset_base
        s_fine = seg.offset_fine - offset_base
        if (s_fine - inizio_blocco_locale) > budget_char:
            blocchi.append(motivazione[inizio_blocco_locale:fine_blocco_locale])
            inizio_blocco_locale = s_inizio
        fine_blocco_locale = s_fine
    blocchi.append(motivazione[inizio_blocco_locale:fine_blocco_locale])
    return blocchi


# --------------------------------------------------------------- estrazione + ancoraggio


@dataclass
class EsitoProvvedimento:
    node_id: str
    coppie: list[dict] = field(default_factory=list)
    scartate: list[dict] = field(default_factory=list)
    coppie_generate_dal_modello: int = 0
    elementi_non_estraibili: list[str] = field(default_factory=list)
    segmentato: bool = False
    n_blocchi: int = 1
    passaggi_falliti: list[str] = field(default_factory=list)
    processabile: bool = True
    motivo_non_processabile: str | None = None


def _ancora(motivazione: str, citazione: str | None) -> dict | None:
    if citazione is None:
        return None
    blocchi = [{"blocco_id": "B01", "inizio": 0, "fine": len(motivazione)}]
    return localizza.localizza(motivazione, blocchi, citazione)


def _processa_coppia(c: dict, *, esito: "EsitoProvvedimento", node_id: str,
                     motivazione: str, testo_integrale: str, offset_base: int) -> dict | None:
    """Filtri, ancoraggio e costruzione del record di UNA coppia grezza uscita
    dal modello. Estratta dal ciclo di estrai_provvedimento() quando e' stata
    aggiunta la variante a due passate (estrai_provvedimento_due_passate): le
    due strade producono candidati in modo diverso ma devono passare per gli
    STESSI otto filtri, altrimenti i loro risultati non sono confrontabili e
    l'audit del 2026-08-25 varrebbe solo per una delle due.

    Ritorna il record da tenere, oppure None dopo avere gia' registrato lo
    scarto in esito.scartate. Aggiorna esito.coppie_generate_dal_modello."""
    esito.coppie_generate_dal_modello += 1

    # Normalizzazione: il modello a volte emette "" o "..." invece
    # di null/lista-vuota per un oggetto placeholder degenere - una
    # stringa vuota o fatta di soli puntini/spazi non e' un dato.
    ecc_testo = (c.get("eccezione_letterale") or "").strip()
    if not ecc_testo or ecc_testo in ("...", "…"):
        esito.scartate.append({"eccezione_letterale": ecc_testo, "motivo_scarto": "vuoto_o_placeholder"})
        return None

    # Difetto [1]: elisione esplicita dell'eccezione, scarto a monte
    # in ogni caso (vedi contiene_elisione_esplicita) - ma la CAUSA
    # (ereditata dalla fonte o inventata dal modello) e' tracciata
    # separatamente, non e' la stessa cosa da riportare.
    if contiene_elisione_esplicita(ecc_testo):
        ereditata = elisione_ereditata_da_fonte(ecc_testo, testo_integrale)
        esito.scartate.append({
            "eccezione_letterale": ecc_testo,
            "motivo_scarto": "elisione_esplicita_eccezione",
            "elisione_ereditata_da_fonte": ereditata,
        })
        return None

    parte_grezza = (c.get("parte_che_la_solleva") or "").strip()

    # Difetto [3]: falsi positivi sistematici, per classe.
    motivo_fp = classifica_falso_positivo(ecc_testo, parte_grezza)
    if motivo_fp is not None:
        esito.scartate.append({"eccezione_letterale": ecc_testo, "parte_che_la_solleva": parte_grezza, "motivo_scarto": motivo_fp})
        return None

    ancora_ecc = _ancora(motivazione, ecc_testo)
    if ancora_ecc["stato"] != "ancorata":
        esito.scartate.append({
            "eccezione_letterale": ecc_testo,
            "motivo_scarto": "non_ancorata",
            "dettaglio_ancoraggio": ancora_ecc.get("motivo", ancora_ecc["stato"]),
        })
        return None

    # Difetto [1]: ratio con elisione esplicita -> trattata come
    # assente (non scarta l'intera coppia: l'eccezione resta
    # valida, solo la ratio dichiarata incompleta dal modello non
    # e' utilizzabile).
    ratio_grezza = (c.get("ratio_letterale") or "").strip()
    ratio_scartata_motivo = None
    ratio_elisione_ereditata = None
    if ratio_grezza and contiene_elisione_esplicita(ratio_grezza):
        ratio_scartata_motivo = "elisione_esplicita_ratio"
        ratio_elisione_ereditata = elisione_ereditata_da_fonte(ratio_grezza, testo_integrale)
        ratio = None
    elif ratio_grezza and ratio_grezza not in ("...", "…"):
        ratio = ratio_grezza
    else:
        ratio = None

    parte = parte_grezza or "non_specificata"
    ancora_ratio = _ancora(motivazione, ratio) if ratio else None
    ratio_ancorata = bool(ancora_ratio and ancora_ratio["stato"] == "ancorata")

    offset_inizio = offset_base + ancora_ecc["inizio"]
    offset_fine = offset_base + ancora_ecc["fine"]
    ratio_offset_inizio = (offset_base + ancora_ratio["inizio"]) if ratio_ancorata else None
    ratio_offset_fine = (offset_base + ancora_ratio["fine"]) if ratio_ancorata else None

    record = {
        "node_id": node_id,
        # NON citabili (output del modello) - vedi META_AVVISO_USO_DATI.
        "eccezione_letterale": ecc_testo,
        "ratio_letterale": ratio,
        # CITABILI (difetto [1]): ricalcolati da Python dal testo_integrale.
        "eccezione_verbatim": calcola_verbatim(testo_integrale, offset_inizio, offset_fine),
        "ratio_verbatim": calcola_verbatim(testo_integrale, ratio_offset_inizio, ratio_offset_fine) if ratio_ancorata else None,
        "parte_che_la_solleva": parte,
        "parte_normalizzata": normalizza_parte(parte),  # difetto [4]
        "esito": c["esito"],
        "offset_inizio": offset_inizio,
        "offset_fine": offset_fine,
        "eccezione_corrispondenza": ancora_ecc["corrispondenza"],
        "eccezione_similarita": ancora_ecc["similarita"],
        "ratio_stato_ancora": ancora_ratio["stato"] if ancora_ratio else "nessuna_ratio",
        "ratio_offset_inizio": ratio_offset_inizio,
        "ratio_offset_fine": ratio_offset_fine,
        "ratio_scartata_motivo": ratio_scartata_motivo,
        "ratio_elisione_ereditata_da_fonte": ratio_elisione_ereditata,
        "classificazione_dato": "citabile" if ratio_ancorata else "strategico",
    }
    return record


def estrai_provvedimento(base_url: str, provv: dict, n_ctx: int, timeout: int = 1800,
                          seed: int = SEED) -> EsitoProvvedimento:
    node_id = provv["node_id"]
    motivazione = provv.get("motivazione")
    esito = EsitoProvvedimento(node_id=node_id)

    # Difetto [7]: percorso esplicito per motivazione nulla, non
    # un'esclusione silenziosa in cima allo script chiamante. 3/41
    # provvedimenti nel corpus di riferimento cadono qui - verificato che
    # ALMENO uno di questi ha testo_integrale con un ragionamento (clausole
    # "considerato che/ritenuto che/rilevato che" fra ORDINANZA e P.Q.M.,
    # ordinanze ex artt. 283/351 c.p.c.): motivazione=None e' con ogni
    # evidenza un buco del parser su questo formato, non l'assenza reale di
    # una motivazione - segnalato nel report finale, il grafo resta fuori
    # perimetro (CLAUDE.md).
    if not motivazione:
        esito.processabile = False
        esito.motivo_non_processabile = "motivazione_nulla_nel_grafo"
        return esito

    testo_integrale = provv["testo_integrale"]
    budget_input = n_ctx - RISERVA_OUTPUT_TOKEN - RISERVA_PROMPT_TOKEN - MARGINE_TOKEN
    n_token_motivazione = llama_server_client.conta_token(base_url, motivazione, timeout=60)

    if n_token_motivazione <= budget_input:
        blocchi_testo = [motivazione]
    else:
        esito.segmentato = True
        blocchi_testo = _costruisci_blocchi(motivazione, testo_integrale, node_id, budget_input)
        esito.n_blocchi = len(blocchi_testo)

    offset_base = testo_integrale.index(motivazione)
    candidati: list[dict] = []

    for i, blocco in enumerate(blocchi_testo):
        prompt = PROMPT_COPPIE.format(testo=blocco)
        try:
            grezzo = llama_server_client.completa_json(
                base_url, prompt, SCHEMA_COPPIE, n_predict=RISERVA_OUTPUT_TOKEN,
                temperature=TEMPERATURA, repeat_penalty=REPEAT_PENALTY, timeout=timeout,
                seed=seed,
            )
        except llama_server_client.RispostaTroncata:
            esito.passaggi_falliti.append(f"blocco_{i + 1}")
            continue
        except json.JSONDecodeError:
            esito.passaggi_falliti.append(f"blocco_{i + 1}_json_non_valido")
            continue

        esito.elementi_non_estraibili.extend(f"[blocco {i + 1}] {x}" for x in grezzo.get("elementi_non_estraibili", []))

        for c in grezzo.get("coppie", []):
            record = _processa_coppia(
                c, esito=esito, node_id=node_id, motivazione=motivazione,
                testo_integrale=testo_integrale, offset_base=offset_base,
            )
            if record is not None:
                candidati.append(record)

    # Difetto [2]: dedup per span DOPO l'ancoraggio, su tutti i blocchi
    # insieme (un duplicato puo' comparire in blocchi diversi tanto quanto
    # nello stesso blocco).
    tenute, scartate_dup = deduplica_per_span(candidati)
    esito.coppie = tenute
    esito.scartate.extend(scartate_dup)

    return esito


def _blocchi_di(base_url: str, provv: dict, n_ctx: int, esito: "EsitoProvvedimento") -> list[str]:
    """Segmentazione della motivazione, identica per le due varianti di
    estrazione: se differissero, il confronto fra le due misurerebbe anche la
    segmentazione invece della sola estrazione."""
    motivazione = provv["motivazione"]
    budget_input = n_ctx - RISERVA_OUTPUT_TOKEN - RISERVA_PROMPT_TOKEN - MARGINE_TOKEN
    n_token = llama_server_client.conta_token(base_url, motivazione, timeout=60)
    if n_token <= budget_input:
        return [motivazione]
    esito.segmentato = True
    blocchi = _costruisci_blocchi(motivazione, provv["testo_integrale"], provv["node_id"], budget_input)
    esito.n_blocchi = len(blocchi)
    return blocchi


def estrai_provvedimento_due_passate(base_url: str, provv: dict, n_ctx: int, timeout: int = 1800,
                                     seed: int = SEED) -> EsitoProvvedimento:
    """Variante a due passate - censimento delle questioni, poi dettaglio di
    ciascuna. Vedi la sezione "due passate" in cima al modulo per il perche'.

    Stessa firma, stesso EsitoProvvedimento e stessi filtri di
    estrai_provvedimento(): le due funzioni sono intercambiabili, ed e' cio'
    che rende confrontabili le loro misure sullo stesso golden set.

    Costa piu' chiamate: una per blocco nella passata 1, piu' una per ogni
    questione censita nella passata 2. Su una motivazione con otto questioni
    sono nove chiamate invece di una."""
    node_id = provv["node_id"]
    motivazione = provv.get("motivazione")
    esito = EsitoProvvedimento(node_id=node_id)

    if not motivazione:
        esito.processabile = False
        esito.motivo_non_processabile = "motivazione_nulla_nel_grafo"
        return esito

    testo_integrale = provv["testo_integrale"]
    offset_base = testo_integrale.index(motivazione)
    blocchi_testo = _blocchi_di(base_url, provv, n_ctx, esito)
    candidati: list[dict] = []

    for i, blocco in enumerate(blocchi_testo):
        etichetta = f"blocco_{i + 1}"
        try:
            censimento = llama_server_client.completa_json(
                base_url, PROMPT_CENSIMENTO.format(testo=blocco), SCHEMA_CENSIMENTO,
                n_predict=RISERVA_OUTPUT_TOKEN, temperature=TEMPERATURA,
                repeat_penalty=REPEAT_PENALTY, timeout=timeout, seed=seed,
            )
        except llama_server_client.RispostaTroncata:
            esito.passaggi_falliti.append(f"{etichetta}_censimento")
            continue
        except json.JSONDecodeError:
            esito.passaggi_falliti.append(f"{etichetta}_censimento_json_non_valido")
            continue

        esito.elementi_non_estraibili.extend(
            f"[{etichetta}] {x}" for x in censimento.get("elementi_non_estraibili", []))

        for n, questione in enumerate(censimento.get("questioni", []), 1):
            testo_questione = (questione.get("eccezione_letterale") or "").strip()
            parte = (questione.get("parte_che_la_solleva") or "").strip()

            # Una questione vuota non merita una chiamata di dettaglio: la si
            # manda comunque a _processa_coppia, che la registra fra le
            # scartate come "vuoto_o_placeholder" - cosi' i contatori della
            # variante a due passate restano confrontabili con quelli della
            # passata unica invece di perdere per strada gli scarti.
            if not testo_questione or testo_questione in ("...", "…"):
                dettaglio = {"esito": "non_chiaro", "ratio_letterale": None}
            else:
                try:
                    dettaglio = llama_server_client.completa_json(
                        base_url,
                        PROMPT_DETTAGLIO.format(
                            testo=blocco,
                            parte=parte or "una parte",
                            questione=testo_questione.replace('"', "'"),
                        ),
                        SCHEMA_DETTAGLIO, n_predict=RISERVA_OUTPUT_DETTAGLIO_TOKEN,
                        temperature=TEMPERATURA, repeat_penalty=REPEAT_PENALTY,
                        timeout=timeout, seed=seed,
                    )
                except llama_server_client.RispostaTroncata:
                    esito.passaggi_falliti.append(f"{etichetta}_dettaglio_{n}")
                    # La questione e' stata censita: non la si butta perche' la
                    # seconda chiamata e' fallita. Entra senza esito accertato.
                    dettaglio = {"esito": "non_chiaro", "ratio_letterale": None}
                except json.JSONDecodeError:
                    esito.passaggi_falliti.append(f"{etichetta}_dettaglio_{n}_json_non_valido")
                    dettaglio = {"esito": "non_chiaro", "ratio_letterale": None}

            record = _processa_coppia(
                {
                    "eccezione_letterale": testo_questione,
                    "parte_che_la_solleva": parte,
                    "esito": dettaglio.get("esito") or "non_chiaro",
                    "ratio_letterale": dettaglio.get("ratio_letterale"),
                },
                esito=esito, node_id=node_id, motivazione=motivazione,
                testo_integrale=testo_integrale, offset_base=offset_base,
            )
            if record is not None:
                candidati.append(record)

    tenute, scartate_dup = deduplica_per_span(candidati)
    esito.coppie = tenute
    esito.scartate.extend(scartate_dup)
    return esito


# --------------------------------------------------------------- [6] vocabolario per contrasto log-odds

_STOPWORD = {
    "che", "non", "per", "con", "una", "uno", "gli", "del", "della", "dello", "delle", "dei", "degli",
    "alla", "allo", "agli", "alle", "nel", "nella", "nello", "nelle", "dal", "dalla", "dallo", "dagli",
    "dalle", "sul", "sulla", "sullo", "sugli", "sulle", "come", "anche", "piu", "meno", "cui", "quale",
    "quali", "questo", "questa", "questi", "queste", "quello", "quella", "quelli", "quelle", "essere",
    "aveva", "avevano", "essendo", "stato", "stata", "stati", "state", "cosi", "detto", "detta", "gia",
    "solo", "sono", "erano", "loro", "essa", "esso", "essi", "esse", "tale", "tali", "tra", "fra",
}


def _parole_normalizzate(testo: str) -> list[str]:
    testo = unicodedata.normalize("NFKC", testo).lower()
    parole = re.findall(r"[a-zàèéìòù]{4,}", testo)
    return [p for p in parole if p not in _STOPWORD]


def _finestra_prima_di(testo: str, offset: int, larghezza: int) -> str:
    return testo[max(0, offset - larghezza):offset]


def contrasto_log_odds(
    coppie_ancorate: list[dict],
    testo_per_nodo: dict[str, str],
    larghezza_finestra: int = 150,
    seed: int = 20260825,
) -> list[tuple[str, float, int, int]]:
    """Difetto [6]: contrasto log-odds fra il contesto che precede ogni
    eccezione ANCORATA e una finestra casuale della STESSA motivazione -
    stesso numero di campioni per motivazione (un controllo per ogni
    trattamento), seed fissato. Non la frequenza grezza sulle 206 coppie
    contro l'intero campione (48 su 206 erano numeratore/denominatore
    diversi: solo le ANCORATE hanno un contesto, il resto no).

    Ritorna [(parola, log_odds, conteggio_trattamento, conteggio_controllo)],
    ordinato per log_odds decrescente. log_odds positivo = la parola
    ricorre piu' spesso subito prima di un'eccezione che altrove nella
    stessa motivazione; smoothing +1 per evitare divisioni per zero su
    parole rare in un lato solo."""
    rng = random.Random(seed)
    conteggio_trattamento: Counter = Counter()
    conteggio_controllo: Counter = Counter()
    totale_trattamento = 0
    totale_controllo = 0

    for c in coppie_ancorate:
        testo = testo_per_nodo.get(c["node_id"])
        if not testo:
            continue

        contesto_trattamento = _finestra_prima_di(testo, c["offset_inizio"], larghezza_finestra)
        parole_t = _parole_normalizzate(contesto_trattamento)
        conteggio_trattamento.update(parole_t)
        totale_trattamento += len(parole_t)

        if len(testo) <= larghezza_finestra:
            offset_casuale = len(testo)
        else:
            offset_casuale = rng.randint(larghezza_finestra, len(testo))
        contesto_controllo = _finestra_prima_di(testo, offset_casuale, larghezza_finestra)
        parole_c = _parole_normalizzate(contesto_controllo)
        conteggio_controllo.update(parole_c)
        totale_controllo += len(parole_c)

    vocabolario = set(conteggio_trattamento) | set(conteggio_controllo)
    risultati = []
    for parola in vocabolario:
        t = conteggio_trattamento.get(parola, 0)
        ctr = conteggio_controllo.get(parola, 0)
        import math
        log_odds = math.log((t + 1) / (totale_trattamento - t + 1)) - math.log((ctr + 1) / (totale_controllo - ctr + 1))
        risultati.append((parola, log_odds, t, ctr))

    risultati.sort(key=lambda r: -r[1])
    return risultati


# --------------------------------------------------------------- [5] verifica indipendenza dei contatori


def verifica_contatori_indipendenti(scartate_totali: list[dict], coppie_totali: list[dict]) -> dict:
    """Difetto [5]: 'coppie_scartate_non_ancorate' e il conteggio delle
    corrispondenze 'fuzzy' pescavano dallo stesso numero (61) nella corsa
    originale - non necessariamente dalla stessa lista (verificato che nel
    codice sono percorsi disgiunti: le non-ancorate non entrano mai in
    'coppie'), ma la coincidenza numerica va comunque riportata, non solo
    spiegata via codice. Ritorna i due conteggi e se coincidono, per il
    report finale."""
    n_non_ancorate = sum(1 for s in scartate_totali if s.get("motivo_scarto") == "non_ancorata")
    n_fuzzy = sum(1 for c in coppie_totali if c.get("eccezione_corrispondenza") == "fuzzy")
    return {
        "coppie_scartate_non_ancorate": n_non_ancorate,
        "coppie_ancorate_fuzzy": n_fuzzy,
        "coincidono": n_non_ancorate == n_fuzzy,
        "liste_disgiunte_per_costruzione": True,  # le non-ancorate non entrano mai in coppie_totali
    }


# --------------------------------------------------------------- corsa sul corpus intero


def estrai_corpus(
    base_url: str,
    provvedimenti: list[dict],
    n_ctx: int,
    seed: int = SEED,
    seed_log_odds: int = 20260825,
    on_progress: "callable | None" = None,
) -> dict:
    """Corre estrai_provvedimento su TUTTI i provvedimenti passati (nessun
    pre-filtro: la motivazione nulla e' un percorso esplicito dentro
    estrai_provvedimento, difetto [7]) e assembla l'output con
    meta/conteggi/contrasto log-odds. Struttura identica indipendentemente
    da quanti provvedimenti sono stati segmentati (stesso schema, difetto
    [7]). on_progress(indice, totale, node_id, esito), se dato, viene
    chiamato dopo ogni provvedimento - solo per osservabilita' su una corsa
    lunga, nessun effetto sul risultato."""
    coppie_totali: list[dict] = []
    scartate_totali: list[dict] = []
    per_provvedimento: dict[str, int] = {}
    segmentati = []
    falliti = {}
    non_processabili = []
    non_estraibili_totali: list[str] = []
    coppie_generate_totale = 0

    for indice, p in enumerate(provvedimenti, 1):
        node_id = p["node_id"]
        esito = estrai_provvedimento(base_url, p, n_ctx, seed=seed)
        if not esito.processabile:
            non_processabili.append({"node_id": node_id, "motivo": esito.motivo_non_processabile})
        else:
            coppie_totali.extend(esito.coppie)
            scartate_totali.extend([{**s, "node_id": s.get("node_id", node_id)} for s in esito.scartate])
            per_provvedimento[node_id] = len(esito.coppie)
            coppie_generate_totale += esito.coppie_generate_dal_modello
            non_estraibili_totali.extend(f"[{node_id}] {x}" for x in esito.elementi_non_estraibili)
            if esito.segmentato:
                segmentati.append({"node_id": node_id, "n_blocchi": esito.n_blocchi, "lunghezza_motivazione": len(p["motivazione"])})
            if esito.passaggi_falliti:
                falliti[node_id] = esito.passaggi_falliti
        if on_progress is not None:
            on_progress(indice, len(provvedimenti), node_id, esito)

    testo_per_nodo = {p["node_id"]: p.get("testo_integrale", "") for p in provvedimenti}
    log_odds = contrasto_log_odds(coppie_totali, testo_per_nodo, seed=seed_log_odds)

    props = llama_server_client.proprieta_server(base_url)
    conteggi_scarto: dict[str, int] = {}
    for s in scartate_totali:
        m = s.get("motivo_scarto", "sconosciuto")
        conteggi_scarto[m] = conteggi_scarto.get(m, 0) + 1

    distribuzione_parte = {}
    for c in coppie_totali:
        pn = c["parte_normalizzata"]
        distribuzione_parte[pn] = distribuzione_parte.get(pn, 0) + 1

    verifica_contatori = verifica_contatori_indipendenti(scartate_totali, coppie_totali)

    return {
        "meta": {
            "versione_modulo": VERSIONE_MODULO,
            "esecuzione": {
                "modello": props.get("modello"),
                "n_ctx": props.get("n_ctx"),
                "temperature_per_passo": {"eccezioni_coppie": TEMPERATURA},
                "repeat_penalty": REPEAT_PENALTY,
                "cache_prompt": CACHE_PROMPT,
                "seed": seed,
                "motore_similarita": "rapidfuzz" if localizza.RAPIDFUZZ_DISPONIBILE else "difflib",
            },
            "provvedimenti_totali_nel_grafo": len(provvedimenti),
            "provvedimenti_processati": len(per_provvedimento),
            "provvedimenti_non_processabili": non_processabili,
            "provvedimenti_segmentati": segmentati,
            "passaggi_falliti": falliti,
            "coppie_generate_dal_modello": coppie_generate_totale,
            "conteggi_scarto": conteggi_scarto,
            "elementi_non_estraibili": non_estraibili_totali,
            "verifica_contatori_indipendenti": verifica_contatori,
            "soglia_iou_duplicato": SOGLIA_IOU_DUPLICATO,
        },
        "coppie": coppie_totali,
        "scartate": scartate_totali,
        "conteggi_per_provvedimento": per_provvedimento,
        "distribuzione_parte_normalizzata": distribuzione_parte,
        "contrasto_log_odds_top30": [
            {"parola": p, "log_odds": round(lo, 4), "trattamento": t, "controllo": c}
            for p, lo, t, c in log_odds[:30]
        ],
        "_avviso_uso_dati": META_AVVISO_USO_DATI,
    }


if __name__ == "__main__":
    provvedimenti = carica_provvedimenti()
    con_motivazione = [p for p in provvedimenti if p.get("motivazione")]
    print(f"provvedimenti totali: {len(provvedimenti)}, con motivazione: {len(con_motivazione)}")
    lens = sorted(len(p["motivazione"]) for p in con_motivazione)
    print(f"lunghezza motivazione: min={lens[0]} max={lens[-1]}")
    print("OK - nessuna chiamata di rete in questo smoke test.")
