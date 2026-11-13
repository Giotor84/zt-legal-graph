"""Tipo di atto e grado, calcolati in Python invece che chiesti al modello.

## Perche' non lo chiede piu' al modello (contratto 1.26)

`tipo_atto` e `grado` sono SCRITTI nell'intestazione dell'atto: il giudice
adito, la norma invocata, il nome che l'atto si da'. Non richiedono lettura
giuridica, richiedono di guardare le prime righe. Chiederli a un modello
significa accettare che indovini, e STATO_PROGETTO §7.14 registra cosa
succede quando indovina: su una corsa vera ha risposto
`opposizione_esecuzione / esecutiva` per una comparsa conclusionale in
opposizione a decreto ingiuntivo, la cui unica materia era l'efficacia
probatoria del saldaconto. Quell'errore non resta li': `tipo_atto` e
`fase_processuale` alimentano l'instradamento per famiglia in Fase 2.

Al modello restano i campi che richiedono davvero lettura
(`natura_rapporto`, `qualita_parti`), dove un'euristica sbaglierebbe.

## I tre strati, e perche' proprio tre

  1. NORMA in testa, risolta sul grafo. E' la fonte piu' forte - quando
     c'e', VINCE - ma parla di rado. Funziona solo da quando il grafo ha
     l'alberatura: `art. 650` sta nel Capo "DEL PROCEDIMENTO DI
     INGIUNZIONE" e qualifica l'atto, `art. 125` sta nel Capo "DELLE FORME
     DEGLI ATTI" e non lo qualifica. Senza l'albero sono indistinguibili.
  2. GIUDICE ADITO nell'intestazione. Da' il GRADO, non il tipo.
  3. AUTODENOMINAZIONE. Da' il TIPO quando la norma manca.

## Cosa e' stato misurato davvero (2026-08-31, 52 atti nativi)

Misura di QUESTA implementazione, non i numeri di progetto di §7.24:

    strato 1 (norma sul grafo)   ha parlato in    6/52
    strato 2 (giudice adito)                     52/52
    strato 3 (autodenominazione)                 44/52
    almeno uno dei tre                           52/52

    tipo_atto risolto                            45/52  (87%)
    grado risolto                                50/52  (96%)
    disaccordi dichiarati                         2/52

**Non e' una misura di correttezza, e' una misura di copertura.** Dire
quante volte il modulo risponde non dice quante volte risponde BENE:
serve il golden set (STATO_PROGETTO §7.1), che e' lavoro dell'utente. Dai
nomi dei file - indizio, non verita' - si vedono almeno 4 errori residui,
tutti della stessa classe: memorie e comparse depositate DENTRO un
giudizio di opposizione, classificate come l'opposizione che raccontano.
La passata sui titoli (sotto) ne ha corretti alcuni, non tutti.

## Confronto col modello, sugli stessi 45 atti del batch 2026-08-30

Concordano 16 volte su 45 (36%). Il modello ha risposto
`comparsa_risposta` per 21 atti su 45, fra cui file che si intitolano
"RICORSO PER CASSAZIONE" e "ATTO DI APPELLO". Quel valore e'
STRUTTURALMENTE sbagliato in questa pipeline, e per dirlo non serve un
golden set: l'ingresso e' per definizione l'atto del DEBITORE, mentre la
comparsa di costituzione e risposta e' l'atto che scriviamo NOI.

Il secondo motivo per preferire il calcolo, indipendente dall'accuratezza:
questo modulo dice sempre COME e' arrivato alla risposta (`strati`,
`disaccordi`), quindi un errore si diagnostica. Il modello no.

## La regola che conta piu' degli strati

**Quando due strati DISCORDANO si dichiara `non_desumibile` invece di
scegliere.** Un disaccordo dichiarato e' un dato che si puo' guardare; una
scelta silenziosa fra due letture e' un errore che si propaga in Fase 2 e
non lascia traccia. Questo modulo preferisce non sapere.

## Il grafo e' opzionale, di proposito

Lo strato 1 e' l'unico che tocca il grafo, ed e' quello che parla meno
(6/52). `--solo-fase1 --batch` deve funzionare SENZA store ne' grafo - e'
l'invariante su cui poggia la costruzione del golden set - quindi
`alberatura_per_articolo` e' opzionale: passando `None` restano gli strati
2 e 3, che da soli coprono 44/52 sul tipo e 52/52 sul grado. Il grafo
aggiunge precisione dove conta (distingue la norma che definisce l'atto da
quella che ne regola la forma), non e' un prerequisito.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

#: Tre finestre, non una: gli strati hanno profili di rischio diversi e
#: misurarli con la stessa soglia e' stato un errore (misura del
#: 2026-08-31 sui 52 atti nativi).
#:
#: NORMA - 10 righe. Non e' una manopola: e' il massimo della precisione
#: misurata, a 20 si raccolgono gia' norme incidentali (art. 58 TUB sulla
#: cessione, art. 83 c.p.c. sulla procura) che non qualificano l'atto.
#:
#: GIUDICE - 60 righe, dove la copertura arriva a 52/52 (era 44/52 a 10).
#: Allargare qui non porta rumore: il nome di una corte che compare in
#: intestazione e' il giudice adito anche se arriva dopo le parti e i
#: difensori, e un atto non nomina due giudici aditi diversi.
#:
#: DENOMINAZIONE - 60 righe (42/52; a 100 sono 44, non abbastanza per
#: pagare il rischio di raccogliere la narrativa del processo altrui).
RIGHE_NORMA = 10
RIGHE_GIUDICE = 60
RIGHE_DENOMINAZIONE = 60

NON_DESUMIBILE = "non_desumibile"

TIPI = ("opposizione_decreto_ingiuntivo", "opposizione_esecuzione",
        "comparsa_risposta", "memoria", "atto_appello", "ricorso_cassazione",
        NON_DESUMIBILE)
GRADI = ("primo_grado", "appello", "legittimita", NON_DESUMIBILE)


def _piatto(testo: str) -> str:
    """Minuscolo, senza accenti, spazi normalizzati. Gli atti arrivano da
    PDF di studi diversi: maiuscolo pieno, spaziature irregolari, accenti
    resi in modi diversi."""
    senza = unicodedata.normalize("NFKD", testo)
    senza = "".join(c for c in senza if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", senza).lower()


def righe_intestazione(testo_atto: str, quante: int) -> list[str]:
    righe = [r.strip() for r in testo_atto.splitlines()]
    return [r for r in righe if r][:quante]


# --------------------------------------------------------------- strato 2
#: Il giudice adito da' il grado. L'ordine conta: "corte di cassazione"
#: prima di "corte", "corte d'appello" prima di "tribunale" (un atto di
#: appello nomina spesso anche il tribunale che ha deciso in primo grado).
_GIUDICE_GRADO = (
    (re.compile(r"\bcorte (?:suprema )?di cassazione\b"), "legittimita"),
    (re.compile(r"\bsuprema corte\b"), "legittimita"),
    (re.compile(r"\bcorte d(?:i |')appello\b"), "appello"),
    (re.compile(r"\bcorte di appello\b"), "appello"),
    (re.compile(r"\btribunale\b"), "primo_grado"),
    (re.compile(r"\bgiudice di pace\b"), "primo_grado"),
)


def grado_da_giudice(testo_atto: str) -> str | None:
    """Strato 2. `None` se nessun giudice e' nominato in testa: e' diverso
    da `non_desumibile`, che e' un esito, mentre questo e' un'astensione
    dello strato."""
    testa = _piatto(" \n ".join(righe_intestazione(testo_atto, RIGHE_GIUDICE)))
    for pattern, grado in _GIUDICE_GRADO:
        if pattern.search(testa):
            return grado
    return None


# --------------------------------------------------------------- strato 3
#: Come l'atto si chiama da se'. L'ordine NON e' dal generico allo
#: specifico: e' dal meno ambiguo al piu' ambiguo, che qui e' un'altra cosa.
#:
#: Cassazione e appello per primi. Misurato il 2026-08-31: un atto di
#: appello contro una sentenza resa in opposizione a decreto ingiuntivo
#: RACCONTA quell'opposizione nelle prime righe, e con l'ordine opposto la
#: narrazione del grado precedente vinceva sulla denominazione dell'atto
#: corrente (2 casi su 52: "ATTO DI APPELLO BIANCHI", "Opposizione ROSSI
#: MARIO" davanti alla Cassazione). "Atto di appello" e "ricorso per
#: cassazione" nominano l'atto che si sta leggendo e nient'altro;
#: "opposizione a decreto ingiuntivo" puo' essere denominazione o storia.
#:
#: NON c'e' "atto di citazione" da solo, ed e' una scelta: una citazione
#: puo' introdurre un'ordinaria quanto un'opposizione, quindi da sola non
#: qualifica nulla. Contarla porterebbe la copertura a 52/52 scegliendo in
#: silenzio fra due letture - il difetto che questo modulo esiste per
#: evitare. Meglio `non_desumibile` dichiarato.
_AUTODENOMINAZIONE = (
    (re.compile(r"ricorso per cassazione|controricorso"), "ricorso_cassazione"),
    (re.compile(r"atto di appello|comparsa (?:di costituzione )?in appello|"
                r"appello avverso|citazione in appello"), "atto_appello"),
    (re.compile(r"opposizione (?:tardiva )?a(?:l)? (?:decreto|d\.?i\.?)\b|"
                r"opposizione a decreto ingiuntivo|"
                r"\bopposizione a d\.i\.|"
                r"opposizione avverso (?:il )?(?:decreto|d\.?i\.?)|"
                r"avverso il decreto ingiuntivo|"
                r"oppone.{0,40}decreto ingiuntivo"), "opposizione_decreto_ingiuntivo"),
    (re.compile(r"opposizione all(?:')?esecuzione|"
                r"\bart(?:icol)?i?\.? ?615\b|\bart(?:icol)?i?\.? ?617\b|"
                r"opposizione a precetto|opposizione agli atti esecutivi"),
     "opposizione_esecuzione"),
    (re.compile(r"comparsa di (?:costituzione|risposta)|comparsa di costituzione e risposta"),
     "comparsa_risposta"),
    (re.compile(r"\bmemoria\b|comparsa conclusionale|note (?:di )?repl(?:ica|iche)"),
     "memoria"),
)


#: Una denominazione e' un TITOLO: riga corta, a se' stante, spesso in
#: maiuscolo, non chiusa da punto fermo. Dentro un periodo la stessa
#: espressione e' quasi sempre narrazione del processo ("...avverso il
#: decreto ingiuntivo n. 450/2017 emesso il 19 marzo, la sig.ra proponeva
#: opposizione..."), e la narrazione parla del grado PRECEDENTE.
#:
#: Misurato il 2026-08-31: senza questa distinzione, memorie e comparse
#: depositate dentro un giudizio di opposizione venivano classificate come
#: l'opposizione stessa, perche' la raccontano nelle prime righe. E'
#: la stessa causa del caso "ATTO DI APPELLO BIANCHI", vista su un'altra
#: classe di atti.
_LUNGHEZZA_TITOLO = 90


def _sembra_titolo(riga: str) -> bool:
    testo = riga.strip()
    if not testo or len(testo) > _LUNGHEZZA_TITOLO:
        return False
    if testo.endswith((".", ";", ",")):
        return False
    lettere = [c for c in testo if c.isalpha()]
    if not lettere:
        return False
    # o e' in maiuscolo, o e' comunque una riga breve e isolata
    return sum(1 for c in lettere if c.isupper()) / len(lettere) > 0.6 or len(testo) <= 60


def tipo_da_autodenominazione(testo_atto: str) -> str | None:
    """Strato 3. Il nome che l'atto si da'.

    Due passate, in quest'ordine: prima solo sulle righe che sembrano un
    TITOLO, poi - se nessuna ha parlato - su tutta la testa. La seconda
    passata resta perche' non tutti i PDF conservano l'impaginazione, e
    perderla costerebbe piu' di quanto costi qualche narrazione presa per
    denominazione."""
    righe = righe_intestazione(testo_atto, RIGHE_DENOMINAZIONE)
    titoli = _piatto(" \n ".join(r for r in righe if _sembra_titolo(r)))
    for pattern, tipo in _AUTODENOMINAZIONE:
        if pattern.search(titoli):
            return tipo
    tutto = _piatto(" \n ".join(righe))
    for pattern, tipo in _AUTODENOMINAZIONE:
        if pattern.search(tutto):
            return tipo
    return None


# --------------------------------------------------------------- strato 1
#: Norme del c.p.c. che QUALIFICANO un atto, riconosciute per la loro
#: posizione nell'albero del codice e non per un elenco scritto a mano: e'
#: il capo che dice se una norma definisce un atto o ne regola la forma.
#: La chiave e' un frammento del capo, confrontato in minuscolo.
_CAPI_CHE_QUALIFICANO = {
    "procedimento d'ingiunzione": "opposizione_decreto_ingiuntivo",
    "procedimento di ingiunzione": "opposizione_decreto_ingiuntivo",
    "opposizioni": "opposizione_esecuzione",
    "impugnazioni": "atto_appello",
}

_RIFERIMENTO_NORMA = re.compile(
    r"art(?:icol)?[.i]?\s*(\d{1,4}(?:[-\s](?:bis|ter|quater|quinquies|sexies|septies|octies))?)"
    r"[^.;\n]{0,30}?\bc\.?\s*p\.?\s*c\.?\b", re.I)


@dataclass
class EsitoStrati:
    """Cosa ha detto ciascuno strato, prima di comporli. Serve a poter
    guardare un disaccordo invece di scoprirne solo l'effetto."""
    tipo_da_norma: str | None = None
    grado_da_norma: str | None = None
    grado_da_giudice: str | None = None
    tipo_da_autodenominazione: str | None = None
    norme_viste: list[str] = field(default_factory=list)
    disaccordi: list[str] = field(default_factory=list)


def tipo_da_norma(testo_atto: str, alberatura_per_articolo) -> tuple[str | None, list[str]]:
    """Strato 1. `alberatura_per_articolo` e' un callable
    `numero -> alberatura | None` (tipicamente costruito dal grafo). Cosi'
    questo modulo non importa ne' lo store ne' networkx, e resta usabile in
    `--solo-fase1` senza grafo passando `None`.

    Ritorna (tipo, norme_viste). `norme_viste` c'e' anche quando il tipo e'
    None: serve a distinguere "nessuna norma in testa" da "norme in testa,
    ma nessuna che qualifichi l'atto"."""
    if alberatura_per_articolo is None:
        return None, []
    testa = " \n ".join(righe_intestazione(testo_atto, RIGHE_NORMA))
    viste, trovati = [], set()
    for grezzo in _RIFERIMENTO_NORMA.findall(testa):
        numero = re.sub(r"\s+", "-", grezzo.strip()).lower()
        viste.append(numero)
        alberatura = alberatura_per_articolo(numero)
        if not alberatura:
            continue
        capo = _piatto(alberatura.get("capo", "") or "")
        titolo = _piatto(alberatura.get("titolo", "") or "")
        for frammento, tipo in _CAPI_CHE_QUALIFICANO.items():
            if frammento in capo or frammento in titolo:
                trovati.add(tipo)
    if len(trovati) == 1:
        return trovati.pop(), viste
    # Due norme che qualificano l'atto in modi diversi nelle stesse dieci
    # righe: e' un disaccordo dentro lo strato, non una scelta da fare.
    return None, viste


# --------------------------------------------------------------- composizione
#: Da (grado, tipo) all'atto da redigere e al suo obiettivo. Tabella di
#: lookup, zero modello: quando il grado e il tipo sono certi e sappiamo di
#: stare dalla parte del creditore, l'atto da scrivere segue.
ATTO_DA_REDIGERE = {
    ("primo_grado", "opposizione_decreto_ingiuntivo"): (
        "comparsa di costituzione e risposta",
        "rigetto dell'opposizione e conferma del decreto ingiuntivo opposto"),
    ("primo_grado", "opposizione_esecuzione"): (
        "comparsa di costituzione e risposta",
        "rigetto dell'opposizione all'esecuzione"),
    ("appello", "atto_appello"): (
        "comparsa di costituzione in appello",
        "rigetto dell'appello e conferma della sentenza impugnata"),
    ("legittimita", "ricorso_cassazione"): (
        "controricorso",
        "rigetto del ricorso"),
}

#: Grado implicato da un tipo, quando il tipo e' univoco sul punto. Serve
#: SOLO a rilevare il disaccordo con lo strato 2, mai a sostituirlo: il
#: giudice adito e' un dato letto, questo e' un'implicazione.
_GRADO_IMPLICATO = {
    "atto_appello": "appello",
    "ricorso_cassazione": "legittimita",
    "opposizione_decreto_ingiuntivo": "primo_grado",
}


def determina(testo_atto: str, alberatura_per_articolo=None) -> dict:
    """Tipo e grado dai tre strati, con il disaccordo dichiarato.

    Ritorna `{tipo_atto, grado, strati, disaccordi}`. `strati` porta cosa
    ha detto ciascuno: senza, un `non_desumibile` non si puo' diagnosticare.
    """
    strati = EsitoStrati()
    strati.tipo_da_norma, strati.norme_viste = tipo_da_norma(testo_atto, alberatura_per_articolo)
    strati.grado_da_giudice = grado_da_giudice(testo_atto)
    strati.tipo_da_autodenominazione = tipo_da_autodenominazione(testo_atto)

    # --- tipo: la norma vince, ma un disaccordo con l'autodenominazione
    #     non si nasconde: si dichiara e si rinuncia.
    da_norma = strati.tipo_da_norma
    da_nome = strati.tipo_da_autodenominazione
    if da_norma and da_nome and da_norma != da_nome:
        strati.disaccordi.append(
            f"tipo: la norma in testa dice '{da_norma}', l'autodenominazione '{da_nome}'")
        tipo = NON_DESUMIBILE
    else:
        tipo = da_norma or da_nome or NON_DESUMIBILE

    # --- grado: il giudice adito e' la fonte; il tipo lo implica solo per
    #     rilevare il disaccordo.
    implicato = _GRADO_IMPLICATO.get(tipo)
    letto = strati.grado_da_giudice
    if letto and implicato and letto != implicato:
        strati.disaccordi.append(
            f"grado: il giudice adito dice '{letto}', il tipo '{tipo}' implica '{implicato}'")
        grado = NON_DESUMIBILE
    else:
        grado = letto or implicato or NON_DESUMIBILE

    return {
        "tipo_atto": tipo,
        "grado": grado,
        "strati": {
            "tipo_da_norma": strati.tipo_da_norma,
            "grado_da_giudice": strati.grado_da_giudice,
            "tipo_da_autodenominazione": strati.tipo_da_autodenominazione,
            "norme_viste_in_testa": strati.norme_viste,
        },
        "disaccordi": strati.disaccordi,
    }


def atto_e_obiettivo(esito: dict) -> tuple[str, str] | None:
    """L'atto da redigere e il suo obiettivo, dalla tabella di lookup.
    `None` quando la coppia non e' in tabella: significa che il caso non e'
    fra quelli per cui la derivazione e' stata decisa, non che si possa
    tirare a indovinare."""
    return ATTO_DA_REDIGERE.get((esito["grado"], esito["tipo_atto"]))
