"""
Estrae citazioni normative da testo libero (es. una risposta generata dal
modello), non da un altro testo normativo (quello è il compito di
references.py, usato per costruire il grafo). Stesso pattern di citazione,
uso diverso: qui non c'è un "articolo sorgente" da cui ereditare il codice se
manca il qualificatore esplicito - la citazione può comparire ovunque nel
testo, isolata.

Per ogni citazione trovata, ritorna anche il "contesto" (la frase che la
contiene): è il testo che verify.py userà come tema_atteso per il controllo
semantico - l'idea è la stessa cosa che farebbe un revisore umano, leggere la
frase e controllare se l'articolo citato dice davvero quello che la frase
afferma.
"""

import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))  # references.py resta condiviso in src/
from references import CODE_QUALIFIER_MAP, REF_PATTERN, _normalize_numero, _normalize_qualifier

# Confine di frase: punto/punto esclamativo/punto interrogativo seguiti da
# spazio o fine riga, oppure newline. Euristica semplice, non un tokenizzatore
# linguistico - sufficiente per isolare il contesto locale di una citazione.
CONFINE_FRASE_RE = re.compile(r"[.!?](?:\s|$)|\n")

# Se il testo non specifica il codice ("art. 2946" nudo), si assume Codice
# Civile: è di gran lunga il default implicito più comune nel linguaggio
# giuridico italiano corrente, ed è anche il codice più grande del nostro
# corpus. Segnalato esplicitamente (codice_inferito=True) perché è
# un'assunzione, non un fatto letto dal testo - il chiamante può scegliere di
# non fidarsene.
CODICE_DEFAULT_SE_ASSENTE = "codice_civile"


@dataclass
class CitazioneTrovata:
    numero: str
    codice: str
    codice_inferito: bool  # True se il codice non era esplicito nel testo ed è stato assunto
    contesto: str  # la frase che contiene la citazione
    posizione: int  # offset carattere nel testo originale


def _contesto_attorno(testo: str, start: int, end: int) -> str:
    inizio_frase = 0
    for m in CONFINE_FRASE_RE.finditer(testo, 0, start):
        inizio_frase = m.end()
    m_fine = CONFINE_FRASE_RE.search(testo, end)
    fine_frase = m_fine.start() + 1 if m_fine else len(testo)
    return testo[inizio_frase:fine_frase].strip()


def estrai_citazioni_da_testo(testo: str) -> list[CitazioneTrovata]:
    trovate = []
    visti = set()  # dedup su (codice, numero, contesto) - la stessa citazione ripetuta nella stessa frase non aggiunge informazione
    for match in REF_PATTERN.finditer(testo):
        numero_raw, _seguenti_raw, qualifier_raw = match.groups()
        codice = _normalize_qualifier(qualifier_raw)
        codice_inferito = codice is None
        if codice is None:
            codice = CODICE_DEFAULT_SE_ASSENTE

        contesto = _contesto_attorno(testo, match.start(), match.end())
        numero = _normalize_numero(numero_raw)

        chiave = (codice, numero, contesto)
        if chiave in visti:
            continue
        visti.add(chiave)

        trovate.append(
            CitazioneTrovata(
                numero=numero,
                codice=codice,
                codice_inferito=codice_inferito,
                contesto=contesto,
                posizione=match.start(),
            )
        )
    return trovate


# --- Citazioni di giurisprudenza (Massime) - gap dichiarato nel modulo fino
# ad ora (vedi redazione.py: "extract_citations.py non ha un pattern per
# quel formato"). Chiuso qui: pattern per ufficio + tipo provvedimento +
# data (lo stesso formato usato da _citazione_breve() in
# constrained_decoding.py per le Massime, quindi il formato che il MODELLO
# STESSO produce quando cita correttamente - la priorità pratica immediata
# è verificare le proprie generazioni, non ancora un atto di controparte
# reale con citazioni "Cass. n. X/anno", formato diverso e non ancora visto
# su un esempio reale, vedi nota in redazione.py).

_UFFICIO_RE = (
    r"(?:corte\s+(?:suprema\s+di\s+)?cassazione|cass\.?"
    r"|corte\s+(?:d['’]|di\s+)?appello\s+di\s+[a-zà-ù]+|c\.\s?app\.?\s+[a-zà-ù]+"
    r"|tribunale\s+di\s+[a-zà-ù]+|trib\.?\s+[a-zà-ù]+)"
)
_TIPO_PROVVEDIMENTO_RE = r"(?:sentenza|sent\.?|ordinanza|ord\.?|decreto|decr\.?)"
_DATA_RE = r"(?:\d{1,2}\s*[/.\-]\s*\d{1,2}\s*[/.\-]\s*\d{4}|\d{1,2}\s+[a-zà-ù]+\s+\d{4})"

GIURISPRUDENZA_PATTERN = re.compile(
    rf"(?P<ufficio>{_UFFICIO_RE})\s*,?\s*"
    rf"(?P<tipo>{_TIPO_PROVVEDIMENTO_RE})?\s*"
    rf"(?:n\.?\s*(?P<numero_sentenza>\d+(?:/\d{{2,4}})?))?\s*"
    rf"(?:del\s+)?(?P<data>{_DATA_RE})?",
    re.IGNORECASE,
)


@dataclass
class CitazioneGiurisprudenzaTrovata:
    ufficio: str
    tipo_provvedimento: str | None
    data: str | None
    numero_sentenza: str | None  # presente in un atto reale ("Cass. n. 12345/2020"), MAI nei dati BDP nel grafo - vedi nota sopra
    contesto: str
    posizione: int


def estrai_citazioni_giurisprudenza_da_testo(testo: str) -> list[CitazioneGiurisprudenzaTrovata]:
    """Estrae citazioni di giurisprudenza da testo libero - stesso principio
    di estrai_citazioni_da_testo() per gli articoli, formato diverso.

    Una citazione è considerata trovata anche con solo l'ufficio (tipo/data
    assenti) - il chiamante (verify.py) decide se è verificabile: senza
    almeno tipo+data non c'è modo di cercarla nel grafo (le Massime BDP non
    hanno un numero di sentenza separato, vedi nota in
    constrained_decoding.py._citazione_breve), va segnalata come "non
    verificabile", non silenziosamente ignorata."""
    trovate = []
    visti = set()
    for match in GIURISPRUDENZA_PATTERN.finditer(testo):
        ufficio = re.sub(r"\s+", " ", match.group("ufficio").strip())
        tipo = match.group("tipo")
        data = match.group("data")
        numero_sentenza = match.group("numero_sentenza")

        if tipo is None and data is None and numero_sentenza is None:
            continue  # solo l'ufficio, senza nessun altro dato - troppo generico per essere una citazione (es. "la banca" in "la Corte d'Appello di Firenze ha stabilito che...")

        contesto = _contesto_attorno(testo, match.start(), match.end())
        chiave = (ufficio.lower(), tipo, data, numero_sentenza, contesto)
        if chiave in visti:
            continue
        visti.add(chiave)

        trovate.append(
            CitazioneGiurisprudenzaTrovata(
                ufficio=ufficio,
                tipo_provvedimento=tipo,
                data=data,
                numero_sentenza=numero_sentenza,
                contesto=contesto,
                posizione=match.start(),
            )
        )
    return trovate
