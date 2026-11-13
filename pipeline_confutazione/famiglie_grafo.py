"""Famiglia, rango processuale e natura del rapporto, ricavati dal grafo.

## Cosa sostituisce, e perche'

Tre decisioni giuridiche vivevano fuori dal grafo, e tutte e tre lo
avevano gia' dentro:

1. **la famiglia** dell'eccezione: `classificazione._KEYWORD_PER_FAMIGLIA`,
   nove famiglie decise a priori e riconosciute per sottostringa. Sul batch
   reale ha lasciato **442 eccezioni su 983 (45%) senza famiglia**;
2. **il rango processuale** che determina l'ordine dell'atto:
   `ordine_motivi.RANGO_PER_FAMIGLIA`, una tabella scritta a mano;
3. **la natura del rapporto**: chiesta al MODELLO. Sull'atto Verdi -
   un'opposizione su conto corrente, 56 eccezioni fra anatocismo,
   capitalizzazione trimestrale e CMS - ha risposto `finanziamento_rateale`,
   e da quel valore sono discese quattro astensioni nel merito
   ("il credito e' determinato fin dalla stipula del contratto di
   finanziamento: non serve l'estratto conto"). Un giudizio di merito
   fondato su un campo inventato.

Il grafo le ha tutte e tre:

- le **famiglie** sono le comunita' di co-citazione fra articoli, misurate
  su 775 provvedimenti (`src/famiglie_da_cocitazione.py`): due articoli che
  i giudici citano nella stessa motivazione stanno nello stesso discorso
  giuridico. Cinque comunita' su sette coincidono con famiglie
  riconoscibili senza che nessuno gliel'abbia detto;
- il **rango** e' l'alberatura: il codice di rito e' rito, il capo della
  prescrizione e' preliminare di merito, il resto e' merito;
- la **natura del rapporto** e' la sezione del c.c., che nomina gli
  istituti da se': "Dell'apertura di credito bancario", "Delle operazioni
  bancarie in conto corrente", "Del mutuo".

## Come ci si arriva: due strati, come nella 1.26

- **strato A - norme citate**: le norme che l'eccezione cita nel proprio
  testo. Misurato sul batch: le cita il **30,2%** delle eccezioni (297 su
  983). Deterministico, non passa da nessun modello;
- **strato B - vicinato nel grafo**: gli articoli citati dai provvedimenti
  che il retrieval ha trovato per quella eccezione. Copre il restante 70%,
  ma esiste solo in Fase 2, dove lo store c'e'.

Quando i due strati DISCORDANO si dichiara, non si sceglie: stessa regola
di `tipo_atto.py`, ed e' la ragione per cui questo modulo esiste separato
invece di essere una funzione dentro il classificatore.

## L'invariante che non si tocca

Qui dentro non si importa il grafo ne' lo store: si legge un artefatto
statico, `data/famiglie/profili_famiglia.json`, prodotto da
`src/profili_famiglia.py`. Senza quel file il modulo si astiene invece di
fallire - `--solo-fase1 --batch` deve continuare a girare dove il grafo non
c'e'.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from extract_citations import estrai_citazioni_da_testo

RADICE = Path(__file__).parent.parent
PERCORSO_PROFILI = RADICE / "data" / "famiglie" / "profili_famiglia.json"

RITO = "rito"
PRELIMINARE = "preliminare_di_merito"
MERITO = "merito"
NON_CLASSIFICATO = "non_classificato"

#: I ranghi nell'ordine di esposizione in un atto.
RANGHI: tuple[str, ...] = (RITO, PRELIMINARE, MERITO, NON_CLASSIFICATO)

NON_DESUMIBILE = "non_desumibile"

#: Istituto dell'alberatura del c.c. -> valore dell'enum `natura_rapporto`
#: del contratto. Non e' una tabella di famiglie: e' la traduzione fra due
#: vocabolari che esistono entrambi gia' - a sinistra il testo del codice
#: civile letto dal nodo, a destra l'enum del contratto. Le chiavi sono
#: confrontate come sottostringhe minuscole perche' l'alberatura conserva
#: gli apostrofi tipografici della fonte.
_NATURA_DA_ISTITUTO: tuple[tuple[str, str], ...] = (
    ("apertura di credito", "apertura_credito_cc"),
    ("operazioni bancarie in conto corrente", "conto_corrente"),
    ("del conto corrente", "conto_corrente"),
    ("del mutuo", "mutuo"),
)

#: Articoli TUB del credito ai consumatori: il finanziamento rateale non ha
#: una sezione propria nel c.c., ma ha i suoi articoli nel TUB, e la
#: comunita' di co-citazione li tiene insieme (artt. 121, 125, 125-bis,
#: 125-sexies, 125-septies).
_TUB_CREDITO_CONSUMATORI = {"121", "125", "125-bis", "125-sexies", "125-septies"}


def carica_profili(percorso: Path | str | None = None) -> dict | None:
    """I profili, o None se il file non c'e' o non e' leggibile.

    None non e' un errore: e' la corsa senza grafo. Chi chiama deve poter
    proseguire astenendosi, non fermarsi."""
    percorso = Path(percorso) if percorso else PERCORSO_PROFILI
    try:
        return json.loads(percorso.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _chiave(codice: str, numero: str) -> str:
    return f"{codice}::{numero}"


def articoli_dal_testo(testo: str, profili: dict) -> tuple[list[str], list[str]]:
    """Le norme citate nel testo, risolte contro gli articoli del grafo.

    Ritorna `(risolte, ambigue)`. Una citazione senza codice esplicito
    ("art. 2946", senza "c.c.") arriva dall'estrattore con
    `codice_inferito=True`: il codice e' un'assunzione, non un dato. Qui si
    prova a risolverla sul grafo, e se lo stesso numero esiste in piu'
    codici la citazione va fra le **ambigue** invece di essere assegnata a
    caso - e' lo stesso principio del BUG-GRAFO-4 sulle citazioni brevi non
    univoche.
    """
    ranghi = profili.get("rango_per_articolo", {})
    codici = sorted({c.split("::", 1)[0] for c in ranghi})
    risolte: list[str] = []
    ambigue: list[str] = []
    for citazione in estrai_citazioni_da_testo(testo):
        diretta = _chiave(citazione.codice, citazione.numero)
        if not citazione.codice_inferito:
            if diretta in ranghi:
                risolte.append(diretta)
            continue
        candidati = [_chiave(c, citazione.numero) for c in codici
                     if _chiave(c, citazione.numero) in ranghi]
        if len(candidati) == 1:
            risolte.append(candidati[0])
        elif candidati:
            ambigue.append(citazione.numero)
    return risolte, ambigue


def rango_di(articoli: list[str], profili: dict) -> str:
    """Il rango dell'eccezione, dai ranghi dei suoi articoli.

    La regola e' di priorita', non di maggioranza, e la ragione e'
    giuridica: un'eccezione che tocca il merito E' di merito anche se cita
    l'art. 645 c.p.c. per inquadrare il giudizio. Il rito decide solo
    quando non c'e' nient'altro - che e' esattamente il caso in cui
    l'eccezione e' davvero processuale.

    E' anche cio' che neutralizza l'impalcatura senza doverla elencare:
    `famiglie_da_cocitazione` osserva che artt. 641-650, 281-sexies e 91/96
    c.p.c. "compaiono ovunque proprio perche' non distinguono nulla", e con
    questa regola non distinguono nulla nemmeno qui.
    """
    ranghi = {profili.get("rango_per_articolo", {}).get(a) for a in articoli}
    if PRELIMINARE in ranghi:
        return PRELIMINARE
    if MERITO in ranghi:
        return MERITO
    if RITO in ranghi:
        return RITO
    return NON_CLASSIFICATO


def famiglia_di(articoli: list[str], profili: dict) -> tuple[int | None, dict[int, int]]:
    """La comunita' di co-citazione a cui l'eccezione appartiene, piu' il
    conteggio di tutte quelle viste.

    Vince la comunita' con piu' articoli dell'eccezione dentro. Un pareggio
    NON si scioglie: ritorna None, perche' un'eccezione a cavallo di due
    discorsi giuridici e' un'informazione, e sceglierne uno a caso la
    distruggerebbe."""
    appartenenza = profili.get("comunita_per_articolo", {})
    conteggi: dict[int, int] = {}
    for articolo in articoli:
        comunita = appartenenza.get(articolo)
        if comunita is not None:
            conteggi[comunita] = conteggi.get(comunita, 0) + 1
    if not conteggi:
        return None, {}
    massimo = max(conteggi.values())
    vincitrici = [c for c, n in conteggi.items() if n == massimo]
    return (vincitrici[0] if len(vincitrici) == 1 else None), conteggi


#: Margine minimo fra la prima e la seconda comunita' perche' la prima
#: vinca. Sotto questo rapporto le due sono indistinguibili sul lessico e
#: la risposta onesta e' nessuna, non la prima per un decimale.
MARGINE_LESSICO = 1.25

_PAROLA = __import__("re").compile(r"[a-zà-ÿ]{4,}")


def famiglia_da_lessico(testo: str, profili: dict) -> tuple[int | None, dict[int, float]]:
    """La comunita' suggerita dalle parole dell'eccezione.

    Il lessico non lo abbiamo scelto noi: e' quello che i giudici usano
    nelle motivazioni che citano gli articoli di quella comunita', misurato
    per log-odds contro il resto del corpus (`src/profili_famiglia.py`).
    Sostituisce `_KEYWORD_PER_FAMIGLIA`, che erano parole scelte a mano.

    Ritorna `(comunita, punteggi)`. Nessuna comunita' se il margine sulla
    seconda non basta: due discorsi giuridici che pesano uguale su questo
    testo sono un'informazione, non un pareggio da sciogliere.
    """
    parole = set(_PAROLA.findall((testo or "").lower()))
    punteggi: dict[int, float] = {}
    for profilo in profili.get("comunita", []):
        somma = sum(peso for termine, peso in profilo.get("lessico", []) if termine in parole)
        if somma > 0:
            punteggi[profilo["comunita"]] = round(somma, 3)
    if not punteggi:
        return None, {}
    ordinati = sorted(punteggi.items(), key=lambda x: -x[1])
    if len(ordinati) == 1 or ordinati[0][1] >= MARGINE_LESSICO * ordinati[1][1]:
        return ordinati[0][0], punteggi
    return None, punteggi


def natura_di(articoli: list[str], profili: dict) -> tuple[str, list[str]]:
    """La natura del rapporto, dagli istituti nominati dall'alberatura.

    Ritorna `(natura, istituti_visti)`. Piu' istituti bancari diversi ->
    `non_desumibile` con l'elenco: un rapporto non e' insieme un mutuo e
    un'apertura di credito, e se il testo li nomina entrambi la risposta
    onesta e' che non si sa quale sia quello in causa.

    `altro` non viene mai prodotto qui: dire "e' un rapporto, ma di altro
    tipo" richiederebbe di aver escluso i tipi noti, e l'assenza di un
    istituto nei pochi articoli citati non lo esclude.
    """
    istituti = profili.get("istituto_per_articolo", {})
    comunita = profili.get("comunita_per_articolo", {})
    quanti: dict[str, int] = {}
    visti: list[str] = []
    for articolo in articoli:
        # Un articolo che il grafo colloca in una comunita' di co-citazione
        # e' un CAMPO DI BATTAGLIA, non la descrizione del rapporto: viene
        # citato per argomentare, non per dire che contratto sia. Misurato:
        # l'art. 1815 c.c. sta nel capo "Del mutuo" ma il corpus lo mette
        # nella comunita' dell'anatocismo e dell'usura (24 provvedimenti),
        # perche' e' li' che si usa - e sull'atto Verdi, che lo cita sei
        # volte per l'usura, qualificava come "mutuo" un'opposizione di
        # conto corrente. Gli articoli che il rapporto lo DEFINISCONO
        # (1842, 1845, 1852) non stanno in nessuna comunita' proprio
        # perche' non si litiga su di essi: si citano per descrivere.
        if articolo in comunita:
            continue
        codice, numero = articolo.split("::", 1)
        if codice == "tub" and numero in _TUB_CREDITO_CONSUMATORI:
            quanti["finanziamento_rateale"] = quanti.get("finanziamento_rateale", 0) + 1
            visti.append(f"TUB art. {numero} (credito ai consumatori)")
            continue
        istituto = istituti.get(articolo)
        if not istituto:
            continue
        minuscolo = istituto.lower()
        for frammento, natura in _NATURA_DA_ISTITUTO:
            if frammento in minuscolo:
                quanti[natura] = quanti.get(natura, 0) + 1
                visti.append(istituto)
                break
    if not quanti:
        return NON_DESUMIBILE, visti
    ordinate = sorted(quanti.items(), key=lambda x: -x[1])
    # Un articolo solo non qualifica il rapporto: l'atto Verdi e' una
    # fideiussione su conto corrente che cita di passaggio un mutuo, e con
    # la sola presenza sarebbe diventato un mutuo - lo stesso errore del
    # modello, commesso da noi. Servono almeno DUE articoli dell'istituto e
    # la maggioranza assoluta fra quelli che ne nominano uno.
    if ordinate[0][1] >= 2 and ordinate[0][1] * 2 > sum(quanti.values()):
        return ordinate[0][0], visti
    return NON_DESUMIBILE, visti


def natura_del_rapporto(testo_atto: str, profili: dict | None) -> dict:
    """La natura del rapporto dell'ATTO, dal nome che il codice civile da'
    agli istituti.

    Non e' un elenco di parole chiave scelte da noi: sono i titoli delle
    sezioni del c.c. scritti sui nodi dall'alberatura - "Dell'apertura di
    credito bancario", "Delle operazioni bancarie in conto corrente", "Del
    mutuo". Il codice nomina i propri istituti, e cercare quei nomi nel
    testo dell'atto e' usare il vocabolario della fonte invece del nostro.

    Perche' sull'atto e non sulla singola eccezione: la natura del rapporto
    e' UNA per causa. Chiederla eccezione per eccezione moltiplica le
    occasioni di sbagliare senza aggiungere informazione.

    Ritorna `{natura, istituti_visti, occorrenze}`. Piu' istituti diversi ->
    `non_desumibile` con l'elenco: e' la risposta che il modello NON ha
    dato sull'atto Verdi, dove ha scelto `finanziamento_rateale` su
    un'opposizione di conto corrente e quel valore ha poi deciso il merito
    di quattro eccezioni.
    """
    vuoto = {"natura_rapporto": NON_DESUMIBILE, "istituti_visti": [], "occorrenze": {},
             "da_norme": None, "da_nomi": None, "disaccordi": []}
    if not profili:
        return vuoto

    # Strato duro: gli articoli che l'atto cita. Se cita gli artt. 1842-1845
    # sta parlando di apertura di credito, e non c'e' niente da interpretare.
    articoli, _ = articoli_dal_testo(testo_atto, profili)
    da_norme, istituti = natura_di(articoli, profili)

    # Strato lessicale: il NOME che il codice civile da' all'istituto,
    # cercato nell'atto. Il vocabolario e' quello della fonte, non nostro.
    minuscolo = (testo_atto or "").lower()
    occorrenze: dict[str, int] = {}
    per_natura: dict[str, int] = {}
    for frammento, natura in _NATURA_DA_ISTITUTO:
        quante = minuscolo.count(frammento)
        if quante:
            occorrenze[frammento] = quante
            per_natura[natura] = per_natura.get(natura, 0) + quante
    ordinate = sorted(per_natura.items(), key=lambda x: -x[1])
    if not ordinate:
        da_nomi = None
    elif len(ordinate) == 1 or ordinate[0][1] >= 2 * ordinate[1][1]:
        # "Apertura di credito in conto corrente" e' UN rapporto solo, e le
        # due espressioni convivono per forza nello stesso atto: senza un
        # margine netto non si sceglie.
        da_nomi = ordinate[0][0]
    else:
        da_nomi = None

    disaccordi = []
    if da_norme != NON_DESUMIBILE and da_nomi is not None and da_norme != da_nomi:
        disaccordi.append(
            f"natura del rapporto: gli articoli citati dicono '{da_norme}', "
            f"i nomi degli istituti nel testo dicono '{da_nomi}'")
        natura = NON_DESUMIBILE
    elif da_norme != NON_DESUMIBILE:
        natura = da_norme
    else:
        natura = da_nomi or NON_DESUMIBILE

    return {"natura_rapporto": natura, "istituti_visti": istituti or list(occorrenze),
            "occorrenze": occorrenze, "da_norme": None if da_norme == NON_DESUMIBILE else da_norme,
            "da_nomi": da_nomi, "disaccordi": disaccordi}


def classifica(testo_eccezione: str, profili: dict | None,
               articoli_dal_vicinato: list[str] | None = None,
               famiglia_dai_vettori: int | None = None) -> dict:
    """Famiglia, rango e natura del rapporto per UNA eccezione.

    `articoli_dal_vicinato` e' lo strato B: gli articoli citati dai
    provvedimenti che il retrieval ha trovato per questa eccezione. Vive in
    Fase 2, dove lo store c'e'; in Fase 1 si passa None e si lavora sul solo
    strato A.

    `famiglia_dai_vettori` e' l'esito di `famiglia_da_vettori`, e vive in
    Fase 2 per la stessa ragione: richiede l'indice dei segmenti aperto.
    Qui arriva gia' come numero perche' questo modulo non deve conoscere ne'
    lo store ne' i modelli di embedding. In Fase 1 si passa None: allora
    `fiducia` vale 'uno_solo' o 'nessuno' e nessuna comunita' viene
    revocata, perche' non c'e' stato nessun voto.

    Quando i due strati indicano famiglie diverse la divergenza finisce in
    `disaccordi` e la famiglia resta quella dello strato A - le norme che
    l'eccezione cita davvero valgono piu' di quelle che cita chi le
    somiglia. Il disaccordo NON viene nascosto: e' il segnale che quella
    eccezione va letta a mano.
    """
    esito = {
        "famiglia": None, "rango": NON_CLASSIFICATO, "natura_rapporto": NON_DESUMIBILE,
        "articoli": [], "istituti": [], "fiducia": "nessuno",
        "strati": {"norme_citate": [], "norme_ambigue": [], "vicinato": [],
                   "famiglia_da_norme": None, "famiglia_da_vicinato": None,
                   "famiglia_da_lessico": None, "famiglia_da_vettori": None,
                   "punteggi_lessico": {}},
        "disaccordi": [],
    }
    if not profili:
        esito["disaccordi"].append(
            "profili_famiglia.json assente: nessuna classificazione dal grafo, "
            "si e' lavorato senza")
        return esito

    da_norme, ambigue = articoli_dal_testo(testo_eccezione, profili)
    dal_vicinato = [a for a in (articoli_dal_vicinato or [])
                    if a in profili.get("rango_per_articolo", {})]

    famiglia_norme, _ = famiglia_di(da_norme, profili)
    famiglia_vicinato, _ = famiglia_di(dal_vicinato, profili)
    famiglia_lessico, punteggi = famiglia_da_lessico(testo_eccezione, profili)

    esito["strati"] = {
        "norme_citate": da_norme,
        "norme_ambigue": ambigue,
        "vicinato": dal_vicinato,
        "famiglia_da_norme": famiglia_norme,
        "famiglia_da_vicinato": famiglia_vicinato,
        "famiglia_da_lessico": famiglia_lessico,
        "famiglia_da_vettori": famiglia_dai_vettori,
        "punteggi_lessico": punteggi,
    }

    for nome, valore in (("i provvedimenti simili", famiglia_vicinato),
                         ("il lessico del corpus", famiglia_lessico),
                         ("i segmenti di motivazione piu' vicini", famiglia_dai_vettori)):
        if famiglia_norme is not None and valore is not None and valore != famiglia_norme:
            esito["disaccordi"].append(
                f"famiglia: le norme citate dicono comunita' {famiglia_norme}, "
                f"{nome} dice comunita' {valore}")

    # Ordine di precedenza, dal dato piu' duro al piu' indiretto: le norme
    # che l'eccezione cita davvero, poi gli articoli dei provvedimenti che
    # il retrieval le ha accostato, poi il lessico. Il lessico non e' un
    # ripiego debole - copre la maggioranza dei casi - ma resta una
    # somiglianza di parole, e una citazione esplicita vale di piu'.
    # I vettori chiudono la catena: valgono quando nessun altro strato ha
    # parlato. Aggiungerli in coda non cambia nessun caso gia' deciso -
    # dove piu' strati rispondono decide la precedenza, non l'ordine di
    # questa riga - e copre le eccezioni che oggi uscivano senza comunita'.
    for candidata in (famiglia_norme, famiglia_vicinato, famiglia_lessico,
                      famiglia_dai_vettori):
        if candidata is not None:
            esito["famiglia"] = candidata
            break

    # 1.29: la regola di concordanza fra i due strati DEBOLI entra nel
    # dossier. `fiducia` descrive sempre lo stato del voto lessico/vettori;
    # la comunita' viene revocata SOLO se poggiava su quel voto. Una norma
    # citata dall'eccezione, o gli articoli del vicinato, non erano nel voto
    # e non si annullano per un voto a cui non hanno partecipato.
    voto = concorda(famiglia_lessico, famiglia_dai_vettori)
    esito["fiducia"] = voto["fiducia"]
    if voto["nota"]:
        esito["disaccordi"].append(voto["nota"])
    if (voto["fiducia"] == "discordi"
            and famiglia_norme is None and famiglia_vicinato is None):
        esito["famiglia"] = None

    articoli = da_norme + [a for a in dal_vicinato if a not in da_norme]
    esito["articoli"] = articoli
    # Rango e natura si calcolano sulle sole norme citate quando ci sono:
    # il vicinato porta con se' l'impalcatura processuale di TUTTI i
    # provvedimenti simili, e la userebbe per qualificare questa eccezione.
    base = da_norme or dal_vicinato
    esito["rango"] = rango_di(base, profili)
    if esito["rango"] == NON_CLASSIFICATO and esito["famiglia"] is not None:
        # Nessuna norma citata: il rango si prende dalla comunita', che ne
        # ha uno solo se i suoi articoli concordano (la comunita' che
        # mescola prescrizione e procedura d'appello non ne ha, e resta
        # non classificata invece di ricevere un rango a maggioranza
        # risicata).
        for profilo in profili.get("comunita", []):
            if profilo["comunita"] == esito["famiglia"]:
                esito["rango"] = profilo.get("rango_dominante", NON_CLASSIFICATO)
                break
    esito["natura_rapporto"], esito["istituti"] = natura_di(base, profili)
    if ambigue:
        esito["disaccordi"].append(
            f"citazioni senza codice esplicito e non univoche sul grafo: {ambigue} - "
            "non assegnate a nessun codice")
    return esito


#: Quante parole del lessico mettere nel contesto di ricerca. Poche: la
#: lezione di §7.15 e' che un contesto iniettato lungo DOMINA il testo vero
#: dell'eccezione e produce query identiche per eccezioni diverse. Qui il
#: contesto serve a dare due o tre termini che il corpus usa davvero, non a
#: riscrivere l'eccezione.
PAROLE_DI_CONTESTO = 6


def contesto_di_ricerca(comunita: int | None, profili: dict | None) -> str:
    """Il contesto giuridico da dare alla riformulazione della query (passo
    1-bis), preso dal corpus invece che da una tabella.

    Sostituisce `classificazione.DESCRIZIONE_FAMIGLIA`, che erano nove
    frasi scritte a mano. Qui la frase la compongono gli **istituti**
    nominati dall'alberatura degli articoli della comunita' e le
    **parole** che i giudici usano nelle motivazioni che li citano: due
    vocabolari che esistono gia' nel grafo.

    Stringa vuota se la comunita' non c'e': si riformula lo stesso, sul
    solo testo dell'eccezione. Un'eccezione non collocata e' proprio
    quella per cui il testo e' l'unico appiglio rimasto, e riempirlo con
    un contesto generico la peggiorerebbe.
    """
    if comunita is None or not profili:
        return ""
    for profilo in profili.get("comunita", []):
        if profilo["comunita"] != comunita:
            continue
        parole = [t for t, _ in profilo.get("lessico", [])[:PAROLE_DI_CONTESTO]]
        materie = [m for m, _ in (profilo.get("vocabolario_del_corpus") or {}).get("materia", [])[:1]]
        # Solo la materia e le parole: NIENTE istituti. Gli istituti di una
        # comunita' includono i capi processuali che l'attraversano
        # ("Dell'appello", "Della prova testimoniale") e allungherebbero il
        # contesto con termini che non distinguono - proprio cio' che nella
        # §7.15 aveva fatto dominare il contesto sul testo dell'eccezione.
        pezzi = []
        if materie:
            pezzi.append(materie[0].lower())
        if parole:
            pezzi.append(", ".join(parole))
        return " - ".join(pezzi)
    return ""


#: Vicini da consultare e quorum richiesto perche' il voto valga.
#: Misurato sul golden set dal grafo (965 eccezioni, ESCLUSO il
#: provvedimento d'origine dai vicini - senza quell'esclusione il numero
#: sale a 0,747 ma misura la memoria, non la capacita'):
#:
#:     voto dei 25, nessun quorum   precisione 0,480  copertura 1,000
#:     voto dei 5,  quorum 3        precisione 0,515  copertura 0,669
#:     voto dei 5,  quorum 4        precisione 0,646  copertura 0,345
#:
#: Si sceglie il quorum 4 non perche' dia il numero piu' alto ma perche'
#: e' l'unico che TACE quando non sa: uno strato che risponde sempre non
#: puo' entrare in una regola di concordanza, perche' concorderebbe per
#: caso.
VICINI = 5
QUORUM = 4


def famiglia_da_vettori(similarita, etichette: dict[str, int],
                        vicini: int = VICINI, quorum: int = QUORUM) -> int | None:
    """La comunita' suggerita dai segmenti di motivazione piu' vicini.

    `similarita` e' il vettore delle somiglianze fra l'eccezione e OGNI
    riga della matrice dei segmenti; `etichette` mappa l'indice di riga
    (come stringa) alla comunita' del provvedimento, ed e' gia' nei
    profili. Qui dentro non si carica nessun modello e non si calcola
    nessun embedding: quello lo fa chi ha gia' l'indice aperto, cioe' la
    Fase 2.

    None se i vicini non raggiungono il quorum: e' il caso in cui i
    segmenti somigliano un po' a tutto, e rispondere sarebbe rumore."""
    candidati = [(float(similarita[int(i)]), c) for i, c in etichette.items()
                 if int(i) < len(similarita)]
    if not candidati:
        return None
    candidati.sort(reverse=True)
    conteggi: dict[int, int] = {}
    for _, comunita in candidati[:vicini]:
        conteggi[comunita] = conteggi.get(comunita, 0) + 1
    migliore, quante = max(conteggi.items(), key=lambda x: x[1])
    return migliore if quante >= quorum else None


def concorda(lessico: int | None, vettori: int | None) -> dict:
    """La regola di concordanza fra i due strati deboli.

    Misurato sul golden set (965 eccezioni): il lessico da solo ha
    precisione 0,523, i vettori con quorum 0,646, e la cascata dell'uno
    sull'altro non supera 0,543. Ma **dove i due concordano la precisione
    e' 0,804**, e dove discordano crollano entrambi (0,224 il lessico,
    0,418 i vettori): il disaccordo non e' un pareggio da sciogliere, e'
    l'informazione che quella eccezione va letta a mano.

    Ritorna `{comunita, fiducia, nota}` con `fiducia` in
    'concordi' | 'uno_solo' | 'discordi' | 'nessuno'."""
    if lessico is not None and vettori is not None:
        if lessico == vettori:
            return {"comunita": lessico, "fiducia": "concordi", "nota": None}
        return {"comunita": None, "fiducia": "discordi",
                "nota": (f"lessico dice comunita' {lessico}, i provvedimenti simili dicono "
                          f"{vettori}: dove i due discordano nessuno dei due e' affidabile "
                          "(0,224 e 0,418 di precisione sul golden set) - da leggere a mano")}
    unico = lessico if lessico is not None else vettori
    if unico is None:
        return {"comunita": None, "fiducia": "nessuno", "nota": None}
    return {"comunita": unico, "fiducia": "uno_solo", "nota": None}
