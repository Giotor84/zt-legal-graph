"""
Classificazione euristica di un'eccezione in una delle nove famiglie.

Estratta da assembla_report.py il 2026-08-20, quando il passo 1-bis e'
diventato per-eccezione: l'orchestratore deve conoscere la famiglia PRIMA
della Fase 2, per riformulare la query di ricerca di quell'eccezione, e
assembla_report importa lo store - tirarselo dietro per un'euristica su
stringhe avrebbe rotto `--solo-fase1 --batch`, che deve girare dove il
grafo non c'e'.

Qui dentro non c'e' nessun accesso al grafo e nessuna chiamata LLM: solo
`motore_regole.Famiglia` e un dizionario di parole chiave.

Euristica V1, dichiarata debole: substring case-insensitive sul
`famiglia_probabile` emesso dal modello PIU' il `testo_letterale`
dell'eccezione - l'etichetta libera da sola e' spesso troppo breve per
discriminare. Upgradabile a una classificazione vincolata via schema se
in produzione si rivela insufficiente; meglio un'euristica dichiarata
debole che un altro giro di generazione.
"""

from __future__ import annotations

import re

from motore_regole import Famiglia

# Parole chiave per famiglia - da SUPERFICIE_ATTACCO.md, non inventate.
_KEYWORD_PER_FAMIGLIA: dict[Famiglia, list[str]] = {
    Famiglia.INCOMPLETEZZA_ESTRATTI_CONTO: ["estratt", "movimentazion"],
    Famiglia.SALDACONTO_ART_50_TUB: ["saldaconto", "saldo conto", "art. 50 tub", "articolo 50 tub", "art.50 tub"],
    Famiglia.LEGITTIMAZIONE_CESSIONARIO: ["cessionari", "cession", "legittimazion", "titolarit", "gazzetta ufficiale", "nemo plus iuris"],
    Famiglia.ANOMALIE_CONTABILI: ["usura", "usurari", "anatocis", "commissione di massimo scoperto", "c.m.s.", "cms", "tasso di mora", "interessi moratori"],
    Famiglia.VIZI_FIDEIUSSIONE: ["fideiuss", "schema abi", "art. 1938", "art. 1957", "garante"],
    Famiglia.QUALIFICAZIONE_CONSUMATORE: ["consumatore", "foro del consumatore", "competenza territoriale", "scopo estraneo"],
    Famiglia.PRESCRIZIONE: ["prescrizion", "prescritt", "dies a quo", "termine prescrizionale", "rimess"],
    Famiglia.DOCUMENTAZIONE_ART_119_TUB: ["art. 119", "articolo 119", "119 tub", "119 co", "119 comma"],
    # Radici, non forme flesse (2026-08-20). Sulla corsa reale
    # "affidamenti" e "conti affidati" non trovavano la keyword
    # "affidamento": tre eccezioni su quattro non classificate erano
    # mancate per morfologia, non per copertura. "affid" copre
    # affidamento/affidamenti/affidati/affidato; "recess" copre
    # recesso/recessi/recedere.
    Famiglia.RECESSO_APERTURA_CREDITO_SENZA_PREAVVISO: ["recess", "recedere", "preavvis", "affid", "1845", "revoca del fido"],
    # Le undici del contratto 1.35. Le chiavi sono quelle con cui le
    # famiglie sono state MISURATE sul corpus (STATO_PROGETTO 7.45):
    # cambiarle rende quei numeri non riproducibili. Le radici seguono la
    # stessa regola delle altre - coprono il suffisso che cambia, non il
    # prefisso, ed e' `_compare` a imporre il confine di parola.
    Famiglia.COMPETENZA_E_RITO: ["incompetenz", "litispendenz", "improcedibil", "inammissibil", "connession", "foro competente"],
    Famiglia.MEDIAZIONE_PROCEDIBILITA: ["mediazion", "negoziazione assistita", "condizione di procedibilit", "organismo di mediazione"],
    Famiglia.CONTESTAZIONE_CTU: ["ctu", "c.t.u", "consulenza tecnica", "consulente tecnico", "perizia econometric", "elaborato peritale"],
    Famiglia.FORMA_SCRITTA_ART_117_TUB: ["art. 117", "articolo 117", "117 tub", "117 co", "forma scritt", "monofirma", "contratto quadro"],
    Famiglia.TAEG_ISC_INDETERMINATEZZA: ["taeg", "tan", "isc", "indice sintetico", "indeterminatezz"],
    Famiglia.AMMORTAMENTO_ALLA_FRANCESE: ["ammortament", "francese", "regime compost", "capitalizzazione degli interessi"],
    Famiglia.GARANZIA_IPOTECARIA: ["ipotec", "escussion", "pegno", "privilegi"],
    Famiglia.CAMBIALE_TITOLO_ESECUTIVO: ["cambial", "titolo esecutiv", "vaglia cambiari", "pagher"],
    Famiglia.SEGNALAZIONE_CENTRALE_RISCHI: ["centrale rischi", "segnalazion", "sofferenz"],
    Famiglia.DECADENZA_BENEFICIO_TERMINE: ["decadenza dal beneficio", "beneficio del termine", "risoluzione per inadempiment", "1186"],
    Famiglia.LEASING: ["leasing", "locazione finanziari", "concedente"],
}

#: Descrizione della famiglia in linguaggio giuridico, usata per
#: riformulare la query di ricerca dell'eccezione (passo 1-bis). Non e'
#: la stessa cosa del valore dell'enum: "vizi_fideiussione" come query di
#: embedding vale poco, "nullita' della fideiussione omnibus conforme allo
#: schema ABI" vale molto - ed e' il punto per cui la riformulazione
#: esiste.
DESCRIZIONE_FAMIGLIA: dict[Famiglia, str] = {
    Famiglia.INCOMPLETEZZA_ESTRATTI_CONTO:
        "incompletezza degli estratti conto, onere della prova del saldo, ricostruzione del rapporto di conto corrente",
    Famiglia.SALDACONTO_ART_50_TUB:
        "efficacia probatoria dell'estratto conto certificato ex art. 50 TUB nel giudizio di opposizione",
    Famiglia.LEGITTIMAZIONE_CESSIONARIO:
        "legittimazione attiva del cessionario del credito, prova della cessione, pubblicazione in Gazzetta Ufficiale",
    Famiglia.ANOMALIE_CONTABILI:
        "anatocismo, usura, commissione di massimo scoperto, interessi moratori nel conto corrente bancario",
    Famiglia.VIZI_FIDEIUSSIONE:
        "nullita' della fideiussione omnibus conforme allo schema ABI, intesa restrittiva della concorrenza",
    Famiglia.QUALIFICAZIONE_CONSUMATORE:
        "qualificazione di consumatore, foro del consumatore, competenza territoriale inderogabile",
    Famiglia.PRESCRIZIONE:
        "prescrizione del credito, decorrenza del termine, rimesse solutorie e ripristinatorie",
    Famiglia.DOCUMENTAZIONE_ART_119_TUB:
        "diritto del cliente alla documentazione bancaria ex art. 119 TUB, termine decennale",
    Famiglia.RECESSO_APERTURA_CREDITO_SENZA_PREAVVISO:
        "recesso della banca dall'apertura di credito, preavviso ex art. 1845 c.c., buona fede nell'esecuzione del contratto",
    Famiglia.COMPETENZA_E_RITO:
        "incompetenza territoriale, litispendenza, improcedibilita' e inammissibilita' dell'appello",
    Famiglia.MEDIAZIONE_PROCEDIBILITA:
        "mediazione obbligatoria come condizione di procedibilita' della domanda, negoziazione assistita",
    Famiglia.CONTESTAZIONE_CTU:
        "contestazione delle conclusioni della consulenza tecnica d'ufficio contabile, perizia econometrica di parte",
    Famiglia.FORMA_SCRITTA_ART_117_TUB:
        "nullita' del contratto bancario per difetto di forma scritta ex art. 117 TUB, contratto monofirma",
    Famiglia.TAEG_ISC_INDETERMINATEZZA:
        "erronea indicazione del TAEG e dell'indice sintetico di costo, indeterminatezza del costo del credito",
    Famiglia.AMMORTAMENTO_ALLA_FRANCESE:
        "anatocismo nel piano di ammortamento alla francese, regime composto e capitalizzazione degli interessi nel mutuo",
    Famiglia.GARANZIA_IPOTECARIA:
        "garanzia ipotecaria, escussione della garanzia, pegno e cause di prelazione",
    Famiglia.CAMBIALE_TITOLO_ESECUTIVO:
        "efficacia della cambiale e del pagher\u00f2 come titolo esecutivo, opposizione all'esecuzione cambiaria",
    Famiglia.SEGNALAZIONE_CENTRALE_RISCHI:
        "illegittima segnalazione a sofferenza in Centrale Rischi e danno da segnalazione",
    Famiglia.DECADENZA_BENEFICIO_TERMINE:
        "decadenza dal beneficio del termine ex art. 1186 c.c. e risoluzione del contratto per inadempimento",
    Famiglia.LEASING:
        "locazione finanziaria, risoluzione del leasing e obblighi del concedente",
}


def _compare(chiave: str, testo: str) -> bool:
    """La chiave compare come INIZIO DI PAROLA, non come sottostringa.

    Il passaggio alle radici (2026-08-20) recupera le forme flesse che il
    match su parola intera perdeva - "affidamenti", "conti affidati" - ma
    apre il rischio opposto, e non in teoria: misurato, 5 falsi positivi su
    10 casi di prova. "successione", "processione" e "concessione"
    contengono tutte "cession" e finivano in legittimazione_cessionario.

    Il confine di parola li elimina tutti e tre senza perdere nulla del
    recupero: una radice serve a coprire il SUFFISSO che cambia, non il
    prefisso.

    Resta una ambiguita' che nessun confine di parola puo' risolvere,
    ed e' dichiarata: "affidamento" del diritto di famiglia e
    "affidamento" bancario sono la stessa parola, come "recesso" del
    lavoratore e "recesso" della banca. Su questa pipeline non fa danno -
    gli atti in ingresso sono bancari e di esecuzione - ma se un giorno
    ci entrasse un atto di famiglia, quelle due radici lo classificherebbero
    male. E' un limite del matching lessicale, non un difetto da
    aggirare con una radice piu' corta."""
    return re.search(r"\b" + re.escape(chiave), testo) is not None


def punteggi_famiglia(famiglia_probabile: str,
                      testo_letterale: str) -> list[Famiglia]:
    """Tutte le famiglie a pari merito in cima, non solo la prima.

    `classifica_famiglia` risolve i pareggi prendendo la prima del
    dizionario: e' deterministico e va bene per la Fase 1, dove una
    famiglia serve comunque a riformulare una query e sbagliarla costa
    poco. Non va bene per contare: una coppia in pareggio messa in una
    delle due gonfia quella e sgonfia l'altra, e la percentuale che ne
    esce sembra una misura.

    Misurato dopo l'aggiunta delle undici famiglie (contratto 1.35): i
    pareggi sono 247 su 2000 classificate, il 12%. A nove famiglie erano
    pochi abbastanza da non vedersi; a venti no.

    Lista vuota se nessuna famiglia ha un riscontro."""
    testo_completo = f"{famiglia_probabile} {testo_letterale}".lower()
    punteggi = {
        famiglia: sum(1 for chiave in chiavi if _compare(chiave, testo_completo))
        for famiglia, chiavi in _KEYWORD_PER_FAMIGLIA.items()
    }
    massimo = max(punteggi.values(), default=0)
    if massimo == 0:
        return []
    return [f for f, p in punteggi.items() if p == massimo]


def classifica_famiglia(famiglia_probabile: str, testo_letterale: str) -> Famiglia | None:
    """None se nessuna famiglia ha un riscontro - non una scelta a caso
    fra le nove: un'eccezione non classificabile va segnalata come tale
    nel report, non forzata in una famiglia sbagliata solo per avere un
    risultato."""
    testo_completo = f"{famiglia_probabile} {testo_letterale}".lower()
    punteggi = {
        famiglia: sum(1 for chiave in chiavi if _compare(chiave, testo_completo))
        for famiglia, chiavi in _KEYWORD_PER_FAMIGLIA.items()
    }
    migliore = max(punteggi, key=punteggi.get)
    if punteggi[migliore] > 0:
        return migliore

    # L'euristica non ha trovato nulla: si ricade sul SUGGERIMENTO del
    # modello, che dal contratto 1.6 e' un enum chiuso e quindi una chiave
    # valida. L'ordine e' quello del contratto - la classificazione
    # definitiva e' di questo modulo, il campo del modello e' il ripiego -
    # ma un ripiego indicizzabile e' meglio di un None, perche' senza
    # famiglia il passo 1-bis riformula senza contesto giuridico.
    try:
        return Famiglia(famiglia_probabile.strip())
    except ValueError:
        return None   # stringa libera di una corsa precedente, o "non_riconosciuta"


def descrizione(famiglia: Famiglia | None) -> str:
    """Il contesto giuridico da dare alla riformulazione della query.
    Stringa vuota se la famiglia non e' stata riconosciuta: si riformula
    lo stesso, sul solo testo dell'eccezione, invece di saltare il passo -
    un'eccezione non classificata e' proprio quella per cui il retrieval
    e' l'unico appiglio rimasto."""
    return DESCRIZIONE_FAMIGLIA.get(famiglia, "") if famiglia else ""
