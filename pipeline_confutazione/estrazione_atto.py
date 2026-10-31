"""
Fase 1 della pipeline di confutazione (ISTRUZIONI_ARCHITETTURA_TOOL.md,
sezione 3) - estrazione strutturata da un atto avversario. Nessuna
argomentazione, nessuna valutazione: solo lettura asettica.

Strategia esplicitamente richiesta dal documento architetturale: passaggi
multipli, non un prompt unico elaborato. Tre chiamate separate (struttura
processuale, eccezioni, citazioni), ciascuna con uno schema JSON piu'
semplice di un unico schema monolitico - un modello piccolo/denso diventa
affidabile con compiti piccoli, non con prompt piu' furbi. Il tempo non e'
un vincolo (vedi conversazione: velocita' negoziata contro accuratezza).

Il campo elementi_non_estraibili NON e' opzionale in nessuno dei passaggi -
e' la difesa principale contro il rischio dichiarato in sezione 6 del
documento architetturale: un'estrazione parziale che sembra completa, in
un processo asincrono dove l'operatore non è davanti allo schermo per
accorgersene.

Non ancora testato dal vivo (nessuna istanza llama-server raggiungibile in
questa sessione, nessun modello 14B ancora scaricato) - la struttura degli
schemi e il flusso multi-passata sono scritti, la chiamata reale al motore
resta da verificare contro un run vero, stesso principio gia' seguito per
llama_server_client.py.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).parent))
import llama_server_client
import localizza
import segmenta_atto

# ------------------------------------------------------------------ schemi

# maxItems/maxLength su OGNI array di stringhe qui sotto: trovato dal vivo
# (2026-08-19, sull'atto reale di prova reale) un loop di ripetizione degenere su
# elementi_non_estraibili SENZA limiti - il modello, dopo aver compilato
# correttamente tutti i campi ben definiti, e' entrato in un ciclo
# producendo decine di voci quasi identiche e sempre piu' lunghe
# ("fideiussione_oggetto", poi "..._oggetto_oggetto", ecc.) fino a esaurire
# n_predict senza mai chiudere il JSON (verificato: RispostaTroncata con
# stop_type=="limit", non un problema di contesto - il prompt era di soli
# 629 token contro NUM_CTX=6144). Riprodotto lo stesso identico prompt che
# aveva fallito con maxItems=10/maxLength=150 sul campo incriminato: il
# motore GBNF di llama.cpp rispetta davvero questi vincoli (non solo sulla
# carta), il loop non puo' piu' iniziare per costruzione, indipendente da
# quanto n_predict venga concesso - fix strutturale, non un cerotto sul
# budget (vedi README per la diagnosi completa).
SCHEMA_STRUTTURA = {
    "type": "object",
    "properties": {
        # 1.26: `tipo_atto` NON si chiede piu' al modello. E' scritto
        # nell'intestazione dell'atto e lo calcola `tipo_atto.py` da tre
        # strati deterministici. Il modello lo indovinava: sul batch del
        # 2026-08-30 ha risposto `comparsa_risposta` per 21 atti su 45,
        # cioe' il nome dell'atto che scriviamo NOI, per atti del
        # debitore - e §7.14 registra il caso in cui l'errore si e'
        # propagato all'instradamento per famiglia in Fase 2.
        "fase_processuale": {
            "type": "string",
            "enum": ["monitoria", "opposizione_cognizione", "esecutiva", "non_desumibile"],
        },
        # 1.28: `natura_rapporto` NON si chiede piu' al modello. Lo calcola
        # famiglie_grafo.natura_del_rapporto dagli istituti che il codice
        # civile nomina nella propria alberatura ("Dell'apertura di credito
        # bancario", "Delle operazioni bancarie in conto corrente", "Del
        # mutuo") e dagli articoli che l'atto cita. Il modello lo
        # indovinava: sull'atto Verdi - opposizione di conto corrente con
        # 56 eccezioni fra anatocismo e CMS - ha risposto
        # `finanziamento_rateale`, e da quel valore sono discese quattro
        # astensioni nel merito. Cio' che dice resta in
        # `natura_rapporto_calcolata.detto_dal_modello`, per poter misurare
        # il disaccordo invece di perderlo.
        # Aggiunto 2026-08-19 insieme alla famiglia 9 di motore_regole.py
        # (recesso da apertura di credito senza preavviso) - l'art. 1845
        # c.c. detta regole opposte per tempo determinato/indeterminato,
        # la regola non puo' decidere senza questo dato. "non_applicabile"
        # se natura_rapporto non e' apertura_credito_cc (il campo non ha
        # senso per un mutuo o un conto corrente semplice).
        "durata_apertura_credito": {
            "type": "string",
            "enum": ["tempo_determinato", "tempo_indeterminato", "non_desumibile", "non_applicabile"],
            "description": "Solo se natura_rapporto e' 'apertura_credito_cc': l'affidamento aveva un termine di scadenza esplicito (tempo_determinato) o poteva essere revocato in qualsiasi momento (tempo_indeterminato)? 'non_applicabile' se natura_rapporto e' diverso da apertura_credito_cc.",
        },
        "qualita_parti": {
            "type": "object",
            "properties": {
                "debitore_principale": {"type": "string", "enum": ["persona_fisica", "societa", "non_desumibile"]},
                "fideiussore_presente": {"type": "boolean"},
                "qualita_fideiussore": {"type": "string", "enum": ["socio", "amministratore", "terzo_estraneo", "consumatore", "non_desumibile", "non_applicabile"]},
                "consumatore_eccepito": {"type": "boolean"},
            },
            "required": ["debitore_principale", "fideiussore_presente", "qualita_fideiussore", "consumatore_eccepito"],
        },
        "creditore_e_cessionario": {"type": "boolean"},
        "elementi_non_estraibili": {
            "type": "array",
            "description": "Elenco esplicito di cosa NON e' stato possibile determinare dall'atto - campo obbligatorio, mai vuoto per omissione: se tutto e' stato estratto con certezza, scrivere esplicitamente che non ci sono elementi non estraibili in questo passaggio.",
            "items": {"type": "string", "maxLength": 150},
            # 20, non 10 (contratto 1.21): stesso aumento di elementi_non_estraibili
            # in SCHEMA_ECCEZIONI/SCHEMA_CITAZIONI, per coerenza semantica -
            # nessun avviso reale su QUESTO campo specifico nel batch, ma e'
            # lo stesso nome e lo stesso significato in tre schemi diversi.
            "maxItems": 20,
        },
    },
    "required": ["fase_processuale", "durata_apertura_credito", "qualita_parti", "creditore_e_cessionario", "elementi_non_estraibili"],
}

SCHEMA_ECCEZIONI = {
    "type": "object",
    "properties": {
        "eccezioni_sollevate": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "famiglia_probabile": {
                        "type": "string",
                        # Enum chiuso dal contratto 1.6, con valore di fuga.
                        # Prima era stringa libera con minLength 1: sulla corsa
                        # reale il modello ne ha emesse 10 vuote su 10, e una
                        # stringa libera non e' indicizzabile - il passo 1-bis
                        # la usa per trovare la descrizione giuridica con cui
                        # riformula la query, e senza chiave la riformulazione
                        # degrada in silenzio.
                        "enum": ["incompletezza_estratti_conto", "saldaconto_art_50_tub", "legittimazione_cessionario", "anomalie_contabili", "vizi_fideiussione", "qualificazione_consumatore", "prescrizione", "documentazione_art_119_tub", "recesso_apertura_credito_senza_preavviso", "competenza_e_rito", "mediazione_procedibilita", "contestazione_ctu", "forma_scritta_art_117_tub", "taeg_isc_indeterminatezza", "ammortamento_alla_francese", "garanzia_ipotecaria", "cambiale_titolo_esecutivo", "segnalazione_centrale_rischi", "decadenza_beneficio_termine", "leasing", "non_riconosciuta"],
                        "description": "Famiglia dell'eccezione. Usa 'non_riconosciuta' se non rientra in nessuna delle altre: e' una risposta corretta quanto le altre, non sceglierne una a caso pur di riempire il campo. La classificazione definitiva la fa il motore delle regole a valle - questo e' un suggerimento.",
                    },
                    # 4000, non 150 come i campi etichetta qui accanto: una
                    # citazione letterale vera puo' essere lunga (vista una da
                    # ~2200 caratteri nel run reale sull'atto reale di prova) - un
                    # limite stretto qui taglierebbe una citazione vera a
                    # meta', lo stesso problema che questo fix vuole evitare.
                    "testo_letterale": {"type": "string", "description": "Citazione letterale dall'atto, non parafrasi.", "maxLength": 4000},
                    "specificita": {"type": "string", "enum": ["specifica", "generica"]},
                    "conteggi_allegati": {"type": "boolean"},
                    "posizione_nel_documento": {"type": "string", "maxLength": 100},
                },
                "required": ["famiglia_probabile", "testo_letterale", "specificita", "conteggi_allegati", "posizione_nel_documento"],
            },
            # 30, non 15 (contratto 1.21): misurato sul batch di 5 atti che
            # 8/11 avvisi sul tetto erano saturazione pura (0
            # quasi-duplicati, contratto 1.20) - il tetto tagliava
            # materiale reale, non ridondanza. Alzato solo dove i dati lo
            # giustificano, non ovunque - vedi CONTRATTI_DATI.md.
            "maxItems": 30,
        },
        "documenti_dichiarati_prodotti_da_controparte": {"type": "array", "items": {"type": "string", "maxLength": 200}, "maxItems": 15},
        # 30, non 15 (contratto 1.21): stessa misura di eccezioni_sollevate
        # - un avviso reale sul batch (12/15, 2 quasi-duplicati, saturazione
        # in maggioranza) su questo campo specifico.
        "documenti_contestati_come_mancanti": {"type": "array", "items": {"type": "string", "maxLength": 200}, "maxItems": 30},
        "domande_riconvenzionali": {"type": "array", "items": {"type": "string", "maxLength": 300}, "maxItems": 10},
        # 20, non 10 (contratto 1.21): stessa misura, avvisi di saturazione
        # pura su questo campo in citazioni (vedi SCHEMA_CITAZIONI, stesso
        # nome di campo, stesso aumento per coerenza semantica).
        "elementi_non_estraibili": {"type": "array", "items": {"type": "string", "maxLength": 150}, "maxItems": 20},
    },
    "required": ["eccezioni_sollevate", "documenti_dichiarati_prodotti_da_controparte", "documenti_contestati_come_mancanti", "domande_riconvenzionali", "elementi_non_estraibili"],
}

SCHEMA_CITAZIONI = {
    "type": "object",
    "properties": {
        # Oggetti {testo, data_rilevante} dal contratto 1.1, non piu'
        # stringhe: la data serve alla catena di risoluzione temporale che
        # il grafo versionato introdurra' (vedi CONTRATTI_DATI.md, sezione
        # "Date di vigenza"). Il campo e' nullable e DEVE restarlo: il
        # modello lo compila solo se l'atto dichiara la data
        # esplicitamente, mai deducendola. Equivalente GBNF in
        # contratti/fase1_citazioni.gbnf, che e' l'espressione normativa
        # di questo stesso vincolo.
        "norme_citate": {
            "type": "array",
            "maxItems": 30,
            "description": "Cosi' come scritte nell'atto, non normalizzate - la normalizzazione e' compito di references.py a valle.",
            "items": {
                "type": "object",
                "properties": {
                    "testo": {"type": "string", "maxLength": 150},
                    "data_rilevante": {
                        "type": ["string", "null"],
                        "description": "Data del fatto/contratto rispetto alla quale la controparte invoca la norma, formato AAAA-MM-GG. SOLO se il testo dell'atto la dichiara esplicitamente: se l'atto non la indica, scrivi null. Non dedurla, non stimarla, non usare la data odierna.",
                    },
                },
                "required": ["testo", "data_rilevante"],
            },
        },
        "precedenti_citati": {"type": "array", "items": {"type": "string", "maxLength": 150}, "maxItems": 30},
        # 20, non 10 (contratto 1.21): questo e' il campo che ha avuto
        # avvisi di saturazione pura (10/10, 0 quasi-duplicati) nel batch
        # di 5 atti - il caso concreto che ha motivato l'aumento, non solo
        # coerenza col nome del campo altrove.
        "elementi_non_estraibili": {"type": "array", "items": {"type": "string", "maxLength": 150}, "maxItems": 20},
    },
    "required": ["norme_citate", "precedenti_citati", "elementi_non_estraibili"],
}

PROMPT_STRUTTURA = (
    "Leggi il seguente atto giudiziario e determina la sua struttura processuale. "
    "Estrazione asettica: nessuna valutazione di merito, nessuna argomentazione. "
    "Se un dato non e' desumibile dal testo, usa esplicitamente 'non_desumibile' - "
    "non indovinare.\n\nAtto:\n{testo}"
)
PROMPT_ECCEZIONI = (
    "Leggi il seguente atto giudiziario ed estrai TUTTE le eccezioni sollevate "
    "da CHI HA SCRITTO QUESTO ATTO (l'autore), con il testo letterale di ciascuna. "
    "Non includere le affermazioni che l'autore attribuisce alla parte contro cui "
    "l'atto e' scritto (una tesi altrui che l'autore riporta per poi contestarla non "
    "e' un'eccezione dell'autore). Non valutarne la fondatezza: solo elencarle. Se "
    "pensi di aver trovato tutte le eccezioni ma non sei certo, "
    "dillo nel campo elementi_non_estraibili invece di ometterlo.\n\n"
    # Aggiunto 2026-08-20 dopo la misura sulla corsa reale di prova: 10
    # testo_letterale su 10 arrivavano racchiusi fra virgolette e 4 su 10
    # troncati con dei puntini. Quel confezionamento faceva scendere i
    # match esatti da 9/10 a 1/10 - le ancore restavano corrette ma
    # dipendenti da una soglia invece che deterministiche. Lo spoglio in
    # localizza.py lo toglie comunque: il prompt serve perche' su un
    # modello piccolo lo spoglio da solo lo lascerebbe libero di degradare
    # in forme peggiori (parafrasi, riassunti), che nessuno spoglio
    # recupera. I due insieme, non uno dei due.
    "Il campo testo_letterale deve contenere ESCLUSIVAMENTE le parole dell'atto, "
    "copiate carattere per carattere. NON racchiuderlo fra virgolette. NON "
    "aggiungere puntini di sospensione all'inizio o alla fine. NON accorciare il "
    "passaggio sostituendo delle parole con '...' in mezzo: se il passaggio e' "
    "lungo, copiane una parte piu' breve ma copiala INTERA - una frase corta e "
    "completa vale piu' di una lunga con dei tagli.\n\n"
    "Il campo famiglia_probabile non va mai lasciato vuoto: se non riconosci "
    "l'istituto giuridico, scrivi comunque in due o tre parole di cosa parla "
    "l'eccezione (es. 'blocco dei conti', 'mancato preavviso').\n\n"
    # Aggiunti 2026-09-02. I due campi erano nello schema della chiamata
    # come `enum` e `boolean` NUDI, senza una riga che dicesse cosa
    # significassero, e il prompt non li nominava affatto: il modello li
    # riempiva a caso. Misurato sulle 365 eccezioni estratte in tutte le
    # corse presenti in `runs/` e `lavoro/`, `conteggi_allegati` e' risultato
    # vero UNA volta. E' il campo su cui la regola delle anomalie contabili
    # decide se l'eccezione regge o si confuta: un booleano che non e' mai
    # stato chiesto davvero stava per diventare il perno di una famiglia da
    # dieci contestazioni su ventuno.
    "Il campo specificita vale 'specifica' se l'eccezione individua a quali "
    "poste, periodi, clausole o operazioni si riferisce; vale 'generica' se "
    "afferma l'irregolarita' senza dire su cosa cade (es. 'sono stati applicati "
    "interessi illegittimi' senza altro). Un passaggio incompleto o interrotto a "
    "meta' non e' specifico.\n\n"
    "Il campo conteggi_allegati e' vero SOLO se l'atto, per questa eccezione, "
    "rinvia a cifre gia' prodotte in giudizio: un ricalcolo, un prospetto, una "
    "perizia o consulenza di parte, un importo rideterminato. Chiedere una "
    "consulenza tecnica al giudice NON e' un conteggio allegato: e' il "
    "contrario. Nel dubbio scrivi false.\n\n"
    "Se in questo "
    "blocco di testo non c'e' NESSUNA eccezione (es. e' solo un'intestazione o "
    "una premessa), restituisci una lista vuota - non inventarne una pur di "
    "riempire il campo.\n\nAtto:\n{testo}"
)
PROMPT_CITAZIONI = (
    "Leggi il seguente atto giudiziario ed estrai TUTTE le norme di legge e i "
    "precedenti giurisprudenziali citati dalla parte, cosi' come scritti nel "
    "testo (non correggere né normalizzare). Se in questo blocco di testo non "
    "c'e' NESSUNA norma o precedente citato (es. e' solo un'intestazione o una "
    "premessa), restituisci liste vuote - non inventare citazioni plausibili "
    "pur di riempire i campi: una lista vuota e' una risposta corretta quanto "
    "una piena.\n\n"
    "Per ogni norma citata, il campo data_rilevante e' la data del fatto o del "
    "contratto rispetto alla quale l'autore dell'atto invoca quella norma, nel "
    "formato AAAA-MM-GG. Scrivila SOLO se l'atto la dichiara esplicitamente in "
    "relazione a quella norma. Se l'atto non la indica, scrivi null: non "
    "dedurla dal contesto, non stimarla, non usare la data di oggi. Un null e' "
    "una risposta corretta quanto una data.\n\nAtto:\n{testo}"
)

#: Filtro delle unita' argomentative (contratto 1.14): PRIMA della
#: classificazione in famiglia, non dopo. Trovato misurando (non
#: supponendo) che Fase 1 estrae come "eccezioni" anche materiale che non
#: lo e': rinvii senza contenuto proprio ("si contestano tutte le
#: eccezioni di cui sopra"), formule di rito/chiusura ("con vittoria di
#: spese", "salvo ogni altro diritto e azione"), e persino affermazioni
#: della parte che redige l'atto processato, non dell'autore (una
#: confutazione scambiata per un'eccezione). Nessuna di queste ha
#: un'affermazione giuridica propria attribuibile all'autore dell'atto - il
#: criterio che le definisce come unita' argomentativa o no.
#:
#: Perche' un'altra chiamata LLM e non un'euristica su pattern/keyword:
#: e' esattamente l'errore che il changelog 1.13 ha appena misurato per
#: la classificazione in famiglia - una regola lessicale non fa un
#: giudizio che richiede leggere la frase nel suo contesto (distinguere
#: "chi sta parlando" non e' un pattern di superficie).
#:
#: Vocabolario "autore/avversa", non "controparte/propria parte" (contratto
#: 1.15): trovato dal vivo (2026-08-24, atto reale di prova) che "controparte" e'
#: lessicalmente ambiguo - nel vocabolario del tool designa il debitore
#: (l'atto che il tool riceve in input, ex parte creditoris), ma nel testo
#: dell'atto stesso "controparte" e' spesso la BANCA, perche' e' il
#: debitore che scrive. Il modello ha adottato il significato del testo, non
#: quello del tool: ha scartato come "propria parte" i bersagli veri
#: (indici 9,14,15,17,18,19,21,22 sulla revisione umana) e tenuto tesi della
#: banca riportate dal debitore. "autore_dell_atto"/"avversa_all_autore" e'
#: ancorato all'atto in esame, non alle parti processuali: e' Python, non il
#: modello, che mappa questi ruoli sulle parti vere (creditore/debitore) -
#: il modello non deve mai sapere per chi lavora il tool.
#:
#: Criterio "di CHI e' la frase" tautologico su un atto scritto da una sola
#: parte (contratto 1.17, trovato dal vivo 2026-08-25): "e' dell'autore?" ha
#: una sola risposta possibile su un atto che l'autore ha scritto per
#: intero - anche "Si contestano tutte le eccezioni di cui sopra" e'
#: letteralmente una frase dell'autore. L'asse "di chi e'" collassa sempre
#: sulla stessa risposta, indipendentemente dal contenuto: misurato che il
#: filtro (gia' passato a una chiamata per unita', 1.16) teneva perfino un
#: rinvio da manuale e la tesi bancaria riportata (l'errore che 1.15 voleva
#: correggere). L'asse giusto non e' CHI parla ma CHE TIPO di affermazione
#: e': un'eccezione/difesa autonoma, o una tesi altrui semplicemente
#: riferita, un rinvio, una formula - la stessa distinzione che 1.15 sapeva
#: gia' fare in prosa ("l'autore la cita o la riassume per poi discuterla")
#: ma non aveva mai reso un valore di enum a se stante.
PROMPT_FILTRO_UNITA = (
    "La frase seguente e' stata estratta da un atto giudiziario come possibile eccezione sollevata "
    "dall'autore dell'atto. Classifica cosa e' DAVVERO - non CHI l'ha scritta (e' tutta scritta "
    "dall'autore, compresi i rinvii e le tesi che riporta), ma CHE TIPO di affermazione contiene:\n\n"
    "- 'eccezione_o_difesa_autonoma': l'unita' afferma un vizio, una nullita', una decadenza, un fatto "
    "impeditivo o estintivo - un contenuto giuridico proprio, verificabile, che l'autore sta sostenendo "
    "nel merito. Esempio dall'atto: \"la fideiussione deve essere dichiarata nulla in quanto la forma "
    "scritta e' prevista ex lege a pena di nullita'\".\n"
    "- 'tesi_avversa_riportata': l'unita' riferisce cosa sostiene l'ALTRA parte - tipicamente con un "
    "verbo dichiarativo (\"ribadisce\", \"argomenta\", \"rileva\", \"sostiene\") o un virgolettato "
    "attribuito - anche se e' l'autore a scriverlo nel proprio atto. Esempio dall'atto: \"L'Istituto di "
    "Credito ribadisce che tutte le condizioni sono state regolarmente convenute\".\n"
    "- 'rinvio_o_richiamo': rimanda ad altro atto o punto senza contenuto proprio. Esempio dall'atto: "
    "\"Si contestano tutte le eccezioni di cui sopra\".\n"
    "- 'norma_o_giurisprudenza_citata': l'unita' riporta il CONTENUTO di una norma, di una massima o "
    "di una pronuncia che l'atto richiama. Chi la sostiene e' il legislatore o la Corte citata, non "
    "l'autore dell'atto - vale anche quando la norma parla di nullita' o di decadenze. Esempio "
    "dall'atto: \"Recita l'art. 125-bis del Dlgs n. 385/1993 ...\".\n"
    "- 'formula_di_rito': epigrafi, conclusioni, formule di stile (es. \"con vittoria di spese\", "
    "\"salvo ogni altro diritto e azione\"). Ci stanno anche le RICHIESTE al giudice e le riserve, "
    "anche quando nominano l'eccezione e anche quando sono motivate: \"si insiste per la nullita' "
    "della fideiussione\" non e' l'eccezione di nullita', e' la domanda che ne discende. Esempio "
    "dall'atto: \"previa fissazione, ai sensi dell'art. 281 undecies comma 2 c.p.c., dell'udienza di "
    "comparizione delle parti\".\n\n"
    "Frase da classificare:\n{frasi}\n\n"
    "Atto per contesto:\n{testo}"
)

#: Le cinque categorie del filtro. `norma_o_giurisprudenza_citata` e'
#: entrata nel contratto 1.31: mancava, e cio' che non ha una casella
#: finisce nella casella sbagliata - qui fra le eccezioni. Misurato dalla
#: verifica umana del 2026-09-01, che ha bocciato 5 delle 8 voci trovate
#: solo da Fase 1 (§7.32).
_TIPI_UNITA = ("eccezione_o_difesa_autonoma", "tesi_avversa_riportata",
               "rinvio_o_richiamo", "formula_di_rito",
               "norma_o_giurisprudenza_citata")


def _schema_filtro_unita(n: int) -> dict:
    """Schema costruito a runtime sul NUMERO di frasi di questo blocco: un
    array di lunghezza ESATTA (minItems == maxItems == n), cosi' la
    corrispondenza posizionale con le frasi in ingresso e' imposta dalla
    grammatica, non affidata al modello che riconta bene."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["classificazioni"],
        "properties": {
            "classificazioni": {
                "type": "array",
                "minItems": n,
                "maxItems": n,
                "items": {"type": "string", "enum": list(_TIPI_UNITA)},
            }
        },
    }


PROMPT_AUTOVERIFICA = (
    "Hai estratto le seguenti eccezioni da un atto giudiziario:\n{eccezioni}\n\n"
    "Rileggi l'atto originale sottostante e verifica: (a) ciascuna eccezione elencata "
    "esiste davvero nel testo, (b) non ne manca nessuna. Rispondi con l'elenco delle "
    "eccezioni CONFERMATE trovate nel testo (puo' differire da quello sopra) e un "
    "elenco separato di eventuali eccezioni MANCANTI nella prima estrazione.\n\nAtto:\n{testo}"
)
#: Tetto imposto in GENERAZIONE (GBNF, via SCHEMA_AUTOVERIFICA sotto) E in
#: VALIDAZIONE FINALE (fase1_estrazione.schema.json). Devono restare uguali
#: per costruzione: e' esattamente il vincolo che un tempo li disallineava
#: (un prefisso "[blocco N] " aggiunto da Python DOPO la generazione, MAI
#: contato nel tetto che la validazione finale ricontrollava sulla stringa
#: intera). Dalla 1.13 il numero di blocco e' un campo separato
#: (blocco_origine), non piu' concatenato nel testo: i due vincoli ora
#: misurano la STESSA cosa - il testo grezzo del modello, mai un testo
#: che Python ha gia' modificato.
MAX_LEN_AUTOVERIFICA = 300

SCHEMA_AUTOVERIFICA = {
    "type": "object",
    "properties": {
        "eccezioni_confermate": {"type": "array", "items": {"type": "string", "maxLength": MAX_LEN_AUTOVERIFICA}, "maxItems": 20},
        "eccezioni_mancanti_nella_prima_estrazione": {"type": "array", "items": {"type": "string", "maxLength": MAX_LEN_AUTOVERIFICA}, "maxItems": 20},
    },
    "required": ["eccezioni_confermate", "eccezioni_mancanti_nella_prima_estrazione"],
}


# ------------------------------------------------------------------ dati


@dataclass
class EsitoEstrazione:
    """Risultato completo dei tre passaggi + l'autoverifica. Ogni passaggio
    che solleva RispostaTroncata viene registrato in `passaggi_falliti`
    invece di far fallire l'intera estrazione - un atto lungo che tronca
    solo sulle citazioni non deve buttare via struttura ed eccezioni gia'
    estratte correttamente (fallimento parziale dichiarato, non totale e
    silenzioso - vedi sezione 6 del documento architetturale)."""

    struttura: dict | None = None
    eccezioni: dict | None = None
    citazioni: dict | None = None
    autoverifica: dict | None = None
    passaggi_falliti: list[str] = field(default_factory=list)
    #: Requisito architetturale (2026-08-24): un campo DIAGNOSTICO non deve
    #: mai poter uccidere l'estrazione. Prima di questo campo, una voce di
    #: autoverifica che violava un vincolo (anche per un bug di Python A
    #: VALLE della generazione, non del modello - il caso reale che ha
    #: motivato la correzione) faceva fallire l'intera Fase 1 in validazione
    #: finale, ore dopo aver gia' estratto struttura/eccezioni/citazioni con
    #: successo. Ora: la voce anomala viene scartata QUI, prima di entrare
    #: nel file, e la ragione registrata qui - mai propagata a rompere la
    #: validazione a valle. Si applica a OGNI campo dell'autoverifica
    #: (eccezioni_confermate ED eccezioni_mancanti_nella_prima_estrazione),
    #: non solo a quello del bug che l'ha fatta scoprire.
    autoverifica_anomalie: list[str] = field(default_factory=list)
    #: Filtro pre-classificazione (contratto 1.14): frammenti estratti come
    #: possibili eccezioni ma scartati perche' non sono unita' argomentative
    #: (rinvii senza contenuto, formule di rito, affermazioni della parte
    #: che ha redatto l'atto). MAI persi: {testo, motivo, blocco_origine}
    #: per ognuno, cosi' si puo' verificare che il filtro non stia
    #: buttando materiale buono - lo stesso principio di trasparenza di
    #: passaggi_falliti/autoverifica_anomalie, applicato un passo prima.
    unita_scartate: list[dict] = field(default_factory=list)
    #: Allarme sul tetto (contratto 1.18): un array che raggiunge o si
    #: avvicina al suo maxItems puo' aver perso materiale reale al taglio
    #: della grammatica, non solo scartato ridondanza. Trovato dal vivo
    #: (2026-08-25, atto reale di prova, blocco B04): 14 eccezioni tenute su un
    #: tetto di 15 - passato in silenzio, scoperto solo perche' mancava un
    #: passaggio specifico che si sapeva dover comparire (la nullita' della
    #: fideiussione). Un tetto vicino al limite va dichiarato SEMPRE, non
    #: solo quando qualcuno nota per caso che manca qualcosa.
    avvisi_tetto: list[str] = field(default_factory=list)
    #: Passaggi TRONCATI di cui si e' salvato il prefisso gia' chiuso
    #: (contratto 1.34). Sono a meta' fra i riusciti e i falliti, e vanno
    #: tenuti separati da entrambi: contarli fra i riusciti nasconderebbe
    #: che l'elenco e' tagliato, contarli fra i falliti direbbe che non
    #: hanno prodotto nulla mentre hanno prodotto. Ogni voce:
    #: {passaggio, motivo, n_predict, caratteri_parziale, elementi, campi}.
    passaggi_recuperati: list[dict] = field(default_factory=list)

    def elementi_non_estraibili_totali(self) -> list[dict]:
        """Unione degli elementi_non_estraibili dei tre passaggi + un
        avviso esplicito per ogni passaggio fallito - il report finale deve
        poter mostrare TUTTI i buchi in un unico posto, non tre campi sparsi
        che l'operatore deve ricordarsi di controllare separatamente."""
        totale: list[dict] = []
        for nome, blocco in [("struttura", self.struttura), ("eccezioni", self.eccezioni), ("citazioni", self.citazioni)]:
            if blocco:
                totale.extend(buco("non_estraibile_dichiarato", f"[{nome}] {e}")
                                for e in blocco.get("elementi_non_estraibili", []))
        for fallito in self.passaggi_falliti:
            totale.append(buco("passaggio_fallito",
                                f"[{fallito}] PASSAGGIO FALLITO (risposta troncata) - nessun dato estratto in questo passaggio"))
        for recuperato in self.passaggi_recuperati:
            totale.append(buco(
                "passaggio_recuperato",
                f"[{recuperato['passaggio']}] RISPOSTA TRONCATA ({recuperato['motivo']}, "
                f"n_predict={recuperato['n_predict']}): recuperati {recuperato['elementi']} "
                f"elementi gia' completi dai {recuperato['caratteri_parziale']} caratteri "
                f"prodotti prima del taglio - l'elenco di questo passaggio e' TAGLIATO, "
                f"non e' detto che sia tutto quello che c'era"))
        for anomalia in self.autoverifica_anomalie:
            totale.append(buco("autoverifica_anomala", f"[autoverifica] {anomalia}"))
        for scartata in self.unita_scartate:
            non_ancorata = scartata["motivo"] == "non_ancorata"
            fase = "controllo ancoraggio" if non_ancorata else "filtro unita' argomentative"
            totale.append(buco(
                "unita_scartata_ancoraggio" if non_ancorata else "unita_scartata_filtro",
                f"[{fase}, blocco {scartata['blocco_origine']}] "
                f"scartata ({scartata['motivo']}): {scartata['testo'][:80]!r}"))
        for avviso in self.avvisi_tetto:
            totale.append(buco("tetto_array", f"[tetto array] {avviso}"))
        return totale


#: Contratto 1.24: ogni voce di `buchi` porta un `tipo` di vocabolario
#: CHIUSO accanto al testo leggibile. Prima erano stringhe con un prefisso
#: in italiano fra parentesi quadre, e chiunque volesse isolarne una classe
#: doveva fare match testuale sul prefisso - confronta_batch.py lo faceva
#: davvero ("tetto array" in b), e un front end avrebbe dovuto rifarlo.
#: Il testo resta invariato: si aggiunge il tipo, non si toglie nulla.
TIPI_BUCO = (
    "non_estraibile_dichiarato",   # elementi_non_estraibili di una passata
    "passaggio_fallito",           # RispostaTroncata: nessun dato da quel passaggio
    "autoverifica_anomala",
    "unita_scartata_ancoraggio",   # non ancorabile nel testo dell'atto
    "unita_scartata_filtro",       # scartata dal filtro unita' argomentative
    "tetto_array",                 # array vincolato vicino al proprio maxItems
    "citazione_senza_data",        # norma in forma testuale, data mai cercata
    "citazione_data_non_valida",   # data non di calendario, trattata come null
    "duplicato_assorbito",         # eccezione contenuta in un'altra
    "ancoraggio_non_riuscito",     # ancora diversa da 'ancorata'
    "verbatim_anomalo",            # fetta citabile lunghissima: dichiarata, mai troncata
    "passaggio_recuperato",        # risposta troncata, prefisso completo recuperato
)


def buco(tipo: str, testo: str) -> dict:
    """Una voce di `buchi` del contratto 1.24. Il tipo e' verificato qui,
    non a valle: un tipo fuori vocabolario e' un errore di programmazione
    del chiamante, non un dato da validare a fine corsa (stessa lezione di
    1.13-1.15: si scarta dove nasce, non ore dopo)."""
    if tipo not in TIPI_BUCO:
        raise ValueError(f"tipo di buco fuori vocabolario: {tipo!r}")
    return {"tipo": tipo, "testo": testo}


# ------------------------------------------------------------------ estrazione


#: repeat_penalty per TUTTE le chiamate di questo modulo (temperature=0.1
#: ovunque qui) - trovato dal vivo (2026-08-19) che a temperatura bassa,
#: SENZA questa penalita', il modello puo' degenerare in una sequenza
#: numerica ripetitiva fabbricata (es. "art. 1235 c.c." ... "art. 1264
#: c.c." consecutivi, nessuno presente nel testo vero) invece di ammettere
#: che un blocco non contiene nulla - verificato che 1.3 riduce
#: drasticamente il fenomeno sullo stesso prompt che l'aveva prodotto (da
#: 60 citazioni fabbricate a 3). Non basta da solo - vedi anche
#: l'istruzione esplicita "non inventare, lista vuota va bene" aggiunta a
#: PROMPT_ECCEZIONI/PROMPT_CITAZIONI: i due fix insieme, non uno dei due.
_REPEAT_PENALTY = 1.3


def recupera_da_troncata(parziale: str) -> dict:
    """Gli oggetti COMPLETI dal prefisso di una risposta JSON troncata.

    Perche' esiste. `RispostaTroncata` dichiara dalla sua prima riga che
    `contenuto_parziale` "resta accessibile per chi vuole loggarlo o
    tentare un retry": nessuno dei due e' mai stato fatto, e il parziale
    veniva buttato. Il costo non era teorico - misurato il 2026-09-01
    sull'atto ROSSI MARIO, 3 blocchi su 4 troncati e **zero eccezioni**
    per l'intero atto, mentre i tre parziali contenevano 11-14 KB di JSON
    con 68 oggetti gia' chiusi dentro.

    Cosa NON e'. Non e' una riparazione: non chiude parentesi, non indovina
    campi, non completa l'oggetto tagliato a meta'. Prende solo cio' che il
    modello aveva gia' finito di scrivere e si ferma al primo pezzo
    incompleto. Un oggetto ricucito sarebbe un oggetto che il modello non
    ha emesso, e finirebbe in un atto difensivo come se l'avesse emesso.

    Schema-agnostica di proposito: legge le chiavi di primo livello finche'
    decodificano, e dell'ultima - quella tagliata - salva gli elementi
    completi se e' un array. Vale per SCHEMA_ECCEZIONI come per gli altri,
    e non va aggiornata quando uno schema cambia.

    Ritorna {} quando non c'e' niente di completo da salvare: il chiamante
    lo tratta esattamente come prima, cioe' come passaggio fallito."""
    decoder = json.JSONDecoder()
    inizio = parziale.find("{")
    if inizio < 0:
        return {}
    fuori: dict = {}
    posizione = inizio + 1
    while True:
        posizione = _salta_bianchi_e_virgole(parziale, posizione)
        if posizione >= len(parziale) or parziale[posizione] != '"':
            return fuori
        try:
            chiave, posizione = decoder.raw_decode(parziale, posizione)
        except ValueError:
            return fuori
        posizione = _salta_bianchi_e_virgole(parziale, posizione)
        if posizione >= len(parziale) or parziale[posizione] != ":":
            return fuori
        posizione = _salta_bianchi_e_virgole(parziale, posizione + 1)
        try:
            valore, posizione = decoder.raw_decode(parziale, posizione)
        except ValueError:
            #: Il valore tagliato. Se e' un array, i suoi elementi gia'
            #: chiusi sono buoni: e' il caso che si verifica sempre, perche'
            #: il budget finisce dentro l'elenco lungo, mai altrove.
            if posizione < len(parziale) and parziale[posizione] == "[":
                elementi = _elementi_completi(parziale, posizione + 1, decoder)
                if elementi:
                    fuori[chiave] = elementi
            return fuori
        fuori[chiave] = valore


def _salta_bianchi_e_virgole(testo: str, posizione: int) -> int:
    while posizione < len(testo) and testo[posizione] in " \t\r\n,":
        posizione += 1
    return posizione


def _elementi_completi(testo: str, posizione: int, decoder: json.JSONDecoder) -> list:
    elementi: list = []
    while True:
        posizione = _salta_bianchi_e_virgole(testo, posizione)
        try:
            elemento, posizione = decoder.raw_decode(testo, posizione)
        except ValueError:
            return elementi
        elementi.append(elemento)


def _notifica(on_progresso: Callable[[dict], None] | None, **campi) -> None:
    """Invoca `on_progresso` (se presente) ingoiando OGNI eccezione che
    solleva - `Exception`, non `BaseException`: `KeyboardInterrupt` deve
    continuare a propagarsi indisturbato (e' cosi' che l'entry point
    intercetta un'interruzione pulita, vedi esegui_pipeline.py).

    Requisito architetturale: un campo DIAGNOSTICO non deve mai poter
    uccidere l'estrazione (lo stesso principio gia' applicato a
    EsitoEstrazione.autoverifica_anomalie/unita_scartate, qui esteso al
    canale di avanzamento invece che ai dati). Un `on_progresso` che
    scrive su disco puo' fallire per motivi che non hanno niente a che
    fare con l'estrazione (disco pieno, file bloccato da un antivirus,
    il front end che si e' staccato) - nessuno di questi deve buttare via
    ore di chiamate al modello gia' pagate. Il conteggio dei fallimenti
    vive lato chiamante (Registro, in esegui_pipeline.py), che e' anche
    dove il fallimento puo' davvero accadere (I/O) - qui c'e' solo la
    garanzia che non si propaghi."""
    if on_progresso is None:
        return
    try:
        on_progresso(campi)
    except Exception:
        pass


def _passata(base_url: str, prompt_template: str, testo_atto: str, schema: dict, nome_passaggio: str,
             esiti: EsitoEstrazione, n_predict: int = 3072, seed: int | None = None,
             on_progresso: Callable[[dict], None] | None = None) -> dict | None:
    """Esegue una singola passata di estrazione, registra il fallimento in
    esiti.passaggi_falliti invece di propagare l'eccezione - una passata
    fallita non deve interrompere le altre due (vedi EsitoEstrazione).

    seed: None finche' il chiamante non lo passa esplicitamente (bug
    trovato il 2026-08-24: `esecuzione['seed']` veniva calcolato, loggato
    e mostrato in console, ma non arrivava mai qui - ogni chiamata di
    Fase 1 girava a seed casuale del server nonostante il contratto
    dichiarasse riproducibilita'. Misurato: tre corse identiche (stesso
    atto, stesso seed nominale) hanno prodotto 29, 15 e 14 eccezioni).

    on_progresso: None (default) = comportamento invariato per ogni
    chiamante esistente. Notificato PRIMA della chiamata (non dopo): un
    front end di avanzamento vuole sapere "sto per fare la chiamata N",
    non scoprirlo solo a chiamata (magari lunga) gia' conclusa."""
    _notifica(on_progresso, passo=nome_passaggio)
    prompt = prompt_template.format(testo=testo_atto)
    try:
        # temperature=0.0, non 0.1 (contratto 1.23): misurato dal vivo che
        # su un output vincolato da GBNF/json_schema, dove la grammatica
        # garantisce gia' la forma, la temperatura residua non aggiunge
        # diversita' utile - spinge il campionamento in cicli degeneri.
        # 10 esecuzioni identiche (stesso blocco, stesso seed, server
        # riavviato ognuna) a 0.1: sempre 4 elementi, tutti quasi-duplicati
        # fra loro, la fideiussione mai trovata. Le stesse 10 a 0.0: sempre
        # 10 elementi distinti, zero quasi-duplicati, la fideiussione
        # trovata ogni volta. Non un margine: la differenza fra un
        # risultato deterministicamente sbagliato e uno deterministicamente
        # giusto sullo stesso identico input.
        return llama_server_client.completa_json(base_url, prompt, schema, n_predict=n_predict, temperature=0.0,
                                                   repeat_penalty=_REPEAT_PENALTY, seed=seed)
    except llama_server_client.RispostaTroncata as troncata:
        return _recupera_o_fallisci(troncata, nome_passaggio, esiti)


def _recupera_o_fallisci(troncata: llama_server_client.RispostaTroncata,
                          nome_passaggio: str, esiti: EsitoEstrazione) -> dict | None:
    """Un passaggio troncato produceva ZERO. Ora produce cio' che il
    modello aveva gia' finito di scrivere, e lo dichiara.

    Misurato il 2026-09-01, riproducendo l'atto ROSSI MARIO (3 blocchi
    su 4 troncati, l'atto intero fermo a 0 eccezioni): i tre parziali
    contenevano 68 oggetti gia' chiusi, 14 dei quali distinti. Il motivo e'
    sempre `limit` - n_predict esaurito, mai il contesto - e non e' scarsa
    capienza: il modello **si ripete**, 26 oggetti per 2 testi distinti nel
    primo blocco, 13 per 3 nel secondo. Alzare n_predict lo farebbe
    ripetere piu' a lungo, non finire. Il campionamento e' gia' stato
    provato e scartato (repeat_penalty 1.3 e' attivo, DRY misurato e
    inefficace, vedi lavoro/_dry_sampling_risultati.json), quindi qui non
    si tocca la generazione: si smette di buttare cio' che ha prodotto.

    Se non c'e' niente di completo da salvare, il comportamento e' quello
    di prima, `passaggi_falliti` compreso: si aggiunge un caso, non se ne
    cambia uno."""
    recuperato = recupera_da_troncata(troncata.contenuto_parziale)
    elementi = sum(len(v) for v in recuperato.values() if isinstance(v, list))
    if not elementi:
        esiti.passaggi_falliti.append(nome_passaggio)
        return None
    esiti.passaggi_recuperati.append({
        "passaggio": nome_passaggio,
        "motivo": troncata.motivo,
        "n_predict": troncata.n_predict_usato,
        "caratteri_parziale": len(troncata.contenuto_parziale),
        "elementi": elementi,
        "campi": sorted(recuperato),
    })
    return recuperato


def estrai_atto(base_url: str, testo_atto: str, autoverifica: bool = True, seed: int | None = None) -> EsitoEstrazione:
    """Orchestratore Fase 1 - tre passate + un'autoverifica opzionale
    (default attiva: costa un giro in piu' di generazione, accettabile dato
    che il progetto non ha vincoli di velocita', vedi docstring del modulo).

    Non normalizza le citazioni ne' classifica le eccezioni nelle 8
    famiglie - quello e' compito di references.py e motore_regole.py a
    valle. Questa funzione fa solo lettura, non interpretazione giuridica,
    per costruzione (stesso principio ripetuto in
    ISTRUZIONI_ARCHITETTURA_TOOL.md/SUPERFICIE_ATTACCO.md: il modello serve
    per estrarre, non per decidere)."""
    esiti = EsitoEstrazione()

    esiti.struttura = _passata(base_url, PROMPT_STRUTTURA, testo_atto, SCHEMA_STRUTTURA, "struttura", esiti, seed=seed)
    esiti.eccezioni = _passata(base_url, PROMPT_ECCEZIONI, testo_atto, SCHEMA_ECCEZIONI, "eccezioni", esiti, seed=seed)
    esiti.citazioni = _passata(base_url, PROMPT_CITAZIONI, testo_atto, SCHEMA_CITAZIONI, "citazioni", esiti, seed=seed)

    if autoverifica and esiti.eccezioni is not None:
        testi_eccezioni = "\n".join(f"- {e['testo_letterale']}" for e in esiti.eccezioni.get("eccezioni_sollevate", []))
        prompt_verifica = PROMPT_AUTOVERIFICA.format(eccezioni=testi_eccezioni, testo=testo_atto)
        verifica = _passata_diretta(base_url, prompt_verifica, SCHEMA_AUTOVERIFICA, "autoverifica", esiti, seed=seed)
        if verifica:
            # Nessuna segmentazione qui (atto intero in una chiamata sola):
            # blocco_origine e' sempre 1, non un vero indice di blocco - ma
            # il campo resta lo stesso per non biforcare la forma di
            # autoverifica fra estrai_atto() ed estrai_atto_segmentato().
            confermate = [t for t in (_sanitizza_stringa_autoverifica(x, "eccezioni_confermate", 1, esiti)
                                       for x in verifica.get("eccezioni_confermate", [])) if t is not None]
            mancanti = [{"testo": t, "blocco_origine": 1} for t in
                        (_sanitizza_stringa_autoverifica(x, "eccezioni_mancanti_nella_prima_estrazione", 1, esiti)
                         for x in verifica.get("eccezioni_mancanti_nella_prima_estrazione", [])) if t is not None]
            esiti.autoverifica = {"eccezioni_confermate": confermate, "eccezioni_mancanti_nella_prima_estrazione": mancanti}

    return esiti


def _sanitizza_stringa_autoverifica(testo: str, campo: str, blocco: int, esiti: EsitoEstrazione) -> str | None:
    """Requisito architetturale (2026-08-24): un campo DIAGNOSTICO non deve
    mai poter uccidere l'estrazione. Ricontrolla in Python lo stesso
    vincolo che la grammatica ha gia' imposto in generazione - non perche'
    la grammatica sia inaffidabile, ma perche' e' esattamente cosi' che si
    e' scoperto il bug reale: un vincolo rispettato in generazione puo'
    essere silenziosamente violato da un passaggio Python successivo (qui
    non ce ne sono piu' - blocco_origine e' un campo separato dalla 1.13 -
    ma la ricontrollo resta la difesa contro il prossimo che ci sara').

    None se la stringa va scartata: il chiamante non la include nel
    risultato, e questa funzione registra IL PERCHE' in
    esiti.autoverifica_anomalie invece di lasciare che una eccezione di
    validazione lo scopra ore dopo, a valle, buttando via anche
    struttura/eccezioni/citazioni gia' estratte con successo."""
    if len(testo) > MAX_LEN_AUTOVERIFICA:
        esiti.autoverifica_anomalie.append(
            f"blocco {blocco}, campo '{campo}': voce scartata, {len(testo)} caratteri oltre il limite di "
            f"{MAX_LEN_AUTOVERIFICA} (il vincolo di generazione l'aveva rispettato: la violazione e' "
            "successiva, non del modello) - testo: "
            f"{testo[:80]!r}..."
        )
        return None
    return testo


#: Soglia di allarme sul tetto (contratto 1.18): un array che la raggiunge
#: potrebbe aver perso materiale reale al taglio della grammatica, non
#: solo scartato ridondanza - 14/15 (93%) e' esattamente il caso reale che
#: ha motivato il controllo.
_SOGLIA_ALLARME_TETTO = 0.8

#: Soglia di quasi-duplicato (contratto 1.20), stessa usata per isolare il
#: primo gruppo di 5 copie del blocco 1 a inizio sessione - rapidfuzz
#: Indel (o difflib in fallback, vedi localizza.RAPIDFUZZ_DISPONIBILE) su
#: testo con spazi collassati.
_SOGLIA_QUASI_DUPLICATO = 0.90


def _quasi_duplicati(testi: list[str]) -> int:
    """Quanti elementi di `testi` hanno ALMENO un altro elemento simile
    sopra soglia. Contratto 1.20: un array che tocca il tetto per 15
    elementi DAVVERO diversi e uno che ne contiene 15 quasi identici sono
    due problemi opposti - il primo chiede piu' capienza (maxItems), il
    secondo un fix di campionamento (repeat_penalty e affini) - e
    l'avviso sul tetto da solo (1.18) non li distingueva."""
    normalizzati = [" ".join(t.split()) for t in testi]
    in_gruppo = [False] * len(normalizzati)
    for i in range(len(normalizzati)):
        for j in range(i + 1, len(normalizzati)):
            if localizza._rapporto(normalizzati[i], normalizzati[j]) >= _SOGLIA_QUASI_DUPLICATO:
                in_gruppo[i] = in_gruppo[j] = True
    return sum(in_gruppo)


def _verifica_tetto(elementi: list, tetto: int, nome_campo: str, contesto: str, esiti: EsitoEstrazione,
                     estrai_testo=lambda x: x) -> None:
    """Registra in esiti.avvisi_tetto (mai bloccante, sempre visibile in
    'buchi') quando un array vincolato si avvicina al proprio maxItems.
    Va chiamata per OGNI campo array di OGNI schema di Fase 1 - il caso
    reale che l'ha motivata (eccezioni_sollevate del blocco B04, 14/15) non
    era speciale, era solo il primo notato perche' mancava un elemento
    specifico che si sapeva dover esserci. Senza questo controllo lo stesso
    difetto puo' ripetersi silenzioso su qualunque altro campo - documenti
    prodotti, norme citate, domande riconvenzionali - dove nessuno saprebbe
    di dover controllare a mano.

    Dalla 1.20, l'avviso include quanti elementi sono quasi-duplicati fra
    loro (_quasi_duplicati): "15/15, di cui 12 quasi-duplicati" e
    "15/15, di cui 0 quasi-duplicati" richiedono correzioni opposte,
    saturazione vera contro degenerazione di campionamento - prima di
    questo campo l'avviso non li distingueva.

    estrai_testo: funzione che dato un elemento dell'array restituisce la
    stringa da confrontare - identita' per array di stringhe,
    `lambda e: e["testo_letterale"]` per un array di oggetti."""
    quantita = len(elementi)
    if tetto and quantita / tetto >= _SOGLIA_ALLARME_TETTO:
        n_duplicati = _quasi_duplicati([estrai_testo(e) for e in elementi])
        esiti.avvisi_tetto.append(
            f"{contesto}, campo '{nome_campo}': {quantita}/{tetto} elementi (>= {_SOGLIA_ALLARME_TETTO:.0%} "
            f"del tetto), di cui {n_duplicati} quasi-duplicati (similarita' >= {_SOGLIA_QUASI_DUPLICATO:.0%}) "
            "- possibile materiale escluso dal limite dell'array, non necessariamente solo ridondanza scartata"
        )


def _passata_diretta(base_url: str, prompt: str, schema: dict, nome_passaggio: str,
                      esiti: EsitoEstrazione, n_predict: int = 2048, seed: int | None = None,
                      on_progresso: Callable[[dict], None] | None = None) -> dict | None:
    """Come _passata() ma con un prompt gia' completo (usata dall'autoverifica,
    che non ha un template a due soli placeholder come le altre tre)."""
    _notifica(on_progresso, passo=nome_passaggio)
    try:
        # temperature=0.0: stessa misura e stesso motivo di _passata() -
        # vedi il suo commento. Usata anche dal filtro unita' argomentative
        # (_filtra_unita_argomentative), non solo dall'autoverifica.
        return llama_server_client.completa_json(base_url, prompt, schema, n_predict=n_predict, temperature=0.0,
                                                   repeat_penalty=_REPEAT_PENALTY, seed=seed)
    except llama_server_client.RispostaTroncata as troncata:
        return _recupera_o_fallisci(troncata, nome_passaggio, esiti)


def _filtra_unita_argomentative(base_url: str, blocco: str, eccezioni_grezze: list[dict],
                                 blocco_indice: int, esiti: EsitoEstrazione,
                                 seed: int | None = None,
                                 on_progresso: Callable[[dict], None] | None = None) -> list[dict]:
    """Filtro pre-classificazione (contratto 1.14, criterio per TIPO di
    affermazione non per CHI parla dalla 1.17): separa le eccezioni/difese
    autonome (eccezione_o_difesa_autonoma) dal resto - tesi altrui
    riportate, rinvii, formule di rito - PRIMA che classifica_famiglia le
    veda. Ritorna solo le prime; le altre finiscono in esiti.unita_scartate
    con testo + motivo + blocco_origine, MAI perse silenziosamente.

    Gira DOPO il controllo di ancoraggio (_scarta_non_ancorate, contratto
    1.15): giudica il CONTENUTO di una frase che l'atto contiene davvero,
    non se la frase esiste - i due controlli misurano cose diverse e
    l'ordine e' obbligato (verificare l'esistenza prima del contenuto).

    UNA CHIAMATA PER UNITA' (contratto 1.16), non piu' un batch per
    blocco. Misurato dal vivo (2026-08-24, atto reale di prova, blocco 5): 5
    copie quasi identiche, classificate INSIEME in una chiamata batch,
    hanno ricevuto 4 verdetti diversi (2 tenute, 3 motivi di scarto
    diversi). Le stesse 5, classificate UNA ALLA VOLTA con lo STESSO
    contesto di blocco (nessuna informazione tolta, solo i candidati
    vicini nella stessa chiamata), hanno ricevuto lo stesso verdetto 5
    volte su 5. Il contesto non era la variabile instabile: era la
    presenza di candidati simili nella stessa chiamata.

    PRINCIPIO ARCHITETTURALE, non solo per questo filtro: un giudizio su
    piu' candidati nella stessa chiamata degrada quando i candidati sono
    simili fra loro. Vale per qualunque futuro passo di classificazione
    batch su materiale che puo' contenere quasi-duplicati - inclusa
    l'eventuale verifica di pertinenza sui segmenti, se mai costruita in
    forma batch: va riconsiderata alla luce di questa misura, non
    assunta sicura per analogia con altri passi a un solo elemento.

    Fail OPEN per singola unita', non chiuso: se la chiamata per
    QUELL'unita' fallisce (RispostaTroncata, gestita da
    _passata_diretta), quella sola unita' resta - le altre proseguono
    indipendentemente. Stesso principio del contratto 1.13 (un passo
    diagnostico non deve poter cancellare materiale quando non riesce a
    esprimersi), applicato per unita' invece che per blocco intero: un
    fallimento isolato non deve piu' buttare via un intero blocco."""
    tenute = []
    for indice, eccezione in enumerate(eccezioni_grezze, start=1):
        prompt = PROMPT_FILTRO_UNITA.format(frasi=eccezione["testo_letterale"], testo=blocco)
        schema = _schema_filtro_unita(1)
        risposta = _passata_diretta(base_url, prompt, schema,
                                     f"filtro_unita_blocco_{blocco_indice}_unita_{indice}",
                                     esiti, n_predict=64, seed=seed, on_progresso=on_progresso)
        if risposta is None:
            tenute.append(eccezione)
            continue

        classificazioni = risposta.get("classificazioni", [])
        if len(classificazioni) != 1:
            # Non dovrebbe succedere (minItems == maxItems == 1 nello
            # schema), ma se succede e' un abbinamento non fidato -
            # fail-open sulla singola unita', come una risposta troncata.
            esiti.autoverifica_anomalie.append(
                f"blocco {blocco_indice}, unita' {indice}: filtro unita' argomentative ha risposto con "
                f"{len(classificazioni)} classificazioni invece di 1 - filtro non applicato a questa unita'")
            tenute.append(eccezione)
            continue

        if classificazioni[0] == "eccezione_o_difesa_autonoma":
            tenute.append(eccezione)
        else:
            esiti.unita_scartate.append({
                "testo": eccezione["testo_letterale"][:MAX_TESTO_SCARTATA],
                "motivo": classificazioni[0],
                "blocco_origine": blocco_indice,
                "dettaglio": None,
            })
    return tenute


#: Tetto del testo di un'unita' SCARTATA, allineato al `maxLength` del
#: contratto. Qui troncare e' sicuro, ed e' l'unico posto in cui lo sia:
#: `unita_scartate[].testo` e' una copia DIAGNOSTICA di quello che il
#: modello aveva emesso, serve a capire perche' un'unita' e' caduta e non
#: finisce mai in un atto. Il campo citabile - `testo_verbatim` - non si
#: tronca mai, per la ragione opposta: e' la fetta agli offset dichiarati,
#: e una fetta tagliata non e' piu' quella fetta (regola 4).
#:
#: Senza questo troncamento due corse del batch del 2026-08-30 sono morte
#: in validazione DOPO aver speso l'intera Fase 1: il modello aveva emesso
#: un `testo_letterale` piu' lungo del tetto e lo scarto se lo portava
#: dietro intero.
MAX_TESTO_SCARTATA = 4000


def _scarta_non_ancorate(testo_atto_pulito: str, blocchi_per_ancoraggio: list[dict],
                          eccezioni_grezze: list[dict], blocco_indice: int,
                          esiti: EsitoEstrazione) -> list[dict]:
    """Controllo 18 (contratto 1.15), PRIMA del filtro semantico
    (_filtra_unita_argomentative): un'unita' la cui ancora e'
    'non_ancorata' - il passaggio non esiste nell'atto, e' fabbricato dal
    modello - non diventa MAI un'eccezione, indipendentemente da cosa dica
    il filtro semantico a valle (che giudica il CONTENUTO di una frase, non
    la sua ESISTENZA nel testo).

    Trovato dal vivo (2026-08-24, atto reale di prova): un passaggio fabbricato
    5 volte nello stesso blocco (tutte non_ancorata: nessuna esiste
    nell'atto) sopravviveva al filtro semantico come X01 - una copia
    classificata "tesi dell'autore" - mentre le altre 4 finivano disperse
    fra tre motivi di scarto incoerenti fra loro. Stesso difetto visto da
    due angolazioni: la "ripetizione degenere" e l'"incoerenza del filtro
    su testi identici" erano entrambe ripetizione di un fatto inesistente,
    non un giudizio instabile sul contenuto - verificare l'esistenza prima
    del contenuto le risolve entrambe con un solo controllo."""
    superstiti = []
    for eccezione in eccezioni_grezze:
        ancora = localizza.localizza(testo_atto_pulito, blocchi_per_ancoraggio, eccezione["testo_letterale"])
        if ancora["stato"] == "non_ancorata":
            esiti.unita_scartate.append({
                "testo": eccezione["testo_letterale"][:MAX_TESTO_SCARTATA],
                "motivo": "non_ancorata",
                "blocco_origine": blocco_indice,
                "dettaglio": ancora["motivo"],
            })
        else:
            superstiti.append(eccezione)
    return superstiti


def estrai_atto_segmentato(base_url: str, testo_atto: str, budget_token_per_blocco: int = 2200,
                            autoverifica: bool = True, seed: int | None = None,
                            filtro_semantico: bool = True,
                            on_progresso: Callable[[dict], None] | None = None) -> EsitoEstrazione:
    """Fase 1 per un atto che non entra nel contesto in un solo pezzo
    (verificato sul caso reale: 7647 token per un atto di 16 pagine,
    contro un contesto disponibile di 8192 su questa macchina - vedi
    README). Segmenta ai confini naturali dell'atto (segmenta_atto.py:
    sezioni numerate, o paragrafi come fallback), elabora ogni blocco
    separatamente, aggrega in un UNICO EsitoEstrazione - stessa forma di
    estrai_atto(), cosi' motore_regole.py/assembla_report.py non devono
    sapere se l'atto e' stato segmentato o no.

    struttura estratta SOLO dal primo blocco: il preambolo/intestazione di
    un atto italiano e' quasi sempre in apertura - reinterrogarla su ogni
    blocco darebbe risposte potenzialmente in conflitto senza beneficio,
    l'unico posto dove quell'informazione vive davvero e' l'inizio dell'atto.

    eccezioni e citazioni estratte da OGNI blocco (possono comparire
    ovunque) e unite deduplicando per testo/stringa ESATTA - non una
    euristica di similarita': un duplicato letterale capita solo se un
    segmento naturale finisce ripetuto tra blocchi vicini, un caso raro
    per costruzione (segmenta_atto.py non sovrappone mai i blocchi).

    autoverifica eseguita PER BLOCCO, contro il testo di quel blocco - non
    sull'atto intero (stesso motivo del punto sopra: non rientrerebbe nel
    contesto), aggregata a sua volta in coda.

    budget_token_per_blocco=2200, non 4000 come nella prima versione:
    trovato dal vivo (log di llama-server, "truncated = 1" su una
    chiamata da 6143/6144 token) che 4000 non lasciava margine sufficiente
    per istruzioni+risposta - il budget calcolato in isolamento (solo il
    testo del blocco) ignorava che ogni chiamata aggiunge anche il
    prompt di istruzioni E il budget di generazione (fino a 3072 per
    estrazione, e l'autoverifica rilegge il blocco una seconda volta
    dentro il proprio prompt). 2200 lascia margine reale per entrambe le
    passate anche nel caso peggiore, calcolato non stimato - vedi anche i
    n_predict ridotti (rispetto a estrai_atto()) nelle chiamate qui sotto,
    stessa correzione applicata su due leve invece di una sola.

    filtro_semantico=False (contratto 1.15, diagnostico): salta
    _filtra_unita_argomentative, lascia attivo solo il controllo di
    ancoraggio (_scarta_non_ancorate). Serve a misurare la baseline - cosa
    sopravvive con il solo cancello di esistenza - contro cui giudicare se
    il filtro semantico aggiunge o toglie valore, senza confondere le due
    domande in una sola corsa.

    on_progresso: None (default) = comportamento invariato. Notificato UNA
    volta per ogni chiamata LLM effettiva (struttura, eccezioni_blocco,
    citazioni_blocco, autoverifica_blocco, una per unita' del filtro),
    con almeno {'passo': nome_passaggio} - mai un totale di chiamate a
    priori: il filtro (1.16) ne fa una per unita' SUPERSTITE, un numero
    che si scopre blocco per blocco, non prima di iniziare. Vedi
    _notifica() per la garanzia che un callback che solleva non tocchi
    l'estrazione."""
    conta_token = lambda testo: llama_server_client.conta_token(base_url, testo)  # noqa: E731
    # segmenta_con_span, non segmenta_atto (contratto 1.15): serve l'offset
    # di ogni blocco per il controllo di ancoraggio (_scarta_non_ancorate),
    # che deve girare qui, PRIMA del filtro semantico, non solo piu' tardi
    # in fase1_assembla.assembla(). blocchi_span[i].testo e' identico a
    # quello che segmenta_atto() avrebbe dato (e' la sua stessa
    # implementazione, vedi segmenta_atto.py) - nessuna differenza per le
    # chiamate LLM sotto, solo dati in piu' disponibili.
    blocchi_span = segmenta_atto.segmenta_con_span(testo_atto, conta_token, budget_token=budget_token_per_blocco)
    blocchi = [b.testo for b in blocchi_span]
    testo_atto_pulito = segmenta_atto.pulisci_numeri_pagina(testo_atto)
    blocchi_per_ancoraggio = [
        {"blocco_id": f"B{indice:02d}", "inizio": b.inizio, "fine": b.fine}
        for indice, b in enumerate(blocchi_span, start=1)
    ]

    esiti = EsitoEstrazione()
    esiti.struttura = _passata(base_url, PROMPT_STRUTTURA, blocchi[0], SCHEMA_STRUTTURA, "struttura", esiti,
                                seed=seed, on_progresso=on_progresso)
    if esiti.struttura:
        _verifica_tetto(esiti.struttura.get("elementi_non_estraibili", []),
                         SCHEMA_STRUTTURA["properties"]["elementi_non_estraibili"]["maxItems"],
                         "elementi_non_estraibili", "struttura", esiti)

    eccezioni_totali: list[dict] = []
    documenti_prodotti_totali: list[str] = []
    documenti_mancanti_totali: list[str] = []
    riconvenzionali_totali: list[str] = []
    non_estraibili_eccezioni: list[str] = []
    norme_totali: list[str] = []
    precedenti_totali: list[str] = []
    non_estraibili_citazioni: list[str] = []
    confermate_totali: list[str] = []
    mancanti_totali: list[str] = []
    testi_eccezioni_visti: set[str] = set()

    for i, blocco in enumerate(blocchi):
        # n_predict 4096, non 2048 (contratto 1.22): 2048 bastava per il
        # tetto precedente (eccezioni_sollevate maxItems 15) ma con
        # maxItems 30 (1.21) causava RispostaTroncata sistematica -
        # misurato dal vivo, 9 blocchi su 21 troncati nel batch di 5 atti,
        # UN INTERO BLOCCO PERSO per ciascuno (non degradato a 15 elementi:
        # perso a zero, _passata cattura RispostaTroncata e ritorna None).
        # Alzare maxItems senza alzare lo spazio di generazione e' un
        # peggioramento silenzioso mascherato da miglioramento - il
        # sintomo era invisibile finche' non si sono contati gli
        # eccezioni_totali per atto e si sono trovati IN CALO, non in
        # aumento, rispetto al tetto piu' basso.
        eccezioni_blocco = _passata(base_url, PROMPT_ECCEZIONI, blocco, SCHEMA_ECCEZIONI, f"eccezioni_blocco_{i + 1}", esiti, n_predict=4096, seed=seed, on_progresso=on_progresso)
        if eccezioni_blocco:
            # Allarme sul tetto (contratto 1.18): sui campi grezzi del
            # modello, PRIMA di qualunque filtro - e' la lunghezza che il
            # modello ha davvero prodotto contro il tetto che vederla
            # riguarda, non la lunghezza sopravvissuta ai controlli a
            # valle (che e' sempre <=).
            _verifica_tetto(eccezioni_blocco.get("eccezioni_sollevate", []),
                             SCHEMA_ECCEZIONI["properties"]["eccezioni_sollevate"]["maxItems"],
                             "eccezioni_sollevate", f"eccezioni blocco {i + 1}", esiti,
                             estrai_testo=lambda e: e["testo_letterale"])
            for campo in ("documenti_dichiarati_prodotti_da_controparte",
                          "documenti_contestati_come_mancanti", "domande_riconvenzionali", "elementi_non_estraibili"):
                _verifica_tetto(eccezioni_blocco.get(campo, []),
                                 SCHEMA_ECCEZIONI["properties"][campo]["maxItems"],
                                 campo, f"eccezioni blocco {i + 1}", esiti)
            # Controllo 18 (contratto 1.15): PRIMA di tutto il resto, anche
            # del filtro semantico - un passaggio che non esiste nell'atto
            # non deve mai arrivare a un giudizio sul suo contenuto.
            eccezioni_esistenti_blocco = _scarta_non_ancorate(
                testo_atto_pulito, blocchi_per_ancoraggio,
                eccezioni_blocco.get("eccezioni_sollevate", []), i + 1, esiti)
            # Filtro pre-classificazione (contratto 1.14): PRIMA di
            # aggregare/deduplicare, non dopo - un rinvio senza contenuto
            # o una formula di rito non deve mai arrivare fino a
            # classifica_famiglia, che a valle avrebbe dovuto inventarsi
            # una famiglia per materiale che non e' un'eccezione.
            # Disattivabile (filtro_semantico=False) per misurare la
            # baseline del solo controllo di ancoraggio - vedi docstring.
            if filtro_semantico:
                eccezioni_grezze_blocco = _filtra_unita_argomentative(
                    base_url, blocco, eccezioni_esistenti_blocco, i + 1, esiti, seed=seed,
                    on_progresso=on_progresso)
            else:
                eccezioni_grezze_blocco = eccezioni_esistenti_blocco
            for e in eccezioni_grezze_blocco:
                chiave = e["testo_letterale"].strip()
                if chiave not in testi_eccezioni_visti:
                    testi_eccezioni_visti.add(chiave)
                    eccezioni_totali.append(e)
            for d in eccezioni_blocco.get("documenti_dichiarati_prodotti_da_controparte", []):
                if d not in documenti_prodotti_totali:
                    documenti_prodotti_totali.append(d)
            for d in eccezioni_blocco.get("documenti_contestati_come_mancanti", []):
                if d not in documenti_mancanti_totali:
                    documenti_mancanti_totali.append(d)
            for r in eccezioni_blocco.get("domande_riconvenzionali", []):
                if r not in riconvenzionali_totali:
                    riconvenzionali_totali.append(r)
            non_estraibili_eccezioni.extend(f"[blocco {i + 1}] {x}" for x in eccezioni_blocco.get("elementi_non_estraibili", []))

            if autoverifica:
                testi_eccezioni_blocco = "\n".join(f"- {e['testo_letterale']}" for e in eccezioni_grezze_blocco)
                prompt_verifica = PROMPT_AUTOVERIFICA.format(eccezioni=testi_eccezioni_blocco, testo=blocco)
                verifica_blocco = _passata_diretta(base_url, prompt_verifica, SCHEMA_AUTOVERIFICA, f"autoverifica_blocco_{i + 1}", esiti, n_predict=1536, seed=seed, on_progresso=on_progresso)
                if verifica_blocco:
                    for campo in ("eccezioni_confermate", "eccezioni_mancanti_nella_prima_estrazione"):
                        _verifica_tetto(verifica_blocco.get(campo, []),
                                         SCHEMA_AUTOVERIFICA["properties"][campo]["maxItems"],
                                         campo, f"autoverifica blocco {i + 1}", esiti)
                    for testo in verifica_blocco.get("eccezioni_confermate", []):
                        testo_sano = _sanitizza_stringa_autoverifica(
                            testo, "eccezioni_confermate", i + 1, esiti)
                        if testo_sano is not None:
                            confermate_totali.append(testo_sano)
                    for testo in verifica_blocco.get("eccezioni_mancanti_nella_prima_estrazione", []):
                        # blocco_origine e' un campo separato (contratto
                        # 1.13), MAI concatenato nel testo: e' esattamente
                        # cio' che prima faceva divergere il vincolo di
                        # generazione (sul testo grezzo) da quello di
                        # validazione finale (sul testo con prefisso).
                        testo_sano = _sanitizza_stringa_autoverifica(
                            testo, "eccezioni_mancanti_nella_prima_estrazione", i + 1, esiti)
                        if testo_sano is not None:
                            mancanti_totali.append({"testo": testo_sano, "blocco_origine": i + 1})

        citazioni_blocco = _passata(base_url, PROMPT_CITAZIONI, blocco, SCHEMA_CITAZIONI, f"citazioni_blocco_{i + 1}", esiti, n_predict=1536, seed=seed, on_progresso=on_progresso)
        if citazioni_blocco:
            _verifica_tetto(citazioni_blocco.get("norme_citate", []),
                             SCHEMA_CITAZIONI["properties"]["norme_citate"]["maxItems"],
                             "norme_citate", f"citazioni blocco {i + 1}", esiti,
                             estrai_testo=lambda n: n["testo"])
            for campo in ("precedenti_citati", "elementi_non_estraibili"):
                _verifica_tetto(citazioni_blocco.get(campo, []),
                                 SCHEMA_CITAZIONI["properties"][campo]["maxItems"],
                                 campo, f"citazioni blocco {i + 1}", esiti)
            for n in citazioni_blocco.get("norme_citate", []):
                if n not in norme_totali:
                    norme_totali.append(n)
            for p in citazioni_blocco.get("precedenti_citati", []):
                if p not in precedenti_totali:
                    precedenti_totali.append(p)
            non_estraibili_citazioni.extend(f"[blocco {i + 1}] {x}" for x in citazioni_blocco.get("elementi_non_estraibili", []))

    esiti.eccezioni = {
        "eccezioni_sollevate": eccezioni_totali,
        "documenti_dichiarati_prodotti_da_controparte": documenti_prodotti_totali,
        "documenti_contestati_come_mancanti": documenti_mancanti_totali,
        "domande_riconvenzionali": riconvenzionali_totali,
        "elementi_non_estraibili": non_estraibili_eccezioni,
    }
    esiti.citazioni = {
        "norme_citate": norme_totali,
        "precedenti_citati": precedenti_totali,
        "elementi_non_estraibili": non_estraibili_citazioni,
    }
    if autoverifica:
        esiti.autoverifica = {
            "eccezioni_confermate": confermate_totali,
            "eccezioni_mancanti_nella_prima_estrazione": mancanti_totali,
        }

    return esiti


if __name__ == "__main__":
    # Smoke test locale: solo la costruzione dei prompt/schema, nessuna
    # chiamata di rete - stesso principio degli altri smoke test nel progetto.
    atto_prova = (
        "Il debitore eccepisce che l'istituto di credito non ha prodotto gli "
        "estratti conto sin dall'apertura del rapporto, con conseguente "
        "indeterminatezza del credito azionato in via monitoria."
    )
    print("Prompt struttura (primi 200 caratteri):")
    print(PROMPT_STRUTTURA.format(testo=atto_prova)[:200])
    print("\nSchema struttura, campi:", list(SCHEMA_STRUTTURA["properties"].keys()))
    print("Schema eccezioni, campi:", list(SCHEMA_ECCEZIONI["properties"].keys()))
    print("Schema citazioni, campi:", list(SCHEMA_CITAZIONI["properties"].keys()))
    print("\nOK - nessuna chiamata di rete in questo smoke test.")
