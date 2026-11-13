# Contratti dati tra le fasi della pipeline di confutazione

## CHANGELOG

**Nota (verifica su batch di produzione, 2026-08-25) - 15 atti a
`temperature=0.0`/`budget=2200` (configurazione 1.23): 14/15 riusciti,
un fallimento nuovo sul tetto aggregato, e saturazione del tetto
per-blocco diffusa su quasi tutto il lotto, non isolata a un atto.**

Batch completo su tutti gli atti presenti in `atti_input/` al momento
del lancio (15; il PDF scannerizzato segnalato in precedenza,
`atto_di_citazione_esempio_01.pdf`, non c'e' piu' - rimosso
o rinominato dall'utente, non indagato). Tempo totale 95m7s. Output in
`out_golden_finale/`.

**Il fallimento**: `atto_di_opposizione_d_i.pdf` (18920 token in
ingresso, 11 blocchi - il piu' grande del lotto) ha prodotto 77
eccezioni, sopra `MAX_ECCEZIONI=60` in `fase1_assembla.py`. Questo e'
un tetto AGGREGATO su tutto l'atto assemblato, distinto dal `maxItems`
per-blocco alzato a 30 in 1.21 - alzare il tetto per-blocco ha reso
raggiungibile un tetto aggregato tarato su un massimo per-blocco piu'
basso. Assemblaggio abortito con `ValueError`, nessun file scritto per
questo atto. **Non alzato in silenzio**: e' una decisione di contratto,
la lascio all'utente (vedi sotto).

**Il fallimento non e' isolato**: 12 dei 14 atti riusciti hanno almeno
un avviso sul tetto (22 avvisi totali). Quasi sempre `eccezioni_sollevate`
satura 30/30, e quando satura il tasso di quasi-duplicati e' quasi
sempre 25-30/30 (83-100%) - lo stesso pattern di "riempimento con
quasi-duplicati vicino al limite" gia' osservato in 1.23 sui 5 atti
originali, ora confermato su un campione piu' ampio (14 atti). I
tetti su `elementi_non_estraibili` (citazioni) saturano piu' raramente
e con quasi-duplicati piu' bassi (0 o 13/20).

Lettura: il fallimento su `atto_di_opposizione_d_i.pdf` non e'
un'anomalia isolata di quell'atto, e' il caso in cui la saturazione
diffusa (che altrove resta sotto il tetto aggregato) lo supera - l'atto
piu' grande del lotto (11 blocchi) ha semplicemente piu' occasioni di
saturare. **Aperto, nessuna decisione presa qui**: alzare
`MAX_ECCEZIONI` risolverebbe il sintomo su questo atto ma non il
pattern di fondo (quasi-duplicati vicino al tetto per-blocco); indagare
la deduplicazione (intra-blocco o fra blocchi) affronterebbe la causa
ma e' lavoro non fatto. Il golden set (annotazione manuale, in corso)
e' la sola via per distinguere "il modello estrae davvero cosi' tante
eccezioni distinte" da "sta riempiendo l'array con varianti dello
stesso testo" - non decido a priori quale sia.

Nota separata, non parte di questo batch: `atti_input/` contiene ora
33 file (18 aggiunti dopo l'avvio di questo batch) - non coperti da
questa verifica.

Le 14 estrazioni riuscite in `out_golden_finale/` sono il set su cui
annotare il golden set (`prepara_annotazione.py`).

**v1.36 (2026-09-03)** - `specificita` impara a dire "non si sa".

L'enum passa da `specifica|generica` a **`specifica|generica|non_desumibile`**.

**Il difetto che l'ha resa necessaria.** `unisci_estrazioni.come_eccezioni_di_fase1`
scriveva `specificita: "specifica"` su ogni voce che scendeva a Fase 2 -
comprese quelle su cui il modello aveva gia' risposto. Misurato sull'atto
ALFA: le 21 eccezioni arrivate al dossier portavano `specifica` **21 volte
su 21**, mentre l'estrazione di Fase 1 dello stesso atto ne aveva **12 su
17 `generica`**.

Non era un travaso sciatto. `specificita` e' la precondizione su cui
girano **quattordici regole su venti**, e `specifica` e' esattamente il
valore che le fa rispondere "l'eccezione regge". Il motore restava acceso
e non attaccava mai: il dossier usciva con **zero confutazioni e l'aria di
averle valutate**.

**Perche' serviva un valore nuovo e non bastava correggere il travaso.**
Corretto il travaso (le voci di Fase 1 rileggono i loro campi da
`id_di_origine`), resta il caso di chi viene dalla **sola spazzata**: li'
la domanda a nessuno e' stata posta. Sull'atto ALFA sono **17 eccezioni su
21**. Con due soli valori bisognava sceglierne uno, e qualunque scelta
decideva l'esito di quelle diciassette: e' la regola che il progetto
applica ovunque - `None` vuol dire "non si sa", mai "non ce n'e'" - e qui
lo schema non la sapeva esprimere.

**La grammatica della chiamata resta binaria, apposta.** `non_desumibile`
non e' un terzo giudizio che il modello puo' dare: e' l'assenza della
domanda. Se entrasse nell'enum della chiamata, "il modello non sa" e
"nessuno ha chiesto" diventerebbero lo stesso valore, e le quattordici
regole non potrebbero piu' distinguerli. Lo scrive Python, e lo scrive
solo dove nessuno ha chiesto. Difeso da
`test_la_grammatica_della_chiamata_resta_binaria`.

**Cosa cambia a valle.** `motore_regole` gia' tratta `non_desumibile`: e'
il ramo che NON decide, con la nota che dice cosa guardare e l'avviso di
non leggerlo come "eccezione infondata di default". Le diciassette
eccezioni della spazzata passano quindi da un giudizio mai misurato a
un'astensione esplicita - **meno risposte, nessuna inventata**.

**Effetto misurato sull'atto ALFA**, a parita' di estrazione, grafo e seed:

    contratto 1.35, prima della correzione   0 confutabili   0 astensioni per specificita
    solo travaso corretto (ancora 1.35)      1 confutabile
    contratto 1.36                           vedi il collaudo di fine giornata

**Nota su `fase1_eccezioni.gbnf`**: l'enum delle famiglie era fermo alle
**nove della 1.6** mentre lo schema ne dichiara venti. Il file dichiara di
essere l'equivalente di `SCHEMA_ECCEZIONI`, quindi la divergenza si
leggeva come una regola. Allineato.

**v1.35 (2026-09-02)** - da nove famiglie a venti. Le undici nuove non
vengono da un elenco a priori: vengono dalle **3502 eccezioni del corpus
che le nove precedenti non riconoscevano**, cercate con schemi che nominano
questioni riconoscibili e contate una per una. Ognuna porta il numero con
cui e' stata trovata e quanto spesso regge (STATO_PROGETTO 7.45-7.46):
`competenza_e_rito` 231 al 38%, `taeg_isc_indeterminatezza` 155 al 18%,
`contestazione_ctu` 74 al 40%, `mediazione_procedibilita` 62 al 54%,
`forma_scritta_art_117_tub` 50 al 6%, `ammortamento_alla_francese` 53 al
20%, `garanzia_ipotecaria`, `cambiale_titolo_esecutivo`,
`segnalazione_centrale_rischi`, `decadenza_beneficio_termine`, `leasing`.
Copertura del classificatore sul corpus: **dal 27% al 36%**.

Non e' entrata "nullita' delle clausole di interessi moratori": e' gia'
dentro `anomalie_contabili`, che fra le sue chiavi ha "tasso di mora" e
"interessi moratori". Sarebbe stata una famiglia che ruba casi a una
esistente, non una famiglia nuova.

**Nessuna delle undici ha una regola in `motore_regole._REGISTRO`**, e
`applica_regola` continua a sollevare `NotImplementedError` come gia' fa
per sette delle nove precedenti. Una famiglia riconosciuta e senza regola
serve comunque - e' quella che rende leggibile un profilo di magistrato - e
non finge di essere altro.

**Un difetto che l'aggiunta ha reso visibile.** `classifica_famiglia`
risolve i pareggi prendendo la prima del dizionario. A nove famiglie
capitava di rado; a venti sono **247 su 2000, il 12%**. Per la Fase 1 va
bene com'e' - li' una famiglia serve a riformulare una query e sbagliarla
costa poco - ma per CONTARE no: una coppia in pareggio messa in una delle
due gonfia quella e sgonfia l'altra, e la percentuale che ne esce sembra
una misura mentre e' l'ordine di dichiarazione. Il nuovo
`punteggi_famiglia` restituisce tutte le famiglie a pari merito, e
`famiglia_delle_coppie` le dichiara **ambigue** invece di sceglierne una,
elencando quali confini si toccano (`competenza_e_rito` /
`mediazione_procedibilita` 26 volte, in testa).

**v1.34 (2026-09-01)** - una risposta troncata non vale piu' zero.
`passaggio_recuperato` entra nel vocabolario chiuso di `buchi`: e' il terzo
esito di un passaggio di estrazione, accanto a riuscito e fallito.

**La diagnosi, misurata e non stimata.** Riprodotto l'atto ROSSI MARIO,
3 blocchi su 4 troncati e l'atto intero fermo a **0 eccezioni**. Il motivo
e' sempre `limit` - n_predict esaurito - **mai** il contesto. E non e'
scarsa capienza: il modello **si ripete**. Blocco 1: 26 oggetti per **2**
testi distinti. Blocco 2: 13 per 3. Blocco 3: 29 per 9. Alzare n_predict lo
farebbe ripetere piu' a lungo, non finire. E' esattamente la distinzione
che la 1.20 aveva costruito `_quasi_duplicati` per fare - saturazione vera
contro degenerazione di campionamento - applicata qui per la prima volta a
un troncamento invece che a un tetto. La leva del campionamento e' gia'
stata provata e scartata: `repeat_penalty` 1.3 e' attivo dalla 1.9, e DRY
e' stato misurato inefficace (`lavoro/_dry_sampling_risultati.json`: 30
elementi e 30 quasi-duplicati con e senza, e in un caso peggiora).

**Quindi non si tocca la generazione.** Si smette di buttare cio' che ha
gia' prodotto. `RispostaTroncata` dichiarava dalla sua prima riga che
`contenuto_parziale` *"resta accessibile per chi vuole loggarlo o tentare un
retry con budget maggiore"*: nessuno dei due e' mai stato fatto, e i soli
tre parziali di quell'atto contenevano 38 KB di JSON con **68 oggetti gia'
chiusi** dentro.

**Il confine, ed e' il punto.** `recupera_da_troncata` prende solo cio' che
il modello aveva **finito** di scrivere e si ferma al primo pezzo
incompleto. Non chiude parentesi, non indovina campi, non completa
l'oggetto tagliato a meta'. Un oggetto ricucito da Python sarebbe un
oggetto che il modello non ha emesso, e finirebbe in un atto difensivo come
se l'avesse emesso. E' schema-agnostica di proposito - legge le chiavi che
trova, non quelle che si aspetta - cosi' non va aggiornata quando uno
schema cambia, che e' il modo tipico in cui un recupero diventa muto senza
che nessun test se ne accorga.

**Perche' una casella nuova e non una delle due esistenti.** Fra i riusciti
nasconderebbe che l'elenco e' **tagliato**; fra i falliti direbbe che non ha
prodotto nulla mentre ha prodotto. E' la lezione gia' vista cinque volte in
questo progetto: *una classificazione senza una casella per qualcosa che
esiste mette quella cosa nella casella sbagliata*. Il riepilogo di batch li
tiene distinti e dichiara che il numero di eccezioni di un atto tagliato e'
**un minimo, non un totale**.

**Verificato dal vivo**, stesso atto: **0 -> 10 eccezioni**, tutte ancorate,
zero passaggi rimasti a vuoto, e i 4 troncamenti tutti dichiarati nei
buchi - uno dei quali nell'autoverifica, che non si sapeva si troncasse.

**v1.33 (2026-09-01)** - l'unione entra nella catena. La 1.32 aveva
scritto il contratto dell'unione; qui l'unione smette di essere uno
strumento da riga di comando e diventa un passo della corsa
(`fase1b_spazzata`, `fase1b_unione`), attivo di default e disattivabile con
`--senza-unione`.

**Dove sta agganciata, e perche' li'.** DOPO la scrittura di
`01_estrazione.json`, non prima. Quel file resta cosi' il verbale di cio'
che ha trovato Fase 1 e nient'altro: se l'unione lo sovrascrivesse, i due
metodi non sarebbero piu' misurabili separatamente, che e' l'unico modo per
accorgersi se uno dei due peggiora. L'unione scrive due file propri
(`01a_spazzata.json`, `01b_unione.json`) e **sostituisce** - mai concatena -
`estrazione["eccezioni"]` in memoria per il seguito della catena.

**Non passa tutto a valle, e non e' un'ottimizzazione.** L'unione tiene
apposta sia il blocco da 2103 caratteri sia le tre fette che stanno dentro
di esso (v1.32, «una zona non e' un'eccezione con varianti»). Mandarle tutte
a Fase 2 farebbe **confutare quattro volte lo stesso punto**. Quindi si
sceglie una volta per zona, in un ordine che e' tutto misurato e tutto
dichiarato nel campo `motivo_della_scelta`:

| motivo | quando | perche' quell'ordine |
|---|---|---|
| `unica_nella_zona` | la zona ha una voce sola | non c'e' scelta da fare |
| `concordi` | i due metodi hanno prodotto la **stessa fetta carattere per carattere** | 10 su 12 di queste stanno in piedi da sole (83%): il segnale di qualita' piu' forte disponibile, e viene gratis dall'unione |
| `citabile` | il controllo dice `sta_in_piedi_da_sola` | e' il giudizio gia' validato su dati nuovi (§7.38) |
| `ripiego_la_piu_lunga` | nessuna fetta della zona e' citabile | e' l'euristica gia' **bocciata** in §7.36 (la spazzata vinse 16-0 sulle coppie di frasi): resta come ripiego perche' una zona non puo' sparire, e resta **etichettata** perche' senza etichetta sarebbe indistinguibile da una scelta motivata |

Fra piu' fette citabili che si sovrappongono non c'e' nessuna soglia: si
**calcola** il sottoinsieme piu' numeroso senza sovrapposizioni
(programmazione per intervalli, soluzione esatta). Massimizzare il *numero*
e non la lunghezza va nel verso della granularita' fine - tre argomenti
confutati uno per uno valgono piu' di un blocco confutato in massa - ed e'
coerente con la diagnosi di §7.38 (Fase 1 taglia male, non trova male).

**`maxItems` 60 -> 90 su `fase1_estrazione.schema.json`.** Il 60 era tarato
su un metodo solo; con due il tetto veniva sfiorato, e l'assemblaggio
**aborta la corsa intera** quando lo supera. Il cambio segue il metodo, non
il caso: e' scritto nella `description` del campo.

**Due campi nuovi su ogni eccezione**, `trovata_da` e `motivo_della_scelta`.
Il primo e' l'unica cosa che questo aggancio poteva rompere in silenzio:
senza, una voce della spazzata sarebbe indistinguibile da una di Fase 1 e la
misura di §7.38 non sarebbe piu' rifacibile su nessuna corsa futura.

**Verificato dal vivo** (corsa `20260901T181706Z-cd568247`, atto reale, fino
a `03_atto.json`): Fase 1 49 eccezioni, spazzata 54, unione **79 voci in 58
zone**, 46 zone viste da un metodo solo, **21 fette identiche fra i due**,
**60 passate a Fase 2**, 3 zone finite sul ripiego e 3 eccezioni di Fase 1
senza ancora - tenute in `01b_unione.json` ma non mandate a valle, perche'
senza offset non sono citabili (regola 4). Costo: 452s la spazzata, 124s
l'unione, sopra i 460s di Fase 1.

**v1.32 (2026-09-01)** - `unione_estrazioni.schema.json`, contratto nuovo.
Fase 1 e la spazzata smettono di essere alternative e diventano due voci
sullo stesso atto.

**Il fatto che l'ha imposto.** Misurato su cinque atti mai visti da nessuno
dei due metodi (STATO_PROGETTO §7.38): trovano **cose diverse**. Su ~210
frasi distinte, 185 le trova uno solo dei due, e ciò che ciascuno trova da
solo è materiale vero in tre casi su quattro. Due misure indipendenti:
un avvocato alla cieca dice che sono eccezioni vere **altrettanto spesso**
(73,3% contro 71,4%, ±11,8 — pari), la macchina dice che Fase 1 le
**delimita peggio** (74,3% contro 57,5%, ±7,0 — distinguibile). Trova le
cose giuste e le taglia male. Nessuna delle due misure dice di scegliere:
scegliere farebbe perdere ~75 eccezioni vere in un verso o nell'altro, e a
Fase 1 non serve un filtro migliore ma un taglio migliore. Quindi il
contratto smette di chiedere quale.

**Le due domande che il contratto tiene separate.** «È la stessa zona del
testo?» si risponde col contenimento (`intersezione / min(lunghezze)`), e
la risposta **non dipende dalla soglia**: la distribuzione misurata è
bimodale — 45 coppie su 54 a contenimento pieno, 5 sopra 0,9, 4 in tutto il
resto — quindi ogni valore fra 0,50 e 0,90 seleziona 52 o 50 delle stesse
54. «È la stessa delimitazione?» si risponderebbe con Jaccard, e lì il
continuo c'è davvero (6 coppie sotto 0,1, poi 5, 8, 9, fino alle 12
identiche): ogni soglia sarebbe un numero inventato, quindi **non se ne usa
nessuna** e si fondono solo le fette identiche carattere per carattere.

**Quello che il contratto vieta di fare, ed è il punto.** Una `zona` con più
voci **non è un'eccezione con varianti**. Dal vivo: Fase 1 con un blocco da
2103 caratteri, la spazzata con tre fette distinte dentro di esso. Fonderle
in una voce sceglierebbe una delimitazione che nessuno dei due ha proposto e
distruggerebbe la granularità fine, cioè esattamente il materiale che si è
deciso di non buttare. La zona è un'informazione per chi rivede — «guarda
queste insieme» — non un'unità di contenuto, e `cosa_non_dice` lo scrive
nell'uscita per chi legge il JSON senza aver letto il modulo.

**Niente viene tolto.** `citabilita.py` gira su ogni voce e nessuna sparisce.
`azione_del_controllo` conserva ciò che il controllo *direbbe* di fare,
`blocca` compreso, ma `blocca` viene declassato a segnalazione: su 58 fette
giudicate a mano avrebbe salvato 4 scarti al prezzo di 3 frasi vere, e in un
atto difensivo un'eccezione persa costa più di una da scartare a mano. **Si
toglie l'azione, non la misura.** Stessa politica per le eccezioni che Fase 1
trova ma non sa collocare: niente offset, quindi niente zona, ma escono in
`non_ancorate` invece di sparire.

**Regola 4.** Gli offset li calcola Python a monte (`localizza.localizza`,
la stessa procedura per entrambi i metodi) e qui non vengono né ricalcolati
né spostati. Che i due lavorino nello stesso sistema di coordinate — entrambi
ancorano su `segmenta_atto.pulisci_numeri_pagina(grezzo)` — è vero per
costruzione, ma è una proprietà di due moduli scritti in momenti diversi:
`verifica_coordinate` la ricontrolla a ogni unione e solleva
`CoordinateIncoerenti` invece di dichiarare, perché due sistemi di
coordinate uniti in silenzio produrrebbero offset sbagliati che sembrano
giusti. Verificato sui sei atti reali: passa su tutti.

**v1.31 (2026-09-01)** - il filtro di Fase 1 impara a riconoscere una
norma citata. Prima verifica UMANA del progetto, e primo difetto della
pipeline che non venga da una macchina che giudica se' stessa.

Delle voci che SOLO Fase 1 trovava, l'avvocato ne ha bocciate **5 su 8**
(§7.32), di due specie:

    "B) Recita l'art. 125 - bis del Dlgs n. 385/1993 ..."
    "previa fissazione, ai sensi dell'art. 281 undecies comma 2 c.p.c.,
     dell'udienza di comparizione delle parti"

`_filtra_unita_argomentative` esiste dal contratto 1.14 ed e' costruito
bene - una chiamata per unita', quattro categorie, scarti mai perduti. Il
difetto non e' nel filtro: e' che **nessuna delle quattro categorie ospita
una norma citata**. Non e' la tesi dell'altra parte, non e' un rinvio, non
e' una formula di stile. Il modello non ha dove metterla e la lascia fra le
eccezioni.

E' la terza volta che questo progetto misura lo stesso difetto: quando la
classificazione non ha una casella per una cosa che esiste, quella cosa
finisce nella casella sbagliata. Le altre due sono in
`golden_esaustivo.NATURE` (la spinta a trovare un'eccezione quando "niente"
non e' una risposta offerta) e in `golden_esaustivo.VOCI_CHE_SOSTENGONO`
(l'attribuzione a tre invece del si'/no che rispondeva sempre no). La
correzione e' sempre la stessa: **aggiungere la casella**, non ritoccare il
prompt intorno a quella che manca.

Due modifiche:

- `norma_o_giurisprudenza_citata` entra in `_TIPI_UNITA` e nell'enum di
  `unita_scartate[].motivo`;
- `formula_di_rito` diceva "epigrafi, conclusioni, formule di stile" e non
  bastava: una richiesta MOTIVATA al giudice non somiglia a una formula di
  stile. Ora nomina le richieste, le richieste istruttorie e le riserve, con
  le stesse parole della regola di annotazione estesa dopo la stessa
  verifica ("si insiste per la nullita' della fideiussione" non e'
  l'eccezione di nullita', e' la domanda che ne discende).

Aggiunta la guardia che mancava:
`test_le_categorie_del_filtro_e_i_motivi_di_scarto_non_divergono` confronta
`_TIPI_UNITA` con l'enum del contratto. Ogni categoria diversa da
`eccezione_o_difesa_autonoma` viene scritta come motivo di scarto, quindi
una categoria nuova senza la voce corrispondente farebbe fallire Fase 1 in
validazione a fine corsa - lo stesso incidente della 1.30, che poteva
ripetersi solo perche' questa guardia non c'era.

**v1.30 (2026-09-01)** - `verbatim_anomalo` entra nel vocabolario chiuso
di `buchi`. Il codice lo emetteva gia'; il contratto non lo conosceva.

Trovato rifacendo Fase 1 sui cinque atti del golden set, con la pipeline di
oggi invece che con l'artefatto del 25 agosto: **uno dei cinque fallisce la
validazione a fine corsa**, dopo tutte le chiamate al modello.

    ['buchi', 40]: Additional properties are not allowed
                   ('eccezione_id' was unexpected)
    ['buchi', 40, 'tipo']: 'verbatim_anomalo' is not one of [...]

`fase1_assembla` dichiara un buco quando la fetta citabile supera
`LUNGHEZZA_VERBATIM_ANOMALA`. Il comportamento e' **giusto e voluto**:
dichiarare invece di troncare, perche' troncare il verbatim produrrebbe una
citazione falsa che continua a sembrare vera (regola 4). Il difetto non e'
la diagnosi, e' che la diagnosi parlava una lingua che il contratto non
conosce - mentre lo schema dice di se' stesso "un tipo fuori vocabolario e'
un errore di programmazione, non un dato".

Tre correzioni, in tre direzioni diverse:

- il **tipo** entra nell'enum e in `estrazione_atto.TIPI_BUCO`. La regola 1
  ("se il codice diverge dai contratti, sbaglia il codice") non impone di
  cancellare una diagnosi vera: impone di dichiararla dove il contratto la
  possa vedere;
- il campo **`eccezione_id` esce**. La voce dei buchi e' `{tipo, testo}`
  per tutte le altre nove specie e il contratto la chiude con
  `additionalProperties: false`; l'id era gia' dentro il testo leggibile
  (`"[verbatim anomalo] X07: ..."`), quindi il campo in piu' non portava
  nulla che non ci fosse;
- la voce passa dal **costruttore** `estrazione_atto.buco()`, che verifica
  il tipo dove nasce. La guardia esisteva gia' - `test_versioni_contratti`
  confronta `TIPI_BUCO` con l'enum dello schema fin dalla 1.24 - ed e'
  stata aggirata scrivendo il dizionario a mano. Un costruttore che si puo'
  aggirare non e' un vincolo, e' un suggerimento.

Perche' nessun test lo prendeva: `test_un_verbatim_anomalo_viene_dichiarato
_non_tagliato` cercava la stringa nel SORGENTE, quindi verificava che il
codice dichiarasse l'anomalia, non che il contratto sapesse leggerla. Un
test che guarda il codice invece del contratto non puo' accorgersi che i
due dicono cose diverse, ed e' il solo errore che quel test doveva
escludere. Aggiunto
`test_ogni_tipo_di_buco_emesso_dal_codice_esiste_nel_contratto`, che legge
i tipi dall'AST e li confronta con l'enum: copre anche chi in futuro
riscrivesse il dizionario a mano invece di passare dal costruttore.

Nessuna modifica di comportamento: la stessa anomalia veniva gia'
dichiarata, e ora arriva a valle invece di far fallire la corsa.

**v1.29 (2026-09-01)** - `dal_grafo.fiducia` nel dossier: la regola di
concordanza fra i due strati deboli entra nella catena, invece di restare
una funzione testata e mai chiamata.

`famiglie_grafo.concorda()` esisteva dalla 1.28 con la sua misura sul
golden set (965 eccezioni): lessico da solo precisione 0,523, vettori con
quorum 0,646, **dove concordano 0,804**, dove discordano 0,224 e 0,418. Era
agganciata a niente. Da questa versione:

- `IndiceSegmenti.similarita()` (nuovo) espone il vettore intero delle
  somiglianze, non i primi k: il voto dei 5 vicini con quorum 4 ha bisogno
  di sapere quali siano i 5, e `top_k` ora ci passa sopra;
- `classifica()` accetta `famiglia_dai_vettori` allo stesso modo in cui gia'
  accettava `articoli_dal_vicinato` - come NUMERO calcolato da chi ha
  l'indice aperto. `famiglie_grafo` continua a non conoscere ne' lo store
  ne' i modelli di embedding, ed e' il motivo per cui la firma e' questa e
  non un oggetto indice;
- lo strato vettoriale entra in coda alla precedenza (norme citate,
  vicinato, lessico, vettori). In coda, quindi non cambia nessun caso gia'
  deciso: copre solo le eccezioni che uscivano senza comunita';
- ogni esito porta `fiducia` in `concordi | uno_solo | discordi | nessuno`.

**Il punto delicato, e la scelta fatta.** Su `discordi` la comunita' viene
revocata SOLO se poggiava sul voto. Una norma che l'eccezione cita davvero,
o gli articoli del vicinato, non erano fra i votanti e non si annullano per
un voto a cui non hanno partecipato. Il disaccordo invece finisce SEMPRE in
`disaccordi`, anche quando non revoca niente: dichiarato, mai silenzioso.

**Il costo atteso era copertura, e la misura dice di no.** Su 600
eccezioni del corpus, con profili e indice segmenti veri: classificate 359
prima, 373 dopo. Si perdono 34 comunita' per disaccordo e se ne guadagnano
48 dove nessun altro strato parlava. Il guadagno che conta pero' non e'
quel +14: sono le **80 eccezioni (13,3%) in fascia 'concordi'**, cioe' a
precisione 0,804, che prima erano indistinguibili dal resto a 0,523. E i
**39 'discordi' (6,5%)** che ora si sanno da leggere a mano invece di
sembrare classificati.

In Fase 1 l'indice dei segmenti non c'e', quindi `famiglia_dai_vettori` e'
None, `fiducia` vale `uno_solo` o `nessuno` e niente viene revocato: e' il
comportamento giusto quando un votante non si e' presentato, non un caso
degradato.

*(Le tre voci sotto - 1.26, 1.27, 1.28 - sono state scritte il 2026-09-01,
a posteriori, ricostruite dai commit `b54ae08`, `04be044`, `ef8c737` e
`14b90b6` e da STATO_PROGETTO.md. Le versioni erano reali e in uso da
giorni; mancavano solo qui. Sono marcate come ricostruite perche' chi legge
un changelog deve sapere quali voci sono nate insieme alla modifica e quali
dopo: le prime raccontano anche cosa si era deciso di NON fare, le seconde
solo cio' che si vede nel diff.)*

**Patch a 1.28 (2026-08-31, commit `14b90b6`), nessun bump.** Tre difetti
dei tetti, tutti dello stesso genere: un `maxLength` scritto per il MODELLO
applicato a cio' che calcola PYTHON.

- `unita_scartate[].testo` veniva scritto intero contro un tetto di 4000, e
  due corse del batch morivano in validazione a Fase 1 gia' spesa. Ora e'
  troncato in Python allo stesso numero del contratto: e' una copia
  diagnostica dell'output del modello, non finisce in nessun atto;
- `testo_verbatim` aveva lo stesso tetto, e li' troncare e' **vietato**. E'
  la fetta agli offset dichiarati; una fetta tagliata non e' piu' quella
  fetta, e resterebbe citabile all'apparenza e falsa nei fatti (regola 4).
  Il tetto e' stato **tolto**, non alzato: non esiste un numero giusto per
  limitare cio' che Python calcola. Una lunghezza anomala si dichiara fra i
  buchi. Misurato sul batch: mediana 230, p99 929, massimo 3755 fra le
  corse riuscite - le altre morivano prima;
- `citazioni_controparte.norme` e `.precedenti` non passavano da
  `_non_degenere`. Sul batch: 6 precedenti degeneri su 317, stringhe di uno
  o due caratteri che sarebbero arrivate in Fase 2 come se fossero
  sentenze.

361 verdi. **Nessun bump benche' lo schema cambi**, contrariamente alla
regola enunciata alla 1.25: qui la modifica RILASSA un vincolo (toglie un
`maxLength`), quindi ogni file gia' prodotto a 1.28 resta valido e non c'e'
niente da rileggere. Un bump avrebbe invalidato file corretti.

**v1.28 (2026-08-31, commit `ef8c737`)** - famiglia, rango e natura del
rapporto vengono dal grafo. *(voce ricostruita)*

Tre decisioni giuridiche vivevano fuori dal grafo, e il grafo le aveva gia'
tutte e tre.

1. La **famiglia** era `_KEYWORD_PER_FAMIGLIA`: nove famiglie decise a
   priori e riconosciute per sottostringa. Ora e' la comunita' di
   co-citazione fra articoli, misurata su 775 provvedimenti - due articoli
   che i giudici citano nella stessa motivazione stanno nello stesso
   discorso giuridico. Sul batch reale 665 eccezioni su 983 (67,7%), di cui
   147 che le parole chiave non prendevano;
2. il **rango** era `RANGO_PER_FAMIGLIA`, tabella scritta a mano. Ora e'
   l'alberatura del nodo: il codice di rito e' rito, il capo della
   prescrizione e' preliminare di merito, il resto e' merito. 658 su 983
   (66,9%);
3. la **natura del rapporto** la diceva il MODELLO. Sull'atto Verdi -
   opposizione di conto corrente con 56 eccezioni fra anatocismo e CMS - ha
   risposto `finanziamento_rateale`, e da quel valore sono discese quattro
   astensioni nel merito. Esce dallo schema GBNF; cio' che diceva resta in
   `natura_rapporto_calcolata.detto_dal_modello`.

**La regola imparata dal grafo, non da noi**: un articolo che il corpus
colloca in una comunita' e' un CAMPO DI BATTAGLIA, non la descrizione del
rapporto. L'art. 1815 c.c. sta nel capo "Del mutuo" ma il corpus lo usa per
l'usura (24 provvedimenti), e senza questa regola qualificava come mutuo
un'opposizione di conto corrente - lo stesso errore del modello, commesso
da noi. Gli articoli che il rapporto lo DEFINISCONO (1842, 1845, 1852) non
stanno in nessuna comunita', perche' non ci si litiga.

Il lessico con cui si classifica chi non cita norme (il 69,8% delle
eccezioni) non l'ha scelto nessuno: e' il log-odds delle motivazioni che
citano gli articoli di quella comunita' contro il resto del corpus.

L'enum `Famiglia` a nove valori **resta**: e' la chiave del motore delle
regole, che non si tocca. Convivono - la comunita' dice dove sta
l'eccezione nel discorso dei giudici, l'enum apre la regola. 340 verdi.

**v1.27 (2026-08-31, commit `04be044`)** - l'ordine dei motivi lo calcola
Python, non il modello. *(voce ricostruita)*

La Fase 3-bis chiedeva al modello una permutazione completa degli
`eccezione_id`, con `maxItems` 15. Misurato sul batch del 2026-08-30:
mediana 17 motivi, massimo 59, **24 atti su 45 oltre il tetto** e altri 5
sotto il `minItems`. Lo schema respingeva l'input e uccideva la corsa DOPO
Fase 2 e Fase 3 - 29 atti su 45, il 64%.

**Alzare il tetto non serviva**, e non per il budget (56 id costano 293
token contro `n_predict` 1536, misurato sul tokenizzatore): una
permutazione generata degrada a K=20-30 e fallisce a K=50, quindi il
controllo 11 l'avrebbe respinta quasi sempre, a chiamata gia' pagata.

Ibrido: l'ordine e' rito, quindi si **calcola** (`ordine_motivi.py`: rito ->
preliminari di merito -> merito -> non classificati, stabile dentro il
rango). Al modello resta la ricerca dei conflitti, a finestre scorrevoli di
8 con passo 4, dove il giudizio e' locale e a coppie. La copertura si
dichiara: `copertura_conflitti` dice quante coppie sono state davvero
guardate, e una finestra troncata o respinta scarta se stessa, non la
passata. Collaudo sull'atto Verdi (56 motivi): 13 finestre su 13,
0,5-0,7s ciascuna, 292/1540 coppie esaminate. 322 verdi.

**v1.26 (2026-08-31, commit `b54ae08`)** - `tipo_atto` e `grado` calcolati,
non piu' chiesti al modello. *(voce ricostruita)*

Due cose insieme, perche' separarle avrebbe lasciato il contratto
incoerente.

1. **Enum allargato.** `tipo_atto` non aveva `atto_appello` ne'
   `ricorso_cassazione`: nel corpus del 2026-08-30 dodici atti su 56 sono
   appelli o ricorsi e finivano per forza in un valore sbagliato, che poi
   instrada la famiglia in Fase 2. Aggiunto anche `grado`, distinto da
   `fase_processuale` - una comparsa conclusionale in opposizione a d.i. e'
   `primo_grado` ma `opposizione_cognizione`;
2. **tolto al modello.** `tipo_atto.py` li calcola da tre strati
   deterministici: norma in testa risolta sul grafo (vince quando c'e'),
   giudice adito, autodenominazione. Quando due strati DISCORDANO si
   dichiara `non_desumibile` invece di scegliere.

Misurato sui 52 atti nativi: strato norma 6/52, strato giudice 52/52,
strato nome 44/52, almeno uno dei tre **52/52**; tipo 45/52 (87%), grado
50/52 (96%), disaccordi dichiarati 2/52. Contro il modello sugli stessi 45
atti del batch: **concordano 16/45 (36%)**. Il modello ha risposto
`comparsa_risposta` per 21 atti su 45, fra cui file intitolati "RICORSO PER
CASSAZIONE" e "ATTO DI APPELLO" - valore strutturalmente sbagliato qui,
perche' l'ingresso e' l'atto del DEBITORE e la comparsa di risposta e'
quella che scriviamo NOI.

**Questa e' copertura, non correttezza**: quante volte risponde, non quante
volte risponde bene. Per il secondo numero serve il golden set. Dai nomi
dei file si vedono almeno 4 errori residui, tutti della stessa classe -
memorie e comparse depositate DENTRO un giudizio di opposizione,
classificate come l'opposizione che raccontano; oltre la passata sui titoli
si andrebbe in overfitting su 52 atti.

L'accesso al grafo e' **opzionale**: `--solo-fase1 --batch` continua a
girare senza store ne' grafo (invariante del golden set), e un grafo
illeggibile degrada lo strato 1 con una nota invece di fermare
l'estrazione. 302 verdi.

**v1.25 (2026-08-26)** - `testo_verbatim` obbligatorio su ogni eccezione;
`domande_riconvenzionali` non accetta piu' stringhe vuote.

**Il difetto che chiude e' stato trovato dalla prima corsa reale**, non da
un ragionamento: `runs/20260826-201613`, unica eccezione estratta, stato
`ancorata`, similarita' `0.9937`, e `testo_letterale` con caratteri di
scaffolding del modello a entrambi gli estremi (un apice in testa, `'}"`
in coda). Un campo dichiarato citabile che non e' verbatim.

La causa non e' un bug: e' il disegno dell'ancoraggio. `SOGLIA_ANCORATA`
e' 0.95, quindi "ancorata" significa **esiste una finestra dell'atto molto
simile a questa stringa**, non **questa stringa e' nell'atto**. Finche' il
campo citabile e' quello che ha scritto il modello, la differenza fra le
due cose finisce in un atto depositato.

`testo_verbatim` e' la fetta di `testo_atto_pulito` agli offset che Python
ha gia' calcolato (`ancora.inizio:ancora.fine`) - costo: una riga, nessuna
chiamata, nessuna euristica. `null` quando `ancora.stato != "ancorata"`:
senza ancoraggio pieno non c'e' nulla di citabile automaticamente, e un
campo vuoto e' preferibile a una stringa che sembra una citazione.
`testo_letterale` resta nel contratto (serve a capire cosa ha prodotto il
modello e a diagnosticare) ma la sua description ora dice esplicitamente
che non e' citabile.

Invariante testato: `len(testo_verbatim) == ancora.fine - ancora.inizio`
per ogni eccezione ancorata, `None` per tutte le altre. Piu' un test
diretto su `_verbatim`, che deve ignorare del tutto la stringa del
modello: se la guardasse, riprodurrebbe il difetto che chiude.

`domande_riconvenzionali`: stessa corsa, il modello ha emesso `[""]` su un
atto che non ne conteneva nessuna. Una stringa vuota nel contratto diventa
una domanda inesistente per chi legge a valle. Filtrate all'assemblaggio.

Aggiunto anche `fase1_assembla.riepilogo_autoverifica()` (funzione, NON un
campo di contratto): confronta le eccezioni tenute con quelle che
l'autoverifica dichiara di aver visto. Non e' un golden set e non lo
sostituisce - e' un indicatore che il sistema produce gratis a ogni corsa,
e che distingue "la passata di estrazione rende poco" da "il cancello di
ancoraggio taglia molto". Sulla corsa che ha motivato questo bump dice
tenute 1, mancanti dichiarate 3, scartate 3.

84/84 verdi. Il file gia' prodotto a 1.24 NON valida contro 1.25 (manca
`testo_verbatim`, che e' `required`): e' voluto, un contratto che accetta
in silenzio file di due versioni non e' un contratto.

**Patch a 1.25, stesso giorno, nessun bump: lo schema non cambia.** Tre
correzioni di comportamento trovate dalla seconda corsa reale
(opposizione Verdi, 56 eccezioni).

1. **`localizza._screma_sovrapposte`.** I candidati rivali venivano
   confrontati SOLO con il migliore, mai fra loro. La finestra scorrevole
   avanza di un confine di parola, quindi lo stesso punto dell'atto
   produce piu' finestre quasi identiche e finivano tutte in
   `occorrenze`: X14 dichiarata ambigua su 4 punti di cui tre sovrapposti
   fra loro ([12935:13260], [12943:13268], [12946:13271]), e lo stesso
   X13, X22, X56 - quattro delle sei ambigue. **Non rende citabile
   nessuna ancora** e non e' pensato per farlo: dopo lo scremo restano i
   punti veri in cui il testo e' davvero ripetuto nell'atto. Corregge il
   conteggio, che un campo diagnostico non puo' permettersi di sbagliare
   (sezione 6). Se dopo lo scremo resta un solo punto, l'ambiguita' non
   c'era: l'esito ricade su ancorata/parziale come qualunque altro caso.

2. **Il buco di un'ancora parziale non parla piu' di soglia quando il
   motivo e' un altro.** X18 aveva similarita' **1.000** e causa vera
   un'omissione interna scritta dal modello, ma il messaggio diceva "con
   similarita' 1.000 (sotto la soglia 0.95)". Ora `ancora["motivo"]`,
   quando c'e', batte la spiegazione generica.

3. **`_non_degenere` sulle liste di stringhe libere.**
   `documenti_contestati_come_mancanti` conteneva `["C2) DETERMINAZIONE
   DELLA VALUTA ED INTERESSI FITTIZI.", "s"]`. Il filtro toglie solo cio'
   che non puo' essere un contenuto (meno di 3 caratteri): e' igiene, non
   merito. `precedenti_citati` NON e' toccato - separare un precedente da
   una frase di raccordo e' classificazione, e resta un aperto (sezione 7,
   item 18).

87/87 verdi. Nessuna delle tre modifica lo schema, quindi la versione
resta 1.25: un bump che non cambia il contratto e' rumore per chi legge
il changelog per capire cosa deve rileggere.

**v1.24 (2026-08-26)** - `buchi` da lista di stringhe a lista di
`{tipo, testo}`, con `tipo` su vocabolario CHIUSO
(`estrazione_atto.TIPI_BUCO`, dieci valori, nessun `altro`).

**Non e' una modifica cosmetica: rimuove un match testuale che era gia'
nel codice.** `confronta_batch._avvisi_tetto` isolava gli avvisi di
saturazione con `"tetto array" in b` - cioe' cercando un prefisso in
italiano dentro una stringa di prosa. Cinque assert di
`test_integrazione_mockata.py` facevano lo stesso (`"filtro unita" in b`,
`"controllo ancoraggio" in b`). Qualunque consumatore nuovo - il front
end locale in particolare - avrebbe dovuto ricostruire la stessa
euristica, cioe' portare logica di dominio fuori dalla pipeline.

Le dieci provenienze erano gia' tutte distinte all'origine, marcate da
un prefisso: `[struttura|eccezioni|citazioni]`, `PASSAGGIO FALLITO`,
`[autoverifica]`, `[controllo ancoraggio]`, `[filtro unita'
argomentative]`, `[tetto array]`, `[citazioni]` (due cause diverse:
norma senza data mai cercata, e data non di calendario),
`[deduplicazione]`, `[ancoraggio]`. Il bump non aggiunge informazione:
la rende leggibile senza parsing. **`testo` resta invariato, prefisso
incluso** - la memoria di analisi mostra le stesse righe di prima.

Scelta di scope: vocabolario completo sulle dieci provenienze, non solo
`tetto_array`. Con un `tipo` a due valori (`tetto_array`/`altro`) il
match di prefisso sarebbe sopravvissuto per nove casi su dieci - si
sarebbe pagato un bump di contratto per spostare il problema invece che
per chiuderlo, e il costo dei due scope e' identico (stessi file, stessi
test, stessa migrazione).

`buco(tipo, testo)` valida il tipo alla costruzione e solleva
`ValueError` su un valore fuori vocabolario: e' un errore di
programmazione del chiamante, non un dato da scoprire in validazione a
fine corsa (stessa lezione di 1.13-1.15 - si scarta dove nasce).

Guardia anti-deriva:
`test_il_vocabolario_dei_tipi_di_buco_non_deriva_dallo_schema` confronta
`TIPI_BUCO` (letta dall'AST, senza importare il modulo) con l'enum di
`buchi.items.tipo` nello schema. Il vocabolario e' scritto in due posti;
senza la guardia, la divergenza si sarebbe scoperta in validazione a
fine corsa - lo stesso costo che ha motivato `test_versioni_contratti.py`
al bump 1.3.

Migrati nello stesso commit tutti i sei lettori reali:
`validazione.py` (controllo 3, BLOCCANTE - faceva
`" ".join(estrazione["buchi"])`, che su una lista di dict sarebbe
esploso con `TypeError`), `confronta_batch.py`, `rendering.py`,
`esegui_pipeline.py` (due punti: propagazione batch e riepilogo),
`assembla_report.py`, piu' i test. 80/80 verdi.

Non misurato in questo bump: nessuna corsa reale con llama-server (non
raggiungibile al momento della modifica). La verifica e' la suite
mockata piu' la validazione di schema; il primo file `01_estrazione.json`
prodotto dal vivo va controllato contro lo schema 1.24 prima di
considerare chiuso il bump.

**v1.23 (2026-08-25)** - patch alla v1.22, stesso giorno. **Il negativo
più importante trovato in questa indagine: non c'era varianza da
spiegare, c'era una temperatura sbagliata su output vincolato da
grammatica.**

La tabella delle 5 varianti di prompt (non ancora in un contratto,
misura isolata) aveva dato 0, 2, 3, 4 elementi sullo stesso blocco B04 -
sembrava alta varianza fra formulazioni diverse. Non lo era: con n=1 per
variante, quella tabella campionava una distribuzione, non confrontava
prompt. Misurato con n=10 a parità di tutto (prompt originale, blocco
B04, seed 1234, server riavviato ogni volta):

| `temperature` | 10 esecuzioni | elementi | quasi-duplicati | fideiussione |
|---|---|---|---|---|
| 0.1 (valore precedente) | 10/10 **identiche** | 4 | 4 (100%) | mai trovata |
| 0.0 | 10/10 **identiche** | 10 | 0 | **trovata ogni volta** |

Non varianza: due configurazioni ciascuna perfettamente deterministica
a server pulito (coerente con `cache_prompt:false`, 1.17) - quello che
sembrava varianza in esperimenti precedenti era sensibilità alla
sequenza di chiamate, già diagnosticata. E non un margine: la differenza
fra un risultato deterministicamente degenere (4 elementi, tutti
copie) e uno deterministicamente corretto (10 elementi distinti) sullo
stesso identico input, stesso seed, stesso prompt.

**Causa**: su un output vincolato da GBNF/`json_schema`, la grammatica
garantisce già la forma - la temperatura residua non aggiunge diversità
utile al contenuto, sposta il campionamento verso cicli di ripetizione.

**Correzione**: `temperature=0.0` su ogni chiamata GBNF-vincolata di
Fase 1 - estrazione (struttura/eccezioni/citazioni, `_passata`),
autoverifica e filtro unità argomentative (`_passata_diretta`),
riformulazione (`retrieval.riformula_query_di_ricerca`). **Non toccati**
`fase3_confutazione` (0.7), `fatto` (0.7), `fase3bis_coerenza` (0.3): la
temperatura più alta lì serve alla prosa, non a un array vincolato -
misura separata prima di cambiarli. Valori registrati in
`meta.esecuzione.temperature_per_passo` (campo già esistente, dalla
1.12).

**Conseguenza dichiarata**: ogni misura di questa sessione fatta a
`temperature=0.1` (il confronto delle 5 varianti di prompt, il batch di
5 atti su cui sono stati tarati filtro/tetto/segmentazione, il confronto
8B/14B) è stata fatta in condizioni degeneri - da rifare, non da
correggere a posteriori.

**Verifica sul batch di 5 atti, server pulito**: la fideiussione ora
compare (X32, ancorata) nella corsa REALE su atto-prova, non solo
nell'isolamento su B04 - il risultato positivo tiene anche fuori dal
laboratorio. Ma il quadro complessivo NON è uniformemente migliore:
eccezioni totali 113 → **104** (giù per 2 atti su 5, non solo su),
avvisi sul tetto **5 → 6**, e la degenerazione nei blocchi che lo
toccano è più marcata (30/30 con 25-30 quasi-duplicati, 83-100%, non
meno che a 0.1). Un atto (`Opposizione_a_precetto`) passa dal 17% all'
**84%** di tasso di scarto, quasi tutto `non_ancorata` (31 fabbricazioni
contro 1 sola a 0.1). Tempo: 29m2s contro 25m16s, più lento sul batch
reale (il test isolato aveva mostrato l'opposto per singola chiamata,
non scala linearmente).

Lettura più coerente con i numeri, non una conferma né una confutazione:
a campionamento greedy puro (`temperature=0.0`) il modello non ha via
di fuga stocastica da un ciclo ripetitivo una volta innescato - a 0.1 la
probabilità residua di campionare un token diverso dal piu' probabile
poteva rompere il ciclo. Il quadro è misto: risolve il caso su cui è
stato misurato, non risolve la degenerazione in generale.

**Chiuso in negativo anche il confronto delle varianti di
`PROMPT_ECCEZIONI`** (4 riformulazioni provate contro il blocco B04):
era stato fatto a `temperature=0.1`, in condizioni degeneri per
costruzione - il controllo (prompt originale) in quelle condizioni non
trova la fideiussione, ma a `temperature=0.0` la trova ogni volta.
Nessuna delle 4 varianti è stata adottata: il prompt originale non era
il problema, la temperatura lo era. `PROMPT_ECCEZIONI` resta invariato.

47 test verdi (nessun nuovo test: e' un valore di configurazione, non un
comportamento nuovo - la misura n=10 sopra e' la verifica).

**Nota (esperimento chiuso in negativo, 2026-08-25) - budget dimezzato a
`temperature=0.0` non aiuta, perde il criterio principale.** Provato
solo dopo la sotto-segmentazione (1.19) - la volta precedente il
segmento da 7516 caratteri era indivisibile e il dimezzamento non
poteva funzionare per costruzione; ora quella causa e' rimossa. Batch
sui 5 atti originali, `budget_token_per_blocco=1100`, `temperature=0.0`
(gia' il default), server pulito, confrontato con la baseline
`budget=2200` @ `temperature=0.0` (stessa sessione, changelog sopra):

| | budget 1100 | budget 2200 |
|---|---:|---:|
| eccezioni totali (5 atti) | 125 | 104 |
| avvisi sul tetto | 6 | 6 |
| fideiussione (atto-prova) | **assente** | **presente** |
| tempo totale | 43m17s | 29m2s |

Più lento, non più veloce (contrario all'ipotesi "generazioni più corte
degradano meno" - verificata sul batch reale, non solo su una chiamata
isolata). Più eccezioni totali, ma senza verità di riferimento "di più"
non si distingue da "più rumore" - è esattamente il problema che il
golden set deve risolvere. Perde il criterio su cui questa indagine si
è giudicata dall'inizio. **Budget di produzione resta 2200.**

**Nota (esperimento chiuso in negativo, 2026-08-25) - DRY sampling non
risolve la degenerazione.** Build b10488 espone `dry_multiplier`/
`dry_base`/`dry_allowed_length`/`dry_penalty_last_n` via `/props`
(verificato prima di provare). Testato `dry_multiplier=0.8,
dry_base=1.75, dry_allowed_length=2` (`temperature=0.0` invariata) sui 6
blocchi che degeneravano nel batch 1.23 (server pulito ognuno, seed
1234), non su un batch intero:

| blocco | controllo | DRY |
|---|---|---|
| Atto1 B04 | 30 elementi, 30 dup | identico |
| Atto1 B07 | 30 elementi, 28 dup | identico |
| Atto2 B02 | 30 elementi, 30 dup | identico |
| opposizione_dec_ing B01 | 30 elementi, 25 dup | **troncata** (nuovo) |
| Opposizione_a_precetto B01 | 30 elementi, 25 dup | identico |
| Opposizione_a_precetto B03 | 30 elementi, 30 dup | 10 elementi, 10 dup (100% comunque) |
| atto-prova B04 (controllo fideiussione) | 10 elementi, 0 dup, trovata | identico |

4 blocchi su 6 invariati, uno peggiora (troncamento nuovo), uno scala da
30 a 10 copie restando al 100% duplicato - non un ciclo rotto, uno più
corto. Nessun cambiamento al codice: DRY penalizza sequenze ripetute,
ma evidentemente non nella forma in cui questo modello degenera qui.

**Nota (non un contratto, un esperimento chiuso in negativo, 2026-08-25)
- ipotesi "modello sottodimensionato" falsificata.** Batch identico (5
atti, stessi prompt, stessi parametri, server pulito) su Qwen3-14B-Q4_K_M
invece di Qwen3-8B-Q4_K_M (sha256 e provenienza in DEPLOY.md), nessun
adattamento. Se la varianza di estrazione fosse un sintomo di modello
troppo piccolo per il task, il 14B avrebbe dovuto estrarre di più e
recuperare la fideiussione. Ha fatto l'opposto:

| | 8B | 14B |
|---|---:|---:|
| eccezioni totali (5 atti) | 113 | **59** |
| tempo totale | 25m16s | 21m16s (non più lento) |
| `non_riconosciuta` | 26/113 (23%) | 20/59 (34%, peggio) |
| fideiussione (atto-prova) | assente | **assente anche qui** |

Su 3 atti su 5 il calo è drastico (17→3, 41→24, 19→2). Il 14B non e'
stato più lento (in alcuni atti molto più rapido, perché ha estratto
meno). Un'anomalia isolata: `opposizione_a_decreto_ingiuntivo` ha
scartato l'89% delle proposte come `formula_di_rito` su 14B contro il
10% su 8B - comportamento del filtro molto più aggressivo su quell'atto
specifico con l'altro modello, causa non indagata.

**Chiuso in negativo**: la dimensione del modello non è la causa. Il
modello resta Qwen3-8B-Q4_K_M. Prossima variabile: `PROMPT_ECCEZIONI`
stesso, mai toccato in tutta questa indagine (filtro, ancoraggio,
segmentazione, campionamento, tetto sono stati tutti corretti - la
passata di estrazione grezza no).

**Ripetuto a `temperature=0.0` (dopo la 1.23), stesso esito**: batch
identico su 14B a temperatura corretta.

| | 8B @0.0 | 14B @0.0 |
|---|---:|---:|
| eccezioni totali | 104 | **56** |
| tempo totale | 29m2s | 23m6s |
| avvisi sul tetto | 6 (tutti degeneri, 83-100%) | 2 (entrambi degeneri, 90-93%) |
| fideiussione (atto-prova) | trovata | trovata |

Il rapporto "14B estrae circa la metà di 8B" persiste quasi identico
(56/104 contro 59/113 a `temperature=0.1`) - non era un artefatto della
temperatura, è un comportamento stabile del modello più grande su
questo task. La fideiussione ora compare su ENTRAMBI i modelli: è stato
`temperature` a sbloccarla, non la dimensione - conferma indipendente
della 1.23, non solo su 8B.

**Osservazione laterale, non richiesta ma visibile**: 14B è molto meno
sensibile al cambio di temperatura di 8B - il suo totale si muove appena
passando da 0.1 a 0.0 (59→56), quello di 8B si muove molto di più
(113→104) con composizione per atto molto diversa. Non indagato oltre.

**v1.22 (2026-08-25)** - patch alla v1.21, stesso giorno. **Regressione
propria, trovata verificando il risultato della 1.21 invece di fidarsene.**
Il batch di 5 atti rilanciato dopo l'aumento dei `maxItems` ha dato
eccezioni_totali IN CALO per 3 atti su 5, non in aumento - un atto e'
sceso a **zero**. Causa: `n_predict=2048` sul passo `eccezioni_blocco`
non e' stato alzato insieme al `maxItems` (15→30) che lo riguarda -
il modello, di fronte a un tetto piu' alto, ha provato a riempirlo di
piu' e ha esaurito lo spazio di generazione prima di chiudere il JSON.
`_passata` cattura `RispostaTroncata` e ritorna `None`: il blocco non
viene degradato a 15 elementi, viene **perso per intero**. Misurato: 9
blocchi troncati su 21 nel batch, non un caso isolato.

Alzare un tetto senza alzare lo spazio per riempirlo e' un
peggioramento mascherato da miglioramento - il sintomo era invisibile
finche' non si e' guardato il totale per atto invece di fidarsi che
"tetto piu' alto" implicasse "piu' materiale". `n_predict` di
`eccezioni_blocco`: 2048 → 4096. `N_PREDICT["fase1"]` (margine di
verifica pre-volo in `esegui_pipeline.py`): 3072 → 4096, per coprire il
caso peggiore reale fra i passi di Fase 1, non la media.

**Verifica numerica**: eccezioni totali su per ogni atto che aveva
perso materiale (14→17, 30→41, 15→19), non solo recuperate al livello
pre-1.21 - tutte OLTRE il tetto originale di 15. Avvisi sul tetto:
11 → 5. Non pulito fino in fondo: restano 4 troncamenti (erano 9), e i 5
avvisi residui sono quasi tutti degenerazione, non saturazione - 30/30
con 30 quasi-duplicati (100%), 30/30 con 18 (60%), 30/30 con 8 (27%),
un solo 16/20 con 0 duplicati (saturazione vera). Il tetto piu' alto ha
lasciato correre anche la ripetizione degenere in alcuni blocchi, non
solo il materiale reale che doveva far passare - stesso fenomeno chiuso
in negativo con `repeat_penalty` sopra, non toccato da questo aumento:
un tetto piu' alto gli lascia semplicemente piu' spazio per manifestarsi.

47 test verdi (nessun nuovo test: la correzione e' un valore di
configurazione, non un comportamento nuovo da verificare in isolamento -
il batch stesso e' la verifica).

**v1.21 (2026-08-25)** - patch alla v1.20, stesso giorno. `maxItems`
alzato dove i dati del batch di 5 atti (1.20) lo giustificano - 8 dei 11
avvisi sul tetto erano saturazione pura (0 quasi-duplicati): il tetto
tagliava materiale reale, non ridondanza.

- `eccezioni_sollevate` (SCHEMA_ECCEZIONI): 15 → 30
- `documenti_contestati_come_mancanti` (SCHEMA_ECCEZIONI): 15 → 30
- `elementi_non_estraibili` (SCHEMA_STRUTTURA, SCHEMA_ECCEZIONI,
  SCHEMA_CITAZIONI - stesso nome, stesso significato in tre schemi):
  10 → 20

Non alzati: `documenti_dichiarati_prodotti_da_controparte`,
`domande_riconvenzionali`, `norme_citate`, `precedenti_citati`,
`eccezioni_confermate`/`eccezioni_mancanti_nella_prima_estrazione` -
nessun avviso reale su questi campi nel batch, alzarli sarebbe una
correzione a un problema non misurato.

L'avviso sul tetto (1.18/1.20) resta attivo sugli stessi campi con i
nuovi limiti: se qualcosa tocca ancora il tetto dopo l'aumento, lo dirà
lui, non serve una nuova indagine per scoprirlo.

**v1.20 (2026-08-25)** - patch alla v1.19, stesso giorno.

**1. Ipotesi repeat_penalty=1.3, testata e non confermata né esclusa
del tutto.** Le 5 finestre della scala di lunghezza (1.19) ripetute con
`repeat_penalty=1.0` (disattivato), server pulito per ciascuna:

| lunghezza | 1.3 (prima) | 1.0 (ora) |
|---|---|---|
| 1594 | trovata, 2 elementi | trovata, 1 elemento |
| 2500 | NON trovata, 2 elementi | **trovata**, 2 elementi |
| 3500 | NON trovata, **15 elementi degeneri** | NON trovata, 2 elementi (2 quasi-duplicati) |
| 4500 | trovata, 2 elementi | **RISPOSTA TRONCATA** |
| 5534 | NON trovata, **15 elementi degeneri** | NON trovata, **15 elementi, 12 quasi-duplicati** |

Non sparisce (5534 resta degenere quanto prima) e non è innocua
(4500 tronca, un fallimento che non esisteva a 1.3) - risultato misto,
non la conferma netta che avrebbe giustificato di disattivarla ovunque.
**Nessun cambiamento globale fatto**, per costruzione della stessa
domanda posta ("se la degenerazione sparisce... se non sparisce, prova
anche..."): non è sparita.

**Chiuso in negativo**: `repeat_penalty` resta `1.3` su tutte le
chiamate di questo modulo. L'ipotesi non regge - non risolve la
degenerazione e introduce un troncamento assente a 1.3 - e la misura non
va ripetuta senza un'ipotesi nuova.

Payload completo verificato contro `/props` del server: oltre a
`prompt`, `n_predict`, `temperature=0.1`, `cache_prompt=false`,
`json_schema`, `repeat_penalty` (1.3 di norma) e `seed`, nessun altro
parametro di campionamento è mai inviato esplicitamente -
`presence_penalty` e `frequency_penalty` sono già a 0.0 (default del
server, mai attivati da questo codice), `dry_multiplier` a 0.0,
`repeat_last_n` a 64, `top_k` 40, `top_p` 0.95, `min_p` 0.05, tutti
default del server mai toccati.

**2. Allarme sul tetto: distingue degenerazione da saturazione.**
`_verifica_tetto` ora calcola quanti elementi dell'array sono
quasi-duplicati fra loro (rapidfuzz Indel o difflib, soglia 0.90 su
testo normalizzato - stesso motore di `localizza.py`, riusato via
`localizza._rapporto`, non duplicato) e lo include nell'avviso: "15/15
elementi..., di cui 12 quasi-duplicati" contro "13/15..., di cui 0
quasi-duplicati" - il primo è rumore di campionamento, il secondo
materiale reale che il tetto ha tagliato, correzioni opposte che
l'avviso della 1.18 non distingueva. 2 nuovi test.

47 test verdi (46 + 1: distingue degenerazione da saturazione - il test
del tetto della 1.18 aggiornato, non sostituito, per il nuovo formato
del messaggio).

**v1.19 (2026-08-25)** - patch alla v1.18, stesso giorno. Sotto-
segmentazione dei segmenti sovradimensionati: la 1.18 aveva scoperto che
il blocco B04 (la sezione numerata "4)", 7516 caratteri) toccava il
tetto di `eccezioni_sollevate` (14/15); un tentativo di dimezzare il
budget di segmentazione (2200 → 1100) NON l'ha risolto - il blocco non
si è diviso per niente (stesso span, 14989-22505), perché
`_raggruppa_con_span` sa solo ACCORPARE segmenti piccoli, mai spezzarne
uno grande: "4)" è UN segmento naturale unico secondo
`_trova_sezioni_numerate`, indivisibile a qualunque budget. Il
dimezzamento ha solo reso più densi gli altri blocchi - **tre** blocchi
al/vicino al tetto invece di uno. **Tentativo registrato e annullato**:
il budget di produzione resta 2200 (mai stato cambiato nel codice, solo
in uno script diagnostico separato).

Test di isolamento (server pulito, seed 1234): il passaggio sulla
nullità della fideiussione, sottoposto da solo a `PROMPT_ECCEZIONI`
(1594 caratteri), viene estratto correttamente - "si perde nella
lunghezza", non "il modello non lo vede".

**Correzione**: un segmento naturale più grande del budget da solo viene
ora SOTTO-segmentato prima dell'accorpamento, mai lasciato intero e mai
troncato. Gerarchia di confini, in ordine: (a) sotto-numerazione interna
(`4.1)`, `a)`, `i)` - richiede ≥2 marcatori, stessa soglia di
affidabilità della numerazione top-level) - (b) capoverso (riga vuota) -
(c) confine di frase, riusando `segmenta_provvedimenti._spezza_in_frasi`
(gestisce le abbreviazioni della prassi giuridica italiana - lecito
importare da `src/`: la restrizione vale per la Fase 3, non per la Fase
1, e quel modulo non ha percorsi verso il grafo). Se nessun livello
trova un confine (caso limite: una frase più lunga del budget), il
segmento resta intero - MAI troncato.

Ogni sotto-segmento porta `segmento_padre` (l'intestazione del segmento
originale) - `Blocco.segmenti_padre` lo aggrega e `esegui_fase1` lo
registra nel log (`registro.nota`), non nello schema JSON di
`atto.blocchi`: è una traccia diagnostica della segmentazione, non un
dato del contratto fra le fasi.

**Verifica sul run reale** (server pulito): 5 blocchi → **4** (non di
più - i frammenti più piccoli vengono ri-accorpati fino al budget,
spesso mescolando contenuto di sezioni numerate prima separate). 30
eccezioni estratte (contro 20 prima), 210.9s (più veloce di prima, non
più lento). Ma **il criterio non è pienamente soddisfatto**: B01
(6074 caratteri) e B02 (6815) toccano ancora il tetto (15/15 ciascuno) -
meno del blocco unico di prima, ma non zero. Il passaggio sulla
fideiussione **resta assente**: non è più nel blocco che tocca il
tetto (cade in B04, 5534 caratteri, che ha prodotto 0 eccezioni tenute
e 4 scartate, nessuna delle quali il passaggio cercato) - la causa
questa volta NON è la saturazione dell'array, e' un'estrazione grezza
che non l'ha proposto, per una ragione non ancora identificata. La
sotto-segmentazione ha risolto il difetto che l'aveva motivata
(l'indivisibilità di un segmento atomico, provata con 5 test dedicati in
`test_segmenta_atto.py`) ma non ha chiuso il caso concreto che la
misurava: il criterio di accettazione dichiarato ("nessun blocco tocca
il tetto e la fideiussione compare") non è raggiunto.

46 test verdi (41 + 5 nuovi: test_segmenta_atto.py).

**v1.18 (2026-08-25)** - patch alla v1.17, stesso giorno. Allarme sul
tetto: la 1.17 aveva scoperto per caso (il caso della fideiussione
mancante, non confermato ma sospetto concreto) che il blocco B04 aveva
prodotto 14 eccezioni tenute su un tetto (`maxItems`) di 15 - passato in
silenzio perché nessun controllo lo dichiarava, scoperto solo perché
mancava un passaggio specifico che si sapeva dover comparire. Un array
che tocca il proprio tetto può aver perso materiale reale al taglio
della grammatica, non solo scartato ridondanza, e non c'è modo di
saperlo guardando il file finale da solo.

Nuovo campo **`avvisi_tetto`** su `EsitoEstrazione`, sempre confluito in
`buchi`: quando un array vincolato raggiunge o supera l'80% del proprio
`maxItems`, una nota esplicita con il conteggio, il campo e il blocco.
Applicato a OGNI campo array di OGNI schema di Fase 1 sul percorso
segmentato (`estrai_atto_segmentato`, l'unico usato dalla pipeline reale
- `estrai_atto()` non segmentato resta scoperto, e' codice morto non
chiamato da nessun punto della pipeline): `eccezioni_sollevate`,
`documenti_dichiarati_prodotti_da_controparte`,
`documenti_contestati_come_mancanti`, `domande_riconvenzionali`,
`elementi_non_estraibili` di struttura/eccezioni/citazioni,
`norme_citate`, `precedenti_citati`, `eccezioni_confermate`,
`eccezioni_mancanti_nella_prima_estrazione` - non solo il campo del caso
che l'ha motivato. Sulla lunghezza GREZZA del modello, prima di
qualunque filtro o controllo di ancoraggio: e' quella che dice se il
modello ha davvero riempito il tetto, non quanto ne e' sopravvissuto ai
controlli a valle (sempre minore o uguale).

41 test verdi (40 + 1 nuovo: allarme sul tetto).

**v1.17 (2026-08-25)** - patch alla v1.16, stesso giorno. Due correzioni
dalla stessa indagine sul residuo di stato scoperto in 1.16, misurate
separatamente prima di essere corrette.

**1. `cache_prompt`, causa isolata del residuo di stato.** Il changelog
1.16 aveva registrato CHE il server accumula stato fra richieste senza
saperne il perché. Isolato: `/completion` ha `cache_prompt: true` di
default - il riuso del prefisso in cache cambia l'ordine di riduzione in
floating point, quindi l'output, anche a `seed` fissato. Verificato:
stessa sonda del 1.16 (blocco 4, `seed=1234`), tre chiamate di fila sullo
stesso processo con `cache_prompt: false` esplicito → identiche byte per
byte, tutte e tre. Impostato su OGNI chiamata della pipeline
(`llama_server_client.completa`), non solo Fase 1. Nuovo campo
**`meta.esecuzione.cache_prompt`** (booleano, sempre `false`) in tutti e
tre gli schemi - registrato perché è esattamente il tipo di parametro la
cui assenza renderebbe una corsa non riproducibile con certezza. Dettagli
e costo in tempo misurato: `DEPLOY.md`.

**2. Il criterio del filtro era tautologico su un atto scritto da una
sola parte.** Il vocabolario "autore/avversa" (1.15) chiedeva "questa
frase è dell'autore?" - ma su un atto che l'autore ha scritto per intero,
ogni frase è letteralmente sua, compresi i rinvii e le tesi altrui che
riporta. L'asse "di chi è" collassa sempre sulla stessa risposta,
indipendente dal contenuto: misurato che il filtro (già a chiamata
singola, 1.16) teneva perfino un rinvio da manuale ("Si contestano tutte
le eccezioni di cui sopra") e la tesi bancaria riportata
("L'Istituto di Credito ribadisce...") - lo stesso errore di polarità che
la 1.15 voleva correggere, tornato per una ragione diversa.

Asse sostituito da CHI parla a CHE TIPO di affermazione è, enum
riscritto: `eccezione_o_difesa_autonoma` (tenuta - un vizio, una nullità,
una decadenza, un fatto impeditivo o estintivo con contenuto proprio),
`tesi_avversa_riportata` (scartata - un verbo dichiarativo o un
virgolettato attribuito all'altra parte, anche se è l'autore a scriverlo),
`rinvio_o_richiamo`, `formula_di_rito`. Prompt con esempi presi dall'atto
reale, non inventati (tenere: il passaggio sulla nullità della
fideiussione per difetto di forma; scartare: "L'Istituto di Credito
ribadisce..."; scartare: "Si contestano tutte le eccezioni di cui
sopra"). `unita_scartate[].motivo`: `tesi_riportata_dell_avversa` →
`tesi_avversa_riportata`, `rinvio_senza_contenuto` → `rinvio_o_richiamo`
(stesso significato, stesso motivo del rinominare della 1.15: il valore
vecchio portava il criterio sbagliato, non torna utilizzabile).

**Verifica sui due casi che avevano motivato la 1.15/1.16** (rilanciato
`--solo-fase1` su server appena riavviato, `cache_prompt: false`, prima
corsa davvero pulita secondo entrambe le correzioni di questa patch): "L'Istituto di Credito ribadisce..." viene **scartata** come
`tesi_avversa_riportata` - criterio soddisfatto. Il passaggio sulla
nullità della fideiussione per difetto di forma, invece, non compare
NE' fra le tenute NE' fra le scartate di questa corsa: la passata grezza
di estrazione (`PROMPT_ECCEZIONI`) non l'ha proposto come candidato in
questo giro. Il blocco che lo contiene (B04) ha prodotto 14 eccezioni
tenute su questa corsa, a un passo dal tetto `maxItems: 15` di
`SCHEMA_ECCEZIONI` - **sospetto concreto, non confermato**: il passaggio
può essere stato escluso dal tetto dell'array prima ancora di arrivare al
filtro, non scartato da un giudizio sbagliato. Il criterio del filtro non
è quindi verificabile su questo caso specifico in questa corsa - il
problema più probabile è a monte, nell'estrazione grezza, non nel filtro
che questa patch corregge. Non affrontato qui.

40 test verdi.

**v1.16 (2026-08-25)** - patch alla v1.15. Il filtro pre-classificazione
(contratto 1.14) passa da una chiamata per BLOCCO a una chiamata per
UNITA'. Misurato dal vivo (atto reale di prova, blocco 5): le stesse 5 unità
quasi identiche, classificate insieme in una chiamata batch, hanno
ricevuto 4 verdetti diversi (2 tenute, 3 motivi di scarto diversi); le
stesse 5, classificate una alla volta con lo STESSO contesto di blocco
(nessuna informazione tolta), hanno ricevuto lo stesso verdetto 5 volte
su 5. La causa dell'incoerenza non era il contesto mancante - c'era in
entrambe le condizioni - ma la presenza di candidati simili nella stessa
chiamata: un giudizio batch su materiale che può contenere
quasi-duplicati degrada per costruzione.

Principio architetturale registrato nel codice
(`estrazione_atto._filtra_unita_argomentative`): vale per qualunque
futuro passo di classificazione batch su materiale non garantito
distinto, non solo per questo filtro - inclusa un'eventuale verifica di
pertinenza sui segmenti, se mai costruita in forma batch.

Costo: ~1 chiamata breve vincolata (`n_predict=64`) per candidato invece
di una per blocco - più chiamate, ciascuna più economica. Fail-open
spostato dal blocco alla singola unità: un fallimento isolato non butta
più via l'intero blocco.

**Scoperta collaterale nella stessa indagine, documentata in
`DEPLOY.md`, non nel contratto**: il residuo non è solo nel filtro. Una
sonda dedicata (`PROMPT_ECCEZIONI` sul blocco 4, stesso seed, stesso
testo) ha mostrato che tre chiamate di fila sullo STESSO processo
server non danno lo stesso risultato, mentre tre chiamate con un riavvio
del server fra l'una e l'altra sì, identiche byte per byte. Il `seed`
controlla il campionamento, non uno stato che il processo server
accumula fra richieste. Nessuna correzione nel codice di questo
progetto - è una proprietà del server, registrata perché le misure di
riproducibilità future la devono conoscere: un confronto A/B pulito
richiede un riavvio del server subito prima, non un processo già usato
per altro.

40 test verdi (nessun nuovo test: la riscrittura del filtro non cambia
la forma dei dati, solo come vengono ottenuti).

**v1.15 (2026-08-24)** - patch alla v1.14, stesso giorno. Due correzioni,
entrambe trovate dalla revisione umana dei 33 candidati della v1.14 (23
scartati, letti uno per uno), non da una misura automatica.

**1. Polarita' invertita nel filtro (e nel vocabolario di Fase 1).** Il
tool e' ex parte creditoris: l'atto in input e' quello del DEBITORE, le
sue argomentazioni sono il bersaglio della confutazione. Il filtro 1.14
usava "controparte" per indicare l'autore dell'atto (il debitore) e
"propria parte" per l'altra - ma nell'atto stesso "controparte" e' la
parola con cui il DEBITORE designa la BANCA, perche' e' lui a scrivere.
Il modello ha adottato il significato del testo, non quello del tool:
sulla revisione reale ha scartato come "propria parte" 8 bersagli veri
(le eccezioni del debitore) e tenuto 2 tesi della banca riportate dal
debitore, cioe' del cliente del tool.

Censimento (solo testo che il modello legge davvero - i nomi/descrizioni
dello schema JSON sono grammatica GBNF, non raggiungono il modello):
`PROMPT_FILTRO_UNITA` conteneva "controparte"/"propria parte" 6 volte;
`PROMPT_CITAZIONI` una volta ("la controparte invoca la norma");
`PROMPT_ECCEZIONI` zero volte in lettera, ma con lo stesso difetto nella
sostanza - "estrai le eccezioni sollevate dalla parte" non ancora mai chi
sia "la parte", zero segnale su chi sta parlando.

Vocabolario sostituito ovunque in Fase 1 con ruoli ancorati all'ATTO, non
alle parti processuali: "autore dell'atto" (chi lo ha scritto) e "parte
avversa all'autore" (contro chi e' scritto). Enum del filtro:
`tesi_dell_autore` (tenuta), `tesi_riportata_dell_avversa` (scartata,
prima si chiamava `affermazione_propria_parte` con polarita' opposta),
`rinvio_senza_contenuto`, `formula_di_rito`. E' Python, mai il modello, a
mappare questi ruoli sulle parti processuali vere (creditore/debitore) a
valle - il modello non deve mai sapere per chi lavora il tool.

**2. Un'unita' non ancorata non deve mai diventare un'eccezione.** La
"scoperta collaterale" lasciata aperta dalla 1.14 (5 copie quasi identiche
nel blocco 1, il filtro le classificava in modo incoerente fra loro) aveva
una causa comune con l'incidente del punto 1: tutte e 5 le copie erano
`ancora.stato == "non_ancorata"` - il passaggio non esiste nell'atto, e'
puramente fabbricato dal modello. Il filtro semantico giudica il
CONTENUTO di una frase, non la sua ESISTENZA: ne ha tenuta una copia
(diventata l'eccezione X01, classificata e pronta per l'argomentazione in
Fase 2/3) mentre le altre 4 finivano disperse fra tre motivi di scarto
diversi - non rumore del filtro, ma lo stesso fatto inesistente giudicato
5 volte separatamente sul suo contenuto invece che sulla sua esistenza.

Nuovo controllo Python **18** (`_scarta_non_ancorate`,
`estrazione_atto.py`): gira PRIMA del filtro semantico (contratto 1.14),
non dopo - un'unita' con `ancora.stato == "non_ancorata"` va in
`unita_scartate` con `motivo: "non_ancorata"` e non arriva mai a
`_filtra_unita_argomentative`. Richiede l'ancoraggio (`localizza.py`)
dentro `estrazione_atto.py`, per blocco, prima dell'assemblaggio - non
piu' solo in `fase1_assembla.assembla()` a valle: le due chiamate restano
indipendenti (l'ancora finale registrata nel contratto resta quella
calcolata da `assembla()`), il controllo qui serve solo a decidere se
un'unita' sopravvive fino a diventare un'eccezione. Un secondo controllo
Python (18 bis, invariante di sicurezza in `confine_fase1`) verifica che
nessuna eccezione nel file finale abbia `ancora.stato == "non_ancorata"` -
rete di sicurezza sul filtro, non un meccanismo alternativo.

- **`unita_scartate[].motivo`**: aggiunto `"non_ancorata"`,
  `"affermazione_propria_parte"` rinominato `"tesi_riportata_dell_avversa"`
  (stesso significato semantico attuale - la polarita' sbagliata del 1.14
  e' quella che questa patch corregge, il valore vecchio non torna
  utilizzabile).
- **`unita_scartate[].dettaglio`** (nuovo campo, nullable, sempre
  presente): il motivo di `localizza.py` quando `motivo: "non_ancorata"`
  (es. "nessuna finestra con similarita' >= 0.80"); `null` per gli altri
  motivi, che vengono dal filtro semantico, non da un fallimento di
  ancoraggio - stesso principio di trasparenza diagnostica gia' applicato
  ad `autoverifica_anomalie`.

**Non affrontato in questa patch** (dipendente dalla polarita' corretta,
non verificabile prima): quasi-duplicati per contenimento sul materiale
gia' filtrato, eventuale troncamento del blocco 4 (12 candidati contro
`maxItems: 15`, mai osservato al limite ma vicino), revisione dei motivi
di scarto residui - tutte misure rimandate a dopo un run con la polarita'
giusta, per non misurare un difetto già corretto.

**v1.14 (2026-08-24)** - patch alla v1.13, stesso giorno. Filtro
pre-classificazione: Fase 1 estrava come "eccezioni" anche materiale che
non lo e' - misurato su piu' run reali dell'atto reale di prova, non solo
supposto: rinvii senza contenuto ("si contestano tutte le eccezioni di
cui sopra"), formule di rito/chiusura ("con vittoria di spese", "salvo
ogni altro diritto e azione"), e affermazioni della parte che ha redatto
l'atto processato (una confutazione scambiata per un'eccezione della
controparte).

Nuovo passo, PRIMA della classificazione in famiglia (non dopo - una
frase senza contenuto proprio non deve mai arrivare a
`classifica_famiglia`, che a valle si troverebbe a dover inventare una
famiglia per materiale che non e' un'eccezione): una chiamata LLM per
blocco, GBNF-vincolata a un enum chiuso a 4 valori
(`affermazione_controparte`, `rinvio_senza_contenuto`, `formula_di_rito`,
`affermazione_propria_parte`), non un'euristica su pattern - lo stesso
principio appena misurato per la classificazione in famiglia: un giudizio
che richiede leggere la frase nel suo contesto non e' un pattern di
superficie.

- Nuovo campo **`unita_scartate`** (array di `{testo, motivo,
  blocco_origine}`, sempre presente anche vuoto): le frasi scartate non
  spariscono mai, cosi' si puo' verificare che il filtro non stia
  buttando via materiale buono. Anche riassunte in `buchi` per la
  memoria di analisi.
- **Fail OPEN**, non chiuso: se la chiamata del filtro fallisce
  (`RispostaTroncata`), TUTTE le eccezioni grezze del blocco passano
  senza filtro - lo stesso principio del 1.13 (un passo diagnostico non
  deve poter cancellare materiale quando non riesce a esprimersi).
- Schema costruito a runtime con `minItems == maxItems` pari al numero di
  frasi del blocco: la corrispondenza posizionale risposta/domanda e'
  imposta dalla grammatica, non affidata al modello che riconta bene - e
  un disallineamento di lunghezza (che non dovrebbe poter accadere) fa
  degradare quel blocco a "filtro non applicato", mai a un abbinamento
  sbagliato.

**Scoperta collaterale, non ancora affrontata**: la prima corsa reale col
filtro attivo (atto reale di prova) ha mostrato che il blocco 1 estrae **5
copie quasi identiche della stessa frase** come eccezioni separate - un
difetto di ripetizione degenere della passata di estrazione stessa
(`PROMPT_ECCEZIONI`/`SCHEMA_ECCEZIONI`), non del filtro ne' del filtro
che le classifica in modo incoerente fra loro. Il filtro le tratta come
elementi indipendenti (corretto, non le deduplica) - il che le rende
visibili per la prima volta in `unita_scartate`, dove prima la
deduplicazione per stringa esatta (`testi_eccezioni_visti`) le
nascondeva silenziosamente collassandole a un'unica voce quando
sopravvivevano tutte. Non corretto in questa patch: e' un problema a
monte del filtro, non introdotto da esso.

39 test verdi (37 + 2 nuovi: filtro scarta e dichiara; filtro fail-open).

**v1.13 (2026-08-24)** - patch alla v1.12, stesso giorno. Due correzioni
indipendenti, decise insieme dopo aver misurato entrambe le cause (non
corrette a discrezione): il crash ricorrente dell'autoverifica di Fase 1,
e la classificazione sbagliata a monte della riformulazione.

**1. Il prefisso di blocco non e' piu' concatenato nel testo.**
`autoverifica.eccezioni_mancanti_nella_prima_estrazione` cambia forma: da
array di stringhe con un `"[blocco N] "` concatenato dopo la generazione,
ad array di oggetti `{testo, blocco_origine}` - `blocco_origine` e' un
intero, mai emesso dal modello, aggiunto da Python come metadato separato.
Misurato: il testo grezzo del modello arrivava esattamente al maxLength di
generazione (300 caratteri, il tetto stesso - il modello si fermava li'
perche' la grammatica non gli permetteva altro), e il prefisso lo portava
a 311 in validazione finale, un tetto che la generazione aveva rispettato
e la validazione ricontrollava su un testo diverso. Separare i due campi
fa si' che generazione e validazione finale misurino la STESSA cosa.

**2. Un campo diagnostico non deve mai poter uccidere l'estrazione**
(principio architetturale, non solo il fix del punto 1). Nuovo campo
`EsitoEstrazione.autoverifica_anomalie`: ogni voce di autoverifica
(`eccezioni_confermate` ED `eccezioni_mancanti_nella_prima_estrazione`)
viene ricontrollata in Python contro lo stesso vincolo di lunghezza prima
di entrare nel file - una violazione scarta la voce, registra il perche'
qui (surfaced in `buchi`), e la Fase 1 completa comunque. Ridondante con
la grammatica per costruzione (che gia' impedisce la violazione in
generazione) - la ridondanza e' voluta: e' esattamente cosi' che si e'
trovato il bug del punto 1, un vincolo rispettato in generazione e violato
da un passaggio Python successivo. La prossima volta che succede, non
uccide piu' la corsa.

**3. Riformulazione: il testo dell'eccezione e' la fonte primaria, la
famiglia un suggerimento.** Causa vera della degradazione misurata (non
il budget di generazione, gia' verificato innocente): `classifica_famiglia`
(euristica dichiarata debole) marcava eccezioni di usura/tasso
indeterminabile come `prescrizione`, e il prompt anteponeva la
descrizione della famiglia (sbagliata) al testo vero senza distinguerne
il ruolo - il modello seguiva il contesto iniettato invece del testo.
Sintomo terminale misurato: due eccezioni su materie diverse (una
generica, una sulla periodicita' del calcolo interessi) producevano query
riformulate byte-identiche. Corretto senza toccare `classificazione.py`
(deciso insieme: prima misurare l'entita' dell'errore - 10/14 eccezioni
misclassificate su un campione reale, vedi analisi in sessione):
  - il prompt di riformulazione ora presenta il testo dell'eccezione come
    fonte primaria e la descrizione di famiglia (quando classificata) come
    "suggerimento secondario... usalo solo se conferma il testo" - SISTEMA_RIFORMULAZIONE
    istruisce esplicitamente a ignorare il suggerimento se contraddice il testo;
  - se la famiglia non e' classificata (incluso il caso dichiarato
    `non_riconosciuta` dal modello), nessun contesto viene iniettato -
    comportamento gia' esistente (`descrizione(None)` era gia' vuota),
    reso esplicito;
  - nuovo controllo: due eccezioni distinte con query riformulata
    IDENTICA sono un errore, non una coincidenza - rilevato, registrato,
    e la query della seconda ricade sul solo `testo_letterale` invece di
    rilanciare la generazione;
  - `n_predict` 80→150: non per il troncamento (mai avvenuto con lo
    schema vincolato) ma per dare margine alla deliberazione fra testo e
    suggerimento, che ora avviene dentro gli stessi token della risposta
    (nessun blocco `<think>` separato con ragionamento spento).

Verificato sulle stesse 14 eccezioni reali: X11/X12 (prima
byte-identiche) ora distinte e specifiche al proprio testo; le tre
eccezioni di usura (prima tutte "prescrizione credito, decorrenza
termine...") ora menzionano tasso/antiusura/108-1996 - anche se la
FAMIGLIA resta ancora sbagliata (`classificazione.py` non toccato per
scelta), la QUERY non la segue piu' ciecamente.

35→37 test verdi (due nuovi: voce di autoverifica anomala non ferma la
corsa; blocco_origine separato dal testo).

**v1.12 (2026-08-24)** - patch alla v1.11, stesso giorno. Chiude la
non-riproducibilità di Fase 1 aperta nel deploy GPU: tre corse identiche
(stesso atto, stesso seed NOMINALE) avevano prodotto 29, 15 e 14
eccezioni. Censiti tutti i punti della pipeline che chiamano il modello -
la causa non era nel batching del server (già sospettato e verificato
innocente): **il seed non arrivava mai al modello**, in NESSUNA delle
chiamate. `esecuzione['seed']` veniva calcolato, loggato in console,
mostrato nell'id di corsa - ma `estrazione_atto.py`, `constrained_decoding.py`
(quindi ogni chiamata di Fase 3, FATTO e coerenza) e la riformulazione
del passo 1-bis chiamavano il modello senza passarlo. Non un bug isolato:
un parametro assente ovunque tranne che al livello più basso
(`llama_server_client.completa`/`completa_json`, che lo accettava e
inoltrava correttamente da sempre).

1. **`seed` propagato in ogni funzione di generazione** della pipeline:
   `estrai_atto`/`estrai_atto_segmentato`/`_passata`/`_passata_diretta`
   (Fase 1), `genera_vincolato`/`genera_con_schema` (Fase 3, FATTO,
   coerenza), `riformula_query_di_ricerca` (passo 1-bis). Verificato:
   tre corse di Fase 1 con il fix, stesso seed, producono un esito
   **identico byte per byte** (stesso crash, stesso blocco, stessa
   stringa esatta) - non solo lo stesso conteggio.
2. **`meta.esecuzione.server`** (nuovo campo obbligatorio):
   `{total_slots, build_info}`, letti da `/props`. La configurazione del
   server è un fattore di riproducibilità quanto il modello - registrarla
   solo a posteriori (dopo aver già sospettato e scagionato il batching)
   sarebbe stato tardi la prossima volta.
3. **`-np 1 --no-cont-batching` promossa a configurazione di riferimento**
   in DEPLOY.md e `esegui_locale_llamaserver.py`: non era la causa della
   non-riproducibilità misurata, ma resta la scelta giusta per lo stesso
   principio - un solo slot esclude per costruzione le interazioni fra
   richieste concorrenti, invece di fidarsi che non ce ne siano. Motivata
   esplicitamente: su macchina mono-utente il determinismo vale più del
   throughput.
4. **`temperature_per_passo.fatto`** aggiunta: esisteva già come
   temperatura reale (il default di `genera_con_schema`, 0.7, mai passato
   esplicitamente da `_sezione_fatto`) ma non come voce registrata - ogni
   altro passo la registrava, questo no.

**Bug trovato e NON corretto in questo giro** (deciso insieme, non a
discrezione): l'autoverifica di Fase 1 può generare un campo che, dopo
un'aggiunta di prefisso (`"[blocco N] "`) fatta da Python DOPO la
generazione vincolata da schema, supera il `maxLength` che lo stesso
schema impone in validazione finale - la stringa grezza del modello è
vincolata correttamente (300 caratteri esatti, il tetto), ma il prefisso
la porta a 311. Misurato deterministico sull'atto reale di prova con il seed
ora corretto: crasha sempre sullo stesso blocco, con la stessa stringa.
Tetto, contenuto e opzioni di correzione documentati, decisione aperta.

**v1.11 (2026-08-24)** - patch alla v1.10, decisa dopo il primo crash reale
della catena completa su GPU: il modello si e' astenuto sulla sezione FATTO
per un dossier con una sola fonte `fatti_di_causa` (sintetica, di
validazione), e `redigi_atto` ha trattato l'astensione come un
`RuntimeError` fatale - perdendo anche i 4 motivi gia' generati prima del
crash, mai scritti su disco. Due correzioni distinte, non una sola:

1. **L'astensione sul FATTO e' un esito di prima classe** (come per i
   motivi dal contratto 1.2), non piu' un guasto. `fatto` cambia forma:
   da `{paragrafi}` a `{esito, paragrafi, dichiarazione_astensione,
   motivo_errore}`, ristretto a tre stati (`trattata`, `astensione_modello`,
   `errore_tecnico` - niente `astensione_dossier` ne' `eccezione_fondata`,
   il FATTO non ha un motore di regole a monte che possa deciderle prima
   della chiamata). L'atto si produce comunque, completo di tutti i
   motivi; l'uscita dell'entry point diventa **2** (STOP_ASTENSIONI), non
   0 e non 1 - il sistema ha funzionato, non ha potuto scrivere i fatti.
   Un troncamento (`RispostaTroncata`) sul FATTO segue la stessa gestione
   gia' in uso per i motivi: `errore_tecnico`, MAI confuso con
   l'astensione - e' la distinzione che questa patch introduce per il
   FATTO, non quella che cancella.
2. **`redigi_atto` non perde piu' il lavoro fatto**: un'eccezione
   imprevista (non `RispostaTroncata`, gia' gestita per-esito) dopo che
   almeno una chiamata e' andata a buon fine solleva
   `GenerazioneFase3Parziale`, che porta con se' i motivi completati - i
   mancanti riempiti con un placeholder `errore_tecnico` esplicito, cosi'
   l'array resta lungo quanto `dossier['esiti']` (controllo 5). L'entry
   point la intercetta, scrive `03_atto_parziale.json` (nome distinto da
   `03_atto.json`: non e' garantito conforme allo schema finale - niente
   `affermazioni`, coerenza mai tentata) e la memoria, poi rilancia come
   `ErroreTecnico` - resta un guasto, uscita 1, ma le chiamate GPU gia'
   pagate non sono piu' silenziosamente perse.

Nessun controllo Python nuovo: `controllo_04_condizionali` esteso a
verificare la stessa coerenza esito/dichiarazione_astensione/motivo_errore
gia' imposta sui motivi, ora anche su `fatto`.

**v1.10 (2026-08-23)** - patch alla v1.9, stesso giorno, decisa prima di
riprendere il deploy: rapidfuzz passa da "alternativa equivalente e piu'
veloce" a **motore di riferimento**. Lo scarto di 0.0072 misurato in 1.8 e'
piu' grande del margine che separava alcuni casi reali dalla soglia (la
corsa reale di prova aveva una citazione ferma esattamente a 0.9500, changelog
1.4): un motore diverso puo' ribaltare uno stato di ancoraggio, e la
tolleranza dichiarata in 1.8 registra la divergenza senza impedirne
l'effetto.

1. **rapidfuzz obbligatorio**: `esegui_pipeline.main()` stampa un avviso
   esplicito e incondizionato (non soppresso da `--silenzioso`) se assente,
   prima di procedere con difflib.
2. **Documentata l'asimmetria** nella sezione "Localizzazione della
   citazione" → "Motore di similarita'": rapidfuzz (Indel/LCS, ottimo) e
   difflib (Ratcliff/Obershelp, euristica greedy) non sono lo stesso
   algoritmo. I commenti in `localizza.py` che li descrivevano come
   "equivalenti" (nel codice, in `DEPLOY.md`, in `requirements.txt`) sono
   corretti per dire cosa sono davvero: un riferimento e un fallback
   degradato, non due strade equivalenti.
3. **`meta.esecuzione.motore_similarita` (dalla 1.8) resta il marcatore**:
   nessun campo nuovo aggiunto in questa patch, la 1.10 e' un cambio di
   *significato dichiarato*, non di schema.

**v1.9 (2026-08-23)** - patch alla v1.8, stesso giorno. Nasce dalla
verifica, richiesta prima del deploy, che l'accorpamento (contratto 1.7)
confuti DAVVERO tutte le eccezioni che fonde, non solo la prima: sull'atto
atto-prova l'accorpamento porta 8 eccezioni a 2 esiti e la Fase 3 da 7
chiamate a 1, ma nulla verificava che quell'una chiamata rispondesse a
tutte e 7 le affermazioni della controparte invece che a una sola.

1. **Controllo Python n. 17** (vedi la sezione dedicata): ogni estratto F01
   di un esito accorpato deve comparire in almeno un'ancora del motivo
   corrispondente. Diagnostico come il controllo 14, non bloccante.
2. **Il finto (`test_integrazione_mockata.LlmFinto`) era la prova che
   mancava**: prima di questa verifica, `_confutazione_finta` generava
   SEMPRE un solo paragrafo con una sola ancora [FONTE] e ZERO ancore F01 -
   per qualunque esito, accorpato o no. La suite "verde" non dimostrava
   nulla sulla copertura degli accorpamenti perche' il finto non citava mai
   nessun F01, nemmeno nel caso non accorpato. Corretto: per un esito con
   piu' di un F01 disponibile, il finto ora genera un paragrafo per
   ciascuno - cosi' la suite e' una prova del controllo 17, non un modo per
   aggirarlo.
3. **Prompt di Fase 3 esplicito sull'accorpamento**: quando
   `eccezioni_accorpate` ha piu' di un elemento, `_prompt_per_eccezione`
   elenca ora ogni estratto F01 separatamente con il proprio id e istruisce
   il modello a confutarli tutti, non solo il primo. Prima l'unico segnale
   che il motivo accorpava piu' eccezioni era la lista `estratti_citabili`
   senza alcuna istruzione a trattarle come affermazioni distinte.
4. **Nessuna prova empirica sul run reale**: non esiste un artefatto
   salvato della Fase 3 reale sull'atto reale di prova con accorpamento (il file
   piu' vicino, `redazione_reale_risultati.json`, precede la Fase 3 ed e'
   privo di `motivi`) - la verifica sopra e' sul finto e sui controlli
   Python, non su un'uscita reale del modello. La prima corsa reale post-
   deploy (DEPLOY.md sezione 6.7) e' la prima occasione per misurarlo su
   dati veri, e va guardata con questo in mente: se `03_atto.json` riporta
   una nota del controllo 17, il motivo accorpato non ha confutato tutto.

**v1.8 (2026-08-23)** - patch alla v1.7. Nasce dalla verifica, richiesta
prima del deploy su macchina nuova, di quale motore avesse prodotto i
punteggi su cui sono tarate le soglie 0.95/0.80 di `localizza.py`: rapidfuzz
era installato nel Python di sistema ma non nel venv della corsa precedente,
quindi non era certo quale dei due avesse generato i numeri.

1. **`meta.esecuzione.motore_similarita`** (`"rapidfuzz"` | `"difflib"`),
   nuovo campo obbligatorio, identico nei tre schemi di file. Registra quale
   implementazione ha calcolato i rapporti di similarita' in QUESTA corsa -
   senza il campo un ancoraggio non e' riproducibile ne' confrontabile fra
   macchine con dipendenze diverse.
2. **Le due implementazioni NON sono lo stesso algoritmo**, misurato non
   supposto: rilanciando l'ancoraggio completo delle 10 citazioni vere
   dell'atto reale di prova con entrambe, 9/10 concordano esattamente (match
   esatto o normalizzato, nessun calcolo di similarita' coinvolto) e 1/10
   passa dal fuzzy match, dove rapidfuzz (Indel/LCS, ottimo) e difflib
   (Ratcliff/Obershelp, euristica greedy) danno 0.8986 contro 0.8913 sulla
   STESSA finestra di testo - 0.0072 di scarto, non rumore numerico. Lo
   STATO risultante (`ancora_parziale`) non cambia in questo caso: nessuna
   delle due soglie di contratto viene attraversata. Il test sintetico
   preesistente (`test_difflib_e_rapidfuzz_danno_lo_stesso_rapporto`, che
   asserisce <1e-9) resta valido SOLO per il pattern di corruzione che
   verifica (sostituzioni singole su una stringa base fissa): non e' una
   prova di identita' generale, e il suo docstring e' stato corretto per
   dirlo.
3. **Nuovo test `test_motori_di_similarita_concordano_su_citazioni_reali`**
   in `test_versioni_contratti.py`: rilancia le 10 citazioni reali con
   entrambi i motori e fallisce (non skip, salvo rapidfuzz assente
   dall'ambiente) se lo STATO diverge o se lo scarto di similarita' supera
   una tolleranza DICHIARATA di 0.01 - sopra il valore peggiore misurato
   (0.0072), non un numero scelto per far passare il test.
4. **Le 40 query di calibrazione della soglia 0.8560 non sono coinvolte**:
   quella soglia e' sulla similarita' coseno degli embedding
   (`sentence_transformers`, indice segmenti), calcolata in `store.py` senza
   difflib ne' rapidfuzz. Confonderla con le soglie di ancoraggio era
   un'assunzione della richiesta di verifica, non un fatto del codice - la
   sua validita' si controlla con le 3 query di DEPLOY.md sezione 6.4, non
   con questo changelog.

*(Nota: questo changelog non ha voci per v1.6 e v1.7. Non e' un buco di
disciplina - e' una perdita: fino al deploy del 2026-08-23 il progetto non
era sotto controllo di versione (nessun `.git`), quindi non esiste una
cronologia da cui ricostruire cosa cambio' fra 1.5 e 1.7, ne' chi lo
decise ne' perche'. Colmarla a memoria o a supposizione sarebbe
inventare una motivazione per un cambio reale del contratto - peggio di
un buco dichiarato. Resta persa. Da qui in avanti non puo' piu' succedere:
il repository e' inizializzato in git dal commit di questo deploy, e ogni
bump di contratto da ora in poi e' un commit.)*

**v1.5 (2026-08-20)** - patch alla v1.4 dello stesso giorno. Chiude il
buco per cui il retrieval restituiva sempre i top-k anche quando il corpus
non conteneva la materia, e separa cio' che il modello puo' LEGGERE da cio'
che il contratto garantisce come LETTERALE.

1. **Criterio di rilevanza, DIVERSO PER INDICE** (vedi la sezione
   dedicata). L'astensione esisteva nell'architettura ma non aveva un
   criterio che scattasse per irrilevanza: cinque segmenti sulle
   fideiussioni a ~0.84 per una query sulla revoca di affidamento
   sarebbero entrati negli `estratti_citabili` come qualunque altra fonte.
2. **Soglia come PARAMETRO, non costante**: `--soglia-segmenti`, default
   0.8560, e il valore effettivo finisce in
   `meta.esecuzione.soglia_segmenti`. Due corse con soglie diverse
   producono dossier diversi a parita' di tutto il resto: senza il campo
   la differenza sarebbe inspiegabile.
3. **Quote separate per indice**, mai un ordinamento unico:
   `fonti[].provenienza` acquisisce `retrieval_segmenti`. Default 4
   dall'indice principale + 2 dai segmenti. Se i segmenti non superano la
   soglia la quota resta VUOTA - non si riempie col principale.
4. **Materiale di prompt contro ancora citabile.** `estratti[].parziale`
   (booleano) e `estratti_citabili[].provenienza:
   "atto_controparte_parziale"`. Un'eccezione con ancora
   `ancora_parziale` produce comunque il suo estratto su F01 - il ritaglio
   della migliore finestra - che entra nel prompt ma NON puo' essere
   ancora di nessuna affermazione: **controllo Python n. 16**. Sull'atto
   atto-prova era un motivo confutabile su quattro ad argomentare senza
   avere davanti le parole della controparte.
5. **Controllo n. 15**: `stato_verifica` e `motivazione_certa` bloccano la
   citazione automatica. Erano nel grafo e non li leggeva nessuno.

**v1.4 (2026-08-20)** - patch alla v1.3 dello stesso giorno. Nasce da una
MISURA sulla corsa reale di prova, non da un'ipotesi: sulle 10 eccezioni
davvero estratte, i match esatti erano 1 su 10 e otto ancore su nove
passavano per il fuzzy, una a `0.9500` esatto.

1. **Spoglio della citazione, ASIMMETRICO** (vedi la sezione dedicata,
   che e' normativa). Il modello confeziona il `testo_letterale`: 10/10
   racchiusi fra virgolette, 4/10 troncati con dei puntini. Quei 2-4
   caratteri ai bordi bastavano a far scendere un match altrimenti
   perfetto a 0.95-0.98. Spogliandoli, i match esatti/normalizzati
   passano da 1/10 a 9/10. La distribuzione degli esiti NON cambia -
   cambia che nove ancore diventano deterministiche invece di dipendere
   da una soglia.
2. **Istruzione nel prompt di Fase 1** (non incapsulare, non troncare) E
   spoglio nella procedura: i due insieme, non uno dei due. Il prompt da
   solo non basta su un modello piccolo; lo spoglio da solo lascia il
   modello libero di degradare in forme che nessuno spoglio recupera
   (parafrasi, riassunti).
3. **Ellissi INTERNA -> `ancora_parziale` per progetto.** Una citazione
   con un'omissione centrale (`"testo A ... testo B"`) non e' un
   intervallo unico dell'atto: forzarla ad `ancorata` produrrebbe una
   tripla che copre anche il testo che la citazione dichiara di aver
   saltato. Rilevata, mai spogliata, con un motivo dedicato. Ancorare per
   segmenti sarebbe possibile: scope non aperto.
4. **Deduplicazione per CONTENIMENTO** in Fase 1. Quella esistente e' per
   stringa esatta e non vede i troncamenti: sulla corsa reale, 10
   eccezioni di cui 8 distinte (due erano la versione troncata di altre
   due), cioe' due esiti doppi in Fase 2 e due chiamate LLM sprecate in
   Fase 3. Si confronta sulla forma spogliata e normalizzata, si tiene la
   piu' lunga, ogni scarto finisce in `buchi`.
5. **`famiglia_probabile` acquisisce `minLength: 1`.** Sulla corsa reale
   il modello ne ha emesse 10 vuote su 10: `required` piu' `maxLength`
   accettano la stringa vuota, e l'euristica di classificazione - che
   legge quel campo piu' il testo letterale - riconosceva 4 famiglie su
   10. Una stringa vuota li' non e' un dato, e' un campo non compilato.

**v1.3 (2026-08-20)** - patch alla v1.2 dello stesso giorno. Chiude il
retrieval globale e porta la riformulazione della query al livello a cui
serve davvero. `versione_contratto` bumpata a "1.3" nei tre schemi di
file: i dossier 1.2 non validano piu' (`meta` ha cambiato forma).

1. **Retrieval globale RIMOSSO dal dossier.** `fonti[].provenienza` perde
   il valore `retrieval_globale`. Un retrieval calibrato su
   obiettivo+fatti della causa non aveva un consumatore legittimo: la
   sezione FATTO di un atto italiano e' NARRATIVA - l'argomentazione in
   diritto sta nei motivi - quindi si ancora a F00/F01 e non cita fonti
   di grafo; e usarlo per completare gli estratti di un motivo era gia'
   vietato dalla 1.2 come rischio "fonte topicamente vicina ma
   sbagliata". Restava una categoria di fonti registrate che nessuno
   poteva citare.
   Quei risultati NON sono buttati: finiscono nella memoria di analisi,
   sezione "Spunti non citati", con il punteggio di similarita'. Sono
   piste di ricerca per l'avvocato, non materiale per il modello - non
   attraversano mai il confine LLM e non compaiono in nessuno schema.
2. **Passo 1-bis per-eccezione.** Conseguenza diretta del punto 1, e di
   un problema che il punto 1 ha fatto emergere: se il retrieval
   per-eccezione usa il `testo_letterale` GREZZO come query di embedding,
   si ripresenta il difetto di recall documentato (stesso articolo, rank
   759 -> rank 4 riformulando) - che e' la ragione per cui la
   riformulazione esiste. Usarla per la query di causa e non per quella
   di eccezione avrebbe messo la riformulazione dove serviva meno.
   Il passo 1-bis resta dell'ORCHESTRATORE (e' una chiamata LLM, la Fase
   2 e' Python puro) ma produce UNA query per eccezione, a partire dal
   `testo_letterale` piu' la descrizione della famiglia assegnata.
   `meta.query_di_ricerca` diventa una mappa
   `{eccezione_id: {originale, riformulata}}`.
   Costo: N chiamate LLM brevi invece di una. Accettato: sono prompt
   corti, e la qualita' del retrieval e' il punto fragile dell'intera
   pipeline su un modello piccolo. Da rivalutare col batching in una
   chiamata sola se la misura reale dice che il costo e' fuori scala.

**v1.2 (2026-08-20)** - patch alla v1.1 dello stesso giorno. Chiude il
percorso di ingresso della Fase 3, separa il guasto dall'astensione e
allinea il contratto all'orchestratore reale. `versione_contratto`
bumpata a "1.2" in tutti gli schemi di file: i dossier 1.1 non validano
piu' (voluto, `esiti[].estratti_citabili` ha cambiato forma).

1. **Passaggio fra le fasi per CHIAMATA DI FUNZIONE**, non scrivendo e
   rileggendo file. L'ultimo paragrafo della 1.1 diceva il contrario:
   descriveva il comportamento degli script di test di allora, non un
   requisito, ed e' stato riscritto. I file `01_`/`02_`/`03_` restano
   come artefatti di ispezione - nessun passo della catena li rilegge.
2. **Riformulazione della query = passo 1-bis dell'orchestratore.** La
   1.1 chiedeva alla Fase 2 di "riformulare query da obiettivo+fatti"
   pur dichiarandola "solo Python, zero LLM": era una contraddizione
   interna. La riformulazione (una chiamata LLM) sta ora fra Fase 1 e
   Fase 2; la Fase 2 riceve `query_di_ricerca` come DATO e resta pura.
   `meta.query_originale` e `meta.query_di_ricerca_usata` la registrano
   nel dossier: senza, un dossier non e' riproducibile a mesi di
   distanza.
3. **`conclusioni_avvocato` nel dossier** (obbligatorio, non vuoto),
   popolato dalla Fase 2 a partire da un argomento obbligatorio della
   riga di comando. La Fase 3 continua ad avere UN SOLO ingresso: la
   firma `redigi_atto(base_url, dossier)` resta a due parametri. Nessun
   template di conclusioni esiste nel progetto (vedi la nota su
   `origine` in `fase3_atto.schema.json`).
4. **`estratti_citabili` diventano oggetti** `{estratto_id,
   provenienza}`, provenienza ∈ {`regola`, `retrieval_per_eccezione`,
   `atto_controparte`}. Il completamento fino a 6 usa il retrieval
   PER-ECCEZIONE (query = `testo_letterale`, nessuna riformulazione), mai
   quello globale. L'estratto su F01 che riporta l'eccezione entra
   sempre e NON conta nel tetto di 6. Nuovo controllo Python n. 14: un
   estratto `atto_controparte` non fonda mai un argomento.
   `fonti[].provenienza` spezza `retrieval` in `retrieval_globale` /
   `retrieval_per_eccezione`.
5. **Blocco di riproducibilita' `meta.esecuzione`** nei tre schemi di
   file (identico in tutti e tre, verificato da `validazione.py`):
   `id_esecuzione`, `avviata_il`, `versione_contratti`,
   `sha256_atto_input`, `modello` (nome + sha256 del GGUF), `n_ctx`,
   `seed`, `temperature_per_passo`, `grafo` (percorso + sha256 + n_nodi).
   Senza, due corse non sono confrontabili e un golden set non misura
   niente: una differenza nell'output potrebbe venire dal modello, dal
   seed, dal contesto, dal corpus o dal codice, e non ci sarebbe modo di
   dirlo. Comporta che l'entry point IMPONGA un seed a ogni chiamata -
   senza seed fissato non c'e' riproducibilita' nemmeno a parita' di
   tutto il resto.
6. **Ingressi alternativi da riga di comando** (`--da-estrazione`,
   `--da-dossier`): vedi la sezione "Come i dati passano fra le fasi" -
   NON sono un ritorno alla 1.1.
7. **`errore_tecnico` e' un esito di prima classe**, distinto
   dall'astensione, in `fase2_dossier` (`stato`), in `fase3_atto`
   (`motivi[].esito`) e in `coerenza` (input). Campo `motivo_errore`
   condizionale. Nessuna GBNF cambia: il modello non emette mai questo
   valore, lo assegna Python (vedi sezione "Astensione e guasto").

**v1.1 (2026-08-20)** - patch alla v1.0 dello stesso giorno, tre lacune
chiuse + un controllo. `versione_contratto` bumpata a "1.1" in tutti gli
schemi: i file prodotti con la 1.0 non validano piu' (voluto: la forma
delle norme citate e' cambiata).

1. **Date di vigenza** (predisposizione al grafo versionato, nullable ora):
   - `fase1_estrazione.schema.json`: `citazioni_controparte.norme` da
     stringhe a oggetti `{testo, data_rilevante}` - il modello emette la
     data SOLO se dichiarata esplicitamente nell'atto, mai dedotta.
   - `fase2_dossier.schema.json`: nel registro `fonti` aggiunti
     `data_vigenza` (versione risolta) e `data_criterio_risoluzione`
     (data usata come criterio), entrambi nullable finche' il grafo e'
     mono-versione.
   - `fase3_atto.schema.json`: `affermazioni` acquisisce `data_vigenza`
     (copiata da Python dalla fonte).
   - GBNF impattate: **SOLO `fase1_citazioni.gbnf`** (vedi sezione
     "Date di vigenza" per il perche' le altre no).
2. **Localizzazione della citazione** promossa a parte del contratto:
   procedura, normalizzazione voce per voce, mappa offset, fuzzy con
   soglie motivate, pseudocodice (sezione dedicata). Enum di ancoraggio
   esteso in `fase1_estrazione.schema.json`: `ancorata` (ora anche
   `corrispondenza: "fuzzy"` + `similarita`), `ancora_ambigua` (nuovo,
   match multipli - mai il primo d'ufficio), `ancora_parziale` (nuovo,
   troncamento/parafrasi probabile), `non_ancorata`.
3. **Passata di coerenza d'insieme (Fase 3-bis)**: nuovi
   `coerenza.schema.json` (input+output) e `coerenza.gbnf`;
   `fase3_atto.schema.json` acquisisce la sezione `coerenza`
   (ordine di rendering applicato + conflitti SEGNALATI, mai risolti);
   entry point aggiornato con il passo 3-bis.
4. **Percorso fonti di regola chiuso**: in `fase2_dossier.schema.json`
   l'alternanza `node_id` null/non-null e' ora imposta da `allOf/if/then`
   sul tipo (non solo descritta); descrizione di `fonti` dichiara
   risolvi_fonte come UNICO ingresso; nuovo controllo Python di
   conservazione (n. 12): ogni fonte proposta dal motore finisce nel
   registro O in `fonti_scartate`, nessuna terza via.

Controlli Python aggiunti: 10 (calendario date), 11 (permutazione
coerenza), 12 (conservazione fonti di regola), 13 (nullabilita' node_id).

---

Definiti il 2026-08-20. Tre file JSON, uno per confine di fase, validati con
`jsonschema` a OGNI passaggio - un file non valido ferma la pipeline
rumorosamente, non degrada.

```
atto.pdf
   │  FASE 1 (LLM: 3-4 passate vincolate + arricchimento Python)
   ▼
01_estrazione.json      ← fase1_estrazione.schema.json
   │  passo 1-bis (LLM: una query di ricerca riformulata PER ECCEZIONE)
   │  FASE 2 (SOLO Python: motore_regole + risolvi_fonte + retrieval + taglio estratti)
   ▼
02_dossier.json         ← fase2_dossier.schema.json   (= UNICO ingresso della Fase 3)
   │  FASE 3 (LLM: una chiamata per eccezione "confutabile" + una per il FATTO)
   ▼
03_atto.json            ← fase3_atto.schema.json
   │  FASE 3-bis (LLM: UNA chiamata sui riassunti - ordina i motivi, segnala conflitti)
   │  rendering deterministico + doppio binario (verifica_risposta)
   ▼
03_bozza_atto.txt + 00_memoria_analisi.md
```

## Principi che i contratti codificano

1. **Il modello non emette mai offset ne' id referenziali.** Un ~3B attivi
   non sa calcolare posizioni nel testo: emette solo testo letterale
   (Fase 1) o id opachi presi da un enum generato a runtime (Fase 3).
   Ogni tripla `(fonte_id, inizio, fine)` del contratto finale e' calcolata
   o risolta da Python, deterministicamente.
2. **L'identita' di una fonte e' `fonte_id`/`node_id`, mai
   `citazione_breve`** (la stringa di visualizzazione puo' collidere: due
   massime stesso ufficio/tipo/data). `citazione_breve` serve solo al
   rendering.
3. **L'astensione e' un esito di prima classe**, e non e' un guasto
   (vedi la sezione "Astensione e guasto"). Presente in tre punti:
   - Fase 2: `stato: "astensione"` + `motivo_astensione` quando una regola
     si applica ma nessuna fonte principale si risolve nel grafo (la fonte
     finisce in `fonti_scartate`, tracciata, mai citabile);
   - Fase 3, grammatica: il ramo `astensione` e' un'alternativa strutturale
     che il modello puo' scegliere quando gli estratti non sostengono
     l'argomento;
   - Fase 3, file finale: ogni esito del dossier ha una voce in `motivi`,
     anche le astensioni - mai un'omissione silenziosa.
4. **La Fase 3 non tocca il grafo.** Tutto cio' che puo' citare sta in
   `02_dossier.json`; l'enum della grammatica e' generato dagli
   `estratti_citabili` della singola eccezione. Il vincolo e' fisico
   (il motore GBNF non puo' emettere altro), non disciplinare.

## Date di vigenza (predisposizione al grafo versionato)

Il grafo oggi e' mono-versione; la migrazione prevista rende ogni ricerca
datata ("testo dell'art. X vigente al \<data\>"). I campi temporali esistono
GIA' nei contratti 1.1, nullable; alla migrazione si bumpa a 2.0 rendendo
non-null quelli di Fase 2 - i file 1.1 restano leggibili, nessuno schema,
GBNF o dossier va riaperto.

| Campo | Dove | Chi lo scrive | Nullable 1.1 → 2.0 |
|---|---|---|---|
| `data_rilevante` | Fase 1, per norma citata | **LLM** (solo se dichiarata esplicitamente nell'atto - mai dedotta; "null se non indicata" sta anche nel prompt) | nullable → resta nullable (il modello puo' legittimamente non trovarla) |
| `data_vigenza` | Fase 2, registro `fonti` | Python (risoluzione nel grafo) | nullable → **obbligatoria** per fonti di tipo grafo |
| `data_criterio_risoluzione` | Fase 2, registro `fonti` | Python | nullable → **obbligatoria**; catena dichiarata: 1) `data_rilevante` della citazione, 2) data dei fatti fornita dall'avvocato, 3) data odierna - il gradino usato va detto nella memoria |
| `data_vigenza` | Fase 3, `affermazioni` | Python (copiata dalla fonte) | nullable → obbligatoria per ancore su fonti di grafo |

**Impatto sulle GBNF - esplicito:**

- `fase1_citazioni.gbnf`: **SI'** - le norme diventano oggetti
  `{testo, data_rilevante}`, con `data-o-null ::= "null" | "\"" [0-9]{4} "-" [0-9]{2} "-" [0-9]{2} "\""`.
  La grammatica impone la FORMA, non il calendario ("2026-99-99" passa):
  controllo Python n. 10.
- `fase1_struttura.gbnf`, `fase1_eccezioni.gbnf`: **NO** - nessun campo
  temporale emesso in quelle passate.
- `fase3_confutazione.gbnf`: **NO, per costruzione** - il modello in Fase 3
  emette solo `estratto_id`, che gia' identifica UNA versione precisa della
  fonte nel dossier. Quando il grafo diventa versionato cambia solo la
  risoluzione in Fase 2 (quale versione finisce nel registro); la Fase 3
  non tocca mai date. Questo e' il beneficio degli id opachi: la
  migrazione non attraversa il confine LLM.
- Fase 2: nessuna GBNF esiste (zero chiamate LLM) - i due campi nuovi sono
  affare del solo Python.
- `coerenza.gbnf`: **NO** - lavora su id e riassunti, niente date.

## Localizzazione della citazione nel testo (parte del contratto)

Il modello emette `testo_letterale`, Python lo localizza. Su testo
estratto da PDF il match esatto fallisce per ragioni banali (a capo dentro
la frase, sillabazione, spazi multipli, virgolette tipografiche, legature,
apostrofi): la procedura sotto e' NORMATIVA - cambiarla, incluse le
soglie, e' un bump di versione del contratto, non un refactoring.

### Spoglio della citazione (passo 0, ASIMMETRICO)

**Si applica alla stringa emessa dal MODELLO, mai al testo dell'atto.**
Va letto cosi' e non altrimenti: gli offset di `ancora` si riferiscono al
testo dell'atto, e toccare quel testo sposterebbe ogni posizione
calcolata. NON e' un'ottava voce della normalizzazione qui sotto, che e'
BILATERALE per costruzione: e' un passo **aggiuntivo e precedente**,
su **un lato solo**.

| | applicato a | scopo |
|---|---|---|
| **spoglio** (questa sezione) | SOLO la citazione del modello | togliere il confezionamento che il modello aggiunge |
| **normalizzazione** (sezione seguente) | atto E citazione | rendere confrontabili due testi che dicono la stessa cosa |

Regola: **solo ai BORDI, mai al centro**, iterato finche' stabile (il
modello produce combinazioni come `"...testo..."`, in cui togliere una
virgoletta scopre dei puntini e viceversa):

1. virgolette di ogni tipo, in apertura e chiusura: `" ' “ ” „ ‟ « » ‘ ’ ‚ ‛ \` ´`;
2. ellissi e puntini di sospensione **ai due bordi**: `...` `…` `..`;
3. spazi.

Sul punto 2, la 1.4 legge "ai bordi" alla lettera e toglie l'ellissi
anche in TESTA, non solo in coda. Non e' un'estensione arbitraria: la
testa e' un bordo quanto la coda, e ometterla farebbe danno invece di
lasciare solo sporco - il rilevatore di ellissi interna cerca in tutta la
stringa, quindi un `...` iniziale sopravvissuto verrebbe scambiato per
un'omissione centrale e manderebbe la citazione in `ancora_parziale` per
una ragione falsa.

**Ellissi INTERNA: rilevata, MAI spogliata.** Una citazione con
un'omissione centrale non e' ancorabile come intervallo unico: l'esito e'
`ancora_parziale` PER PROGETTO - non per punteggio, per quanto bene i
pezzi combacino - con un motivo dedicato, e `migliore_candidato`
valorizzato col primo segmento come punto di partenza per la revisione.

### Normalizzazione (nell'ordine, su atto E citazione)

1. Unicode **NFKC** (scioglie le legature: ﬁ→fi, ﬂ→fl, ecc.);
2. virgolette e apostrofi tipografici → dritti (`' ' ʼ ´` → `'`;
   `" " « »` → `"`);
3. trattini tipografici (`– — ‐`) → `-`;
4. **de-sillabazione**: `-` seguito da fine riga (+ eventuali spazi) →
   rimosso, SOLO se preceduto e seguito da lettera minuscola (evita di
   incollare "art. 1832-" + "bis" in modo sbagliato solo dove non e'
   sillabazione);
5. NBSP, tab, newline, spazi multipli → UN singolo spazio;
6. `casefold()`;
7. strip esterno.

### Mappa degli offset (normalizzato → originale)

Costruita durante la normalizzazione, carattere per carattere: per ogni
carattere emesso nell'output normalizzato si registra l'offset del
carattere originale che l'ha generato (`mappa[i]`); i caratteri soppressi
(sillabazione, spazi collassati) non emettono nulla; una run collassata
mappa sul primo carattere della run. Gli offset scritti in `ancora` sono
SEMPRE riferiti al testo originale dell'atto: `inizio = mappa[i]`,
`fine = mappa[j-1] + 1` per un match `[i, j)` nel normalizzato.

### Procedura (pseudocodice normativo)

```
def localizza(testo_atto, blocchi, citazione) -> Ancora:
    # 0. match esatto grezzo, senza normalizzazione
    posizioni = trova_tutte(testo_atto, citazione)
    if len(posizioni) == 1: return Ancorata(pos, corrispondenza="esatta", similarita=None)
    if len(posizioni) >= 2: return AncoraAmbigua(occorrenze=posizioni)

    # 1. match esatto sul normalizzato, offset rimappati
    norm_atto, mappa = normalizza_con_mappa(testo_atto)
    norm_cit, _     = normalizza_con_mappa(citazione)
    posizioni = trova_tutte(norm_atto, norm_cit)
    if len(posizioni) == 1: return Ancorata(rimappa(posizioni[0]), "normalizzata", None)
    if len(posizioni) >= 2: return AncoraAmbigua(occorrenze=rimappa_tutte(posizioni))

    # 2. fuzzy: finestra scorrevole sul normalizzato,
    #    larghezza = len(norm_cit), passo = un confine di parola,
    #    ratio = rapidfuzz Indel.normalized_similarity(norm_cit, finestra)
    #    - rapidfuzz e' IL RIFERIMENTO (dalla 1.10), non un'ottimizzazione
    #    facoltativa: senza, si ricade su
    #    difflib.SequenceMatcher(None, norm_cit, finestra, autojunk=False),
    #    che NON e' lo stesso algoritmo (Ratcliff/Obershelp contro
    #    Indel/LCS) e puo' dare un rapporto diverso sulla STESSA finestra -
    #    vedi "Motore di similarita'" sotto.
    candidati = [(r, i, j) per ogni finestra con r >= 0.80]
    if not candidati: return NonAncorata(motivo="nessuna finestra con similarita' >= 0.80")

    migliore = max(candidati, key=ratio)
    rivali = [c for c in candidati
              if non_sovrapposta(c, migliore) and migliore.r - c.r <= 0.02]
    if rivali: return AncoraAmbigua(occorrenze=rimappa_tutte([migliore] + rivali))

    if migliore.r >= 0.95:
        return Ancorata(rimappa(migliore), corrispondenza="fuzzy", similarita=migliore.r)
    return AncoraParziale(migliore_candidato=rimappa(migliore), similarita=migliore.r,
                          motivo="probabile troncamento o parafrasi del modello")
```

### Soglie (costanti di contratto V1, da tarare sul corpus reale)

- **≥ 0.95 → `ancorata` (fuzzy)**: dopo la normalizzazione il rumore
  residuo legittimo (errori OCR isolati, residui di sillabazione) e'
  locale e raro - una citazione davvero letterale resta sopra 0.95. Sotto,
  l'affermazione "questo e' letteralmente nell'atto" non e' piu' difendibile
  in automatico.
- **0.80 ≤ r < 0.95 → `ancora_parziale`**: quasi certamente lo stesso
  passaggio, ma troncato o leggermente parafrasato dal modello - candidato
  registrato, revisione umana, mai citabile in automatico.
- **< 0.80 → `non_ancorata`**: la pretesa "stesso passaggio" non regge.
- **Δ ≤ 0.02 tra finestre non sovrapposte → `ancora_ambigua`**: due punti
  dell'atto quasi ugualmente plausibili non si risolvono col primo match.

### Motore di similarita' (dalla 1.10: rapidfuzz e' il riferimento)

Le soglie sopra sono numeri assoluti, e un numero assoluto significa
qualcosa solo insieme all'algoritmo che l'ha prodotto. **rapidfuzz
(`Indel.normalized_similarity`) e' il riferimento su cui le soglie
0.95/0.80 sono tarate.** Il fallback `difflib.SequenceMatcher(autojunk=False)`
NON e' un'implementazione equivalente piu' lenta: e' un algoritmo diverso
(Ratcliff/Obershelp, euristica greedy, contro Indel/LCS, ottimo) che puo'
dare un rapporto diverso sulla stessa finestra di testo - misurato: 0.0072
di scarto su una citazione reale dell'atto reale di prova (0.8986 contro
0.8913), abbastanza da spostare un caso vicino a soglia da uno stato di
ancoraggio all'altro (la corsa reale di prova aveva gia' una citazione ferma
esattamente a 0.9500 - vedi changelog 1.4).

Conseguenze normative:

1. **rapidfuzz e' obbligatorio**, non facoltativo. Se assente,
   `esegui_pipeline.main()` stampa un avviso esplicito e incondizionato
   (non soppresso da `--silenzioso`) prima di procedere con difflib.
2. **`meta.esecuzione.motore_similarita`** (`"rapidfuzz"` | `"difflib"`,
   dalla 1.8) registra quale motore ha prodotto OGNI corsa. Un file con
   `motore_similarita: "difflib"` non e' un file scorretto per questo
   solo fatto, ma i suoi stati di ancoraggio vicino a soglia (fuzzy, non
   esatti/normalizzati) vanno riletti con questo in mente: potrebbero
   differire da cio' che rapidfuzz avrebbe prodotto sulla stessa citazione.
3. Il test di concordanza (`test_motori_di_similarita_concordano_su_citazioni_reali`)
   verifica lo scarto su dati reali con una tolleranza DICHIARATA
   (0.01): registra la divergenza, non la annulla. Uno scarto sotto
   tolleranza puo' comunque, in casi patologici vicini al confine 0.95/0.80,
   cambiare lo stato risultante - la tolleranza limita quanto i due motori
   possono discordare in punteggio, non garantisce che non discordino MAI
   in stato.

### Enum completo degli esiti

| stato | quando | effetto a valle |
|---|---|---|
| `ancorata` (esatta / normalizzata / fuzzy≥0.95) | una sola posizione | tripla automatica; estratto F01 citabile, con testo = `atto_originale[inizio:fine]`, MAI la stringa del modello |
| `ancora_ambigua` | ≥2 occorrenze (esatte, normalizzate o fuzzy entro 0.02) | tutte le occorrenze registrate, scelta umana; voce in `buchi`; nessuna tripla automatica |
| `ancora_parziale` | migliore finestra in [0.80, 0.95) | candidato registrato + similarita'; voce in `buchi`; revisione |
| `non_ancorata` | niente sopra 0.80 | voce in `buchi`; la Fase 2 tratta comunque l'eccezione (la classificazione non dipende dall'ancora) |

## Astensione e guasto sono cose diverse

`astensione` = il sistema ha funzionato correttamente e ha rifiutato di
argomentare senza ancoraggio. `errore_tecnico` = il sistema si e'
guastato. **Non vanno mai collassati**, in nessuna direzione e in nessun
punto della catena: collassarli rende impossibile misurare l'uno senza
contaminare l'altro, e - piu' grave - fa sembrare prudenza quello che e'
un guasto. Un atto in cui dieci motivi mancano perche' il modello si e'
astenuto e' un atto prudente; uno in cui mancano perche' `n_predict` era
basso e' un atto rotto. All'avvocato che legge la memoria devono
apparire come due cose diverse, perche' lo sono.

La regola vale per **qualunque** fallimento tecnico che si incontri in
futuro: mai riciclare `astensione` come contenitore di errori. Se serve
un esito nuovo, si bumpa il contratto.

| Dove | Astensione | Guasto |
|---|---|---|
| Fase 2, `esiti[].stato` | `astensione` / `non_classificata` + `motivo_astensione` | `errore_tecnico` + `motivo_errore` |
| Fase 3, `motivi[].esito` | `astensione_dossier` (decisa a monte) / `astensione_modello` (ramo della grammatica) + `dichiarazione_astensione` | `errore_tecnico` + `motivo_errore` |
| Fase 3, `fatto.esito` (dalla 1.11) | `astensione_modello` (ramo della grammatica; niente `astensione_dossier`, il FATTO non ha un motore di regole a monte) + `dichiarazione_astensione` | `errore_tecnico` + `motivo_errore` |
| Fase 3-bis | finestra scartata e dichiarata in `copertura_conflitti`; `coerenza = null` solo sotto i 2 motivi | idem, con il motivo in memoria |

`motivo_errore` non e' una nota di colore: va scritto in forma
utilizzabile da chi deve rilanciare - quale passo, quale eccezione,
quale budget, quanti caratteri parziali scartati.

**Nessuna GBNF cambia** per questo. Il modello non emette mai
`errore_tecnico`: `fase3_confutazione.gbnf` continua ad avere due soli
rami (`trattata` | `astensione`), che sono le due cose che il MODELLO
puo' scegliere. `errore_tecnico` lo assegna Python quando la chiamata non
e' arrivata a destinazione - per definizione non e' una scelta del
modello, quindi non puo' stare in una grammatica che vincola cio' che il
modello scrive.

## Dove sta la GBNF (e dove NON sta)

| Confine | Chi lo produce | Grammatica |
|---|---|---|
| Uscita Fase 1 (file) | Python assembla le passate LLM | `fase1_struttura.gbnf`, `fase1_eccezioni.gbnf`, `fase1_citazioni.gbnf` (una per chiamata; l'autoverifica segue il pattern di citazioni) |
| Uscita Fase 2 (dossier) | **Solo Python, zero LLM** | **Nessuna** - il vincolo e' jsonschema + controlli sotto. Che non serva una grammatica qui e' una proprieta' dell'architettura, non una mancanza |
| Chiamata Fase 3 | LLM, una per eccezione | `fase3_confutazione.gbnf` - TEMPLATE: `ancora-id` generata a runtime |
| Chiamata Fase 3-bis (conflitti) | LLM, una per finestra, sui riassunti | `coerenza.gbnf` - TEMPLATE: `motivo-id` generata a runtime |
| Ordine dei motivi (Fase 3-bis) | Python, `ordine_motivi.py` - rango processuale | nessuna: non e' generato |
| Uscita Fase 3 (file) | Python assembla le chiamate | Nessuna (file assemblato) |

### Integrazione con llama-server

`llama_server_client.completa_json` passa gia' `json_schema`: llama-server
lo converte internamente nello STESSO motore GBNF. Due strade equivalenti:

- **(consigliata, zero modifiche al client)** continuare a costruire il
  `json_schema` a runtime come fa oggi `costruisci_schema()`, usando
  `$defs/confutazione_generata` di `fase3_atto.schema.json` con l'enum
  delle ancore sostituito. I file `.gbnf` restano l'espressione normativa
  del contratto (audit + test).
- passare GBNF grezzo: llama-server accetta anche il campo `grammar`;
  servirebbe un parametro opzionale in `completa()`.

Attenzione: il convertitore json_schema di llama.cpp supporta `oneOf`,
`const`, `enum`, `minItems`/`maxItems`, `minLength`/`maxLength` - ma
**ignora in silenzio** `uniqueItems`, `allOf`/`if`/`then`, `pattern` (in
parte) e i vincoli numerici di valore. I payload delle chiamate usano solo
parole chiave supportate; `if/then` e `uniqueItems` compaiono SOLO negli
schemi di file, che valida Python, mai llama-server.

### Generatore della regola runtime (Fase 3)

```python
def gbnf_ancora_id(estratti_citabili: list[dict]) -> str:
    """estratti_citabili: dall'esito della SINGOLA eccezione nel dossier.
    Dalla 1.2 sono oggetti {estratto_id, provenienza}: la grammatica
    vincola gli ID, la provenienza governa l'USO (controllo n. 14) e non
    entra nell'enum - il modello non deve poter scegliere in base a essa,
    deve solo non poter uscire dalla lista."""
    ids = [e["estratto_id"] for e in estratti_citabili]
    alternative = " | ".join(f'"\\"{i}\\""' for i in ids)
    return f"ancora-id ::= {alternative}"
```

(Equivalente via json_schema: sostituire l'enum
`["SEGNAPOSTO_RUNTIME_estratti_citabili"]` con quella stessa lista di id.
Stesso identico meccanismo per `motivo-id` in `coerenza.gbnf`, a partire
dagli `eccezione_id` dell'input.)

## Passata di coerenza d'insieme (Fase 3-bis)

Una chiamata per eccezione risolve il budget ma nessuno vede l'insieme:
un'eccezione subordinata che presuppone il rigetto della principale, due
motivi reciprocamente contraddittori, un ordine non giuridicamente
sensato. Dal contratto **1.27** la Fase 3-bis e' **ibrida**: l'ordine lo
calcola Python, i conflitti li cerca il modello.

### Perche' l'ordine e' uscito dal modello

Fino alla 1.26 la passata era UNA chiamata che doveva restituire
`ordine_motivi`, una permutazione completa degli `eccezione_id`, con
`maxItems: 15`. Misurato sul batch del 2026-08-30 (45 atti reali):
**mediana 17 motivi, massimo 59, e 24 atti su 45 oltre il tetto**. Lo
schema respingeva l'input e fermava la corsa DOPO che Fase 2 e Fase 3
avevano gia' lavorato; altri 5 atti (0 o 1 motivo) cadevano dal lato
opposto, sul `minItems`. Il difetto non era il numero 15: era un tetto
senza semantica di superamento, in un contratto che per il pavimento e
per l'uscita non conforme una semantica ce l'aveva.

Alzarlo non era la soluzione. Non per il budget - misurato sul
tokenizzatore, 56 id costano 293 token contro un `n_predict` di 1536 - ma
perche' una permutazione generata degrada gia' a K=20-30 e fallisce a
K=50, omettendo candidati (arXiv 2601.07449), e il bias posizionale
favorisce sistematicamente gli elementi in testa (arXiv 2604.03642). A
K=56 il controllo 11 l'avrebbe respinta quasi ogni volta: costo pieno di
una chiamata, risultato nullo.

L'ordine di un atto difensivo non e' gusto, e' rito: prima le pregiudiziali
di rito, poi le preliminari di merito, poi il merito. Lo calcola
`ordine_motivi.py`, stabile dentro il rango (a parita' di rango vince
l'ordine dell'atto di controparte). E' una permutazione **per
costruzione**. La tabella `RANGO_PER_FAMIGLIA` e' giudizio giuridico da
validare, come il golden set: i motivi la cui famiglia non vi compare
vanno in coda con rango `non_classificato` e l'elenco viene dichiarato,
mai collocato in silenzio.

### Cosa resta al modello

La ricerca dei **conflitti**, che e' un giudizio locale a coppie - il
compito per cui serve davvero, e dove una finestra corta non lascia spazio
al bias posizionale. La passata:

- lavora SOLO sui riassunti (`coerenza.schema.json/$defs/input`, costruito
  da Python: `contro_argomento` del dossier - o `motivo_astensione`/`nota`
  per gli esiti non trattati - troncato, + prima frase del primo paragrafo
  generato; MAI i materiali grezzi ne' gli estratti). Cio' che tiene il
  budget non e' piu' il numero totale di motivi ma l'ampiezza della
  **finestra**: 8 × 400 char ≈ 1k token per chiamata, qualunque sia la
  dimensione dell'atto;
- gira a **finestre scorrevoli** sui motivi gia' ordinati
  (`ordine_motivi.FINESTRA = 8`, `PASSO = 4`; l'ultima finestra e' ancorata
  in fondo, non troncata). Le finestre si sovrappongono apposta, e la
  stessa coppia vista due volte viene segnalata una sola;
- produce SOLO `conflitti` (`$defs/output`, grammatica `coerenza.gbnf`):
  coppie `tra` + `tipo` ∈ {contraddizione, subordinazione,
  sovrapposizione} + descrizione ≤300;
- NON riscrive il testo dei paragrafi, NON tocca le ancore, NON risolve i
  conflitti: li segnala come voci esplicite in `03_atto.json` (sezione
  `coerenza`) e in testa alla memoria di analisi - la decisione resta
  all'avvocato.

**La copertura si dichiara.** Due motivi mai finiti nella stessa finestra
NON sono stati confrontati, e `coerenza.copertura_conflitti`
(`finestre`, `finestre_riuscite`, `coppie_esaminate`, `coppie_totali`) dice
quante coppie sono state davvero guardate. Senza quel blocco "nessun
conflitto segnalato" verrebbe letto come "nessun conflitto", che e'
esattamente il silenzio che il contratto vieta.

Innesto in `esegui_pipeline.py`: passo 3-bis, DOPO l'assemblaggio di
`03_atto.json` e PRIMA del rendering della bozza. L'ordine del file resta
quello del dossier (stabilita' referenziale); `ordine_motivi` e' l'ordine
di RENDERING, applicato da Python alla bozza .txt - e non essendo piu'
generato non e' piu' subordinato ad `applicata`, che ora riguarda la sola
ricerca dei conflitti. Salvaguardie:

- meno di 2 motivi → passata saltata, `coerenza = null`, dichiarato in
  memoria (senza almeno una coppia non esiste conflitto possibile);
- finestra con `tra[0] == tra[1]` o con id estranei alla finestra →
  finestra scartata, le sue coppie restano NON esaminate e la copertura lo
  dice (controllo Python n. 11);
- `RispostaTroncata` su una finestra → come sopra: la finestra salta, le
  altre proseguono. Una chiamata andata male non uccide piu' la passata;
- nessuna finestra riuscita → `applicata = false`, ordine comunque
  calcolato, voce in memoria.

## Cosa GBNF NON puo' controllare → controlli Python obbligatori

GBNF garantisce la FORMA, mai la verita'. Questi controlli vivono in
Python, all'entry point, su ogni confine di fase:

1. **Integrita' referenziale**: ogni `eccezione_id` degli esiti esiste in
   Fase 1; ogni `fonte_id` degli estratti esiste in `fonti`; ogni
   `estratto_id` in `estratti_citabili`/`ancore` esiste in `estratti`.
   (L'enum runtime gia' lo impone alla generazione - il ricontrollo e' il
   doppio binario applicato ai dati.)
2. **Offset**: `0 <= inizio < fine <= len(testo_fonte)` e
   `estratto.testo == testo_fonte[inizio:fine]` (identita' testuale, non
   esprimibile in JSON Schema ne' in GBNF).
3. **Ancoraggio Fase 1**: `testo_letterale` localizzato con la procedura
   NORMATIVA della sezione "Localizzazione della citazione" (esatto →
   normalizzato con mappa offset → fuzzy 0.95/0.80, ambiguita' a Δ≤0.02);
   ogni esito diverso da `ancorata` → voce in `buchi`, mai il primo match
   d'ufficio.
4. **Condizionali di astensione e di guasto**: `motivo_astensione`
   presente se e solo se `stato ∈ {astensione, non_classificata}`;
   `motivo_errore` presente se e solo se `stato = errore_tecnico`; i due
   non sono mai entrambi valorizzati; `estratti_citabili` non vuoto se e
   solo se `stato = confutabile`. Stessa forma in Fase 3 su
   `motivi[].esito` (`dichiarazione_astensione` / `motivo_errore`).
   (Negli schemi di file via `if/then`, ricontrollato in Python perche' il
   convertitore llama.cpp li ignorerebbe.)
5. **Copertura totale**: |esiti Fase 2| == |eccezioni Fase 1| == |motivi
   Fase 3|, stesso ordine - nessuna eccezione saltata in silenzio, in
   nessuna direzione.
6. **Contenuto non degenere**: `uniqueItems` sulle ancore; `testo` non
   vuoto dopo `strip()` (la grammatica ammette `"   "`); nessun paragrafo
   duplicato letterale. In `estratti_citabili` l'unicita' e' sull'
   `estratto_id`, non sull'oggetto: dalla 1.2 sono oggetti, e
   `uniqueItems` considererebbe "diverse" due voci con lo stesso id e
   provenienza diversa - quindi il controllo e' Python, non di schema.
7. **Citazioni nella prosa**: la grammatica vincola le `ancore`, NON il
   campo `testo` - il modello puo' ancora NOMINARE nella prosa una fonte
   non ancorata ("come noto, l'art. 1957 c.c. ..."). Il doppio binario
   esistente (`extract_citations` + `verify`/`pipeline.verifica_risposta`
   sul testo renderizzato) resta obbligatorio: ogni citazione trovata nel
   testo libero deve corrispondere a una fonte del dossier, altrimenti la
   sezione e' respinta (rigenerata una volta, poi astensione dichiarata) e
   `meta.verifica_post_generazione_superata = false`.
8. **Completamento**: la grammatica non garantisce che il JSON venga
   CHIUSO entro `n_predict` - `RispostaTroncata`/`stop_type` resta l'unico
   guardiano (gia' in `llama_server_client`).
9. **Nota sui limiti di lunghezza**: `char{1,N}` conta caratteri logici
   (un escape `\uXXXX` = 1), non byte ne' token - coerente con `maxLength`
   di JSON Schema, ma NON e' un limite di token: il budget resta n_predict.
10. **Validita' di calendario delle date**: la grammatica impone solo la
   forma `[0-9]{4}-[0-9]{2}-[0-9]{2}` ("2026-99-99" e "2026-02-31"
   passano) - `datetime.date.fromisoformat` su ogni `data_rilevante`,
   `data_vigenza`, `data_criterio_risoluzione`; data invalida →
   trattata come null + voce in `buchi`/memoria. Che `data_rilevante` sia
   DAVVERO dichiarata nel testo non e' verificabile ne' in grammatica ne'
   in modo affidabile in Python (l'atto la scrive "14 marzo 2018"):
   istruzione di prompt + revisione, dichiarato come limite.
11. **Coerenza (Fase 3-bis)**: in ogni conflitto `tra[0] != tra[1]` e i
   due id appartengono alla FINESTRA su cui la chiamata ha lavorato - la
   grammatica impone l'enum ma non queste due proprieta'. Violazione →
   finestra scartata, le sue coppie restano non esaminate e la copertura
   lo dichiara, le altre finestre proseguono. Fino alla 1.26 il controllo
   verificava anche che `ordine_motivi` fosse una permutazione esatta:
   quel campo non esiste piu', l'ordine lo calcola Python ed e' una
   permutazione per costruzione.
12. **Conservazione delle fonti di regola**: per ogni esito, OGNI `Fonte`
   proposta dal catalogo di motore_regole compare o nel registro `fonti`
   (passata da `risolvi_fonte`, unico ingresso) o in `fonti_scartate`:
   `|proposte| == |risolte| + |scartate|`, nessuna terza via, nessuna
   sparizione silenziosa.
13. **Nullabilita' di node_id**: `node_id == null` ⇔ `tipo` ∈
   {fatti_di_causa, atto_controparte} (gia' imposto dall'`allOf/if/then`
   nello schema, ricontrollato qui perche' e' il lucchetto del punto 12:
   una fonte di grafo senza node_id reale non puo' superare il controllo
   2 sull'identita' testuale degli estratti).
14b. Vedi anche il controllo 16: un estratto `parziale` non e' ancorabile
   nemmeno quando la sua provenienza sarebbe ammessa.
14. **L'atto di controparte non e' autorita'**: nessun paragrafo puo'
   avere come UNICA ancora un estratto con `provenienza:
   "atto_controparte"`. Un estratto F01 riporta cio' che la controparte
   afferma: serve a dire *"la controparte deduce X"*, mai a dire *"come
   stabilito in X"*. Un paragrafo ancorato solo a F01 e' un paragrafo che
   fonda un argomento sull'atto avversario - il che, se l'argomento e' a
   favore del creditore, e' quasi sempre un fraintendimento del modello, e
   se non lo e', e' una citazione dell'avversario travestita da fonte.
   Violazione → il paragrafo e' respinto, la sezione rigenerata una volta,
   poi `errore_tecnico` dichiarato (stessa scala di risposta del controllo
   7). La grammatica non puo' imporlo: l'enum ammette l'id F01 perche' il
   paragrafo che riferisce l'eccezione DEVE poterlo ancorare - e' l'uso,
   non la disponibilita', a essere vincolato.
17. **Copertura F01 negli accorpamenti** (dalla 1.9): un motivo che accorpa
   N eccezioni (`eccezioni_accorpate`, contratto 1.7) porta dentro
   l'estratto F01 di OGNUNA - niente pero' garantiva che il testo generato
   le confutasse tutte invece di ancorarsi solo alla prima e ignorare le
   altre N-1. Per ogni esito con `len(eccezioni_accorpate) > 1`, ogni
   estratto F01 di quell'esito deve comparire nel campo `ancore` di ALMENO
   UN paragrafo del motivo corrispondente - non necessariamente lo stesso
   paragrafo, l'accorpamento non impone una prosa unica. La grammatica non
   puo' imporlo per lo stesso motivo del controllo 14: l'enum ammette gli
   id F01, e' l'USO (tutti, non solo il primo) a essere vincolato. Stessa
   scala di risposta del controllo 14 (diagnostico, non bloccante): un
   accorpamento confutato a meta' e' un difetto di argomentazione del
   modello, non un dato rotto.

## Criterio di rilevanza (uno per indice, non uno solo)

Il retrieval semantico restituisce sempre i top-k, anche quando il corpus
non contiene la materia cercata. Senza un criterio di rilevanza, quei
risultati diventano `estratti_citabili` e la Fase 3 argomenta su materiale
non pertinente: le fonti esistono davvero nel grafo, quindi `risolvi_fonte`
le verifica e nulla le ferma.

**I due indici NON ammettono lo stesso criterio.** Calibrazione del
2026-08-20, n=20 query per lato (20 fuori dominio, 20 di dominio scelte
dall'avvocato fra le materie che interroga davvero):

| | rumore top-1 | segnale top-1 | separate? |
|---|---|---|---|
| principale (5892 voci) | 0.8437 - **0.9157** | **0.8487** - 0.9170 | NO: 19/20 di dominio sotto il tetto del rumore |
| segmenti (689 voci) | 0.8272 - **0.8554** | **0.8547** - 0.9229 | quasi: sovrapposizione 0.0008, 1/20 |

Sull'indice **principale** nessun criterio numerico funziona: il punteggio
piu' alto dell'intero esperimento era una query fuori dominio, e anche il
margine relativo (top1 meno la mediana dei top-20) si sovrappone su 19
casi su 20. Non e' che l'indice sia cieco - il contenuto restituito per le
query di dominio e' spesso ottimo - e' che il punteggio non discrimina.
La' il criterio e' la **verifica di pertinenza a valle**: una chiamata LLM
breve per eccezione, con l'elenco dei candidati e uno schema che vincola
una lista di verdetti.

Sull'indice **segmenti** la soglia assoluta funziona, e la soglia e'
**0.8560**. Non e' una costante misurata: e' una **decisione operativa**
presa su questi numeri, e va letta cosi'. Con n=20 per lato la
sovrapposizione e' di 0.0008 e coinvolge una query per parte - il rumore
piu' alto e' "condominio ripartizione delle spese per l'ascensore"
(0.8554), il segnale piu' basso e' "opposizione all'esecuzione e
contestazione del titolo esecutivo" (0.8547). A 0.8560 nessuna query fuori
dominio passa e se ne perde una di dominio.

**Quella perdita e' comportamento CORRETTO, non un falso negativo**: il
corpus di Ancona non copre l'opposizione all'esecuzione, e cio' che offre
per quella query non e' materiale su quel tema. Una soglia che la
recuperasse farebbe passare anche il condominio.

Le due scale non sono confrontabili, e non si tratta di una differenza di
taratura: la **mediana del RUMORE sull'indice principale (0.8804) e' piu'
alta del minimo del SEGNALE sui segmenti (0.8547)**. Ordinare i risultati
dei due indici insieme metterebbe sistematicamente il rumore dell'uno
sopra il segnale dell'altro. Per questo le quote sono separate (default
4 + 2) e una quota non riempita **resta vuota**.

Un'eccezione i cui candidati non superano il criterio non produce un esito
confutabile con fonti deboli: produce `astensione`, con il motivo che lo
dice.

**Cautela dichiarata**: 0.0008 di sovrapposizione con n=20 per lato e' un
margine che una ventunesima query puo' spostare. Rifare la calibrazione
quando il corpus cresce, e trattare il valore come rivedibile - e' un
parametro proprio per questo.

### La calibrazione originale non e' riproducibile

Le 20 query di dominio e le 20 fuori dominio del 2026-08-20 (quelle che
hanno prodotto 0.8554/0.8547 sopra) **non furono mai salvate**: solo i
due valori estremi finirono in questo documento, in prosa. Non esiste
oggi un modo di rilanciare quell'esperimento - il dato che lo genera e'
perso, non solo il codice che lo eseguiva.

`contratti/calibrazione_soglia_segmenti.json` (deploy del 2026-08-23) e'
un tentativo di rimediare, ma **non e' l'originale**: 20+20 query
ricostruite (dominio: materie bancarie coerenti col corpus; fuori
dominio: successione, separazione, appalto, locazione, infortunio, come
da istruzione), non le query che l'avvocato scelse davvero. Rilanciate
sul nuovo hardware danno rumore massimo 0.8580 e segnale minimo 0.8470 -
diverse da 0.8554/0.8547, con 1/20 fuori-dominio ("assegno divorzile e
criteri di determinazione") sopra la soglia 0.8560.

**La soglia RESTA 0.8560, non ricalibrata su questo file**: le 3 query
ufficiali di DEPLOY.md (sezione 6.4, quelle sì testuali e verificate)
danno risultati identici a 4 decimali su questo hardware, il che dimostra
che imbedding e modello non sono cambiati - la divergenza del set da 40 e'
quasi certamente l'effetto di query diverse dalle originali, non di un
cambio di ambiente. Ricalibrare su un file ricostruito significherebbe
fissare un numero nuovo su dati che non sono quelli su cui il numero
vecchio fu deciso: `calibrazione_soglia_segmenti.json` serve da
**regressione** (rilevare se qualcosa cambia rispetto a QUESTA corsa),
non da **riferimento** per rifissare la soglia.

La fragilita' che il file conferma (1/20 fuori dominio sopra soglia, in
un campione diverso dall'originale) e' comunque reale e coerente con la
"Cautela dichiarata" sopra: la soglia numerica sui segmenti e' un
pre-filtro grossolano quanto quello mancante sull'indice principale, solo
con un margine piu' stretto. La chiusura prevista e' estendere ai
segmenti la stessa verifica LLM di pertinenza gia' decisa per l'indice
principale (una chiamata per eccezione, elenco dei candidati, schema che
vincola una lista di verdetti) - la soglia diventa il pre-filtro, la
verifica LLM il giudice fine. Non ancora implementata: richiede
`llama-server` attivo per essere provata, non solo scritta.

**Regola da qui in avanti**: nessuna calibrazione produce un numero senza
prima salvare le query usate nel repository. Un valore di soglia senza il
dato che lo ha generato e' un numero non falsificabile.

## Budget 16k per chiamata (perche' regge)

La Fase 3 per-eccezione e' anche la risposta al budget: sistema (~600 tok)
+ eccezione (`testo_letterale` ≤ 4000 char ≈ 1300 tok, che dalla 1.2
arriva come l'estratto F01 di `provenienza: "atto_controparte"` - percio'
NON conta nel tetto di 6: i 6 sono le fonti a supporto, F01 e' l'oggetto
dell'attacco, ed era gia' contato qui come voce a se') + contro_argomento
e nota della regola (~300 tok) + estratti (≤ 6 × 2000 char ≈ 2400 tok
nel caso peggiore) + `n_predict` 3072 ≈ **7.7k token nel caso peggiore**,
meta' del budget. La grammatica non costa token di prompt. Mai piu' di una
eccezione per chiamata; mai l'atto intero in un prompt di Fase 3.

## Nuova firma di redazione.py

```python
# PRIMA (redazione.py:107) - puo' fare retrieval autonomo:
def redigi_atto(store, embedding_index, base_url, obiettivo, fatti_di_causa,
                atto_controparte=None, k=25,
                fonti_aggiuntive_verificate=None) -> RisultatoRedazione: ...

# DOPO - non PUO' fare retrieval, non ha da dove:
def redigi_atto(base_url: str, dossier: dict) -> dict:
    """dossier: gia' validato contro fase2_dossier.schema.json.
    Ritorna il payload conforme a fase3_atto.schema.json SENZA la tabella
    'affermazioni', SENZA 'conclusioni' e senza
    meta.verifica_post_generazione_superata, con 'coerenza' a null -
    risolte dall'entry point, che e' l'unico ad avere il grafo, gli
    argomenti di riga di comando e il testo renderizzato."""
```

**Due parametri, non tre.** Le conclusioni dell'avvocato NON entrano da
un terzo parametro: viaggiano nel dossier (`conclusioni_avvocato`, 1.2)
come gia' fanno `obiettivo` e `fatti_di_causa`. La promessa del contratto
e' che tutto cio' che la Fase 3 vede stia in `02_dossier.json`: un
secondo canale di ingresso la renderebbe falsa, e il primo a dimenticarlo
sarebbe chi legge il dossier per capire cosa e' stato generato e da cosa.

Cosa sparisce e dove va:

- `store`, `embedding_index`, `k` → il retrieval semantico si sposta in
  **Fase 2b** (assembla_report), in una forma sola: **per-eccezione**,
  sulla query riformulata di QUELLA eccezione
  (`meta.query_di_ricerca[eccezione_id].riformulata`, prodotta dal passo
  1-bis dell'orchestratore e ricevuta qui come dato). Completa gli
  `estratti_citabili` fino a 6 SOLO quando le fonti della regola ne hanno
  prodotti meno; `provenienza: "retrieval_per_eccezione"`.

  I candidati sono nodi del grafo, quindi verificati per costruzione; le
  fonti delle regole passano da `risolvi_fonte` come oggi.

  Il retrieval di CAUSA (su obiettivo+fatti) non entra piu' nel dossier -
  vedi changelog 1.3 punto 1. Finisce nella memoria di analisi come
  "Spunti non citati", che e' un documento interno, non un contratto.
- `fonti_aggiuntive_verificate` → non serve piu': le fonti delle regole
  stanno gia' nel dossier, non vanno "iniettate" nei candidati.
- `obiettivo`, `fatti_di_causa`, `atto_controparte` → campi del dossier.
- `verifica_risposta`/`verifica_risposta_giurisprudenza` (richiedono lo
  store) → escono da `redigi_atto`, le chiama l'entry point sul testo
  renderizzato.

Applicazione strutturale, non solo di firma - spacchettare
`constrained_decoding.py`:

- `retrieval.py` (nuovo, dipende da `store`): `candidati_per_prompt`,
  `candidato_da_node_id`, `riformula_query_di_ricerca`. Importato SOLO da
  assembla_report/Fase 2.
- `constrained_decoding.py` (resta, dipende SOLO da
  `llama_server_client`): `costruisci_schema`, `genera_vincolato`.

Dopo lo split, `redazione.py` importa solo `constrained_decoding` +
`llama_server_client`: il grafo non e' raggiungibile nemmeno per sbaglio.
Test di guardia consigliato:

```python
def test_redazione_non_tocca_il_grafo():
    sorgente = Path("redazione.py").read_text(encoding="utf-8")
    assert "from store import" not in sorgente
    assert "GraphStore" not in sorgente
    assert "retrieval" not in sorgente
```

## Entry point unico (da scrivere): esegui_pipeline.py

```
python esegui_pipeline.py atto.pdf --obiettivo "..." --fatti "..."                           --conclusioni percorso/al/file.txt [--out out/]
```

`--conclusioni` e' **obbligatorio**: senza, la pipeline si ferma prima
della Fase 3 con un errore esplicito. Non esiste un default, non esiste
un template, e le conclusioni non vengono generate dal modello.

0. Se e' stato indicato un ingresso alternativo (`--da-estrazione` /
   `--da-dossier`): il file viene letto UNA volta, validato contro il suo
   schema come input esterno, e la catena riparte dal passo successivo.
1. Fase 1 → scrive `01_estrazione.json`, **valida** contro lo schema,
   calcola gli ancoraggi (controllo 3).
1-bis. Riformulazione della query di ricerca, UNA PER ECCEZIONE (chiamate
   LLM brevi) → la mappa `{eccezione_id: {originale, riformulata}}`
   finisce in `meta.query_di_ricerca` del dossier. E' un passo
   dell'ORCHESTRATORE, non della Fase 2: la Fase 2 e' "solo Python, zero
   LLM" e riceve le query come dato. La famiglia dell'eccezione serve alla
   riformulazione, quindi la classificazione euristica
   (`classificazione.py`, senza grafo e senza LLM) gira qui, prima della
   Fase 2 che la rifara' identica.
2. Fase 2 → scrive `02_dossier.json`, valida + controlli 1-2-4-5-12-13.
   Se TUTTI gli esiti sono astensioni: si ferma qui, scrive la memoria di
   analisi e lo dice - niente Fase 3 su un dossier vuoto.
3. Fase 3 → una chiamata per esito confutabile + FATTO; assembla
   `03_atto.json`, copia `conclusioni` da `conclusioni_avvocato`
   (origine `avvocato`), risolve `affermazioni` (incl. `data_vigenza`
   dalla fonte), valida + controlli 5-6-14.
3-bis. Passata di coerenza (se ≥2 motivi) → ordine calcolato da
   `ordine_motivi.py` (rango processuale, mai il modello), poi UNA chiamata
   per FINESTRA scorrevole con `coerenza.gbnf` (enum `motivo-id` a
   runtime), controllo 11 su ciascuna → scrive la sezione `coerenza` in
   `03_atto.json`, con `origine_ordine` e `copertura_conflitti`; i
   conflitti vanno ANCHE in testa alla memoria di analisi.
   Fallimento/troncamento di una finestra → finestra scartata e
   dichiarata nella copertura, la pipeline prosegue.
**Budget misurato, non stimato.** I ~7.7k token per chiamata di Fase 3 e
i ~2k della coerenza sono stime a priori. L'entry point misura il payload
REALE via `/tokenize` prima di ogni chiamata: oltre il budget dichiarato
→ avviso nel log con il valore vero; oltre `n_ctx` meno il margine di
generazione → **errore bloccante**. Un troncamento silenzioso del prompt
produce un output plausibile costruito su materiali incompleti, che e' il
fallimento peggiore possibile qui: l'atto sembra scritto bene e si regge
su meta' delle fonti.

**Scrittura atomica.** Nessun file finale viene lasciato sul posto se una
validazione successiva fallisce: si scrive su un temporaneo e si rinomina
solo a passo completato. Una bozza di atto parziale che sembra completa e'
piu' pericolosa di un file assente.

4. Doppio binario sul testo renderizzato (controllo 7) → imposta
   `verifica_post_generazione_superata`, scrive `03_bozza_atto.txt`
   (motivi nell'ordine di `ordine_motivi`, che dalla 1.27 e' sempre
   valido perche' calcolato da Python; ordine del dossier solo se la
   passata non e' stata eseguita) e `00_memoria_analisi.md` (buchi in
   testa, come oggi).

### Come i dati passano fra le fasi

**Per chiamata di funzione.** `fase1_assembla(...) -> dict` →
`costruisci_dossier(dict, ...) -> dict` → `redigi_atto(base_url, dict) ->
dict`. L'orchestratore tiene l'oggetto in memoria, lo valida contro lo
schema a OGNI confine, e lo passa al passo successivo.

**I file `01_`/`02_`/`03_` sono artefatti di ispezione, non il
meccanismo.** Vengono scritti dopo la validazione perche' l'avvocato (e
chi debugga) devono poter leggere cosa e' stato prodotto a ogni stadio.
Nessun passo della catena li rilegge: cancellarli a meta' corsa non
cambia il risultato, ed e' cosi' che si verifica che la proprieta' valga
davvero.

La 1.1 diceva il contrario ("ogni passo rilegge il file del precedente da
disco"). Descriveva il comportamento degli script di test di allora -
`test_redazione_reale.py` ricaricava `estrazione_atto_reale_risultati.json`
da disco - non un requisito, ed e' stato corretto. Il giro attraverso il
filesystem non aggiunge nessuna garanzia: la validazione avviene
sull'oggetto, non sui byte, e rileggere introduce due modi di fallire
(serializzazione e I/O) al posto di zero.

**Le fasi restano comunque eseguibili e ispezionabili singolarmente**:
sono funzioni pure sui dizionari di contratto, quindi si possono
richiamare a mano su un file `.json` salvato da una corsa precedente.

### Ingressi alternativi da riga di comando (NON un ritorno alla 1.1)

```
esegui_pipeline.py --da-estrazione 01_estrazione.json ...
esegui_pipeline.py --da-dossier    02_dossier.json    ...
```

La Fase 1 e' il passo piu' costoso (decine di minuti su un atto lungo).
Un fallimento in Fase 3 non deve costringere a rifarla, quindi la CLI
accetta di ripartire da un file intermedio.

**La distinzione con la 1.1 e' sostanziale, non nominale**, e va tenuta
ferma:

| | 1.1 (superata) | 1.2 |
|---|---|---|
| Chi decide di leggere il file | la catena, a ogni passo | l'utente, una volta, da riga di comando |
| Quando | sempre | solo se lo chiede |
| Che cos'e' il file | il meccanismo di passaggio | un INPUT ESTERNO come il PDF |
| Fra un passo e il successivo | disco | chiamata di funzione, sempre |

Un file passato con `--da-estrazione`/`--da-dossier` e' trattato come
qualunque altro input esterno: **validato contro il suo schema
all'ingresso**, esattamente come si valida il PDF che arriva da fuori.
Non e' fidato per il fatto di essere stato prodotto da questa pipeline -
puo' essere stato modificato a mano, prodotto da una versione precedente
dei contratti, o troncato da una copia interrotta.

Da li' in poi la catena procede per chiamata di funzione come sempre:
l'ingresso alternativo sostituisce il PRIMO passo, non il meccanismo.

15. **Fonti non verificate**: nessun estratto citabile puo' venire da una
   fonte con `stato_verifica != "verificato"` o `motivazione_certa is
   False`. Non sono etichette informative: `estremi_incerti` significa che
   non si sa QUALE provvedimento sia quel testo, e citarlo attribuirebbe
   un principio a una sentenza che potrebbe essere un'altra;
   `motivazione_certa = False` significa che non si sa quale parte del
   testo sia la motivazione, e un estratto ritagliato da li' puo'
   spacciare per principio di diritto lo svolgimento del processo o la
   tesi della parte soccombente riportata per essere respinta. I nodi
   restano interrogabili dal retrieval e visibili nella memoria: e' la
   CITAZIONE AUTOMATICA a essere vietata, non la consultazione. Il
   controllo si applica sia al nodo sia al singolo SEGMENTO, che porta i
   propri `stato_verifica`/`motivazione_certa` nell'indice.
16. **Estratti parziali non ancorabili**: un estratto con `parziale: true`
   e' MATERIALE DI PROMPT. La Fase 3 lo legge - serve a farle vedere cosa
   dice la controparte quando l'ancoraggio di Fase 1 non e' riuscito - ma
   nessun paragrafo puo' ancorarvisi. Ancorarlo produrrebbe una tripla
   (fonte_id, inizio, fine) che dichiara "questo e' letteralmente
   nell'atto" su un ritaglio che la procedura di localizzazione ha gia'
   giudicato non abbastanza simile. E' il confine fra "cosa il modello
   puo' LEGGERE" e "cosa il contratto garantisce come LETTERALE".
