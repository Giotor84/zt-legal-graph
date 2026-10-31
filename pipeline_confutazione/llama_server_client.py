"""
Client per llama-server (llama.cpp nativo, endpoint POST /completion) - motore
scelto al posto di Ollama per l'architettura a modello denso (vedi
ISTRUZIONI_ARCHITETTURA_TOOL.md, sezione 7). API verificata contro la
documentazione ufficiale (ggml-org/llama.cpp, tools/server/README.md), non
assunta per analogia con Ollama:

- richiesta: "prompt", "n_predict" (non "num_predict" come Ollama),
  "temperature", "json_schema" (vincolo grammaticale sull'output - stesso
  motore GBNF usato per il vincolo sulle citazioni, esposto qui via schema
  invece che grammatica grezza).
- risposta: "content" (testo generato - NON "response" come Ollama),
  "stop_type" ("limit" = troncato per aver esaurito n_predict, "eos"/"word" =
  terminato normalmente), "truncated" (bool, contesto superato).

Il campo stop_type risolve alla radice la classe di bug trovata dal vivo il
2026-08-18 su Ollama (query di riformulazione troncata a meta' da un
num_predict troppo basso, scoperta solo rileggendo l'output a mano) - invece
di sperare che il budget sia sufficiente, ogni chiamata qui dichiara
esplicitamente se ha troncato, e questo modulo fa fallire la chiamata invece
di restituire in silenzio un risultato parziale che sembra completo.
Coerente con la sezione 6 di ISTRUZIONI_ARCHITETTURA_TOOL.md: un processo
asincrono deve fallire rumorosamente, non tacere sui propri buchi.

Non ancora testato dal vivo contro un'istanza llama-server reale (nessuna
istanza raggiungibile in questa sessione) - l'API e' verificata contro la
documentazione ufficiale, non contro un run vero. Primo test dal vivo da fare
non appena disponibile una macchina con llama-server in ascolto.

**Trovato verificando, non assunto (2026-08-19): `/completion` NON applica
il chat template del modello.** Solo `/v1/chat/completions` lo fa
automaticamente (confermato: github.com/ggml-org/llama.cpp/discussions/9741
e issue #6624) - `/completion` prende il prompt cosi' com'e', nessun
formato a turni. Il codice di questo progetto (redazione.py,
constrained_decoding.py) concatenava sistema+domanda come testo semplice,
pensato originariamente per Ollama (il cui /api/generate applica il
Modelfile TEMPLATE in automatico, comportamento diverso da llama-server
che qui non era stato replicato) - un modello instruction-tuned senza i
token di turno puo' non riconoscere i confini del turno e "continuare" il
testo invece di rispondere: un contributo reale, probabilmente non
l'unico, al bug 2 (generazione che ripete le istruzioni) osservato sul
modello potato. Corretto qui con `costruisci_prompt_chatml()`, che
costruisce il prompt nel formato ChatML verificato contro il vero
tokenizer_config.json di Qwen3-14B, invece di continuare a concatenare
testo semplice.

**Disattivazione del ragionamento verificata contro il vero chat
template, non assunta per sentito dire**: `--chat-template-kwargs
'{"enable_thinking":false}'` lato server ha bug aperti documentati su
Qwen3.5 (github.com/ggml-org/llama.cpp/issues/20409 e #20182) - non
usato qui per questo motivo. Il meccanismo "/no_think" nel testo del
messaggio, citato in giro per la serie Qwen3 precedente, NON e' quello
del template ufficiale di Qwen3-14B: il vero template Jinja
(tokenizer_config.json) usa una variabile `enable_thinking` e, quando
false, PRE-RIEMPIE il turno assistant con `<think>\n\n</think>\n\n`
vuoto - e' quello che costruisci_prompt_chatml() replica quando
pensiero_attivo=False, non dipende da nessun flag lato server.
"""

import re
from pathlib import Path

_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)

# Timeout di default alto: il progetto ha esplicitamente negoziato la
# velocita' contro l'accuratezza (vedi conversazione) - un ciclo puo' durare
# 15-45 minuti per Fase 1 dichiarata, nessun vincolo di interattivita'.
TIMEOUT_DEFAULT_SECONDI = 1800


def costruisci_prompt_chatml(sistema: str, utente: str, pensiero_attivo: bool = True) -> str:
    """Costruisce il prompt nel formato ChatML che Qwen3 si aspetta,
    verificato contro il vero tokenizer_config.json di Qwen3-14B (non un
    ChatML generico assunto per somiglianza con altri modelli Qwen/Llama):
    token <|im_start|>/<|im_end|> per delimitare i turni, e per
    pensiero_attivo=False il turno assistant PRE-RIEMPITO con
    '<think>\\n\\n</think>\\n\\n' vuoto - esattamente la logica Jinja del
    template ufficiale (`{%- if enable_thinking is defined and
    enable_thinking is false %}{{- '<think>\\n\\n</think>\\n\\n' }}{%- endif %}`),
    replicata qui perche' /completion non applica il template da solo (vedi
    docstring del modulo) e il flag --chat-template-kwargs lato server ha
    bug aperti documentati su questa stessa famiglia di modelli."""
    prompt = f"<|im_start|>system\n{sistema}<|im_end|>\n<|im_start|>user\n{utente}<|im_end|>\n<|im_start|>assistant\n"
    if not pensiero_attivo:
        prompt += "<think>\n\n</think>\n\n"
    return prompt


class RispostaTroncata(RuntimeError):
    """Sollevata quando llama-server segnala stop_type == 'limit' (n_predict
    esaurito) o truncated == True (contesto superato) - non si prende in
    silenzio un output tagliato. contenuto_parziale resta accessibile per chi
    vuole loggarlo o tentare un retry con budget maggiore, ma il chiamante
    deve gestirlo esplicitamente, non riceverlo come se fosse completo."""

    def __init__(self, motivo: str, n_predict_usato: int, contenuto_parziale: str):
        self.motivo = motivo  # "limit" o "context_overflow"
        self.n_predict_usato = n_predict_usato
        self.contenuto_parziale = contenuto_parziale
        super().__init__(
            f"generazione troncata ({motivo}, n_predict={n_predict_usato}) - "
            f"{len(contenuto_parziale)} caratteri parziali disponibili in .contenuto_parziale"
        )


def completa(
    base_url: str,
    prompt: str,
    n_predict: int = 1024,
    temperature: float = 0.7,
    json_schema: dict | None = None,
    timeout: int = TIMEOUT_DEFAULT_SECONDI,
    repeat_penalty: float | None = None,
    seed: int | None = None,
) -> str:
    """Chiamata di base a POST /completion. Solleva RispostaTroncata se
    stop_type=='limit' o truncated==True - MAI restituisce testo tagliato in
    silenzio (vedi motivazione nel docstring del modulo).

    repeat_penalty: None (default, comportamento invariato per i chiamanti
    esistenti) = usa il default nativo di llama.cpp. Trovato dal vivo
    (2026-08-19, estrazione sull'atto reale di prova) che SENZA una penalita' di
    ripetizione esplicita, a temperature bassa (0.1, usata per l'estrazione
    "asettica" in estrazione_atto.py) il modello puo' degenerare in una
    sequenza numerica ripetitiva fabbricata (es. "art. 1235 c.c." ...
    "art. 1264 c.c." in sequenza, nessuno dei quali presente nel testo vero)
    invece di fermarsi - verificato che repeat_penalty=1.3 riduce
    drasticamente il fenomeno sullo stesso prompt che l'aveva prodotto (da
    60 citazioni fabbricate a 3). Non elimina la fabbricazione da solo (le 3
    residue erano comunque finte) - vedi anche l'istruzione esplicita
    "non inventare" aggiunta a PROMPT_CITAZIONI/PROMPT_ECCEZIONI, la
    combinazione dei due e' il fix, non uno dei due da solo.

    seed: None (default) = seed casuale scelto dal server, comportamento
    invariato per i chiamanti esistenti. L'entry point della pipeline ne
    impone SEMPRE uno e lo registra in meta.esecuzione: senza un seed
    fissato due corse non sono riproducibili nemmeno a parita' di modello,
    prompt e temperatura, e un golden set costruito su corse non
    riproducibili non misura il sistema, misura il rumore."""
    import requests

    # cache_prompt: false su OGNI chiamata (2026-08-25) - il default di
    # llama-server e' true. Trovato dal vivo che e' la causa del residuo
    # di stato fra richieste sullo stesso processo server: stesso prompt,
    # stesso seed, tre chiamate di fila su un server appena avviato NON
    # davano lo stesso risultato (la prima, senza nulla in cache, 15 item
    # degeneri; la seconda e la terza, che riusano il prefisso in cache,
    # 2 item - identiche fra loro ma diverse dalla prima). Con
    # cache_prompt:false esplicito, le stesse tre chiamate sono risultate
    # identiche byte per byte, tutte e tre - stesso tempo (~46s) di quella
    # che prima era "la prima" (l'unica senza riuso di cache). Il costo e'
    # reale (le chiamate che PRIMA beneficiavano del riuso, stesso prompt
    # o prefisso condiviso, ora ricalcolano sempre da zero) ma la
    # riproducibilita' del contratto (seed fissato = stessa corsa) vale
    # piu' della velocita' su una macchina mono-utente senza vincoli di
    # tempo (vedi DEPLOY.md).
    payload = {"prompt": prompt, "n_predict": n_predict, "temperature": temperature, "cache_prompt": False}
    if json_schema is not None:
        payload["json_schema"] = json_schema
    if repeat_penalty is not None:
        payload["repeat_penalty"] = repeat_penalty
    if seed is not None:
        payload["seed"] = seed

    resp = requests.post(f"{base_url}/completion", json=payload, timeout=timeout)
    resp.raise_for_status()
    dati = resp.json()
    contenuto = dati.get("content", "")

    if dati.get("stop_type") == "limit":
        raise RispostaTroncata("limit", n_predict, contenuto)
    if dati.get("truncated"):
        raise RispostaTroncata("context_overflow", n_predict, contenuto)

    return contenuto


def completa_ripulendo_ragionamento(
    base_url: str,
    prompt: str,
    n_predict: int = 1024,
    temperature: float = 0.1,
    json_schema: dict | None = None,
    timeout: int = TIMEOUT_DEFAULT_SECONDI,
    seed: int | None = None,
) -> str:
    """Come completa(), ma scarta un eventuale blocco <think>...</think> prima
    di restituire il testo - per quando si vuole solo l'esito finale di un
    modello "ragionante" (Qwen3 e successivi), non il ragionamento visibile.
    Se il modello non produce <think>, e' un no-op. Il troncamento viene
    comunque rilevato PRIMA di questo scarto (RispostaTroncata si applica al
    testo grezzo, non a quello ripulito) - un blocco <think> troncato a meta'
    fa comunque fallire la chiamata, non produce un testo ripulito ma vuoto
    che sembra un successo."""
    testo = completa(base_url, prompt, n_predict=n_predict, temperature=temperature,
                      json_schema=json_schema, timeout=timeout, seed=seed)
    return _THINK_BLOCK_RE.sub("", testo).strip()


def conta_token(base_url: str, testo: str, timeout: int = 60) -> int:
    """Numero di token REALE secondo il tokenizer del GGUF caricato
    (endpoint /tokenize di llama-server) - non una stima dai caratteri.
    Usato da segmenta_atto.py per decidere dove tagliare un atto lungo
    rispettando il budget di contesto vero, non un'approssimazione (verificato
    che 4 caratteri/token, la stima grezza comune, sottostima parecchio
    sull'italiano giuridico - misurato 24092 caratteri = 7647 token reali
    sull'atto reale di prova, non i ~6023 che la stima darebbe)."""
    import requests

    resp = requests.post(f"{base_url}/tokenize", json={"content": testo}, timeout=timeout)
    resp.raise_for_status()
    return len(resp.json()["tokens"])


def proprieta_server(base_url: str, timeout: int = 30) -> dict:
    """Proprieta' REALI dell'istanza in ascolto (endpoint /props): modello
    caricato e contesto effettivo.

    Ritorna {"modello": str|None, "n_ctx": int|None, "total_slots": int|None,
    "build_info": str|None}. Serve a due cose che non si possono ricavare
    da una costante scritta in uno script:

    1. registrare in `meta.esecuzione` il modello e il contesto DAVVERO
       usati - NUM_CTX in esegui_locale_llamaserver.py e' quello che lo
       script passerebbe se fosse lui ad avviare il server, ma il server
       puo' essere gia' acceso da prima con parametri diversi (e' anzi il
       caso normale: llama-server resta residente fra una corsa e
       l'altra);
    2. calcolare il tetto oltre il quale un prompt verrebbe troncato in
       silenzio.

    I campi di /props hanno cambiato posizione fra le versioni di
    llama.cpp: si cercano in piu' punti e si tollera l'assenza (None)
    invece di far fallire la corsa per un dato diagnostico. Il chiamante
    decide se un n_ctx sconosciuto sia accettabile - per il controllo di
    budget NON lo e', e l'entry point lo tratta come tale."""
    import requests

    risposta = requests.get(f"{base_url}/props", timeout=timeout)
    risposta.raise_for_status()
    dati = risposta.json()

    impostazioni = dati.get("default_generation_settings") or {}
    n_ctx = impostazioni.get("n_ctx") or dati.get("n_ctx")
    modello = (
        dati.get("model_path")
        or dati.get("model")
        or impostazioni.get("model")
    )
    total_slots = dati.get("total_slots")
    return {
        "modello": Path(modello).name if modello else None,
        # Il PERCORSO INTERO, non solo il nome. Tenere il solo nome
        # sembrava piu' pulito e rendeva impossibile calcolare lo sha256
        # del GGUF: l'entry point ne faceva un `Path` relativo alla
        # cartella di lavoro, il file non c'era, e ogni corsa registrava
        # "modello non raggiungibile da questa macchina" - su una
        # macchina dove il modello c'e'. Risultato: la proprieta' 1 della
        # pipeline (riproducibilita': nome + sha256 del GGUF) non era mai
        # soddisfatta, e due modelli diversi con lo stesso nome file
        # producevano meta.esecuzione identici.
        "modello_percorso": str(modello) if modello else None,
        "n_ctx": int(n_ctx) if isinstance(n_ctx, (int, float)) else None,
        # total_slots: determina se il batching continuo puo' mischiare
        # richieste diverse nello stesso passo di decodifica - la causa
        # sospettata (poi confermata infondata) di una non-riproducibilita'
        # misurata su Fase 1. Registrato comunque: la configurazione del
        # server e' un fattore di riproducibilita' quanto il modello.
        "total_slots": int(total_slots) if isinstance(total_slots, (int, float)) else None,
        "build_info": dati.get("build_info") if isinstance(dati.get("build_info"), str) else None,
    }


def completa_json(
    base_url: str,
    prompt: str,
    schema: dict,
    n_predict: int = 2048,
    temperature: float = 0.7,
    timeout: int = TIMEOUT_DEFAULT_SECONDI,
    repeat_penalty: float | None = None,
    seed: int | None = None,
) -> dict:
    """completa() + parsing JSON, per le chiamate vincolate da schema
    (generazione strutturata, Fase 1 ed Fase 3). Scarta un eventuale blocco
    <think> PRIMA del parsing - difensivo: in teoria la grammatica vincola
    l'intero output a JSON valido fin dal primo token, quindi <think> non
    dovrebbe poter comparire, ma non e' un'assunzione da cui dipendere
    ciecamente (ipotesi da verificare sul bug 2, vedi README) - se il
    vincolo lascia comunque passare un preambolo di ragionamento, va
    scartato qui invece di far fallire il parsing con un errore fuorviante.

    Se il parsing fallisce dopo lo scarto del blocco <think> ED una
    risposta NON troncata (stop_type diverso da 'limit'), è un errore
    genuino da propagare, non un caso da silenziare con un valore di
    default - un JSON strutturalmente valido ma vuoto sarebbe indistinguibile
    da un fallimento reale se qui si restituisse {}."""
    import json as _json

    testo = completa(base_url, prompt, n_predict=n_predict, temperature=temperature,
                      json_schema=schema, timeout=timeout, repeat_penalty=repeat_penalty, seed=seed)
    testo_ripulito = _THINK_BLOCK_RE.sub("", testo).strip()
    return _json.loads(testo_ripulito)
