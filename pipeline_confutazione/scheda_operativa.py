"""
La scheda operativa: cosa fare di questa causa, su una pagina.

Non sostituisce `00_memoria_analisi.md` e non ne e' un riassunto piu'
corto. Sono due documenti per due lettori diversi, e finora ne esisteva
uno solo, scritto per il secondo:

- la **memoria** e' il registro forense della corsa. Deve poter far
  ricostruire ogni passo a chi contesta un risultato, quindi dice tutto,
  in ordine di elaborazione, con i nomi interni dei campi. Su un atto
  vero sono 44 KB che si aprono con cinquanta righe di diagnostica;
- la **scheda** e' cio' che si legge prima di decidere se coltivare il
  giudizio. Sta su una pagina, ordina per quanto pesa e non per quando e'
  successo, e non contiene un solo nome di campo.

## Le tre regole che la governano

1. **Le cause, non le eccezioni.** Quindici astensioni con la stessa
   causa sono UNA riga, non quindici. Un elenco di quindici blocchi
   identici non e' informazione: e' la stessa informazione ripetuta
   quindici volte, e costringe il lettore a scoprire da solo che sono
   identiche.
2. **Ogni "non si puo'" ha un "per farlo servirebbe".** Un limite senza
   la sua azione e' una lamentela. Le azioni sono ordinate per quante
   contestazioni sbloccano, che e' l'unico ordine che aiuta a decidere.
3. **Niente vocabolario interno.** `anomalie_contabili` non e' italiano,
   `astensione` non dice a un avvocato cosa sia successo, e
   uno stato interno non e' una risposta a "posso rispondere o no".

## Come si decide la causa di un'astensione

Non leggendo il testo del motivo - sarebbe un match di stringhe su una
frase che il giorno dopo qualcuno riscrive. Si guardano due cose
strutturali: se la famiglia e' stata riconosciuta, e se il motore delle
regole ha un ramo per quella famiglia (`motore_regole._REGISTRO`, che e'
il registro vero, non una lista scritta a parte che diverge). Da li'
escono le quattro cause reali, e sono diverse fra loro nel modo che conta:
tre si risolvono scrivendo codice, una si risolve leggendo l'atto.
"""

from __future__ import annotations

import sys
from pathlib import Path

CARTELLA = Path(__file__).parent
if str(CARTELLA) not in sys.path:
    sys.path.insert(0, str(CARTELLA))

import motore_regole  # noqa: E402

#: I nomi delle famiglie come li direbbe una persona. Le chiavi sono
#: l'enum del contratto (`Famiglia`), verificato da un test: una famiglia
#: nuova senza il suo nome italiano fa fallire la suite, invece di
#: comparire in un documento per l'avvocato con l'underscore in mezzo.
IN_ITALIANO: dict[str, str] = {
    "incompletezza_estratti_conto": "estratti conto incompleti",
    "saldaconto_art_50_tub": "valore probatorio del saldaconto",
    "legittimazione_cessionario": "legittimazione del cessionario del credito",
    "anomalie_contabili": "anomalie contabili (interessi, anatocismo, commissioni)",
    "vizi_fideiussione": "vizi della fideiussione",
    "qualificazione_consumatore": "qualifica di consumatore",
    "prescrizione": "prescrizione",
    "documentazione_art_119_tub": "documentazione bancaria (art. 119 TUB)",
    "recesso_apertura_credito_senza_preavviso": "recesso dall'affidamento senza preavviso",
    "competenza_e_rito": "competenza e rito",
    "mediazione_procedibilita": "mediazione e procedibilita'",
    "contestazione_ctu": "consulenza tecnica",
    "forma_scritta_art_117_tub": "forma scritta del contratto (art. 117 TUB)",
    "taeg_isc_indeterminatezza": "TAEG/ISC indeterminato",
    "ammortamento_alla_francese": "ammortamento alla francese",
    "garanzia_ipotecaria": "garanzia ipotecaria",
    "cambiale_titolo_esecutivo": "cambiale come titolo esecutivo",
    "segnalazione_centrale_rischi": "segnalazione in Centrale Rischi",
    "decadenza_beneficio_termine": "decadenza dal beneficio del termine",
    "leasing": "leasing",
    "non_riconosciuta": "non riconosciuta",
}

#: Le quattro cause. Il testo di ognuna dice al lettore due cose: che cosa
#: e' successo, e se dipende da noi o dall'atto.
CAUSA_RISPOSTA = "risposta_disponibile"
CAUSA_RETTA = "eccezione_che_regge"
CAUSA_REGOLA_ASSENTE = "regola_non_scritta"
CAUSA_FATTO_MANCANTE = "fatto_mancante"
CAUSA_FONTI_ASSENTI = "fonti_non_verificate"
CAUSA_NON_RICONOSCIUTA = "non_riconosciuta"
CAUSA_GUASTO = "guasto"

_TITOLO_CAUSA: dict[str, str] = {
    CAUSA_RISPOSTA: "Si puo' rispondere",
    CAUSA_RETTA: "L'eccezione regge: serve un altro terreno",
    CAUSA_REGOLA_ASSENTE: "Manca la regola per questa materia",
    CAUSA_FATTO_MANCANTE: "La regola c'e' ma le manca un fatto dell'atto",
    CAUSA_FONTI_ASSENTI: "Nessuna fonte verificata a supporto",
    CAUSA_NON_RICONOSCIUTA: "Materia non riconosciuta",
    CAUSA_GUASTO: "Guasto tecnico",
}

_SPIEGA_CAUSA: dict[str, str] = {
    CAUSA_RISPOSTA: (
        "La regola si applica, ha prodotto una linea di risposta e le fonti a "
        "sostegno sono state verificate una per una nel nostro archivio."),
    CAUSA_RETTA: (
        "L'eccezione avversaria risulta fondata. Non e' un errore dell'analisi: "
        "e' un avviso a non impostare la difesa su questo punto."),
    CAUSA_REGOLA_ASSENTE: (
        "La contestazione e' stata letta e riconosciuta, ma per questa materia "
        "non e' ancora stata scritta la regola che la tratta. Non e' un giudizio "
        "sul merito: nessuna confutazione e' stata tentata. Il limite e' "
        "nell'analisi, non nell'atto."),
    CAUSA_FATTO_MANCANTE: (
        "La regola esiste e sa come rispondere, ma per scegliere la risposta le "
        "serve un dato che dall'atto non risulta. Si sblocca leggendo l'atto o i "
        "documenti allegati, non scrivendo codice."),
    CAUSA_FONTI_ASSENTI: (
        "La regola ha indicato le fonti su cui poggia la risposta, ma nessuna di "
        "quelle fonti e' stata ritrovata e verificata nel nostro archivio. La "
        "risposta esiste in astratto e non e' citabile."),
    CAUSA_NON_RICONOSCIUTA: (
        "La contestazione e' stata estratta dall'atto ma non ricondotta a nessuna "
        "materia nota. Va letta a mano: puo' trattarsi di una materia non ancora "
        "prevista, oppure di un passaggio che non e' una vera contestazione."),
    CAUSA_GUASTO: (
        "L'elaborazione di questa contestazione si e' interrotta per un guasto. "
        "E' l'unico caso in cui il risultato non vale niente."),
}


def causa_di(esito: dict) -> str:
    """La causa di UN esito, dedotta dalla struttura e non dal testo.

    L'ordine dei controlli non e' indifferente: `eccezione_fondata` va
    guardato prima di tutto perche' e' l'unico stato sfavorevole a noi, ed
    e' quello che non deve mai finire confuso con un'astensione."""
    stato = esito.get("stato")
    if stato == "errore_tecnico":
        return CAUSA_GUASTO
    if stato == "eccezione_fondata":
        return CAUSA_RETTA
    if stato == "confutabile":
        return CAUSA_RISPOSTA
    if not esito.get("famiglia"):
        return CAUSA_NON_RICONOSCIUTA
    if esito.get("contro_argomento"):
        # La regola una risposta l'ha prodotta: se siamo qui, e' caduta
        # sulle fonti.
        return CAUSA_FONTI_ASSENTI
    if _famiglia_coperta(esito["famiglia"]):
        return CAUSA_FATTO_MANCANTE
    return CAUSA_REGOLA_ASSENTE


def _famiglia_coperta(famiglia: str) -> bool:
    """Il registro vero del motore, non un elenco tenuto a mano qui.

    Una lista scritta a parte diverge il giorno in cui qualcuno aggiunge
    una regola, e la scheda continuerebbe a dire "manca la regola" a
    regola scritta."""
    try:
        return motore_regole.Famiglia(famiglia) in motore_regole._REGISTRO
    except ValueError:
        return False


def raggruppa(esiti: list[dict]) -> list[dict]:
    """Gli esiti per causa, e dentro ogni causa per materia.

    L'ordine delle cause e' quello di `_ORDINE`: prima cio' che si puo'
    usare, poi cio' che ci avverte, poi i limiti dal piu' numeroso. Non e'
    l'ordine di elaborazione e non e' l'ordine alfabetico: e' l'ordine in
    cui servono a chi deve decidere."""
    per_causa: dict[str, list[dict]] = {}
    for esito in esiti:
        per_causa.setdefault(causa_di(esito), []).append(esito)

    gruppi = []
    for causa in _ORDINE:
        voci = per_causa.get(causa)
        if not voci:
            continue
        materie: dict[str, list[str]] = {}
        for esito in voci:
            nome = IN_ITALIANO.get(esito.get("famiglia") or "",
                                   esito.get("famiglia") or "non riconosciuta")
            materie.setdefault(nome, []).append(esito["eccezione_id"])
        gruppi.append({
            "causa": causa,
            "titolo": _TITOLO_CAUSA[causa],
            "spiegazione": _SPIEGA_CAUSA[causa],
            "quante": len(voci),
            "materie": sorted(({"materia": m, "quante": len(ids), "id": ids}
                               for m, ids in materie.items()),
                              key=lambda r: (-r["quante"], r["materia"])),
        })
    return gruppi


_ORDINE = (CAUSA_RISPOSTA, CAUSA_RETTA, CAUSA_GUASTO, CAUSA_REGOLA_ASSENTE,
           CAUSA_FATTO_MANCANTE, CAUSA_FONTI_ASSENTI, CAUSA_NON_RICONOSCIUTA)


def azioni(gruppi: list[dict]) -> list[dict]:
    """Da ogni limite, la cosa da fare, ordinata per quanto sblocca.

    Le azioni di materie diverse non si sommano fra loro: scrivere la
    regola delle anomalie contabili sblocca le sue nove contestazioni e
    nient'altro. Per questo l'unita' e' la materia e non la causa."""
    fuori = []
    for gruppo in gruppi:
        if gruppo["causa"] == CAUSA_REGOLA_ASSENTE:
            for riga in gruppo["materie"]:
                fuori.append({
                    "quante": riga["quante"], "id": riga["id"],
                    "chi": "sviluppo",
                    "cosa": "scrivere la regola per '%s'" % riga["materia"]})
        elif gruppo["causa"] == CAUSA_FATTO_MANCANTE:
            for riga in gruppo["materie"]:
                fuori.append({
                    "quante": riga["quante"], "id": riga["id"],
                    "chi": "lettura dell'atto",
                    "cosa": ("reperire il dato che manca alla regola di '%s' "
                             "(il dettaglio e' nella memoria, alla voce di ciascuna "
                             "contestazione)" % riga["materia"])})
        elif gruppo["causa"] == CAUSA_FONTI_ASSENTI:
            for riga in gruppo["materie"]:
                fuori.append({
                    "quante": riga["quante"], "id": riga["id"],
                    "chi": "archivio",
                    "cosa": ("far entrare nell'archivio le fonti su cui poggia la "
                             "risposta di '%s'" % riga["materia"])})
        elif gruppo["causa"] == CAUSA_NON_RICONOSCIUTA:
            fuori.append({
                "quante": gruppo["quante"],
                "id": [i for r in gruppo["materie"] for i in r["id"]],
                "chi": "lettura dell'atto",
                "cosa": "leggere a mano le contestazioni non riconosciute e dire di "
                        "che materia sono"})
    return sorted(fuori, key=lambda r: -r["quante"])


def _riga_materie(gruppo: dict) -> list[str]:
    righe = []
    for riga in gruppo["materie"]:
        ids = ", ".join(riga["id"])
        righe.append(f"  - **{riga['materia']}** - {riga['quante']} "
                     f"{'contestazione' if riga['quante'] == 1 else 'contestazioni'} ({ids})")
    return righe


def _titolo(dossier: dict, nome_atto: str | None) -> list[str]:
    obiettivo = (dossier.get("obiettivo") or "").strip()
    righe = ["# Scheda operativa", ""]
    if nome_atto:
        righe.extend([f"**Atto esaminato**: {nome_atto}", ""])
    if obiettivo:
        righe.extend([f"**Obiettivo della difesa**: {obiettivo}", ""])
    fatti = (dossier.get("fatti_di_causa") or "").strip()
    if fatti:
        righe.extend([f"**Fatti di causa, come risultano dalla lettura**: {fatti}", ""])
    return righe


def _in_una_riga(esiti: list[dict], gruppi: list[dict]) -> list[str]:
    """Il verdetto, prima di tutto il resto.

    Deve reggere da solo: chi legge questa riga e chiude il file non deve
    poter credere che una risposta ci sia quando non c'e'.
    E' la frase che nel dossier ALFA mancava, mentre due esiti si
    dichiaravano confutabili senza contenere una confutazione."""
    totale = len(esiti)
    pronte = next((g["quante"] for g in gruppi if g["causa"] == CAUSA_RISPOSTA), 0)
    if not totale:
        return ["## In una riga", "",
                "Nessuna contestazione estratta dall'atto: non c'e' niente da "
                "confutare, il che di solito vuol dire che qualcosa e' andato "
                "storto in lettura, non che l'atto non contesti nulla.", ""]
    if not pronte:
        return ["## In una riga", "",
                f"Controparte solleva **{totale} contestazioni**. Sono state lette e "
                f"classificate tutte, ma **nessuna ha prodotto una risposta "
                f"utilizzabile**. Sotto, le cause raggruppate e cosa serve per "
                "sbloccarle.", ""]
    return ["## In una riga", "",
            f"Controparte solleva **{totale} contestazioni**. Di queste, "
            f"**{pronte} hanno una risposta pronta e con fonti verificate**; per "
            f"le altre {totale - pronte} il motivo e' indicato sotto.", ""]


def rendi(dossier: dict, estrazione: dict | None = None,
          nome_atto: str | None = None, fase3_eseguita: bool = False) -> str:
    """La scheda intera, in Markdown.

    `estrazione` serve solo per il testo verbatim delle contestazioni e
    per la struttura processuale: se manca, la scheda esce comunque, piu'
    corta. E' voluto - una corsa fermata presto deve poter produrre
    qualcosa di leggibile, non un errore."""
    esiti = dossier.get("esiti") or []
    gruppi = raggruppa(esiti)

    righe = _titolo(dossier, nome_atto)
    righe.extend(_in_una_riga(esiti, gruppi))

    righe.extend(["## Perche', per causa", ""])
    for gruppo in gruppi:
        quante = gruppo["quante"]
        righe.append(f"### {gruppo['titolo']} - {quante} su {len(esiti)}")
        righe.append("")
        righe.append(gruppo["spiegazione"])
        righe.append("")
        righe.extend(_riga_materie(gruppo))
        righe.append("")

    da_fare = azioni(gruppi)
    righe.extend(["## Cosa serve per sbloccare", ""])
    if not da_fare:
        righe.extend(["Niente: ogni contestazione ha avuto una risposta.", ""])
    else:
        righe.append("In ordine di quante contestazioni sblocca ciascuna.")
        righe.append("")
        for indice, azione in enumerate(da_fare, start=1):
            righe.append(f"{indice}. **Sblocca {azione['quante']}** - {azione['cosa']} "
                         f"*({azione['chi']})*")
        righe.append("")

    righe.extend(_da_verificare(estrazione))
    righe.extend(_non_fatto(dossier, estrazione, fase3_eseguita))
    return "\n".join(righe).rstrip() + "\n"


def _da_verificare(estrazione: dict | None) -> list[str]:
    """I dati usati nell'analisi e non verificati da nessun calcolo.

    Non e' un elenco di tutto cio' che e' incerto - sarebbe tutto. Sono i
    campi che il modello ASSERISCE e che nessun calcolo Python conferma,
    cioe' quelli su cui un errore non lascia traccia da nessuna parte."""
    if not estrazione:
        return []
    struttura = estrazione.get("struttura") or {}
    parti = struttura.get("qualita_parti") or {}
    avvisi = []

    qualita = parti.get("qualita_fideiussore")
    if parti.get("fideiussore_presente") and qualita not in (None, "non_desumibile",
                                                             "non_applicabile"):
        avvisi.append(
            "La qualifica del fideiussore ('%s') e' **dichiarata dal modello e " % qualita +
            "non verificata da nessun calcolo**. Una persona fisica che garantisce non "
            "e' per cio' solo un consumatore: dipende dal collegamento con la societa' "
            "garantita, che dall'atto puo' non risultare. Se la qualifica conta per la "
            "linea difensiva, va accertata sui documenti.")

    natura = struttura.get("natura_rapporto_calcolata") or {}
    if natura.get("disaccordi"):
        avvisi.append(
            "Gli strati che determinano la natura del rapporto **non concordano** "
            f"({'; '.join(str(d) for d in natura['disaccordi'])}): il valore usato e' "
            "quello dichiarato, ma il disaccordo va sciolto a mano.")
    detto = natura.get("detto_dal_modello")
    if detto and detto != struttura.get("natura_rapporto"):
        avvisi.append(
            "Sulla natura del rapporto il modello diceva '%s', il calcolo "
            "deterministico dice '%s', e vale il " % (detto, struttura.get("natura_rapporto")) +
            "secondo. Se il primo fosse quello giusto, cambierebbero le regole "
            "applicabili.")

    if not avvisi:
        return []
    return ["## Da verificare a mano prima di usarla", ""] + [f"- {a}" for a in avvisi] + [""]


def _non_fatto(dossier: dict, estrazione: dict | None,
               fase3_eseguita: bool) -> list[str]:
    """Cio' che non e' stato esaminato, detto per intero.

    Sta in fondo e non in cima di proposito: in cima c'era gia', nella
    memoria, e cinquanta righe di limiti prima di una riga di contenuto
    hanno l'effetto opposto a quello voluto - si saltano. Qui il lettore
    ci arriva dopo aver capito cosa ha in mano."""
    voci = []
    if not fase3_eseguita:
        voci.append("La bozza di atto **non e' stata prodotta**: la corsa e' stata "
                    "fermata alla fase di analisi. Non e' una rinuncia: la scrittura "
                    "non e' stata chiesta.")
    if estrazione:
        buchi = estrazione.get("buchi") or []
        senza_ancora = sum(1 for b in buchi if b.get("tipo") == "ancoraggio_non_riuscito")
        if senza_ancora:
            voci.append(
                f"**{senza_ancora} passaggi** che il modello aveva segnalato non sono "
                "stati collocati con certezza nel testo dell'atto, e quindi non sono "
                "scesi in analisi. Restano nei file della corsa e vanno letti a mano: "
                "non sono stati giudicati infondati, non sono stati giudicati affatto.")
        degeneri = [b["testo"] for b in buchi
                    if b.get("tipo") == "autoverifica_anomala"
                    and "famiglia degenere" in b.get("testo", "")]
        if degeneri:
            voci.append("Il modello ha proposto quasi sempre la stessa materia per "
                        "contestazioni diverse: la sua etichetta, in questa corsa, non "
                        "e' un dato affidabile. La classificazione usata e' quella "
                        "ricalcolata dopo, non la sua.")
    scartate = dossier.get("fonti_scartate") or []
    if scartate:
        voci.append(f"**{len(scartate)} fonti** sono state trovate ma non sono state "
                    "usate perche' non citabili automaticamente. Sono elencate nella "
                    "memoria, con il motivo di ciascuna.")
    if not voci:
        return []
    return ["## Cosa non e' stato esaminato", ""] + [f"- {v}" for v in voci] + [""]
