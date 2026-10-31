"""
Rendering deterministico dei due documenti finali, a partire dai file di
contratto. Nessuna chiamata LLM: la bozza e' un RENDERING di
`03_atto.json`, non un output separato del modello.

Due documenti con DESTINATARI DIVERSI, e per questo due file e non uno:

1. `03_bozza_atto.txt` - la prosa pulita, pronta da rifinire e depositare.
   Nessun rumore diagnostico: un avvocato che deposita non deve cancellare
   a mano le note di sistema, e una nota dimenticata dentro un atto
   depositato e' un incidente vero.
2. `00_memoria_analisi.md` - il lavoro mostrato, uso interno. I buchi in
   TESTA, non in fondo: un processo asincrono deve dichiarare cosa NON ha
   fatto, e l'avvocato non e' davanti allo schermo per accorgersi di
   un'omissione.
"""

from __future__ import annotations

from datetime import datetime


def rendi_bozza(atto: dict, dossier: dict) -> str:
    """La bozza depositabile.

    L'ordine dei motivi e' quello di `coerenza.ordine_motivi`, che dal
    contratto 1.27 calcola Python per rango processuale: non dipende piu'
    dall'esito della chiamata, quindi non e' piu' subordinato ad
    `applicata` - che ora riguarda la sola ricerca dei conflitti. Senza
    passata (`coerenza = null`, meno di due motivi) resta l'ordine del
    dossier. Il FILE `03_atto.json` conserva sempre l'ordine del dossier
    (stabilita' referenziale: le `affermazioni` puntano ai paragrafi per
    id, e riordinare il file spezzerebbe la corrispondenza con gli
    esiti); e' solo il RENDERING che riordina."""
    motivi_per_id = {m["eccezione_id"]: m for m in atto["motivi"]}
    coerenza = atto.get("coerenza")
    if coerenza:
        ordine = coerenza["ordine_motivi"]
    else:
        ordine = [m["eccezione_id"] for m in atto["motivi"]]

    righe = ["FATTO", ""]
    if atto["fatto"]["esito"] == "trattata":
        for paragrafo in atto["fatto"]["paragrafi"]:
            righe.extend([paragrafo["testo"], ""])
    else:
        # Stessa regola dei motivi non trattati sotto: un'astensione o un
        # guasto dichiarati dentro un atto depositabile sarebbero
        # un'ammissione scritta al giudice. Il motivo sta nella memoria.
        righe.extend(["(Sezione FATTO non redatta: vedi la memoria di analisi.)", ""])

    righe.extend(["", "MOTIVI DI DIRITTO", ""])
    numero = 0
    for eccezione_id in ordine:
        motivo = motivi_per_id[eccezione_id]
        if motivo["esito"] != "trattata":
            # Gli esiti non trattati NON entrano nella bozza depositabile:
            # sono voci della memoria di analisi. Un'astensione dichiarata
            # dentro un atto sarebbe un'ammissione scritta al giudice.
            continue
        numero += 1
        righe.append(f"{numero}. ")
        for paragrafo in motivo["paragrafi"]:
            righe.extend([paragrafo["testo"], ""])
        righe.append("")

    if numero == 0:
        righe.extend(["(Nessun motivo di diritto e' stato redatto: vedi la memoria di analisi.)", ""])

    righe.extend(["", "CONCLUSIONI", "", atto["conclusioni"]["testo"], ""])
    return "\n".join(righe)


def rendi_memoria(estrazione: dict, dossier: dict | None, atto: dict | None,
                   problemi_verifica: list[str], note_esecuzione: list[str],
                   spunti: list[dict]) -> str:
    """La memoria di analisi. Tutto cio' che non e' andato come previsto
    sta nelle prime righe."""
    righe = [
        "# Memoria di analisi",
        "",
        f"*Generata automaticamente il {datetime.now().strftime('%Y-%m-%d %H:%M')} - uso interno, non depositare.*",
        "",
    ]

    esecuzione = estrazione["meta"]["esecuzione"]
    righe.extend([
        "## Identita' della corsa (per riprodurla)",
        "",
        f"- **id_esecuzione**: `{esecuzione['id_esecuzione']}`",
        f"- **avviata il**: {esecuzione['avviata_il']}",
        f"- **contratti**: v{esecuzione['versione_contratti']}",
        f"- **modello**: {_descrivi_modello(esecuzione['modello'])}",
        f"- **n_ctx**: {esecuzione['n_ctx'] or 'non rilevato'} · **seed**: {esecuzione['seed']}",
        f"- **temperature**: {esecuzione['temperature_per_passo'] or 'nessuna chiamata LLM'}",
        f"- **grafo**: {_descrivi_grafo(esecuzione['grafo'])}",
        f"- **sha256 del testo dell'atto**: `{esecuzione['sha256_atto_input']}`",
        "",
    ])

    righe.extend(["## Cosa questo report NON copre (leggere prima del resto)", ""])
    voci = ([b["testo"] for b in estrazione["buchi"]]
            + list(note_esecuzione) + list(problemi_verifica))
    if dossier is not None:
        voci.extend(_buchi_del_dossier(dossier))
    if atto is not None:
        voci.extend(_buchi_dell_atto(atto))
    if not voci:
        righe.append("Nessun buco dichiarato in questa esecuzione.")
    else:
        righe.extend(f"- {voce}" for voce in voci)
    righe.append("")

    if atto is not None:
        righe.extend(_sezione_coerenza(atto))

    righe.extend(_sezione_struttura(estrazione))
    righe.extend(_sezione_eccezioni(estrazione, dossier, atto))

    righe.extend(_sezione_spunti(spunti))

    if dossier is not None and dossier["fonti_scartate"]:
        righe.extend(["## Fonti raccomandate dalle regole ma NON risolte nel grafo", "",
                       "Da verificare a mano. Non sono citabili in automatico: probabilmente sono "
                       "giurisprudenza reale non ancora nel corpus indicizzato.", ""])
        for scartata in dossier["fonti_scartate"]:
            righe.append(f"- **{scartata['citazione_breve']}** ({scartata['ruolo']}, "
                          f"{scartata['eccezione_id']}): {scartata['motivo']}")
        righe.append("")

    return "\n".join(righe)


def _descrivi_modello(modello: dict | None) -> str:
    if modello is None:
        return "nessuno (nessuna chiamata LLM in questa corsa)"
    impronta = modello["sha256"][:16] + "..." if modello["sha256"] else "sha256 non calcolabile"
    return f"{modello['nome_file']} (`{impronta}`)"


def _descrivi_grafo(grafo: dict | None) -> str:
    if grafo is None:
        return "non usato in questa corsa"
    impronta = grafo["sha256"][:16] + "..." if grafo["sha256"] else "sha256 non calcolato"
    return f"{grafo['percorso']} - {grafo['n_nodi']} nodi (`{impronta}`)"


def _buchi_del_dossier(dossier: dict) -> list[str]:
    voci = []
    for esito in dossier["esiti"]:
        if esito["motivo_astensione"]:
            voci.append(f"[Fase 2] {esito['eccezione_id']} - astensione: {esito['motivo_astensione']}")
        if esito["motivo_errore"]:
            voci.append(f"[Fase 2] {esito['eccezione_id']} - **GUASTO** (non un'astensione): "
                         f"{esito['motivo_errore']}")
    return voci


def _buchi_dell_atto(atto: dict) -> list[str]:
    voci = []
    fatto = atto["fatto"]
    if fatto["esito"] == "astensione_modello":
        voci.append(f"[Fase 3] FATTO - il modello si e' astenuto: {fatto['dichiarazione_astensione']}")
    elif fatto["esito"] == "errore_tecnico":
        voci.append(f"[Fase 3] FATTO - **GUASTO** (non un'astensione): {fatto['motivo_errore']}")
    for motivo in atto["motivi"]:
        if motivo["esito"] == "astensione_modello":
            voci.append(f"[Fase 3] {motivo['eccezione_id']} - il modello si e' astenuto: "
                         f"{motivo['dichiarazione_astensione']}")
        elif motivo["esito"] == "errore_tecnico":
            voci.append(f"[Fase 3] {motivo['eccezione_id']} - **GUASTO** (non un'astensione): "
                         f"{motivo['motivo_errore']}")
    if not atto["meta"]["verifica_post_generazione_superata"]:
        voci.append("**La verifica post-generazione NON e' stata superata**: il file esiste ma NON e' "
                     "pronto per la rifinitura. I problemi sono elencati sopra.")
    return voci


def _sezione_coerenza(atto: dict) -> list[str]:
    """I conflitti in testa, come impone il contratto: sono la cosa che
    l'avvocato deve decidere, e nessuno li ha risolti per lui."""
    coerenza = atto.get("coerenza")
    righe = ["## Coerenza d'insieme dei motivi", ""]
    if coerenza is None:
        righe.extend(["Passata di coerenza NON eseguita (meno di due motivi). "
                       "L'ordine dei motivi nella bozza e' quello del dossier.", ""])
        return righe

    righe.extend([f"Ordine di rendering applicato: {' -> '.join(coerenza['ordine_motivi'])}", "",
                   "Calcolato da Python per rango processuale (rito, preliminari di merito, merito, "
                   "non classificati in coda), stabile dentro il rango: **non e' un ordine generato "
                   "dal modello**, e l'assegnazione di una famiglia a un rango e' una scelta "
                   "giuridica che vive in `ordine_motivi.RANGO_PER_FAMIGLIA`.", ""])

    copertura = coerenza["copertura_conflitti"]
    if not coerenza["applicata"]:
        righe.extend(["**Ricerca dei conflitti NON riuscita**: nessuna finestra ha prodotto un "
                       "risultato utilizzabile. Nessuna coppia di motivi e' stata esaminata - "
                       "il che non significa che non ci siano conflitti.", ""])
        if coerenza["nota"]:
            righe.extend([f"Dettaglio: {coerenza['nota']}", ""])
    elif copertura["coppie_esaminate"] < copertura["coppie_totali"]:
        righe.extend([
            f"Copertura della ricerca conflitti: **{copertura['coppie_esaminate']} coppie esaminate "
            f"su {copertura['coppie_totali']}** ({copertura['finestre_riuscite']} finestre riuscite "
            f"su {copertura['finestre']}). Le coppie non esaminate NON sono state giudicate prive di "
            "conflitto: non sono state guardate.", ""])

    if coerenza["conflitti"]:
        righe.extend(["**Conflitti segnalati - NON risolti automaticamente, la decisione e' tua:**", ""])
        for conflitto in coerenza["conflitti"]:
            righe.append(f"- **{conflitto['tipo']}** fra {conflitto['tra'][0]} e {conflitto['tra'][1]}: "
                          f"{conflitto['descrizione']}")
        righe.append("")
    else:
        righe.extend(["Nessun conflitto segnalato fra i motivi.", ""])
    return righe


def _sezione_struttura(estrazione: dict) -> list[str]:
    struttura = estrazione.get("struttura")
    if not struttura:
        return ["## Struttura processuale", "",
                "Non estratta (passata fallita) - dichiarato fra i buchi.", ""]
    qualita = struttura.get("qualita_parti", {})
    return [
        "## Struttura processuale", "",
        f"- **Tipo atto**: {struttura['tipo_atto']}",
        f"- **Fase processuale**: {struttura['fase_processuale']}",
        f"- **Natura del rapporto**: {struttura['natura_rapporto']}",
        f"- **Durata apertura di credito**: {struttura['durata_apertura_credito']}",
        f"- **Creditore e' cessionario**: {struttura['creditore_e_cessionario']}",
        f"- **Debitore principale**: {qualita.get('debitore_principale')}",
        f"- **Fideiussore presente**: {qualita.get('fideiussore_presente')} "
        f"({qualita.get('qualita_fideiussore')})",
        f"- **Consumatore eccepito**: {qualita.get('consumatore_eccepito')}",
        "",
    ]


def _sezione_eccezioni(estrazione: dict, dossier: dict | None, atto: dict | None) -> list[str]:
    esiti = {e["eccezione_id"]: e for e in (dossier or {}).get("esiti", [])}
    motivi = {m["eccezione_id"]: m for m in (atto or {}).get("motivi", [])}

    righe = [f"## Eccezioni sollevate da controparte ({len(estrazione['eccezioni'])})", ""]
    if not estrazione["eccezioni"]:
        righe.extend(["Nessuna eccezione estratta dall'atto.", ""])
        return righe

    for numero, eccezione in enumerate(estrazione["eccezioni"], start=1):
        eid = eccezione["eccezione_id"]
        anteprima = " ".join(eccezione["testo_letterale"].split())[:100]
        righe.extend([f"### {numero}. {eid} - {anteprima}{'...' if len(anteprima) == 100 else ''}", ""])
        righe.append(f"> {eccezione['testo_letterale']}")
        righe.append("")
        righe.append(f"- **Ancoraggio**: {_descrivi_ancora(eccezione['ancora'])}")
        righe.append(f"- **Posizione dichiarata dal modello** (non verificata): "
                      f"{eccezione['posizione_dichiarata']}")
        righe.append(f"- **Specificita'**: {eccezione['specificita']}")
        righe.append(f"- **Famiglia dichiarata dal modello**: {eccezione['famiglia_probabile']}")

        esito = esiti.get(eid)
        if esito is not None:
            righe.append(f"- **Famiglia classificata**: {esito['famiglia'] or 'NON RICONOSCIUTA'}")
            righe.append(f"- **Esito Fase 2**: `{esito['stato']}`")
            righe.append("")
            righe.append(esito["nota"])
            if esito["contro_argomento"]:
                righe.extend(["", f"**Contro-argomento**: {esito['contro_argomento']} "
                                   f"(consolidamento: {esito['consolidamento'] or 'non specificato'})"])
            if esito["estratti_citabili"]:
                righe.extend(["", "**Estratti citabili in Fase 3**:"])
                for voce in esito["estratti_citabili"]:
                    righe.append(f"  - `{voce['estratto_id']}` ({voce['provenienza']})")
        motivo = motivi.get(eid)
        if motivo is not None:
            righe.extend(["", f"- **Esito Fase 3**: `{motivo['esito']}`, "
                               f"{len(motivo['paragrafi'])} paragrafi generati"])
        righe.append("")
    return righe


def _descrivi_ancora(ancora: dict) -> str:
    stato = ancora["stato"]
    if stato == "ancorata":
        similarita = f", similarita' {ancora['similarita']:.3f}" if ancora["similarita"] is not None else ""
        return (f"`ancorata` ({ancora['corrispondenza']}{similarita}) - "
                f"{ancora['blocco_id']} [{ancora['inizio']}:{ancora['fine']}]")
    if stato == "ancora_ambigua":
        return (f"`ancora_ambigua` - {len(ancora['occorrenze'])} posizioni possibili, "
                "nessuna scelta d'ufficio: serve una lettura umana")
    if stato == "ancora_parziale":
        candidato = ancora["migliore_candidato"]
        return (f"`ancora_parziale` - migliore candidato {candidato['blocco_id']} "
                f"[{candidato['inizio']}:{candidato['fine']}], similarita' {ancora['similarita']:.3f} "
                "(sotto 0.95): non citabile in automatico")
    return f"`non_ancorata` - {ancora['motivo']}"


def _sezione_spunti(spunti: list[dict]) -> list[str]:
    """"Spunti non citati": il retrieval di CAUSA, che dal contratto 1.3
    non entra piu' nel dossier.

    Sono piste di ricerca per l'avvocato, non materiale per il modello: non
    hanno attraversato il confine LLM e nessuna di queste fonti e'
    citabile in automatico nell'atto. Il punteggio di similarita' e' quello
    grezzo dell'indice semantico - serve a ordinare, non e' una misura di
    pertinenza giuridica, e va letto sapendo che il retrieval di questo
    progetto sbaglia (art. 2852 c.c. a rank 648, art. 1936 c.c. a 4963)."""
    if not spunti:
        return []
    righe = [
        "## Spunti non citati", "",
        f"{len(spunti)} fonti che il retrieval semantico ha trovato pertinenti ai fatti di causa nel "
        "loro insieme, e che NON sono nel dossier: nessuna e' stata offerta al modello e nessuna e' "
        "citata nella bozza. Sono piste da valutare a mano.", "",
        "Il punteggio e' la similarita' grezza dell'indice: ordina, non certifica. In questo progetto "
        "il retrieval ha sbagliato in modo documentato (art. 2852 c.c. a rank 648, art. 1936 c.c. a "
        "4963), quindi un punteggio basso non significa \"non pertinente\" e uno alto non significa "
        "\"usabile\".", "",
        "| fonte | tipo | similarita' | di cosa parla |", "|---|---|---:|---|",
    ]
    for spunto in spunti:
        descrizione = " ".join(spunto["descrizione"].split())[:90]
        righe.append(f"| {spunto['citazione_breve']} | {spunto['tipo_nodo']} | "
                     f"{spunto['score']:.3f} | {descrizione} |")
    righe.append("")
    return righe
