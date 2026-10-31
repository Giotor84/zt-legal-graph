# -*- coding: utf-8 -*-
"""Il registro delle parti: chi e' creditore e chi debitore, provvedimento
per provvedimento, con la prova nel testo.

Sostituisce la tabella a mano che traduceva il ruolo processuale in lato
(opponente -> debitore, appellante -> debitore, ...). Quella tabella e' un
giudizio giuridico travestito da normalizzazione, e sul corpus dissente dal
testo nel 5,8% dei casi in cui entrambi rispondono - dopo che tre inversioni
sono state tolte dal codice. Prima delle correzioni il disaccordo era il 17%.

La lettura sta tutta in `pipeline_confutazione/parti_del_giudizio.py`, che
non importa ne' il grafo ne' lo store: qui c'e' solo il giro sui nodi e la
scrittura del file.

Sola lettura sul grafo. Nessun modello coinvolto, in nessun punto.

Uso:
    python src/registro_parti.py --grafo data/graph/grafo.gpickle
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import pickle
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "pipeline_confutazione"))

import parti_del_giudizio as pdg  # noqa: E402

GRAFO_DEFAULT = ROOT / "data" / "graph" / "grafo.gpickle"
USCITA_DEFAULT = ROOT / "data" / "parti" / "registro_parti.json"

#: Quando l'epigrafe manca (129 provvedimenti su 775 non ce l'hanno come
#: campo separato), le parti si cercano nella testa del testo integrale:
#: e' li' che l'epigrafe sta comunque, solo non ritagliata.
TESTA_DEL_TESTO = 3000


def sha256_file(percorso: Path) -> str:
    digest = hashlib.sha256()
    with open(percorso, "rb") as sorgente:
        for blocco in iter(lambda: sorgente.read(1 << 20), b""):
            digest.update(blocco)
    return digest.hexdigest()


#: Dove finisce l'epigrafe e comincia l'atto. Serve solo al ripiego sul
#: testo integrale: le conclusioni e il fatto sono pieni di parole di
#: ruolo usate in prosa ("respingere l'appello", "gli opponenti
#: chiedevano"), che non attribuiscono un ruolo a nessuno.
FINE_DELL_EPIGRAFE = re.compile(
    r"\b(conclusion[ie]|svolgimento|fatto\s+e\s+diritto|ragioni\s+(?:di\s+fatto|della)"
    r"|motivi\s+della|in\s+fatto|p\.?\s*q\.?\s*m\.?)\b",
    re.IGNORECASE,
)


def epigrafe(dati: dict) -> str:
    """L'intestazione, o la testa del testo integrale quando manca."""
    dichiarata = (dati.get("intestazione") or "").strip()
    if dichiarata:
        return dichiarata
    testa = (dati.get("testo_integrale") or "")[:TESTA_DEL_TESTO]
    taglio = FINE_DELL_EPIGRAFE.search(testa)
    return testa[:taglio.start()] if taglio else testa


def costruisci(grafo) -> dict:
    registri, conteggi = {}, collections.Counter()
    for nodo, dati in grafo.nodes(data=True):
        if "dispositivo" not in dati:
            continue
        registro = pdg.registro(epigrafe(dati), dati.get("dispositivo") or "")
        registri[nodo] = registro
        conteggi["provvedimenti"] += 1
        conteggi["direzione_" + (registro["direzione"]["verso"] or "ignota")] += 1
        for voce in registro["parti"].values():
            conteggi["parti"] += 1
            conteggi["lato_" + (voce["lato"] or "ignoto")] += 1
            conteggi["fiducia_" + voce["fiducia"]] += 1
    return {"conteggi": dict(conteggi.most_common()), "registri": registri}


def scrivi(grafo, percorso_grafo: Path, uscita: Path) -> dict:
    esito = costruisci(grafo)
    documento = {
        "meta": {
            "generato_il": date.today().isoformat(),
            "grafo": str(percorso_grafo),
            "sha256_grafo": sha256_file(percorso_grafo),
            "distanza_massima_ruolo": pdg.DISTANZA_MASSIMA_RUOLO,
            "finestra_condanna": pdg.FINESTRA_CONDANNA,
            "avviso": (
                "Il lato NON e' assunto dal ruolo processuale: e' letto dal "
                "dispositivo e dall'epigrafe, e ogni attribuzione porta la fetta "
                "di testo che la prova. Dove i criteri discordano il lato resta "
                "nullo: una controdeduzione presa dalla parte sbagliata e' un "
                "errore invisibile, e vale meno di un'astensione dichiarata."
            ),
            **esito["conteggi"],
        },
        "registri": esito["registri"],
    }
    uscita.parent.mkdir(parents=True, exist_ok=True)
    uscita.write_text(json.dumps(documento, ensure_ascii=False, indent=1),
                      encoding="utf-8")
    return documento


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--grafo", type=Path, default=GRAFO_DEFAULT)
    parser.add_argument("--uscita", type=Path, default=USCITA_DEFAULT)
    argomenti = parser.parse_args()

    with open(argomenti.grafo, "rb") as sorgente:
        grafo = pickle.load(sorgente)
    documento = scrivi(grafo, argomenti.grafo, argomenti.uscita)

    meta = documento["meta"]
    print("provvedimenti letti: %d" % meta["provvedimenti"])
    print("parti: %d  -  creditore %d, debitore %d, non deciso %d"
          % (meta["parti"], meta.get("lato_creditore", 0),
             meta.get("lato_debitore", 0), meta.get("lato_ignoto", 0)))
    print("direzione: favor creditoris %d, favor debitoris %d, ignota %d"
          % (meta.get("direzione_creditore", 0), meta.get("direzione_debitore", 0),
             meta.get("direzione_ignota", 0)))
    print("attribuzioni discordi (dichiarate, non scelte): %d"
          % meta.get("fiducia_discordi", 0))
    print("Scritto in %s" % argomenti.uscita)


if __name__ == "__main__":
    main()
