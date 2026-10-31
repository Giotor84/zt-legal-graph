"""
Fase 2a della pipeline di confutazione (ISTRUZIONI_ARCHITETTURA_TOOL.md,
sezione 3 - SUPERFICIE_ATTACCO.md per il dettaglio giuridico delle 8
famiglie). Lookup deterministica su regole, nessun modello coinvolto:
data la combinazione (famiglia_eccezione + precondizioni estratte), la
regola restituisce fondatezza + contro-argomento + fonti + livello di
consolidamento.

Impalcatura, non contenuto: qui c'e' il MECCANISMO (dispatch, dataclass,
enum delle 8 famiglie) verificato con UN esempio completo (famiglia 1,
la piu' documentata in SUPERFICIE_ATTACCO.md). Le altre sette famiglie
sono dichiarate ma non popolate - "la base giurisprudenziale la
costruiamo dopo" (decisione esplicita, non una dimenticanza): serve
giudizio giuridico che va oltre le fonti pubbliche gia' lette, e
SUPERFICIE_ATTACCO.md lo dice di se stesso ("la validazione giuridica
spetta a te").

Ogni regola e' un test automatico verificabile riga per riga (vedi
__main__) - coerente con quanto gia' osservato in questo progetto: ogni
controllo automatico ha prodotto falsi positivi quando non riletto a
mano, ma qui il "controllo automatico" e' la regola stessa, scritta da
chi ha competenza giuridica, non un giudizio delegato al modello.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional


class Famiglia(str, Enum):
    INCOMPLETEZZA_ESTRATTI_CONTO = "incompletezza_estratti_conto"
    SALDACONTO_ART_50_TUB = "saldaconto_art_50_tub"
    LEGITTIMAZIONE_CESSIONARIO = "legittimazione_cessionario"
    ANOMALIE_CONTABILI = "anomalie_contabili"
    VIZI_FIDEIUSSIONE = "vizi_fideiussione"
    QUALIFICAZIONE_CONSUMATORE = "qualificazione_consumatore"
    PRESCRIZIONE = "prescrizione"
    DOCUMENTAZIONE_ART_119_TUB = "documentazione_art_119_tub"
    # 9a famiglia, aggiunta 2026-08-19 - non prevista da SUPERFICIE_ATTACCO.md
    # (verificato: nessun riscontro nel documento per "recesso"/"preavviso"/
    # "apertura di credito"/"1845"), trovata leggendo le eccezioni VERE
    # estratte dall'atto reale di prova (recesso da un affidamento a tempo
    # indeterminato senza preavviso scritto - nessuna delle 8 famiglie
    # esistenti la copre).
    RECESSO_APERTURA_CREDITO_SENZA_PREAVVISO = "recesso_apertura_credito_senza_preavviso"
    # Dalla 10a alla 20a, aggiunte 2026-09-02 (contratto 1.35). Trovate
    # MISURANDO: sono le questioni piu' frequenti fra le 3502 eccezioni del
    # corpus che le prime nove non riconoscevano, con accanto quanto spesso
    # reggono (STATO_PROGETTO 7.45). Nessuna di esse ha ancora una regola in
    # `_REGISTRO`: `applica_regola` solleva NotImplementedError, come gia'
    # fa per sette delle nove precedenti. Una famiglia riconosciuta e senza
    # regola serve comunque - e' quella che rende leggibile un profilo di
    # magistrato - e non finge di essere altro.
    COMPETENZA_E_RITO = "competenza_e_rito"
    MEDIAZIONE_PROCEDIBILITA = "mediazione_procedibilita"
    CONTESTAZIONE_CTU = "contestazione_ctu"
    FORMA_SCRITTA_ART_117_TUB = "forma_scritta_art_117_tub"
    TAEG_ISC_INDETERMINATEZZA = "taeg_isc_indeterminatezza"
    AMMORTAMENTO_ALLA_FRANCESE = "ammortamento_alla_francese"
    GARANZIA_IPOTECARIA = "garanzia_ipotecaria"
    CAMBIALE_TITOLO_ESECUTIVO = "cambiale_titolo_esecutivo"
    SEGNALAZIONE_CENTRALE_RISCHI = "segnalazione_centrale_rischi"
    DECADENZA_BENEFICIO_TERMINE = "decadenza_beneficio_termine"
    LEASING = "leasing"


class Consolidamento(str, Enum):
    PACIFICO = "pacifico"
    CONTRASTATO = "contrastato"
    MINORITARIO = "minoritario"


@dataclass(frozen=True)
class Fonte:
    citazione_breve: str
    ruolo: str = "principale"  # "principale" o "subordinato" - dipende dal consolidamento, vedi RisultatoRegola
    # Stato di verifica contro IL NOSTRO grafo (non contro l'esistenza reale
    # in assoluto - una fonte puo' essere giurisprudenza vera e mai
    # verificata qui semplicemente perche' il nostro corpus BDP non la
    # contiene ancora). Popolati da assembla_report.risolvi_fonte(), non
    # qui: il motore delle regole resta deliberatamente senza dipendenza dal
    # grafo (nessun I/O, testabile in isolamento - vedi __main__) - la
    # risoluzione e' un passo separato, a valle.
    node_id: Optional[str] = None
    verificata: bool = False


@dataclass(frozen=True)
class RisultatoRegola:
    famiglia: Famiglia
    fondata: bool  # True = l'eccezione avversaria e' fondata, cercare terreno diverso (nessun contro-argomento qui)
    contro_argomento: Optional[str]
    fonti: list[Fonte]
    consolidamento: Optional[Consolidamento]
    nota: str  # spiegazione della precondizione che ha determinato l'esito - sempre presente, anche quando fondata=True


@dataclass(frozen=True)
class Precondizioni:
    """Vista tipizzata sui fatti estratti in Fase 1 rilevanti per QUESTA
    famiglia - un sottoinsieme di EsitoEstrazione (estrazione_atto.py),
    non un doppione: ogni regola dichiara esplicitamente quali campi le
    servono, invece di ricevere l'intero atto estratto e ripescare i
    campi al proprio interno (piu' facile da testare in isolamento)."""

    natura_rapporto: str  # "conto_corrente" | "apertura_credito_cc" | "mutuo" | "finanziamento_rateale" | "altro" | "non_desumibile"
    fase_processuale: str = "non_desumibile"
    specificita_eccezione: str = "non_desumibile"  # "specifica" | "generica"
    conteggi_allegati: bool = False
    qualita_fideiussore: str = "non_applicabile"
    documenti_prodotti_cessionario: str = "non_desumibile"
    # Usata da RECESSO_APERTURA_CREDITO_SENZA_PREAVVISO - l'art. 1845 c.c.
    # detta regole diverse per tempo determinato/indeterminato (vedi la
    # regola), quindi la durata e' dirimente quanto natura_rapporto lo e'
    # per la famiglia 1. Non ancora estratta da SCHEMA_STRUTTURA in
    # estrazione_atto.py al momento in cui questo campo e' stato aggiunto -
    # vedi nota li'.
    durata_rapporto: str = "non_desumibile"  # "tempo_determinato" | "tempo_indeterminato" | "non_desumibile"
    # Calcolato da Python sul testo dell'atto (`conteggi_di_parte.cerca`),
    # non chiesto al modello: e' il guardiano del contro-argomento della
    # famiglia 4. Quel contro-argomento dice che l'avversario non ha messo
    # cifre sul tavolo, e se le cifre ci sono e' FALSO. `conteggi_allegati`
    # non basta a difenderlo - e' per-eccezione, viene dal modello, ed e'
    # risultato vero una volta su 365 - mentre un ricalcolo prodotto in
    # giudizio e' un fatto dell'atto intero.
    # False non vuol dire "non ce ne sono": vuol dire "non se ne sono
    # trovati". Vedi il modulo per la misura e per la direzione dell'errore.
    conteggi_nell_atto: bool = False
    # Usati da LEGITTIMAZIONE_CESSIONARIO. Il primo viene dall'estrazione
    # (`struttura.creditore_e_cessionario`), il secondo lo calcola Python
    # sul testo dell'atto (`cessione_del_credito.cerca`): il fatto che
    # decide questa famiglia non e' nel corpus delle decisioni - misurato,
    # vedi il modulo - ma nell'atto avversario, che si lamenta proprio di
    # cio' che il cessionario ha prodotto.
    creditore_e_cessionario: bool = False
    contestata_solo_gazzetta: bool = False
    cessioni_plurime: bool = False
    # Usato da VIZI_FIDEIUSSIONE: quale vizio la contestazione deduce,
    # riconosciuto da `vizi_della_fideiussione.cerca` sul testo
    # dell'eccezione. Non la qualita' del fideiussore, che
    # SUPERFICIE_ATTACCO.md indicava come precondizione ma che sul corpus
    # non separa niente - ed e' anche il campo che il modello asserisce
    # senza che nulla lo verifichi.
    vizio_fideiussione: str | None = None
    # Usati da COMPETENZA_E_RITO, ed entrambi CALCOLATI: il primo confronta
    # l'ufficio in intestazione con i comuni degli indirizzi in epigrafe
    # (`foro_dell_atto.cerca`, che usa la stessa mappa dei circondari del
    # portafoglio), il secondo verifica il requisito dell'art. 38 co. 2
    # c.p.c. sul testo dell'eccezione. Nessuno dei due e' una parola
    # cercata: e' la risposta al negativo accertato del 2026-09-03, dove i
    # marcatori lessicali su questa famiglia non separavano niente.
    # `indica_giudice_competente` e' None quando l'eccezione non risulta di
    # competenza TERRITORIALE: l'art. 38 co. 2 pone il requisito solo per
    # quella, e applicarlo a materia o valore sarebbe un errore.
    foro_adito: str = "non_verificabile"
    indica_giudice_competente: bool | None = None


TipoRegola = Callable[[Precondizioni], RisultatoRegola]

_REGISTRO: dict[Famiglia, TipoRegola] = {}


def registra(famiglia: Famiglia) -> Callable[[TipoRegola], TipoRegola]:
    def decoratore(funzione: TipoRegola) -> TipoRegola:
        _REGISTRO[famiglia] = funzione
        return funzione
    return decoratore


def applica_regola(famiglia: Famiglia, precondizioni: Precondizioni) -> RisultatoRegola:
    """Punto di ingresso della Fase 2a - dispatch deterministico, nessun
    modello. Solleva NotImplementedError con un messaggio esplicito per le
    famiglie non ancora popolate, invece di restituire un risultato vuoto
    che sembrerebbe una risposta valida (stesso principio del fallimento
    dichiarato gia' seguito in estrazione_atto.py)."""
    regola = _REGISTRO.get(famiglia)
    if regola is None:
        raise NotImplementedError(
            f"famiglia '{famiglia.value}' non ancora popolata - vedi SUPERFICIE_ATTACCO.md "
            "per il materiale grezzo, la validazione giuridica resta da fare"
        )
    return regola(precondizioni)


# ------------------------------------------------------------------
# Famiglia 1 - unica popolata per intero, prova di funzionamento del
# meccanismo (SUPERFICIE_ATTACCO.md, sezione "1. Incompletezza degli
# estratti conto").
# ------------------------------------------------------------------


@registra(Famiglia.INCOMPLETEZZA_ESTRATTI_CONTO)
def _regola_incompletezza_estratti_conto(p: Precondizioni) -> RisultatoRegola:
    if p.natura_rapporto == "conto_corrente":
        return RisultatoRegola(
            famiglia=Famiglia.INCOMPLETEZZA_ESTRATTI_CONTO,
            fondata=True,
            contro_argomento=None,
            fonti=[],
            consolidamento=None,
            nota=(
                "Rapporto di conto corrente: la banca resta attore in senso sostanziale "
                "nell'opposizione e deve documentare la formazione del saldo dall'origine. "
                "Eccezione FONDATA se gli estratti conto mancano davvero - cercare terreno "
                "diverso (contestazione generica, incontestabilita' ex art. 1832 c.c. se "
                "applicabile, produzione parziale se orientamento Trib. Perugia applicabile)."
            ),
        )

    if p.natura_rapporto in ("mutuo", "finanziamento_rateale"):
        return RisultatoRegola(
            famiglia=Famiglia.INCOMPLETEZZA_ESTRATTI_CONTO,
            fondata=False,
            contro_argomento=(
                "Il credito e' determinato fin dalla stipula del contratto di finanziamento/mutuo: "
                "non serve l'estratto conto ne' l'elenco delle movimentazioni, basta il contratto "
                "piu' il piano di ammortamento e l'evidenza delle rate insolute. L'eccezione di "
                "incompletezza degli estratti conto e' priva di rilievo per questa natura di rapporto."
            ),
            fonti=[Fonte("Trib. Foggia 116/2024", ruolo="principale"), Fonte("Cass. 13533/2001", ruolo="principale")],
            consolidamento=Consolidamento.PACIFICO,
            nota="Precondizione dirimente (natura del rapporto) verificata: mutuo/finanziamento, non conto corrente.",
        )

    # Due cose diverse, che fino al 2026-09-02 uscivano con la stessa
    # frase. L'enum del contratto ha sei valori; questa regola ne tratta
    # tre. Gli altri tre finivano tutti qui sotto una nota che diceva
    # "natura non determinata con certezza (valore: 'apertura_credito_cc')"
    # - una frase che si contraddice da sola, perche' quel valore la
    # natura la determina eccome: nella corsa ALFA l'aveva calcolato
    # Python da `natura_rapporto_calcolata.da_nomi`, senza un solo
    # disaccordo fra gli strati. Il buco non era nell'estrazione, era
    # nella regola, e la nota mandava a rileggere l'atto chi avrebbe
    # dovuto scrivere un ramo.
    if p.natura_rapporto in ("altro", "non_desumibile"):
        return RisultatoRegola(
            famiglia=Famiglia.INCOMPLETEZZA_ESTRATTI_CONTO,
            fondata=False,
            contro_argomento=None,
            fonti=[],
            consolidamento=None,
            nota=(
                f"Natura del rapporto non determinata con certezza dall'estrazione "
                f"(valore: '{p.natura_rapporto}') - la regola non puo' decidere, serve "
                "rileggere l'atto o i documenti allegati prima di applicare questa famiglia. "
                "NON trattare come 'eccezione infondata di default' - e' un buco da segnalare "
                "nel report finale, non un esito silenzioso."
            ),
        )

    return RisultatoRegola(
        famiglia=Famiglia.INCOMPLETEZZA_ESTRATTI_CONTO,
        fondata=False,
        contro_argomento=None,
        fonti=[],
        consolidamento=None,
        nota=(
            f"Natura del rapporto NOTA e non coperta da questa regola: '{p.natura_rapporto}'. "
            "Il dato di ingresso c'e' ed e' determinato - il ramo che lo tratta non e' "
            "ancora scritto. Non e' un'ambiguita' dell'atto e non si risolve rileggendolo: "
            "va deciso, per l'apertura di credito in conto corrente, se l'onere di "
            "documentare il saldo dall'origine sia quello del conto corrente (e allora il "
            "ramo e' quello) oppure no. Fino ad allora nessuna confutazione su questa "
            "famiglia per questa natura di rapporto."
        ),
    )


# ------------------------------------------------------------------
# Famiglia 9 - RECESSO_APERTURA_CREDITO_SENZA_PREAVVISO, aggiunta
# 2026-08-19. NON viene da SUPERFICIE_ATTACCO.md (verificato: nessun
# riscontro nel documento) - trovata leggendo le eccezioni VERE estratte
# dall'atto reale di prova, che non rientravano in nessuna delle 8 famiglie
# esistenti. Fondata sul testo REALE dell'art. 1845 c.c. (verificato
# contro il grafo: codice_civile::1845, rubrica "Recesso dal contratto"),
# non su giurisprudenza inventata - il nostro corpus BDP non contiene
# ancora massime su questo punto specifico (verificato, ricerca vuota
# per "apertura di credito"/"recesso"/"preavviso"/"1845" su tutte le 185
# massime). Coerente con la disciplina di questa sessione: niente
# citazioni senza una fonte verificabile, un buco dichiarato e' meglio
# di una fonte inventata.
# ------------------------------------------------------------------


@registra(Famiglia.RECESSO_APERTURA_CREDITO_SENZA_PREAVVISO)
def _regola_recesso_apertura_credito_senza_preavviso(p: Precondizioni) -> RisultatoRegola:
    if p.natura_rapporto != "apertura_credito_cc":
        return RisultatoRegola(
            famiglia=Famiglia.RECESSO_APERTURA_CREDITO_SENZA_PREAVVISO,
            fondata=False,
            contro_argomento=None,
            fonti=[],
            consolidamento=None,
            nota=(
                f"Questa famiglia riguarda il recesso da un'apertura di credito - natura "
                f"del rapporto estratta: '{p.natura_rapporto}', non 'apertura_credito_cc'. "
                "La regola non si applica: non e' un giudizio di infondatezza nel merito "
                "dell'eccezione, solo un mancato aggancio a questa famiglia."
            ),
        )

    if p.durata_rapporto == "tempo_indeterminato":
        return RisultatoRegola(
            famiglia=Famiglia.RECESSO_APERTURA_CREDITO_SENZA_PREAVVISO,
            fondata=False,
            contro_argomento=(
                "Per l'apertura di credito a tempo indeterminato, l'art. 1845 c.c. consente "
                "il recesso di ciascuna delle parti mediante preavviso nel termine stabilito "
                "dal contratto, dagli usi o, in mancanza, in quello di quindici giorni - la "
                "norma non richiede la FORMA SCRITTA del preavviso, ne' particolari "
                "formalita' di trasmissione: cio' che rileva e' il decorso del termine, non "
                "la forma con cui il preavviso e' stato dato. L'eccezione, per come "
                "formulata, sovrappone due profili distinti (assenza di preavviso in "
                "assoluto vs assenza di preavviso in forma SCRITTA) senza che il secondo "
                "sia richiesto dalla norma, salvo che il contratto stesso non preveda "
                "diversamente - da verificare sul testo del contratto di affidamento, non "
                "desumibile dalla sola eccezione avversaria."
            ),
            fonti=[Fonte("art. 1845 c.c.", ruolo="principale")],
            consolidamento=None,  # nessuna massima nel nostro corpus su questo punto specifico - non dichiarare un consolidamento mai verificato
            nota=(
                "Apertura di credito a tempo indeterminato: il contro-argomento si basa "
                "sul testo dell'art. 1845 c.c. (verificato contro il grafo), NON su "
                "giurisprudenza - il corpus BDP di questo progetto non contiene ancora "
                "massime su questo punto specifico (verificato). Da rafforzare con "
                "giurisprudenza reale prima di un uso in un atto vero: senza, il "
                "contro-argomento resta valido in astratto ma privo di autorita' "
                "giurisprudenziale a supporto - un buco dichiarato, non nascosto. "
                "Verificare inoltre cosa dice IL CONTRATTO sul termine di preavviso: se "
                "prevede una forma o un termine specifico, quello prevale sul default "
                "legale dei quindici giorni."
            ),
        )

    if p.durata_rapporto == "tempo_determinato":
        return RisultatoRegola(
            famiglia=Famiglia.RECESSO_APERTURA_CREDITO_SENZA_PREAVVISO,
            fondata=True,
            contro_argomento=None,
            fonti=[],
            consolidamento=None,
            nota=(
                "Apertura di credito A TEMPO DETERMINATO: l'art. 1845 c.c. consente il "
                "recesso della banca prima della scadenza solo per giusta causa (salvo "
                "patto contrario), e impone comunque un termine di almeno quindici giorni "
                "per la restituzione delle somme utilizzate. Se l'atto conferma che il "
                "recesso e' avvenuto senza preavviso e senza giusta causa dichiarata, "
                "l'eccezione avversaria e' verosimilmente FONDATA su questo punto - "
                "cercare terreno diverso (esistenza di una giusta causa non ancora "
                "dedotta in giudizio, o un patto contrattuale contrario all'art. 1845 c.c.)."
            ),
        )

    return RisultatoRegola(
        famiglia=Famiglia.RECESSO_APERTURA_CREDITO_SENZA_PREAVVISO,
        fondata=False,
        contro_argomento=None,
        fonti=[],
        consolidamento=None,
        nota=(
            f"Durata del rapporto (tempo determinato/indeterminato) non determinata con "
            f"certezza dall'estrazione (valore: '{p.durata_rapporto}') - la regola non puo' "
            "decidere quale comma dell'art. 1845 c.c. si applica (regole opposte per "
            "tempo determinato vs indeterminato). NON trattare come 'eccezione infondata "
            "di default' - e' un buco da segnalare nel report finale, non un esito "
            "silenzioso. Il campo durata_rapporto non e' ancora popolato da "
            "estrazione_atto.py al momento in cui questa regola e' stata scritta - "
            "questo ramo sara' quello effettivamente preso finche' non viene esteso lo "
            "schema di estrazione."
        ),
    )


# ------------------------------------------------------------------
# Famiglia 4 - ANOMALIE_CONTABILI (usura, anatocismo, commissioni,
# capitalizzazione, valute, mora), aggiunta il 2026-09-02.
#
# Perche' questa e perche' adesso: sull'atto ALFA e' la famiglia di DIECI
# contestazioni su ventuno, e nessun'altra ne vale piu' di due. Scriverla
# e' l'unico intervento che sposti il tool su quell'atto.
#
# La precondizione dirimente NON e' la natura del rapporto - qui il
# rapporto e' sempre bancario - ma la SPECIFICITA' della contestazione,
# ed e' scritta in SUPERFICIE_ATTACCO.md §4: "l'avversario ha indicato i
# conteggi, o ha dedotto genericamente l'anomalia? E' il discrimine che
# decide". La stessa eccezione ("la banca ha applicato interessi
# usurari") e' un'allegazione seria se poggia su un conteggio in atti, e
# una formula di stile se non poggia su nulla.
#
# I due segnali NON hanno lo stesso peso, ed e' la ragione per cui questa
# regola li tratta separatamente invece di sommarli:
# - `conteggi_allegati` e' un fatto verificabile - o un conteggio c'e' o
#   non c'e';
# - `specificita_eccezione` e' un GIUDIZIO del modello, e nella corsa ALFA
#   ha marcato "specifica" un frammento troncato a meta' periodo ("...con
#   un cosiddetto criterio 'per difetto', se si"). Su quel campo da solo
#   non si decide niente.
#
# Le quattro fonti sono verificate contro il grafo il 2026-09-02, per
# numero E per rubrica: art. 2697 c.c. "Onere della prova", art. 115
# c.p.c. "Disponibilita' delle prove", art. 210 c.p.c. "Ordine di
# esibizione alla parte o al terzo", art. 191 c.p.c. "Nomina del
# consulente tecnico". Sono il TESTO DELLA LEGGE, non giurisprudenza: il
# corpus BDP non contiene ancora massime verificate su questo punto, e
# `consolidamento` resta None invece di dichiarare un orientamento mai
# misurato - stessa disciplina della famiglia 9.
#
# La validazione giuridica resta dell'avvocato: SUPERFICIE_ATTACCO.md lo
# dice di se stesso in apertura, e questa regola ne e' la trascrizione.
# ------------------------------------------------------------------


@registra(Famiglia.ANOMALIE_CONTABILI)
def _regola_anomalie_contabili(p: Precondizioni) -> RisultatoRegola:
    if p.conteggi_allegati:
        return RisultatoRegola(
            famiglia=Famiglia.ANOMALIE_CONTABILI,
            fondata=True,
            contro_argomento=None,
            fonti=[],
            consolidamento=None,
            nota=(
                "L'eccezione poggia su conteggi allegati: e' un'allegazione "
                "specifica, e l'argomento della contestazione generica NON si "
                "applica. Eccezione FONDATA nel senso del motore - regge, e non si "
                "confuta con fonti deboli. Terreni diversi da percorrere, in ordine: "
                "(a) se l'opponente ha proposto domanda riconvenzionale di "
                "ripetizione, l'onere probatorio si sposta su di lui e deve produrre "
                "LUI tutti gli estratti conto dall'origine; (b) incontestabilita' "
                "dell'estratto conto approvato ex art. 1832 c.c., se sono decorsi i "
                "termini dalla comunicazione; (c) contestazione nel merito del "
                "conteggio avversario, che e' lavoro contabile e non di questo "
                "motore. Nessuno dei tre e' automatizzato: vanno verificati sui "
                "documenti."
            ),
        )

    if p.specificita_eccezione == "generica" and p.conteggi_nell_atto:
        # Il ramo che impedisce l'errore peggiore che questa regola possa
        # fare. Il contro-argomento qui sotto afferma che l'avversario non
        # ha messo cifre sul tavolo: se l'atto porta una perizia di parte
        # con un saldo rideterminato, quell'affermazione e' smentita dal
        # fascicolo, e finirebbe in un atto depositato.
        # Sull'atto ALFA succedeva davvero: sette contestazioni marcate
        # "generica" dal modello, e a pagina 14 una perizia econometrica che
        # quantifica 150.000,00 euro.
        return RisultatoRegola(
            famiglia=Famiglia.ANOMALIE_CONTABILI,
            fondata=False,
            contro_argomento=None,
            fonti=[],
            consolidamento=None,
            nota=(
                "Contestazione GENERICA nella formulazione, ma l'atto porta conteggi "
                "di parte: il contro-argomento della contestazione non idonea NON si "
                "applica finche' non si verifica se quei conteggi riguardino anche "
                "questa eccezione. Se la riguardano, l'eccezione e' documentata e "
                "vale il ramo dell'eccezione che regge; se sono riferiti ad altro, "
                "vale quello della contestazione generica. La verifica e' una lettura "
                "dell'atto, non un calcolo. NON confutare prima di averla fatta: "
                "sostenere che l'avversario non ha prodotto cifre mentre le ha "
                "prodotte e' un'affermazione che il fascicolo smentisce."
            ),
        )

    if p.specificita_eccezione == "generica":
        return RisultatoRegola(
            famiglia=Famiglia.ANOMALIE_CONTABILI,
            fondata=False,
            contro_argomento=(
                "L'eccezione di anomalia del rapporto e' dedotta in forma generica, "
                "senza conteggi ne' individuazione delle poste contestate: chi "
                "eccepisce l'applicazione di interessi o commissioni non dovuti "
                "afferma un fatto costitutivo della propria pretesa restitutoria e "
                "deve provarlo (art. 2697 c.c.), e il giudice deve porre a "
                "fondamento della decisione le prove proposte dalle parti (art. 115 "
                "c.p.c.). Ne' l'ordine di esibizione (art. 210 c.p.c.) ne' la "
                "consulenza tecnica d'ufficio (art. 191 c.p.c.) sono rimedi "
                "all'inerzia probatoria della parte: sono poteri istruttori "
                "discrezionali del giudice, e non hanno la funzione di procurare "
                "alla parte la prova che essa non ha offerto. Una contestazione che "
                "non individua le poste, i periodi e i criteri di ricalcolo non "
                "mette il giudice in condizione di verificarla, e non e' idonea a "
                "superare le risultanze del conto."
            ),
            fonti=[Fonte("art. 2697 c.c.", ruolo="principale"),
                   Fonte("art. 115 c.p.c.", ruolo="principale"),
                   Fonte("art. 210 c.p.c.", ruolo="subordinato"),
                   Fonte("art. 191 c.p.c.", ruolo="subordinato")],
            consolidamento=None,
            nota=(
                "Precondizione dirimente verificata: contestazione GENERICA, nessun "
                "conteggio allegato e nessun conteggio di parte trovato nel testo "
                "dell'atto (che non e' la prova che non ce ne siano - vedi "
                "`conteggi_di_parte`). Il contro-argomento poggia sul testo di quattro "
                "articoli verificati contro il grafo, NON su giurisprudenza: il "
                "corpus BDP di questo progetto non contiene ancora massime "
                "verificate su questo punto, quindi `consolidamento` resta nullo "
                "invece di dichiarare un orientamento mai misurato. Da rafforzare "
                "con giurisprudenza reale prima dell'uso in un atto vero - un buco "
                "dichiarato, non nascosto."
            ),
        )

    if p.specificita_eccezione == "specifica":
        return RisultatoRegola(
            famiglia=Famiglia.ANOMALIE_CONTABILI,
            fondata=False,
            contro_argomento=None,
            fonti=[],
            consolidamento=None,
            nota=(
                "Contestazione dichiarata SPECIFICA ma senza conteggi allegati: i "
                "due segnali non concordano, e la regola non decide su quello "
                "debole. `conteggi_allegati` e' un fatto (o un conteggio c'e' o non "
                "c'e'); `specificita` e' un giudizio del modello, e nella corsa ALFA "
                "del 2026-09-02 ha marcato 'specifica' un frammento troncato a meta' "
                "periodo. Cosa guardare per sciogliere: se l'atto avversario rinvia "
                "a una consulenza di parte o a un prospetto di ricalcolo prodotto in "
                "giudizio, i conteggi CI SONO e vale il ramo dell'eccezione "
                "specifica; se il rinvio e' a documenti mai prodotti, vale quello "
                "della contestazione generica. NON trattare come infondata di "
                "default."
            ),
        )

    return RisultatoRegola(
        famiglia=Famiglia.ANOMALIE_CONTABILI,
        fondata=False,
        contro_argomento=None,
        fonti=[],
        consolidamento=None,
        nota=(
            f"Specificita' della contestazione non determinata dall'estrazione "
            f"(valore: '{p.specificita_eccezione}') e nessun conteggio allegato - la "
            "regola non puo' decidere quale ramo si applica. Serve rileggere il "
            "passaggio contestato nell'atto: e' l'unico dato che serve, e si vede a "
            "occhio. NON trattare come 'eccezione infondata di default'."
        ),
    )


# ------------------------------------------------------------------
# Famiglia 3 - LEGITTIMAZIONE_CESSIONARIO, aggiunta il 2026-09-02.
#
# E' la famiglia con piu' materiale nel corpus - 393 coppie, 279 decise
# nel merito, 40,5% accolte sui 666 provvedimenti - e la sola in cui
# l'avversario vince quattro volte su dieci. E' anche l'unica in cui il
# nostro stesso grafo contiene un'AUTORITA' AVVERSA: Trib. Bologna,
# decreto 29/05/2025, sull'onere di provare tutte le cessioni intermedie.
# Il retrieval non ha l'annotazione di direzione e potrebbe proporla come
# se sostenesse: la regola non cita nulla, e lo dice nella nota.
#
# **Questa regola non confuta mai, e non e' una svista.** Il fatto che
# decide e' che cosa ha prodotto il cessionario - il solo avviso in
# Gazzetta Ufficiale, oppure il contratto di cessione con l'evidenza che
# quello specifico credito ci sta dentro - e quel fatto sta nel NOSTRO
# fascicolo, non nell'atto avversario e non nel corpus. Nessun contro-
# argomento e' scrivibile senza saperlo, e scriverlo lo stesso
# significherebbe affermare di aver prodotto documenti che nessuno ha
# guardato.
#
# Quello che la regola fa, e che oggi non fa nessuno, e' RICONOSCERE la
# situazione e consegnare la lista di cio' che serve. Per 279 casi su cui
# il sistema oggi tace e' il salto piu' grosso disponibile - e nel
# dossier l'esito smette di essere "famiglia senza regola" (che manda
# allo sviluppo) e diventa "manca un fatto" (che manda al fascicolo).
#
# Il tentativo di ricavare la precondizione dal corpus e' stato fatto ed
# e' fallito: i marcatori nelle motivazioni non separano l'accoglimento
# dal rigetto (36%, 42%, 29% contro una base del 40,5%). La misura per
# esteso sta in `cessione_del_credito`, insieme alla ragione per cui non
# va ritentata.
# ------------------------------------------------------------------


@registra(Famiglia.LEGITTIMAZIONE_CESSIONARIO)
def _regola_legittimazione_cessionario(p: Precondizioni) -> RisultatoRegola:
    if not p.creditore_e_cessionario:
        return RisultatoRegola(
            famiglia=Famiglia.LEGITTIMAZIONE_CESSIONARIO,
            fondata=False,
            contro_argomento=None,
            fonti=[],
            consolidamento=None,
            nota=(
                "Dall'estrazione il creditore non risulta cessionario del credito: "
                "questa famiglia non si aggancia. Non e' un giudizio di infondatezza "
                "nel merito dell'eccezione - e' un mancato aggancio, e va riletto se "
                "il credito e' invece stato acquistato in blocco."
            ),
        )

    if p.contestata_solo_gazzetta:
        aggravante = (
            " L'atto lamenta inoltre una CATENA di cessioni: in quel caso l'onere si "
            "moltiplica, perche' l'ultimo cessionario deve provare tutte le cessioni "
            "intermedie (nemo plus iuris transferre potest quam ipse habet). Su questo "
            "punto il nostro stesso corpus contiene un provvedimento SFAVOREVOLE (Trib. "
            "Bologna, decreto 29/05/2025): se il retrieval lo propone, non e' una fonte "
            "a supporto."
        ) if p.cessioni_plurime else ""
        return RisultatoRegola(
            famiglia=Famiglia.LEGITTIMAZIONE_CESSIONARIO,
            fondata=True,
            contro_argomento=None,
            fonti=[],
            consolidamento=None,
            nota=(
                "L'avversario contesta specificamente che sia stato prodotto il solo "
                "avviso di cessione in Gazzetta Ufficiale. Su questo punto la "
                "giurisprudenza e' in larga parte SFAVOREVOLE al creditore, e il "
                "nostro corpus lo conferma: e' la famiglia piu' numerosa (279 "
                "eccezioni decise nel merito) ed e' quella con la quota di "
                "accoglimento piu' alta, il 40,5%. Eccezione FONDATA nel senso del "
                "motore: regge, e non si confuta con l'avviso in Gazzetta."
                + aggravante +
                " Cosa serve per superarla, e va cercato NEL NOSTRO FASCICOLO perche' "
                "dall'atto avversario non risulta: (a) il contratto di cessione, non "
                "il solo avviso; (b) l'evidenza che QUESTO specifico credito rientri "
                "fra quelli ceduti - l'allegato o l'elenco, con l'indicazione del "
                "rapporto; (c) se le cessioni sono piu' d'una, la stessa evidenza per "
                "ognuna. Se i tre documenti ci sono, l'eccezione cade e la regola va "
                "riapplicata; se non ci sono, il terreno e' questo e conviene saperlo "
                "prima dell'udienza."
            ),
        )

    return RisultatoRegola(
        famiglia=Famiglia.LEGITTIMAZIONE_CESSIONARIO,
        fondata=False,
        contro_argomento=None,
        fonti=[],
        consolidamento=None,
        nota=(
            "Il creditore e' cessionario e l'eccezione tocca la sua legittimazione, ma "
            "dall'atto non risulta COME sia contestata: se per la produzione del solo "
            "avviso in Gazzetta Ufficiale, o per altro. E' l'unico dato che serve, e "
            "decide da solo. Da guardare in due punti: nell'atto avversario, il "
            "passaggio in cui elenca cosa la controparte ha prodotto; nel nostro "
            "fascicolo, se oltre all'avviso ci sia il contratto di cessione con "
            "l'evidenza dell'inclusione di questo credito. NON trattare come "
            "'eccezione infondata di default': in questa famiglia l'avversario vince "
            "quattro volte su dieci."
        ),
    )


# ------------------------------------------------------------------
# Famiglia 5 - VIZI_FIDEIUSSIONE, aggiunta il 2026-09-03.
#
# Seconda del corpus per volume (278 coppie, 196 decise nel merito) e la
# prima con una quota di accoglimento BASSA - 20,4% - cioe' la prima in
# cui una confutazione vera e' probabile, non solo un avvertimento.
#
# La precondizione non e' quella che SUPERFICIE_ATTACCO.md §5 indicava.
# Li' e' la qualita' del fideiussore; misurata sui 196 casi decisi, non
# separa niente (`socio`/`amministratore` compaiono in 3 casi in tutto,
# `consumatore` in 11, al 18% contro una base del 20,4%) ed e' per giunta
# il campo che il modello asserisce senza che nulla lo verifichi. Cio'
# che separa e' QUALE VIZIO viene dedotto - vedi la tabella per esteso in
# `vizi_della_fideiussione`, con i suoi limiti.
#
# Due estremi opposti, ed e' il motivo per cui la regola non e'
# simmetrica:
# - **schema ABI / antitrust**: 2 accolte su 30. E' il vizio piu' dedotto
#   fra quelli riconoscibili e il piu' rigettato, e su 30 casi il dato
#   regge abbastanza da fondarci un contro-argomento;
# - **art. 1957**: 20 accolte su 69, il 29%, sopra la media e con la base
#   piu' larga. Li' l'eccezione regge piu' spesso del solito.
#
# Le righe con sei e dieci casi (art. 1938, genericita') NON fondano un
# ramo: sono nominate nelle note e basta. Un rigetto su sei casi non e'
# una regola, e' un aneddoto.
#
# Le tre fonti sono verificate contro il grafo per numero E rubrica il
# 2026-09-03: art. 1419 c.c. "Nullita' parziale", art. 1938 c.c.
# "Fideiussione per obbligazioni future o condizionali", art. 1957 c.c.
# "Scadenza dell'obbligazione principale". Le Sezioni Unite 41994/2021
# NON sono citate: non sono nel nostro corpus, e questa regola non
# dichiara fonti che non ha verificato - e' la stessa disciplina delle
# famiglie 4 e 9.
# ------------------------------------------------------------------


@registra(Famiglia.VIZI_FIDEIUSSIONE)
def _regola_vizi_fideiussione(p: Precondizioni) -> RisultatoRegola:
    if p.vizio_fideiussione == "schema_abi":
        return RisultatoRegola(
            famiglia=Famiglia.VIZI_FIDEIUSSIONE,
            fondata=False,
            contro_argomento=(
                "L'eccezione deduce la nullita' della fideiussione per conformita' "
                "allo schema ABI, ma ne fa discendere la caducazione dell'INTERA "
                "garanzia. La conseguenza non segue dalla premessa: l'invalidita' che "
                "colpisce singole clausole non travolge il contratto, salvo che "
                "risulti che i contraenti non lo avrebbero concluso senza la parte "
                "colpita (art. 1419 c.c.), e quella prova grava su chi la invoca. "
                "L'obbligazione di garanzia resta, e restano le clausole che non sono "
                "state dichiarate nulle: l'eccezione, se non individua quali clausole "
                "siano state applicate in concreto a suo danno e in che misura, non "
                "incide sul credito azionato."
            ),
            fonti=[Fonte("art. 1419 c.c.", ruolo="principale")],
            consolidamento=None,
            nota=(
                "Vizio dedotto: conformita' allo schema ABI. Nel corpus e' il vizio "
                "piu' dedotto fra quelli riconoscibili e il piu' rigettato - 24 rigetti "
                "su 27 casi decisi, l'11% di accoglimento contro una base del 20,4% "
                "sull'intera famiglia. Il dato e' una frequenza osservata su ventisette "
                "casi, non una previsione su questa causa. Il contro-argomento poggia "
                "sul testo dell'art. 1419 c.c., verificato contro il grafo, NON sulle "
                "Sezioni Unite 41994/2021, che non sono nel nostro corpus e quindi non "
                "si citano: e' un buco dichiarato, e va colmato con giurisprudenza "
                "reale prima dell'uso in un atto vero."
            ),
        )

    if p.vizio_fideiussione == "decadenza":
        return RisultatoRegola(
            famiglia=Famiglia.VIZI_FIDEIUSSIONE,
            fondata=True,
            contro_argomento=None,
            fonti=[],
            consolidamento=None,
            nota=(
                "Vizio dedotto: decadenza ex art. 1957 c.c. E' l'eccezione che nel "
                "corpus regge piu' della media - 11 accoglimenti su 42 casi decisi, il "
                "26% contro una base del 20,4% - ed e' anche quella con la base piu' "
                "larga fra i vizi riconosciuti, quindi il dato e' il piu' solido. Non si confuta a "
                "tavolino: la risposta dipende da due fatti che stanno nel NOSTRO "
                "fascicolo e non nell'atto avversario. (a) Il contratto contiene una "
                "clausola di deroga al termine dell'art. 1957? In quel caso va "
                "verificato se sia fra quelle di cui si discute la nullita', perche' "
                "se cade la deroga il termine torna a correre. (b) Le istanze contro "
                "il debitore principale sono state proposte nel termine, e c'e' "
                "l'evidenza documentale della data? Se il termine e' stato rispettato "
                "l'eccezione cade a prescindere dalla clausola, ed e' la strada piu' "
                "breve."
            ),
        )

    if p.specificita_eccezione == "generica":
        return RisultatoRegola(
            famiglia=Famiglia.VIZI_FIDEIUSSIONE,
            fondata=False,
            contro_argomento=(
                "L'eccezione di invalidita' della fideiussione e' dedotta senza "
                "individuare la clausola viziata ne' l'effetto che ne deriverebbe sul "
                "credito azionato. Chi eccepisce la nullita' deve indicare quale "
                "pattuizione ne sia colpita e perche' (art. 2697 c.c.), tanto piu' che "
                "l'invalidita' di singole clausole non travolge il contratto se non si "
                "prova che senza di esse non sarebbe stato concluso (art. 1419 c.c.). "
                "Una deduzione che non individua la clausola non mette il giudice in "
                "condizione di verificarla."
            ),
            fonti=[Fonte("art. 2697 c.c.", ruolo="principale"),
                   Fonte("art. 1419 c.c.", ruolo="principale")],
            consolidamento=None,
            nota=(
                "Nessun vizio riconoscibile nominato e contestazione dichiarata "
                "generica: i due segnali concordano. Nel corpus le eccezioni respinte "
                "per genericita' o novita' sono 10 su 10, ma dieci casi non fondano "
                "una regola e quel numero e' qui per contesto, non per decidere - "
                "decide la genericita', che e' un difetto della deduzione, non una "
                "statistica."
            ),
        )

    if p.vizio_fideiussione:
        return RisultatoRegola(
            famiglia=Famiglia.VIZI_FIDEIUSSIONE,
            fondata=False,
            contro_argomento=None,
            fonti=[],
            consolidamento=None,
            nota=(
                "Vizio dedotto riconosciuto ('%s') ma non coperto da un ramo di questa "
                "regola: nel corpus ha troppo pochi casi decisi perche' se ne possa "
                "trarre qualcosa (l'importo massimo ex art. 1938 c.c. ne ha due, la "
                "liberazione ex art. 1956 c.c. sei, il disconoscimento della "
                "sottoscrizione tre). Un rigetto su sei casi non e' una regola, e' un "
                "aneddoto. Va trattato a mano: il dato di ingresso c'e' ed e' "
                "determinato, manca la base per decidere."
                % p.vizio_fideiussione
            ),
        )

    return RisultatoRegola(
        famiglia=Famiglia.VIZI_FIDEIUSSIONE,
        fondata=False,
        contro_argomento=None,
        fonti=[],
        consolidamento=None,
        nota=(
            "L'eccezione riguarda la fideiussione ma non nomina un vizio "
            "riconoscibile, e la sua specificita' non e' determinata: la regola non "
            "puo' decidere quale ramo si applica. Serve rileggere il passaggio e dire "
            "che cosa viene dedotto - conformita' allo schema ABI, decadenza ex art. "
            "1957 c.c., liberazione ex art. 1956 c.c., mancanza dell'importo massimo, "
            "disconoscimento della firma. E' l'unico dato che serve. NON trattare come "
            "'eccezione infondata di default'."
        ),
    )


# ------------------------------------------------------------------
# Famiglia 10 - COMPETENZA_E_RITO, aggiunta il 2026-09-03.
#
# La prima regola che NON poggia su una frequenza del corpus, e non per
# scelta: il 2026-09-03 e' stato accertato che su questa famiglia i
# marcatori lessicali non separano l'accoglimento dal rigetto (nessuna
# riga con insieme uno scarto dalla base del 38,6% e un campione
# sufficiente - vedi STATO_PROGETTO §5). La precondizione qui non e' una
# parola che qualcuno scrive: e' un fatto geografico, e va CALCOLATO.
#
# Il ramo che confuta poggia sul TESTO DELL'ART. 38 co. 2 c.p.c.,
# verificato contro il grafo per numero e rubrica ("Incompetenza"):
# "l'eccezione di incompetenza per territorio si ha per non proposta se
# non contiene l'indicazione del giudice che la parte ritiene
# competente". E' un requisito di legge, non una statistica, e infatti
# **il corpus non lo conferma**: le eccezioni territoriali riconoscibili
# sono 18 su 192, e fra quelle che non indicano il giudice ce ne sono 2
# accolte su 3. Tre casi non dicono niente in nessuna direzione, e il
# ramo non e' scritto su di loro - ma vanno segnalati, perche' un domani
# quel numero potra' crescere e allora dira' qualcosa.
#
# Il confronto geografico NON produce mai una confutazione: dice solo se
# valga la pena guardare. Le ragioni per cui non puo' dire di piu' stanno
# in `foro_dell_atto` - non si sa di chi sia ciascun indirizzo, la
# competenza non e' solo anagrafica, e sui 52 atti reali nove riscontri
# negativi su dieci avevano fra gli indirizzi la sede del creditore.
# ------------------------------------------------------------------


@registra(Famiglia.COMPETENZA_E_RITO)
def _regola_competenza_e_rito(p: Precondizioni) -> RisultatoRegola:
    if p.indica_giudice_competente is False:
        return RisultatoRegola(
            famiglia=Famiglia.COMPETENZA_E_RITO,
            fondata=False,
            contro_argomento=(
                "L'eccezione di incompetenza per territorio non indica quale giudice "
                "la parte ritenga competente. L'art. 38 co. 2 c.p.c. dispone che in "
                "tal caso l'eccezione 'si ha per non proposta': non si tratta di un "
                "difetto di allegazione da valutare nel merito, ma di una conseguenza "
                "che la norma ricollega direttamente all'omissione. L'eccezione, cosi' "
                "come formulata, non e' idonea a devolvere al giudice la questione di "
                "competenza, e la causa resta davanti all'ufficio adito."
            ),
            fonti=[Fonte("art. 38 c.p.c.", ruolo="principale")],
            consolidamento=None,
            nota=(
                "Precondizione dirimente verificata sul testo dell'eccezione: e' "
                "un'eccezione di competenza TERRITORIALE e non nomina un giudice "
                "alternativo. Il contro-argomento poggia sul testo dell'art. 38 co. 2 "
                "c.p.c., verificato contro il grafo - e' un requisito di legge, non "
                "una frequenza osservata. Il corpus su questo punto NON conferma "
                "nulla: le eccezioni territoriali riconoscibili sono 18 su 192, e fra "
                "quelle prive dell'indicazione ce ne sono due accolte su tre. Tre casi "
                "non dicono niente, e questo ramo non e' scritto su di loro. Prima "
                "dell'uso in un atto vero va verificato che l'eccezione sia stata "
                "sollevata nella comparsa tempestiva: la decadenza del primo comma e' "
                "l'altra meta' della norma, e quella dipende dal fascicolo."
            ),
        )

    if p.foro_adito == "nessun_riscontro":
        return RisultatoRegola(
            famiglia=Famiglia.COMPETENZA_E_RITO,
            fondata=True,
            contro_argomento=None,
            fonti=[],
            consolidamento=None,
            nota=(
                "L'eccezione indica il giudice che ritiene competente, e il controllo "
                "geografico non aiuta: l'ufficio adito non corrisponde al tribunale di "
                "nessuno degli indirizzi dichiarati in epigrafe. Non e' una diagnosi "
                "di incompetenza - gli indirizzi trovati possono essere quelli del "
                "creditore, ed e' il caso di nove riscontri negativi su dieci fra i 52 "
                "atti misurati - ma e' il caso in cui vale la pena guardare, e va "
                "guardato PRIMA dell'udienza. Cosa verificare, in ordine: (a) esiste "
                "un foro contrattuale pattuito, e la clausola e' valida ed "
                "esclusiva? (b) il debitore ha agito come consumatore, nel qual caso "
                "il foro e' quello della sua residenza e non e' derogabile; (c) i "
                "convenuti sono piu' d'uno, e allora vale il cumulo. Nessuna delle tre "
                "si vede dagli indirizzi."
            ),
        )

    if p.indica_giudice_competente is True and p.foro_adito == "compatibile":
        return RisultatoRegola(
            famiglia=Famiglia.COMPETENZA_E_RITO,
            fondata=False,
            contro_argomento=None,
            fonti=[],
            consolidamento=None,
            nota=(
                "L'eccezione e' formalmente completa - indica il giudice che ritiene "
                "competente - e il controllo geografico non la smentisce: l'ufficio "
                "adito corrisponde al tribunale di almeno uno degli indirizzi in "
                "epigrafe. E' una COMPATIBILITA' ANAGRAFICA, non una competenza "
                "accertata: la competenza in diritto non e' stata valutata, e puo' "
                "poggiare o cadere su un titolo che negli indirizzi non si vede (foro "
                "contrattuale, foro del consumatore, cumulo di convenuti, "
                "connessione). Non si confuta con la geografia: serve la lettura del "
                "contratto e la qualifica delle parti."
            ),
        )

    return RisultatoRegola(
        famiglia=Famiglia.COMPETENZA_E_RITO,
        fondata=False,
        contro_argomento=None,
        fonti=[],
        consolidamento=None,
        nota=(
            "La regola non puo' decidere: dall'eccezione non risulta che sia di "
            "competenza territoriale (l'art. 38 co. 2 c.p.c. pone il requisito "
            "dell'indicazione solo per quella, non per materia o valore) e il "
            "confronto geografico non e' stato possibile - manca l'ufficio in "
            "intestazione, oppure nessun indirizzo dell'epigrafe e' riconducibile a un "
            "tribunale, oppure l'atto e' di secondo grado, dove il confronto non si "
            "applica. Va letta a mano. NON trattare come 'eccezione infondata di "
            "default': in questa famiglia l'avversario e' accolto nel 38,6% dei casi "
            "decisi, la quota piu' alta dopo la legittimazione del cessionario."
        ),
    )


# ------------------------------------------------------------------
# Le quattordici famiglie restanti, popolate il 2026-09-03.
#
# Scritte insieme e con lo stesso impianto, perche' hanno lo stesso
# problema: nessuna ha, da sola, un campione che regga un ramo come
# reggeva lo schema ABI con 27 casi. Inventare per ciascuna una tesi
# giuridica propria sarebbe stato scrivere quattordici argomenti che
# nessuno ha verificato.
#
# L'impianto e' invece quello che il corpus conferma tre volte su tre -
# anomalie contabili, vizi della fideiussione, competenza - e che
# SUPERFICIE_ATTACCO.md enuncia in apertura: **quasi nessuna eccezione e'
# vincente o perdente in assoluto; lo diventa in funzione di cio' che chi
# la solleva ha allegato**. Ogni regola qui sotto ha quindi tre rami:
#
# 1. l'eccezione non soddisfa il REQUISITO DI ALLEGAZIONE che quella
#    specifica materia impone -> si confuta, sul testo dell'articolo che
#    quel requisito lo pone, verificato contro il grafo per numero e
#    rubrica il 2026-09-03;
# 2. il corpus dice che in quella famiglia l'avversario vince spesso ->
#    l'eccezione REGGE, e la nota consegna cosa verificare;
# 3. non si sa -> non si decide, e si dice cosa guardare.
#
# La quota di accoglimento di ciascuna famiglia e' riportata nella nota
# del ramo 2 con la sua numerosita', e non e' una previsione: e' la
# frequenza osservata sui 666 provvedimenti del 2026-09-02.
#
# Due famiglie non hanno nemmeno questo: `saldaconto_art_50_tub` ha tre
# coppie nel corpus e `leasing` due. Li' la regola riconosce e si ferma,
# perche' tre casi non fondano niente.
# ------------------------------------------------------------------


def _regola_per_allegazione(
    famiglia: "Famiglia", p: "Precondizioni", *, cosa_indicare: str,
    contro: str, fonti: list["Fonte"], quota: str, checklist: str,
) -> "RisultatoRegola":
    """L'impianto comune delle quattordici. Non e' una scorciatoia: e'
    l'unico modo di non ripetere quattordici volte la stessa struttura e
    poi sbagliarla in una."""
    if p.specificita_eccezione == "generica":
        return RisultatoRegola(
            famiglia=famiglia, fondata=False, contro_argomento=contro,
            fonti=fonti, consolidamento=None,
            nota=("Precondizione verificata: contestazione GENERICA. Per questa "
                  "materia l'eccezione deve indicare %s, e non lo fa. Il "
                  "contro-argomento poggia sul testo degli articoli citati, "
                  "verificati contro il grafo, NON su giurisprudenza: il corpus BDP "
                  "non contiene ancora massime verificate su questo punto, e "
                  "`consolidamento` resta nullo invece di dichiarare un orientamento "
                  "mai misurato. Da rafforzare prima dell'uso in un atto vero."
                  % cosa_indicare))
    if p.specificita_eccezione == "specifica":
        return RisultatoRegola(
            famiglia=famiglia, fondata=True, contro_argomento=None, fonti=[],
            consolidamento=None,
            nota=("Contestazione specifica: l'argomento della deduzione generica non "
                  "si applica, e la regola non ne ha un altro. %s Eccezione FONDATA "
                  "nel senso del motore - regge, e non si confuta con fonti deboli. "
                  "Cosa verificare: %s" % (quota, checklist)))
    return RisultatoRegola(
        famiglia=famiglia, fondata=False, contro_argomento=None, fonti=[],
        consolidamento=None,
        nota=("Specificita' della contestazione non determinata dall'estrazione "
              "(valore: '%s'): la regola non puo' decidere quale ramo si applica. "
              "Serve rileggere il passaggio e dire se indichi %s. NON trattare come "
              "'eccezione infondata di default'." % (p.specificita_eccezione, cosa_indicare)))


#: Le quattordici, in una tabella invece che in quattordici funzioni
#: quasi identiche. Ogni voce: che cosa l'eccezione deve indicare, il
#: contro-argomento se non lo indica, le fonti (verificate contro il
#: grafo per numero E rubrica il 2026-09-03), la quota di accoglimento
#: osservata con la sua numerosita', e la lista di cosa verificare quando
#: l'eccezione regge.
_PER_ALLEGAZIONE: dict[Famiglia, dict] = {
    Famiglia.PRESCRIZIONE: dict(
        cosa_indicare="quale termine invoca, da quale data lo fa decorrere e perche'",
        contro=(
            "L'eccezione di prescrizione e' dedotta senza individuare il termine "
            "invocato ne' il momento da cui lo si fa decorrere. La prescrizione "
            "comincia a decorrere dal giorno in cui il diritto puo' essere fatto "
            "valere (art. 2935 c.c.), e quel giorno va allegato: senza, non e' "
            "possibile verificare ne' quale termine si applichi - ordinario decennale "
            "(art. 2946 c.c.) o quinquennale per le prestazioni periodiche (art. 2948 "
            "c.c.) - ne' se sia maturato. L'onere di allegare il dies a quo grava su "
            "chi eccepisce, ed e' un onere di allegazione prima che di prova."),
        fonti=[Fonte("art. 2935 c.c.", ruolo="principale"),
               Fonte("art. 2946 c.c.", ruolo="principale"),
               Fonte("art. 2948 c.c.", ruolo="subordinato")],
        quota="Nel corpus questa famiglia e' accolta nel 28% dei 134 casi decisi.",
        checklist=(
            "(a) il dies a quo indicato dall'avversario e' corretto - per il conto "
            "corrente la chiusura del rapporto, non le singole rimesse, salvo che si "
            "discuta di rimesse solutorie; (b) esistono atti interruttivi (art. 2943 "
            "c.c.) o un riconoscimento del debito (art. 2944 c.c.), con la data e il "
            "documento; (c) il termine invocato e' coerente con l'istituto - il "
            "verificatore ha gia' trovato in passato un art. 2946 citato bene e "
            "computato a cinque anni."),
    ),
    Famiglia.TAEG_ISC_INDETERMINATEZZA: dict(
        cosa_indicare="quale voce di costo sarebbe stata omessa dal calcolo e con "
                      "quale effetto sul tasso",
        contro=(
            "L'eccezione di indeterminatezza del TAEG/ISC non individua quale voce di "
            "costo sarebbe stata esclusa dal computo, ne' quantifica lo scostamento "
            "che ne deriverebbe. L'art. 117 TUB richiede che il contratto indichi il "
            "tasso e ogni altro prezzo e condizione praticati: e' un requisito "
            "verificabile sul documento, e chi ne deduce la violazione deve indicare "
            "la clausola e la voce. Una deduzione che si limita ad affermare "
            "l'indeterminatezza non consente il confronto fra il dato contrattuale e "
            "quello praticato, che e' l'unico modo di accertarla."),
        fonti=[Fonte("art. 117 TUB", ruolo="principale"),
               Fonte("art. 1346 c.c.", ruolo="subordinato")],
        quota="Nel corpus questa famiglia e' accolta nel 21% dei 112 casi decisi.",
        checklist=(
            "(a) il contratto indica il tasso e le condizioni, e in quale clausola; "
            "(b) lo scostamento dedotto e' calcolato su quali voci; (c) se "
            "l'indeterminatezza fosse accertata, l'effetto e' la sostituzione del "
            "tasso ex art. 117 co. 7 TUB, non la gratuita' del rapporto: e' una "
            "differenza che cambia il quantum e va misurata."),
    ),
    Famiglia.CONTESTAZIONE_CTU: dict(
        cosa_indicare="quali passaggi della consulenza siano viziati e per quale "
                      "ragione tecnica",
        contro=(
            "La contestazione della consulenza tecnica non individua i passaggi "
            "censurati ne' la ragione tecnica della censura. La consulenza non e' un "
            "mezzo di prova ma uno strumento di valutazione affidato al giudice (artt. "
            "61 e 191 c.p.c.), e le osservazioni delle parti hanno la sede e i termini "
            "dell'art. 195 c.p.c.: una contestazione generica non impone al giudice ne' "
            "di disattenderla ne' di rinnovare le indagini (art. 196 c.p.c.), che resta "
            "un potere discrezionale."),
        fonti=[Fonte("art. 191 c.p.c.", ruolo="principale"),
               Fonte("art. 195 c.p.c.", ruolo="subordinato"),
               Fonte("art. 196 c.p.c.", ruolo="subordinato")],
        quota="Nel corpus questa famiglia e' accolta nel 36% dei 36 casi decisi.",
        checklist=(
            "(a) le censure sono state proposte nei termini dell'art. 195 c.p.c. o "
            "compaiono per la prima volta ora; (b) riguardano il metodo o solo il "
            "risultato; (c) attenzione a non confondere la consulenza d'ufficio con la "
            "CONSULENZA DI PARTE: contestare la seconda, o chiederne una d'ufficio, "
            "sono cose diverse e ricadono altrove."),
    ),
    Famiglia.MEDIAZIONE_PROCEDIBILITA: dict(
        cosa_indicare="quale adempimento sarebbe mancato e in quale fase",
        contro=(
            "L'eccezione di improcedibilita' non individua quale adempimento sarebbe "
            "mancato ne' in quale fase del giudizio. Nell'opposizione a decreto "
            "ingiuntivo (art. 645 c.p.c.) la posizione sostanziale delle parti non "
            "coincide con quella formale, e da questo dipende su chi gravi l'onere di "
            "attivare il procedimento: l'eccezione dedotta genericamente non consente "
            "di stabilire se l'adempimento fosse dovuto, da chi, e se sia stato "
            "compiuto. Chi la solleva deve almeno indicare quale adempimento manchi."),
        fonti=[Fonte("art. 645 c.p.c.", ruolo="subordinato")],
        quota=("Nel corpus questa famiglia e' accolta nel 48% dei 27 casi decisi - la "
               "quota piu' alta di tutte, su un campione piccolo."),
        checklist=(
            "(a) la domanda di mediazione e' stata depositata, da chi e quando; (b) la "
            "banca ha partecipato all'incontro o e' rimasta assente, ed e' un fatto che "
            "l'avversario allega spesso; (c) il primo incontro si e' concluso con un "
            "verbale, e cosa dice."),
    ),
    Famiglia.AMMORTAMENTO_ALLA_FRANCESE: dict(
        cosa_indicare="quale clausola produrrebbe la capitalizzazione e con quale "
                      "differenza di importo",
        contro=(
            "L'eccezione non individua la clausola dalla quale deriverebbe la "
            "capitalizzazione degli interessi, ne' quantifica la differenza rispetto a "
            "un piano che ne fosse privo. Il divieto dell'art. 1283 c.c. riguarda gli "
            "interessi SCADUTI che producono a loro volta interessi: dedurlo dal solo "
            "nome del piano di ammortamento, senza indicare la clausola e senza il "
            "raffronto numerico, non consente di verificare se la capitalizzazione ci "
            "sia."),
        fonti=[Fonte("art. 1283 c.c.", ruolo="principale"),
               Fonte("art. 821 c.c.", ruolo="subordinato")],
        quota="Nel corpus questa famiglia e' accolta nel 19% dei 42 casi decisi.",
        checklist=(
            "(a) il contratto allega il piano di ammortamento e con quale periodicita'; "
            "(b) il raffronto numerico prodotto dall'avversario, se c'e', su quale "
            "criterio alternativo poggia; (c) l'eccezione riguarda la capitalizzazione "
            "o l'indeterminatezza del regime finanziario, che sono due cose diverse e "
            "spesso vengono dedotte insieme."),
    ),
    Famiglia.QUALIFICAZIONE_CONSUMATORE: dict(
        cosa_indicare="per quale scopo il garante o il debitore avrebbe agito",
        contro=(
            "L'eccezione afferma la qualita' di consumatore senza allegare per quale "
            "scopo la parte avrebbe agito. La qualifica non discende dall'essere "
            "persona fisica: dipende dall'estraneita' dell'atto all'attivita' "
            "professionale, ed e' un fatto che va allegato e provato da chi ne trae la "
            "conseguenza (art. 2697 c.c.). Senza l'allegazione dello scopo non e' "
            "possibile ne' verificare la qualifica ne' contestarla."),
        fonti=[Fonte("art. 2697 c.c.", ruolo="principale")],
        quota=("Nel corpus questa famiglia e' accolta nel 54% dei 46 casi decisi - la "
               "quota piu' alta fra quelle con almeno quaranta casi."),
        checklist=(
            "(a) il garante e' socio, amministratore o comunque collegato alla societa' "
            "garantita, e con quale documento lo si prova; (b) la qualifica e' dedotta "
            "per spostare il foro o per altro effetto, perche' cambia cosa serve "
            "provare; (c) ATTENZIONE: la qualita' del fideiussore che l'estrazione "
            "riporta viene dal modello e non e' verificata da nessun calcolo (ARRETRATO "
            "D5) - non usarla come se fosse un accertamento."),
    ),
    Famiglia.FORMA_SCRITTA_ART_117_TUB: dict(
        cosa_indicare="quale contratto sarebbe privo di forma scritta e in che senso",
        contro=(
            "L'eccezione di difetto di forma non individua quale contratto ne sarebbe "
            "privo. L'art. 117 TUB impone la forma scritta a pena di nullita' e la "
            "consegna di un esemplare al cliente: sono requisiti verificabili sul "
            "documento, e chi ne deduce la mancanza deve dire di quale documento parla. "
            "Una deduzione generica non consente il riscontro, tanto piu' che la "
            "nullita' e' posta nell'interesse del cliente e opera nei limiti in cui "
            "questi la faccia valere."),
        fonti=[Fonte("art. 117 TUB", ruolo="principale"),
               Fonte("art. 1418 c.c.", ruolo="subordinato")],
        quota=("Nel corpus questa famiglia e' accolta nel 10% dei 30 casi decisi - la "
               "quota piu' bassa di tutte."),
        checklist=(
            "(a) il contratto prodotto reca la sottoscrizione del cliente; (b) esiste "
            "prova della consegna dell'esemplare; (c) la nullita' e' dedotta per "
            "l'intero rapporto o per una singola pattuizione, perche' l'effetto sul "
            "credito e' diverso."),
    ),
    Famiglia.GARANZIA_IPOTECARIA: dict(
        cosa_indicare="quale profilo dell'iscrizione sarebbe viziato",
        contro=(
            "L'eccezione non individua quale profilo dell'iscrizione ipotecaria sarebbe "
            "viziato. L'ipoteca si costituisce con l'iscrizione nei registri "
            "immobiliari (art. 2808 c.c.), e i suoi effetti - grado, estensione agli "
            "interessi - sono determinati dalla legge e verificabili sulla nota di "
            "iscrizione. Una contestazione che non indica il profilo censurato non "
            "consente il riscontro documentale."),
        fonti=[Fonte("art. 2808 c.c.", ruolo="principale"),
               Fonte("art. 2855 c.c.", ruolo="subordinato")],
        quota="Nel corpus questa famiglia e' accolta nel 17% dei 23 casi decisi.",
        checklist=(
            "(a) la nota di iscrizione e' prodotta; (b) la censura riguarda la "
            "costituzione, il grado o l'estensione agli interessi, che hanno discipline "
            "diverse; (c) l'eccezione incide sul credito o solo sulla garanzia: sono "
            "due domande, e spesso l'avversario le confonde."),
    ),
    Famiglia.DOCUMENTAZIONE_ART_119_TUB: dict(
        cosa_indicare="quando la richiesta e' stata fatta, per quale periodo e con "
                      "quale offerta di spese",
        contro=(
            "L'eccezione non individua gli estremi della richiesta di documentazione. "
            "L'art. 119 TUB attribuisce al cliente il diritto di ottenere copia della "
            "documentazione relativa alle singole operazioni degli ultimi dieci anni, "
            "dietro rimborso delle spese: la richiesta deve quindi essere circoscritta "
            "nel tempo e nell'oggetto, e chi ne lamenta l'inevasione deve indicare "
            "quando l'ha formulata e per che cosa. Senza, non e' possibile verificare "
            "se fosse una richiesta ex art. 119 TUB o una domanda esplorativa."),
        fonti=[Fonte("art. 119 TUB", ruolo="principale")],
        quota="Nel corpus questa famiglia e' accolta nel 38% dei 26 casi decisi.",
        checklist=(
            "(a) la richiesta e' agli atti, con data e destinatario; (b) copre un "
            "decennio o un periodo piu' ampio; (c) c'e' l'offerta di rimborso delle "
            "spese; (d) che cosa e' stato consegnato in risposta e quando."),
    ),
    Famiglia.SEGNALAZIONE_CENTRALE_RISCHI: dict(
        cosa_indicare="quale segnalazione, quando, e quale danno ne sarebbe derivato",
        contro=(
            "L'eccezione non individua la segnalazione contestata ne' il danno che ne "
            "sarebbe derivato. La domanda risarcitoria richiede l'allegazione del "
            "fatto, del danno e del nesso (art. 2043 c.c.), e la segnalazione va "
            "individuata per data e contenuto: dedotta genericamente non consente ne' "
            "di verificarne l'illegittimita' ne' di quantificare alcunche'. Va inoltre "
            "considerato che la contestazione della segnalazione non incide di per se' "
            "sull'esistenza del credito azionato."),
        fonti=[Fonte("art. 2043 c.c.", ruolo="principale"),
               Fonte("art. 2697 c.c.", ruolo="subordinato")],
        quota=("Nel corpus questa famiglia e' accolta nell'11% dei 19 casi decisi, il "
               "campione piu' piccolo fra quelli usati per una quota."),
        checklist=(
            "(a) la segnalazione e' individuata per data e importo; (b) il danno e' "
            "allegato e in che forma; (c) la domanda e' riconvenzionale o solo "
            "un'eccezione, perche' cambia cosa deve essere provato e da chi."),
    ),
    Famiglia.CAMBIALE_TITOLO_ESECUTIVO: dict(
        cosa_indicare="quale requisito del titolo sarebbe mancante",
        contro=(
            "L'eccezione non individua quale requisito del titolo sarebbe mancante. "
            "L'esecuzione forzata puo' aver luogo solo in forza di un titolo esecutivo "
            "per un diritto certo, liquido ed esigibile (art. 474 c.p.c.), e i "
            "requisiti del titolo cambiario sono tassativi e verificabili sul "
            "documento: una contestazione che non li indica non consente il riscontro."),
        fonti=[Fonte("art. 474 c.p.c.", ruolo="principale")],
        quota=("Nel corpus questa famiglia ha 12 casi decisi, il 25% accolti: troppo "
               "pochi perche' la percentuale voglia dire qualcosa."),
        checklist=(
            "(a) il titolo e' prodotto in originale; (b) la censura riguarda un "
            "requisito formale o il rapporto sottostante, che sono piani diversi; (c) "
            "l'eccezione e' proposta come opposizione all'esecuzione o all'atto "
            "esecutivo, con termini diversi."),
    ),
    Famiglia.DECADENZA_BENEFICIO_TERMINE: dict(
        cosa_indicare="quale presupposto della decadenza sarebbe mancato",
        contro=(
            "L'eccezione non individua quale presupposto della decadenza sarebbe "
            "mancato. L'art. 1186 c.c. consente al creditore di esigere immediatamente "
            "la prestazione quando il debitore e' divenuto insolvente o ha diminuito "
            "per fatto proprio le garanzie date: sono presupposti determinati, e chi ne "
            "contesta la ricorrenza deve dire quale non si sia verificato."),
        fonti=[Fonte("art. 1186 c.c.", ruolo="principale")],
        quota=("Nel corpus questa famiglia ha 12 casi decisi, il 42% accolti: troppo "
               "pochi perche' la percentuale voglia dire qualcosa."),
        checklist=(
            "(a) la comunicazione di decadenza e' agli atti, con data; (b) il "
            "presupposto invocato dalla banca e' quello contrattuale o quello legale; "
            "(c) le rate impagate al momento della decadenza, con l'evidenza."),
    ),
}


def _crea_regola(famiglia: Famiglia, voce: dict) -> TipoRegola:
    def regola(p: Precondizioni) -> RisultatoRegola:
        return _regola_per_allegazione(famiglia, p, **voce)
    regola.__name__ = "_regola_%s" % famiglia.value
    return regola


for _famiglia, _voce in _PER_ALLEGAZIONE.items():
    registra(_famiglia)(_crea_regola(_famiglia, _voce))


# ------------------------------------------------------------------
# Le due che restano fuori: il corpus non le contiene abbastanza da
# permettere nemmeno una quota. `saldaconto_art_50_tub` ha TRE coppie e
# `leasing` DUE, sui 666 provvedimenti. Riconoscere e fermarsi e' l'unica
# cosa onesta - ed e' comunque meglio del silenzio, perche' nel dossier
# l'esito diventa un motivo scritto invece di "famiglia senza regola".
# ------------------------------------------------------------------


@registra(Famiglia.SALDACONTO_ART_50_TUB)
def _regola_saldaconto(p: Precondizioni) -> RisultatoRegola:
    return RisultatoRegola(
        famiglia=Famiglia.SALDACONTO_ART_50_TUB, fondata=False,
        contro_argomento=None, fonti=[], consolidamento=None,
        nota=(
            "Famiglia riconosciuta e deliberatamente non decisa: il corpus contiene "
            "TRE coppie su questa materia, e tre casi non fondano niente. La "
            "precondizione che conta la indica SUPERFICIE_ATTACCO.md §2 ed e' la FASE "
            "del giudizio - in sede monitoria il decreto puo' essere chiesto anche "
            "sulla base del saldaconto, in sede di opposizione la regola si inverte - "
            "quindi l'eccezione va prima collocata e poi valutata. Fase letta "
            "dall'estrazione: '%s'. Va trattata a mano." % p.fase_processuale),
    )


@registra(Famiglia.LEASING)
def _regola_leasing(p: Precondizioni) -> RisultatoRegola:
    return RisultatoRegola(
        famiglia=Famiglia.LEASING, fondata=False,
        contro_argomento=None, fonti=[], consolidamento=None,
        nota=(
            "Famiglia riconosciuta e deliberatamente non decisa: il corpus contiene DUE "
            "coppie su questa materia. Non c'e' nessuna base per una regola, e nessuna "
            "delle precondizioni delle altre famiglie si trasferisce qui: il leasing ha "
            "una disciplina propria, e la natura del rapporto letta dall'estrazione "
            "('%s') non la coglie. Va trattata a mano." % p.natura_rapporto),
    )

# ------------------------------------------------------------------
# Famiglie 2-8 (delle 8 originarie di SUPERFICIE_ATTACCO.md) - scaffolding
# dichiarato, NON popolato. Ogni voce qui solleva esplicitamente
# NotImplementedError tramite applica_regola() se invocata - non c'e' un
# fallback silenzioso. (La 9a famiglia, RECESSO_APERTURA_CREDITO_SENZA_
# PREAVVISO, aggiunta dopo e fuori da SUPERFICIE_ATTACCO.md, e' invece
# popolata per intero - vedi sopra.)
# ------------------------------------------------------------------
# Famiglia.SALDACONTO_ART_50_TUB - precondizione: fase_processuale
# Famiglia.LEGITTIMAZIONE_CESSIONARIO - precondizione: documenti_prodotti_cessionario
#   (attenzione: giurisprudenza in gran parte sfavorevole al creditore su
#   cessioni plurime, vedi SUPERFICIE_ATTACCO.md punto 3 - il grafo ha gia'
#   un'autorita' avversa reale su questo, Trib. Bologna 29/05/2025)
# (Famiglia.ANOMALIE_CONTABILI e' stata popolata il 2026-09-02 - vedi sopra.)
# Famiglia.VIZI_FIDEIUSSIONE - precondizione: qualita_fideiussore
# Famiglia.QUALIFICAZIONE_CONSUMATORE - precondizione: qualita_fideiussore (scopo estraneo attivita' professionale)
# Famiglia.PRESCRIZIONE - precondizione: natura della rimessa (ripristinatoria/solutoria, SS.UU. 24418/2010)
# Famiglia.DOCUMENTAZIONE_ART_119_TUB - precondizione: decennio + oggetto (operazioni vs contratto quadro)


if __name__ == "__main__":
    # Test della famiglia 1 sui tre casi che la regola stessa distingue -
    # verificabile riga per riga, nessuna chiamata di rete.
    casi_prova = [
        (Precondizioni(natura_rapporto="conto_corrente"), True, "conto corrente -> fondata"),
        (Precondizioni(natura_rapporto="mutuo"), False, "mutuo -> infondata, contro-argomento presente"),
        (Precondizioni(natura_rapporto="finanziamento_rateale"), False, "finanziamento -> infondata, contro-argomento presente"),
        (Precondizioni(natura_rapporto="non_desumibile"), False, "non desumibile -> infondata MA senza contro-argomento (buco dichiarato)"),
    ]
    print("=== Famiglia 1 (incompletezza estratti conto) - verifica ===")
    for precondizioni, fondata_attesa, descrizione in casi_prova:
        esito = applica_regola(Famiglia.INCOMPLETEZZA_ESTRATTI_CONTO, precondizioni)
        assert esito.fondata == fondata_attesa, f"FALLITO: {descrizione}"
        ha_fonti = len(esito.fonti) > 0
        print(f"[OK] {descrizione}: fondata={esito.fondata}, fonti={[f.citazione_breve for f in esito.fonti]}")

    print("\n=== Famiglia 9 (recesso apertura di credito senza preavviso) - verifica ===")
    casi_prova_9 = [
        (Precondizioni(natura_rapporto="conto_corrente", durata_rapporto="tempo_indeterminato"), False,
         "natura sbagliata (conto_corrente, non apertura_credito_cc) -> non si applica"),
        (Precondizioni(natura_rapporto="apertura_credito_cc", durata_rapporto="tempo_indeterminato"), False,
         "apertura credito, tempo indeterminato -> infondata, contro-argomento su art. 1845 c.c."),
        (Precondizioni(natura_rapporto="apertura_credito_cc", durata_rapporto="tempo_determinato"), True,
         "apertura credito, tempo determinato, senza giusta causa -> fondata"),
        (Precondizioni(natura_rapporto="apertura_credito_cc", durata_rapporto="non_desumibile"), False,
         "durata non desumibile -> infondata MA senza contro-argomento (buco dichiarato)"),
    ]
    for precondizioni, fondata_attesa, descrizione in casi_prova_9:
        esito = applica_regola(Famiglia.RECESSO_APERTURA_CREDITO_SENZA_PREAVVISO, precondizioni)
        assert esito.fondata == fondata_attesa, f"FALLITO: {descrizione}"
        print(f"[OK] {descrizione}: fondata={esito.fondata}, fonti={[f.citazione_breve for f in esito.fonti]}")

    print("\n=== Famiglie non popolate - deve fallire esplicitamente, non in silenzio ===")
    for famiglia in Famiglia:
        if famiglia in (Famiglia.INCOMPLETEZZA_ESTRATTI_CONTO, Famiglia.RECESSO_APERTURA_CREDITO_SENZA_PREAVVISO):
            continue
        try:
            applica_regola(famiglia, Precondizioni(natura_rapporto="non_desumibile"))
            print(f"[ERRORE] {famiglia.value} avrebbe dovuto sollevare NotImplementedError!")
        except NotImplementedError as e:
            print(f"[OK] {famiglia.value}: fallisce esplicitamente ({str(e)[:60]}...)")

    print("\nTutti i controlli passati.")
