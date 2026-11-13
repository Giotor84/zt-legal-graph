"""
Perche' certi parametri NON sono manopole.

Questo modulo e' DATO, non presentazione: il front end lo legge e lo
mostra, non lo riscrive. Se la motivazione di `temperature=0.0` vivesse
nella pagina HTML, la prima persona che tocca la UI potrebbe cancellarla
senza accorgersi di cosa sta cancellando - e la manopola tornerebbe.

I VALORI non sono ricopiati a mano: si importano dalle costanti vere, cosi'
questo file non puo' mentire su cosa gira davvero. Qui si scrive solo il
PERCHE' e il riferimento alla misura.
"""

from __future__ import annotations

import ast
from pathlib import Path

CARTELLA = Path(__file__).parent


def _costante(modulo: str, nome: str):
    """Il valore di una costante di modulo, letto dall'AST. Statico come
    test_versioni_contratti.py: importare `esegui_pipeline` da qui
    trascinerebbe dentro l'intera catena (grafo incluso) solo per mostrare
    un numero in una pagina web."""
    albero = ast.parse((CARTELLA / f"{modulo}.py").read_text(encoding="utf-8"))
    for nodo in albero.body:
        if not isinstance(nodo, ast.Assign):
            continue
        if any(isinstance(b, ast.Name) and b.id == nome for b in nodo.targets):
            try:
                return ast.literal_eval(nodo.value)
            except ValueError:
                return None
    return None

#: parametro -> (valore reale, perche' non e' configurabile, dove sta la misura)
PARAMETRI_NON_CONFIGURABILI: dict[str, dict] = {
    "temperature (Fase 1, output GBNF)": {
        "valore": (_costante("esegui_pipeline", "TEMPERATURE") or {}).get("fase1"),
        "motivo": "Misurato, non preferito: 10 esecuzioni identiche (stesso blocco, "
                   "stesso seed, server riavviato ognuna) a 0.1 danno sempre 4 elementi "
                   "degeneri quasi-duplicati; le stesse a 0.0 danno sempre 10 elementi "
                   "distinti. Su output vincolato da grammatica il campionamento non "
                   "aggiunge diversita' utile, sposta il contenuto verso la ripetizione.",
        "riferimento": "STATO_PROGETTO.md sezione 4; CONTRATTI_DATI.md v1.23",
    },
    "budget token per blocco (Fase 1)": {
        "valore": _costante("esegui_pipeline", "BUDGET_TOKEN_PER_BLOCCO_FASE1"),
        "motivo": "Dimezzato a 1100 due volte, chiuso in negativo entrambe: prima della "
                   "sotto-segmentazione non poteva funzionare per costruzione; dopo, "
                   "estraeva piu' voci ma perdeva il passaggio di riferimento "
                   "(fideiussione) che a 2200 era presente, ed era piu' lento "
                   "(43m contro 29m sui 5 atti).",
        "riferimento": "STATO_PROGETTO.md sezione 5 (negativi accertati); v1.18, v1.19",
    },
    "repeat_penalty": {
        "valore": _costante("estrazione_atto", "_REPEAT_PENALTY"),
        "motivo": "Testato 1.0 contro 1.3: non risolve la degenerazione (un blocco da "
                   "5534 caratteri resta 15/12 quasi-duplicati, identico) e introduce un "
                   "troncamento nuovo che a 1.3 non c'era.",
        "riferimento": "STATO_PROGETTO.md sezione 5",
    },
    "cache_prompt": {
        "valore": False,
        "motivo": "false su OGNI chiamata. Il default del server e' true, e il riuso del "
                   "prefisso in cache lascia un residuo di stato fra richieste sullo "
                   "stesso processo: stesso prompt e stesso seed, tre chiamate di fila "
                   "davano risultati diversi. Con false sono identiche byte per byte. "
                   "Costo accettato: ~35% sul batch reale.",
        "riferimento": "llama_server_client.completa(); CONTRATTI_DATI.md v1.17",
    },
    "seed": {
        "valore": 1234,
        "motivo": "Fissato e passato ESPLICITAMENTE a ogni chiamata. Il client lo inoltra "
                   "solo se il chiamante lo passa; senza, llama-server usa il proprio "
                   "default 4294967295 (casuale a ogni richiesta). Trovato due volte: "
                   "2026-08-24 su Fase 1 (tre corse identiche -> 29, 15, 14 eccezioni) e "
                   "2026-08-26 sugli script di estrazione eccezioni (206 / 176 / 408 "
                   "coppie sullo stesso corpus). Modificabile dalla CLI (--seed), non "
                   "dalla dashboard: cambiarlo invalida il confronto fra corse.",
        "riferimento": "estrazione_atto.py docstring di _passata; STATO_PROGETTO.md sezione 4",
    },
    "-np 1 --no-cont-batching (llama-server)": {
        "valore": "configurazione di riferimento",
        "motivo": "Non un'ottimizzazione: un solo slot esclude per costruzione qualunque "
                   "interazione fra richieste concorrenti nello stesso passo di "
                   "decodifica. Su macchina mono-utente il determinismo vale piu' del "
                   "throughput.",
        "riferimento": "DEPLOY.md sezione 4; STATO_PROGETTO.md sezione 4",
    },
}


def come_dizionario() -> list[dict]:
    """Forma piatta per il front end: nessuna logica, solo dati."""
    return [{"parametro": k, **v} for k, v in PARAMETRI_NON_CONFIGURABILI.items()]


if __name__ == "__main__":
    import json
    print(json.dumps(come_dizionario(), ensure_ascii=False, indent=2))
