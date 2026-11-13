"""Promozione di un grafo candidato a `data/graph/grafo.gpickle`.

NON e' una rinomina. Il grafo e' l'unica fonte di diritto citabile della
pipeline: sostituirlo con `mv` e' un'operazione da cui non si torna
indietro e di cui non resta traccia. Questo script fa tre cose che una
rinomina non fa - verifica il candidato contro il grafo in carica,
archivia il grafo in carica prima di toccarlo, e lascia un record di cosa
e' stato promosso, quando, e con quali numeri.

Rifiuta di scrivere senza `--conferma`: senza quel flag gira in prova,
esegue TUTTI i controlli e stampa cosa farebbe.

## I controlli (tutti bloccanti, nessuno saltabile da riga di comando)

1. Il candidato si carica ed e' un MultiDiGraph.
2. Nessuna classe di nodo sparisce: ogni `tipo_nodo` presente nel grafo in
   carica deve esistere anche nel candidato, con un conteggio non inferiore.
   Un grafo che perde per strada le 185 massime non e' un aggiornamento.
3. Nessun articolo sparisce: ogni nodo Articolo del grafo in carica deve
   esistere nel candidato.
4. Il testo di legge non e' cambiato: per ogni articolo comune, `testo` e
   `testo_raw` devono essere identici byte per byte. Un'ingestione di
   giurisprudenza non ha alcuna ragione di riscrivere il testo di una
   norma; se lo fa, e' un bug, e va visto PRIMA della promozione.
5. Ancoraggio: per ogni arco che dichiara `fonte_campo`, ogni ancora deve
   soddisfare `testo_verbatim == nodo[fonte_campo][inizio:fine]`. E' la
   regola 4 di CLAUDE.md verificata sul prodotto finito, non solo su chi
   lo ha costruito.
6. Nessun arco pendente verso un nodo inesistente.
7. Nessuna forma di arco sconosciuta (BUG-GRAFO-5). Le popolazioni sono
   tre, una per produttore, e `popolazioni_archi.censimento` le riconosce
   dagli attributi. Una quarta forma non farebbe fallire nessun
   consumatore - usano tutti `.get()` con un default - farebbe solo uscire
   conteggi piu' piccoli del vero, e plausibili. Questo e' il momento in
   cui si vede.
8. Ogni `citazione_breve` doppia si scioglie (BUG-GRAFO-4/1). Nel grafo in
   carica 36 citazioni brevi valgono per piu' di un articolo - sono le
   preleggi contro il corpo del codice civile - e per tutte e 36 esiste
   esattamente UN nodo con `is_main_body` vero. E' su quella unicita' che
   `GraphStore._build_lookup` decide chi vince, quindi il giorno in cui
   una collisione ne avesse zero o due, `store.trova` comincerebbe a
   restituire l'articolo sbagliato senza dirlo.
9. Solo se si promuovono anche gli embedding dei segmenti di motivazione:
   la matrice e l'indice hanno lo stesso numero di righe, e ogni node_id
   dell'indice esiste nel candidato ed e' un provvedimento.

## Perche' i segmenti si promuovono INSIEME al grafo

Sono la stessa generazione di dati vista da due lati, e separarli rompe in
un modo che non si vede prima di una corsa: grafo nuovo senza indice nuovo
= i provvedimenti aggiunti restano invisibili al retrieval; indice nuovo
senza grafo nuovo = il retrieval legge `graph.nodes[node_id]` di nodi che
non esistono e solleva. Percio' `--embeddings-segmenti` e
`--indice-segmenti` si passano insieme o non si passano, l'archiviazione
copre anche loro, e la scrittura avviene dopo quella del grafo (un grafo
vecchio con un indice vecchio e' uno stato coerente, il contrario no).

## Cosa NON verifica

Che il contenuto giuridico sia giusto. Nessun controllo automatico lo puo'
fare, ed e' il motivo per cui la promozione resta un comando che una
persona digita.

Uso:
    python src/promuovi_grafo.py --candidato PATH              # prova
    python src/promuovi_grafo.py --candidato PATH --conferma   # promuove
    python src/promuovi_grafo.py --candidato PATH \\
        --embeddings-segmenti PATH.npy --indice-segmenti PATH.json --conferma
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import networkx as nx
import numpy as np

import popolazioni_archi  # BUG-GRAFO-5: le tre forme di arco

ROOT = Path(__file__).parent.parent
DESTINAZIONE_DEFAULT = ROOT / "data" / "graph" / "grafo.gpickle"
ARCHIVIO_DEFAULT = ROOT / "data" / "graph_backup"


class Bocciato(Exception):
    """Un controllo non passato. Nessuna scrittura e' ancora avvenuta."""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blocco in iter(lambda: f.read(1 << 20), b""):
            h.update(blocco)
    return h.hexdigest()


def _tipo(dati: dict) -> str:
    # I nodi Articolo non hanno mai avuto un `tipo_nodo` esplicito - stessa
    # retrocompatibilita' di store._build_lookup().
    return dati.get("tipo_nodo", "articolo")


def _articoli(grafo) -> dict[str, dict]:
    return {n: d for n, d in grafo.nodes(data=True) if _tipo(d) == "articolo"}


def verifica(candidato, in_carica) -> list[str]:
    """Esegue tutti i controlli. Ritorna le righe del referto; solleva
    Bocciato al primo che non passa (con il dettaglio nel messaggio)."""
    referto: list[str] = []

    # 1 - forma
    if not isinstance(candidato, nx.MultiDiGraph):
        raise Bocciato(f"il candidato e' {type(candidato).__name__}, atteso MultiDiGraph")
    referto.append(f"[1] forma: MultiDiGraph, {candidato.number_of_nodes()} nodi, "
                   f"{candidato.number_of_edges()} archi")

    # 2 - nessuna classe di nodo persa
    tipi_prima = Counter(_tipo(d) for _, d in in_carica.nodes(data=True))
    tipi_dopo = Counter(_tipo(d) for _, d in candidato.nodes(data=True))
    persi = {t: (n, tipi_dopo.get(t, 0)) for t, n in tipi_prima.items() if tipi_dopo.get(t, 0) < n}
    if persi:
        raise Bocciato("classi di nodo in calo: " +
                       ", ".join(f"{t} {prima}->{dopo}" for t, (prima, dopo) in persi.items()))
    referto.append("[2] classi di nodo: nessuna in calo")
    for tipo in sorted(set(tipi_prima) | set(tipi_dopo)):
        prima, dopo = tipi_prima.get(tipo, 0), tipi_dopo.get(tipo, 0)
        segno = f"+{dopo - prima}" if dopo != prima else "="
        referto.append(f"      {tipo:24s} {prima:6d} -> {dopo:6d}  ({segno})")

    # 3 - nessun articolo sparito
    art_prima, art_dopo = _articoli(in_carica), _articoli(candidato)
    spariti = set(art_prima) - set(art_dopo)
    if spariti:
        raise Bocciato(f"{len(spariti)} articoli spariti, es.: {sorted(spariti)[:5]}")
    referto.append(f"[3] articoli: {len(art_prima)} tutti presenti nel candidato")

    # 4 - testo di legge immutato
    alterati = [
        n for n in art_prima
        if art_dopo[n].get("testo") != art_prima[n].get("testo")
        or art_dopo[n].get("testo_raw") != art_prima[n].get("testo_raw")
    ]
    if alterati:
        raise Bocciato(f"{len(alterati)} articoli col testo alterato, es.: {alterati[:5]}")
    referto.append("[4] testo di legge: identico su tutti gli articoli comuni")

    # 5 - ancoraggio (regola 4)
    tot = incoerenti = 0
    for u, _v, d in candidato.edges(data=True):
        campo = d.get("fonte_campo")
        if not campo:
            continue
        sorgente = candidato.nodes[u].get(campo) or ""
        for ancora in d.get("ancore", []):
            tot += 1
            if sorgente[ancora["inizio"]:ancora["fine"]] != ancora["testo_verbatim"]:
                incoerenti += 1
    if incoerenti:
        raise Bocciato(f"{incoerenti} ancore su {tot} non combaciano col testo di origine")
    referto.append(f"[5] ancoraggio: {tot} ancore, tutte verbatim sul campo dichiarato")

    # 6 - archi pendenti
    pendenti = [(u, v) for u, v in candidato.edges() if u not in candidato or v not in candidato]
    if pendenti:
        raise Bocciato(f"{len(pendenti)} archi pendenti, es.: {pendenti[:3]}")
    referto.append("[6] archi: nessuno pendente")

    # 7 - nessuna forma di arco sconosciuta (BUG-GRAFO-5)
    censimento = popolazioni_archi.censimento(candidato.edges(data=True))
    if censimento[popolazioni_archi.SCONOSCIUTA]:
        raise Bocciato(
            f"{censimento[popolazioni_archi.SCONOSCIUTA]} archi di una forma "
            "che nessun produttore noto scrive: non farebbero fallire niente, "
            "sparirebbero dai conteggi. Vedi src/popolazioni_archi.py")
    referto.append("[7] forme di arco: solo le tre note")
    for nome in (popolazioni_archi.FRA_ARTICOLI, popolazioni_archi.DA_PROVVEDIMENTO,
                 popolazioni_archi.DA_FONTE_ESTERNA):
        referto.append(f"      {nome:24s} {censimento[nome]:6d}")

    # 8 - ogni citazione breve doppia si scioglie (BUG-GRAFO-4/1)
    per_citazione: dict[str, list[str]] = {}
    for node_id, dati in candidato.nodes(data=True):
        if not dati.get("codice") or not dati.get("citazione_breve"):
            continue
        per_citazione.setdefault(dati["citazione_breve"], []).append(node_id)
    irrisolte = {
        citazione: nodi for citazione, nodi in per_citazione.items()
        if len(nodi) > 1
        and sum(1 for n in nodi if candidato.nodes[n].get("is_main_body")) != 1
    }
    if irrisolte:
        primo = sorted(irrisolte)[:3]
        raise Bocciato(
            f"{len(irrisolte)} citazioni brevi doppie senza un solo "
            f"is_main_body che le sciolga, es.: {primo}. store.trova() "
            "restituirebbe l'articolo sbagliato senza dirlo")
    doppie = sum(1 for nodi in per_citazione.values() if len(nodi) > 1)
    referto.append(f"[8] citazioni brevi: {doppie} doppie, tutte sciolte da "
                   "un solo is_main_body")

    return referto


def verifica_indice_segmenti(candidato, indice: list[dict]) -> str:
    """Controllo 7, solo se si promuovono anche gli embedding dei segmenti.

    L'indice dei segmenti e il grafo devono essere della STESSA generazione.
    Se si promuove il grafo senza l'indice, i provvedimenti nuovi restano
    invisibili al retrieval; se si promuove l'indice senza il grafo, il
    retrieval va a leggere `graph.nodes[node_id]` di nodi che non esistono e
    solleva. Nessuno dei due errori si vede prima di una corsa.

    Qui si verifica il secondo, che e' quello che rompe: ogni node_id
    dell'indice deve esistere nel candidato ed essere un provvedimento."""
    ignoti, non_provvedimenti = set(), set()
    for riga in indice:
        node_id = riga["node_id"]
        if node_id not in candidato:
            ignoti.add(node_id)
        elif candidato.nodes[node_id].get("tipo_nodo") != "provvedimento":
            non_provvedimenti.add(node_id)
    if ignoti:
        raise Bocciato(
            f"l'indice dei segmenti nomina {len(ignoti)} nodi che il grafo candidato non ha, "
            f"es.: {sorted(ignoti)[:2]} - indice e grafo non sono della stessa generazione"
        )
    if non_provvedimenti:
        raise Bocciato(
            f"l'indice dei segmenti nomina {len(non_provvedimenti)} nodi che non sono "
            f"provvedimenti, es.: {sorted(non_provvedimenti)[:2]}"
        )
    coperti = len({r["node_id"] for r in indice})
    totali = sum(1 for _n, d in candidato.nodes(data=True)
                 if d.get("tipo_nodo") == "provvedimento" and d.get("motivazione"))
    return (f"[9] indice segmenti: {len(indice)} segmenti su {coperti} provvedimenti "
            f"(dei {totali} con motivazione), tutti presenti nel candidato")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--candidato", type=Path, required=True, help="Il .gpickle da promuovere")
    parser.add_argument("--destinazione", type=Path, default=DESTINAZIONE_DEFAULT,
                        help=f"Il grafo in carica da sostituire (default: {DESTINAZIONE_DEFAULT})")
    parser.add_argument("--archivio", type=Path, default=ARCHIVIO_DEFAULT,
                        help=f"Radice dell'archivio dei grafi sostituiti (default: {ARCHIVIO_DEFAULT})")
    parser.add_argument("--conferma", action="store_true",
                        help="Senza questo flag lo script gira in PROVA: verifica tutto e non scrive nulla")
    # I due file dei segmenti si promuovono INSIEME al grafo o non si
    # promuovono: sono la stessa generazione di dati vista da due lati, e
    # separarli rompe il retrieval in un modo che non si vede prima di una
    # corsa (vedi verifica_indice_segmenti).
    parser.add_argument("--embeddings-segmenti", type=Path, default=None,
                        help="embeddings_segmenti_provvedimenti.npy costruito SUL candidato")
    parser.add_argument("--indice-segmenti", type=Path, default=None,
                        help="embeddings_segmenti_provvedimenti_index.json costruito SUL candidato")
    args = parser.parse_args()

    if not args.candidato.exists():
        raise SystemExit(f"candidato inesistente: {args.candidato}")
    if not args.destinazione.exists():
        raise SystemExit(f"destinazione inesistente: {args.destinazione} (nulla da sostituire)")
    if bool(args.embeddings_segmenti) != bool(args.indice_segmenti):
        raise SystemExit(
            "--embeddings-segmenti e --indice-segmenti vanno passati insieme: "
            "una matrice senza il suo indice, o viceversa, non e' utilizzabile."
        )
    compagni = []
    if args.embeddings_segmenti:
        for percorso in (args.embeddings_segmenti, args.indice_segmenti):
            if not percorso.exists():
                raise SystemExit(f"file dei segmenti inesistente: {percorso}")
            compagni.append(percorso)

    print(f"candidato:    {args.candidato}")
    print(f"destinazione: {args.destinazione}")
    for c in compagni:
        print(f"insieme a:    {c}")
    print(f"modo:         {'PROMOZIONE' if args.conferma else 'PROVA (nessuna scrittura)'}\n")

    with open(args.candidato, "rb") as f:
        candidato = pickle.load(f)
    with open(args.destinazione, "rb") as f:
        in_carica = pickle.load(f)

    try:
        referto = verifica(candidato, in_carica)
        if compagni:
            indice = json.loads(args.indice_segmenti.read_text(encoding="utf-8"))
            righe_npy = np.load(args.embeddings_segmenti, mmap_mode="r").shape[0]
            if righe_npy != len(indice):
                raise Bocciato(
                    f"la matrice dei segmenti ha {righe_npy} righe e l'indice {len(indice)} voci: "
                    "non si corrispondono, ogni riga dell'indice descrive una riga della matrice"
                )
            referto.append(verifica_indice_segmenti(candidato, indice))
    except Bocciato as e:
        print(f"BOCCIATO: {e}")
        print("\nNessuna scrittura effettuata.")
        raise SystemExit(1)

    for riga in referto:
        print(riga)
    print("\nTutti i controlli passati.")

    if not args.conferma:
        print("\nProva: nessun file toccato. Per promuovere davvero, rilancia con --conferma.")
        return

    # Archiviazione del grafo IN CARICA prima di sovrascriverlo. Il grafo
    # sostituito e' l'unico modo di tornare indietro se la promozione si
    # rivela sbagliata dopo, quindi va messo al sicuro PRIMA, non dopo.
    marca = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%dT%H%M%S")
    dir_archivio = args.archivio / f"sostituito-{marca}"
    dir_archivio.mkdir(parents=True, exist_ok=True)
    sha_sostituito = sha256_file(args.destinazione)
    copia = dir_archivio / args.destinazione.name
    shutil.copy2(args.destinazione, copia)
    if sha256_file(copia) != sha_sostituito:
        raise SystemExit(f"la copia in {copia} non combacia con l'originale - promozione interrotta")
    print(f"\nArchiviato il grafo sostituito in: {copia}")
    print(f"  sha256: {sha_sostituito}")

    # I file dei segmenti si archiviano PRIMA del grafo e si scrivono DOPO:
    # se qualcosa va storto a meta', un grafo vecchio con un indice vecchio e'
    # uno stato coerente, un grafo nuovo con un indice vecchio no.
    compagni_sostituiti = []
    for percorso in compagni:
        vecchio = args.destinazione.parent / percorso.name
        if vecchio.exists():
            copia_c = dir_archivio / percorso.name
            shutil.copy2(vecchio, copia_c)
            compagni_sostituiti.append(str(copia_c))
            print(f"Archiviato anche: {copia_c}")

    sha_candidato = sha256_file(args.candidato)
    shutil.copy2(args.candidato, args.destinazione)
    if sha256_file(args.destinazione) != sha_candidato:
        raise SystemExit("la copia promossa non combacia col candidato - stato incerto, ripristinare da " + str(copia))

    for percorso in compagni:
        arrivo = args.destinazione.parent / percorso.name
        atteso = sha256_file(percorso)
        shutil.copy2(percorso, arrivo)
        if sha256_file(arrivo) != atteso:
            raise SystemExit(f"la copia di {arrivo} non combacia con l'originale - stato incerto, "
                             f"ripristinare da {dir_archivio}")
        print(f"Promosso anche: {arrivo}")

    # I profili di famiglia sono un DERIVATO del grafo: le comunita' di
    # co-citazione, il rango dall'alberatura, il lessico delle motivazioni.
    # Lasciarli indietro dopo una promozione significherebbe classificare le
    # eccezioni con il corpus di ieri, in silenzio - e siccome il file vive
    # sotto data/ non e' nemmeno versionato, nessuno se ne accorgerebbe da
    # un diff. Si rigenerano qui, subito, e il record dice quali sono.
    profili_scritti = None
    try:
        import profili_famiglia

        riepilogo = profili_famiglia.rigenera(args.destinazione)
        profili_scritti = {
            "percorso": str(profili_famiglia.USCITA_DEFAULT),
            "comunita": len(riepilogo["comunita"]),
            "sha256_grafo": riepilogo["meta"]["sha256_grafo"],
        }
        print(f"Profili di famiglia rigenerati: {profili_famiglia.USCITA_DEFAULT} "
              f"({len(riepilogo['comunita'])} comunita')")
    except Exception as guasto:   # noqa: BLE001 - vedi sotto
        # Un guasto qui NON annulla la promozione, che e' gia' avvenuta e
        # verificata: si dichiara, e la pipeline che trovera' i profili
        # disallineati lo dira' a sua volta. Fallire in silenzio sarebbe
        # l'unica cosa inaccettabile.
        profili_scritti = {"errore": f"{type(guasto).__name__}: {guasto}"}
        print(f"ATTENZIONE: profili di famiglia NON rigenerati ({guasto}). "
              f"Rilanciare a mano: python src/profili_famiglia.py --grafo {args.destinazione}")

    # Stessa ragione per il registro delle parti: chi e' creditore e chi
    # debitore lo dicono l'epigrafe e il dispositivo dei provvedimenti che
    # stanno NEL grafo. Cambiato il grafo, un registro vecchio attribuirebbe
    # le eccezioni alle parti di ieri - e un'eccezione attribuita alla parte
    # sbagliata diventa una controdeduzione contro il proprio assistito.
    registro_scritto = None
    try:
        import pickle as _pickle

        import registro_parti

        with open(args.destinazione, "rb") as sorgente:
            grafo_promosso = _pickle.load(sorgente)
        documento = registro_parti.scrivi(grafo_promosso, args.destinazione,
                                          registro_parti.USCITA_DEFAULT)
        registro_scritto = {
            "percorso": str(registro_parti.USCITA_DEFAULT),
            "provvedimenti": documento["meta"]["provvedimenti"],
            "sha256_grafo": documento["meta"]["sha256_grafo"],
        }
        print(f"Registro delle parti rigenerato: {registro_parti.USCITA_DEFAULT} "
              f"({documento['meta']['provvedimenti']} provvedimenti)")
    except Exception as guasto:   # noqa: BLE001 - come sopra
        registro_scritto = {"errore": f"{type(guasto).__name__}: {guasto}"}
        print(f"ATTENZIONE: registro delle parti NON rigenerato ({guasto}). "
              f"Rilanciare a mano: python src/registro_parti.py --grafo {args.destinazione}")

    record = {
        "quando": datetime.now(timezone.utc).astimezone().isoformat(),
        "candidato": str(args.candidato),
        "candidato_sha256": sha_candidato,
        "destinazione": str(args.destinazione),
        "sostituito_sha256": sha_sostituito,
        "sostituito_archiviato_in": str(copia),
        "nodi": candidato.number_of_nodes(),
        "archi": candidato.number_of_edges(),
        "referto": referto,
        "compagni_promossi": [str(c) for c in compagni],
        "compagni_sostituiti_archiviati": compagni_sostituiti,
        "profili_famiglia": profili_scritti,
        "registro_parti": registro_scritto,
    }
    with open(dir_archivio / "promozione.json", "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)

    print(f"\nPromosso: {args.destinazione}")
    print(f"  sha256: {sha_candidato}")
    print(f"  record: {dir_archivio / 'promozione.json'}")
    print("\nPer tornare indietro:")
    print(f"  copy /Y \"{copia}\" \"{args.destinazione}\"")


if __name__ == "__main__":
    main()
