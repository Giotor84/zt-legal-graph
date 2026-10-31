# -*- coding: utf-8 -*-
"""Fase 1 e la spazzata insieme, senza che nessuna delle due perda niente.

## Perche' l'unione, e non la scelta

Misurato il 2026-09-01 su cinque atti mai visti da nessuno dei due metodi
(§7.38): trovano **cose diverse**, non uno il doppio dell'altro. Su ~210
frasi distinte, 185 le trova uno solo dei due. E cio' che ciascuno trova da
solo e' materiale vero in tre casi su quattro, misurato due volte per
strade indipendenti:

    e' un'eccezione (umano) 73,3% contro 71,4%   differenza  1,9  +-11,8
    citabilita' (macchina)  74,3% contro 57,5%   differenza 16,8  +- 7,0

Le due righe dicono cose diverse e nessuna delle due dice di scegliere:
cio' che Fase 1 trova da sola e' materiale vero **altrettanto spesso**, ma
**delimitato peggio**. Trova le cose giuste e le taglia male. Scegliere
farebbe perdere ~75 eccezioni vere in un verso o nell'altro; e cio' che
serve a Fase 1 non e' un filtro migliore, e' un taglio migliore - che e'
un'altra cosa, e non si ottiene buttandola via.

## Le due domande, che NON sono la stessa

**«E' la stessa zona del testo?»** si risponde con il contenimento,
`intersezione / min(lunghezze)`, e la risposta non dipende dalla soglia:
sulle 54 coppie che si toccano la distribuzione e' **bimodale** - 45 a
contenimento pieno, 5 sopra 0,9, e solo 4 in tutto il resto dell'intervallo.
Qualunque valore fra 0,50 e 0,90 seleziona 52 o 50 coppie delle stesse 54.
`SOGLIA_ZONA` non e' un parametro da tarare: e' una cifra scritta dove il
continuo non c'e'.

**«E' la stessa delimitazione?»** si risponderebbe con Jaccard,
`intersezione / unione` - e li' il continuo C'E', misurato: 6 coppie fra
0,0 e 0,1, 5 fra 0,1 e 0,2, 8 fra 0,2 e 0,3, e cosi' via fino a 12 identiche.
Ogni soglia sarebbe un numero inventato. Quindi non se ne usa nessuna: si
fondono **solo le fette identiche**, e tutto il resto resta separato.

## Cosa NON fa, ed e' il punto

Non fonde un gruppo in una voce sola. Trovato dal vivo:

    fase1     [16337:18440] 2103 car     <- un blocco solo
    spazzata  [17670:18031]  361 car     <- tre eccezioni distinte
    spazzata  [18032:18292]  260 car
    spazzata  [18293:18440]  147 car

Quel gruppo non e' un'eccezione: e' una zona dove i due metodi non sono
d'accordo su QUANTE ne stiano leggendo. Fonderlo distruggerebbe la
granularita' fine, che e' esattamente il materiale che si e' deciso di non
buttare. La zona e' un'informazione per chi rivede - «guarda queste
insieme» - non un'unita' di contenuto.

## La citabilita' segnala e non blocca

`citabilita.py` gira su ogni voce, e nessuna voce viene tolta. Misurato
sulle 58 fette giudicate a mano (§7.38):

    dipende_dal_contesto  prende 8 scarti su 16, disturba 2 buone su 42
    frammento_sospeso     prende 4 scarti su 16, disturba 3 buone su 42

La prima e' un affare, la seconda no: bloccare su `frammento_sospeso`
butterebbe quasi una frase vera per ogni scarto risparmiato, e in un atto
difensivo un'eccezione persa costa piu' di una da scartare a mano. Quindi
`AZIONI_ATTIVE` non contiene `blocca`, e il perche' e' misurato, non
preferito.

## Regola 4

Ogni voce esce con `(inizio, fine)` gia' calcolati da Python da chi l'ha
prodotta - `localizza.localizza` per entrambi i metodi - e qui non vengono
ne' ricalcolati ne' spostati. Verificato che i due lavorino nello stesso
sistema di coordinate: entrambi ancorano su
`segmenta_atto.pulisci_numeri_pagina(grezzo)`, e `verifica_coordinate`
lo ricontrolla a ogni unione invece di fidarsene.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

CARTELLA = Path(__file__).parent
if str(CARTELLA) not in sys.path:
    sys.path.insert(0, str(CARTELLA))

import citabilita  # noqa: E402

VERSIONE_CONTRATTO = "1.36"

#: Contenimento minimo perche' due fette stiano nella stessa zona.
#: NON e' un parametro da tarare - vedi il docstring: fra 0,50 e 0,90 la
#: selezione cambia di due coppie su 54, perche' la distribuzione e'
#: bimodale e in mezzo non c'e' quasi niente.
SOGLIA_ZONA = 0.5

#: I due metodi uniti. L'ordine e' quello in cui compaiono nelle varianti
#: a parita' di posizione, e serve solo perche' l'uscita sia riproducibile.
METODI = ("fase1", "spazzata")

#: Che cosa si fa DAVVERO di un giudizio di citabilita' qui. `blocca` non
#: c'e': su 58 fette giudicate a mano bloccava 4 scarti al prezzo di 3
#: frasi vere, un cambio che in un atto difensivo non conviene. La
#: categoria resta scritta nell'uscita per intero - si toglie l'azione,
#: non la misura.
AZIONI_ATTIVE = ("segnala",)


class CoordinateIncoerenti(Exception):
    """Le due estrazioni non parlano dello stesso testo.

    E' l'unico errore che questo modulo solleva invece di dichiarare,
    perche' unire due sistemi di coordinate diversi produrrebbe offset
    sbagliati che sembrano giusti - e la regola 4 poggia su quegli offset.
    Meglio non produrre niente."""


def _sovrapposizione(a: dict, b: dict) -> tuple[int, float]:
    """(caratteri in comune, contenimento). Il contenimento usa la fetta
    PIU' CORTA al denominatore: una fetta corta interamente dentro una
    lunga e' la stessa zona, e con l'unione al denominatore risulterebbe
    diversa proprio nel caso in cui i due metodi concordano di piu'."""
    inter = max(0, min(a["fine"], b["fine"]) - max(a["inizio"], b["inizio"]))
    if not inter:
        return 0, 0.0
    corta = min(a["fine"] - a["inizio"], b["fine"] - b["inizio"])
    return inter, (inter / corta if corta else 0.0)


def verifica_coordinate(voci: Iterable[dict], testo: str) -> None:
    """Ogni offset deve ritagliare il proprio testo. Non e' paranoia: i due
    metodi ancorano sullo stesso testo ripulito per costruzione, ma quella
    e' una proprieta' di due moduli scritti in momenti diversi, e se un
    giorno uno dei due cambiasse pulizia gli offset resterebbero numeri
    plausibili che puntano al posto sbagliato. Un confronto di stringhe
    costa niente e rende impossibile quell'errore."""
    for voce in voci:
        atteso = " ".join(voce["testo"].split())
        trovato = " ".join(testo[voce["inizio"]:voce["fine"]].split())
        if atteso and trovato != atteso:
            raise CoordinateIncoerenti(
                "%s [%d:%d] ritaglia %r invece di %r"
                % (voce["trovata_da"], voce["inizio"], voce["fine"],
                   trovato[:60], atteso[:60]))


def voci_di_fase1(estrazione: dict) -> tuple[list[dict], list[dict]]:
    """(ancorate, non ancorate). Le non ancorate non hanno offset e non
    possono entrare in nessuna zona: escono a parte invece di sparire,
    perche' un'eccezione che Fase 1 ha trovato ma non e' riuscita a
    collocare resta un'eccezione trovata."""
    dentro, fuori = [], []
    for e in estrazione.get("eccezioni") or []:
        ancora = e.get("ancora") if isinstance(e.get("ancora"), dict) else {}
        testo = e.get("testo_verbatim") or e.get("testo_letterale") or ""
        comune = {"trovata_da": "fase1", "testo": testo,
                  "famiglia_probabile": e.get("famiglia_probabile"),
                  "id_di_origine": e.get("eccezione_id")}
        if ancora.get("inizio") is None or ancora.get("fine") is None:
            fuori.append({**comune, "stato_ancora": ancora.get("stato") or "assente"})
        else:
            dentro.append({**comune, "inizio": ancora["inizio"], "fine": ancora["fine"],
                           "corrispondenza": ancora.get("corrispondenza")})
    return dentro, fuori


def voci_della_spazzata(spazzata: dict) -> list[dict]:
    return [{"trovata_da": "spazzata", "testo": e.get("verbatim") or "",
             "famiglia_probabile": e.get("famiglia_probabile"),
             "id_di_origine": None,
             "inizio": e["inizio"], "fine": e["fine"],
             "corrispondenza": e.get("corrispondenza")}
            for e in spazzata.get("eccezioni") or []]


def fondi_identiche(voci: list[dict]) -> list[dict]:
    """Due fette con gli STESSI offset sono la stessa cosa trovata due
    volte, e questo e' l'unico caso in cui fondere non richiede di
    inventare una soglia: e' un'uguaglianza, non una somiglianza.

    Jaccard direbbe di fondere anche le quasi-identiche, ma li' il continuo
    c'e' davvero (misurato: 6 coppie sotto 0,1, poi 5, 8, 9... fino alle 12
    identiche) e qualunque taglio sarebbe un numero inventato. Non fonderle
    costa al revisore di vedere due fette simili; fonderle a caso costa una
    delimitazione scelta da nessuno."""
    per_posizione: dict[tuple[int, int], dict] = {}
    for voce in sorted(voci, key=lambda v: (v["inizio"], v["fine"],
                                            METODI.index(v["trovata_da"]))):
        chiave = (voce["inizio"], voce["fine"])
        if chiave in per_posizione:
            gia = per_posizione[chiave]
            if voce["trovata_da"] not in gia["trovata_da"]:
                gia["trovata_da"] = gia["trovata_da"] + [voce["trovata_da"]]
            gia["famiglie_proposte"].append(voce.get("famiglia_probabile"))
        else:
            per_posizione[chiave] = {
                **voce, "trovata_da": [voce["trovata_da"]],
                "famiglie_proposte": [voce.get("famiglia_probabile")]}
    return list(per_posizione.values())


def raggruppa_in_zone(voci: list[dict], soglia: float = SOGLIA_ZONA) -> list[dict]:
    """Assegna a ogni voce una `zona`, per componenti connesse.

    La zona NON e' un'eccezione: e' un pezzo di testo su cui i due metodi
    si sono espressi in modo sovrapposto, e puo' contenere quattro voci
    perche' uno dei due ha letto un blocco solo dove l'altro leggeva tre
    eccezioni. Serve a chi rivede, per non giudicare una delimitazione
    senza vedere le altre proposte sullo stesso punto."""
    ordinate = sorted(voci, key=lambda v: (v["inizio"], v["fine"]))
    padre = list(range(len(ordinate)))

    def radice(i: int) -> int:
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    for i, a in enumerate(ordinate):
        for j in range(i + 1, len(ordinate)):
            b = ordinate[j]
            if b["inizio"] >= a["fine"]:
                break  # ordinate per inizio: nessuna successiva puo' toccare a
            if _sovrapposizione(a, b)[1] >= soglia:
                padre[radice(i)] = radice(j)

    etichette: dict[int, int] = {}
    for i, voce in enumerate(ordinate):
        r = radice(i)
        if r not in etichette:
            etichette[r] = len(etichette) + 1
        voce["zona"] = etichette[r]
    conta = Counter(v["zona"] for v in ordinate)
    for voce in ordinate:
        voce["voci_nella_zona"] = conta[voce["zona"]]
    return ordinate


def applica_citabilita(voci: list[dict], base_url: str, *, seed: int,
                       temperature: float) -> None:
    """Scrive il giudizio su ogni voce. Non ne toglie nessuna: `blocca` non
    e' fra le `AZIONI_ATTIVE`, e la categoria resta scritta per intero
    perche' la misura sopravviva alla politica che la usa."""
    for voce in voci:
        if len((voce["testo"] or "").strip()) < 12:
            voce["citabilita"] = {"categoria": "troppo_corta_per_giudicare",
                                  "motivo": "", "da_rivedere": True}
            continue
        esito = citabilita.valuta(base_url, voce["testo"], seed=seed,
                                  temperature=temperature)
        #: `blocca` viene DECLASSATO a segnalazione, non ignorato: la
        #: categoria resta scritta, e chi legge l'uscita puo' sempre
        #: rifare il conto di quante ne avrebbe tolte. Qui non si toglie
        #: niente perche' su 58 fette giudicate a mano ne avrebbe salvate
        #: 4 al prezzo di 3 vere - vedi AZIONI_ATTIVE.
        voce["citabilita"] = {
            "categoria": esito["categoria"], "motivo": esito["motivo"],
            "azione_del_controllo": esito["azione"],
            "da_rivedere": esito["categoria"] != citabilita.CITABILE}


def unisci(estrazione_fase1: dict, spazzata: dict, testo_pulito: str, *,
           base_url: str | None = None, seed: int = 1234,
           temperature: float = 0.0, sorgenti: dict | None = None) -> dict:
    """L'unione delle due estrazioni sullo stesso atto.

    `base_url` a None salta il giudizio di citabilita': serve ai test e a
    chi vuole le zone senza spendere una chiamata al modello per voce."""
    ancorate, non_ancorate = voci_di_fase1(estrazione_fase1)
    tutte = ancorate + voci_della_spazzata(spazzata)
    verifica_coordinate(tutte, testo_pulito)
    voci = raggruppa_in_zone(fondi_identiche(tutte))
    if base_url:
        applica_citabilita(voci, base_url, seed=seed, temperature=temperature)

    zone = Counter(v["zona"] for v in voci)
    da = Counter()
    for voce in voci:
        da["+".join(sorted(voce["trovata_da"]))] += 1
    return {
        "meta": {
            "versione_contratto": VERSIONE_CONTRATTO,
            "generato_il": datetime.now(timezone.utc).isoformat(),
            #: Un'unione senza il nome di cio' che ha unito non e'
            #: rifacibile, e questo file e' il punto in cui due corse
            #: distinte diventano una sola.
            "sorgenti": sorgenti or {"fase1": "(non dichiarata)",
                                     "spazzata": "(non dichiarata)"},
            #: `null` quando il giudizio non e' stato chiesto: senza questo
            #: campo un'uscita senza giudizi e una in cui passano tutti si
            #: scriverebbero allo stesso modo.
            "citabilita": ({"base_url": base_url, "seed": seed,
                            "temperature": temperature} if base_url else None),
        },
        "n_caratteri_testo_pulito": len(testo_pulito),
        "voci": voci,
        "non_ancorate": non_ancorate,
        "conteggi": {
            "voci": len(voci),
            "zone": len(zone),
            "zone_con_una_voce_sola": sum(1 for n in zone.values() if n == 1),
            "zone_con_piu_voci": sum(1 for n in zone.values() if n > 1),
            "per_provenienza": dict(da),
            "non_ancorate_di_fase1": len(non_ancorate),
            "da_rivedere": sum(1 for v in voci
                               if v.get("citabilita", {}).get("da_rivedere")),
        },
        "cosa_non_dice": (
            "Una zona con piu' voci NON e' un'eccezione sola: e' un punto "
            "del testo su cui i due metodi non concordano su quante ne "
            "stiano leggendo. Nessuna voce e' stata tolta, nemmeno quelle "
            "che il controllo di citabilita' segnala."),
    }


def _carica(percorso: Path) -> dict:
    return json.loads(percorso.read_text(encoding="utf-8"))


def testo_pulito_di(percorso_atto: Path) -> str:
    """Lo stesso testo su cui i due metodi hanno ancorato. Una sola
    definizione, qui, perche' due definizioni sarebbero due sistemi di
    coordinate che si scoprono diversi troppo tardi."""
    import segmenta_atto
    if percorso_atto.suffix.lower() == ".pdf":
        from estrazione_pdf_atto import estrai_testo_da_pdf
        grezzo = estrai_testo_da_pdf(percorso_atto).testo
    else:
        grezzo = percorso_atto.read_text(encoding="utf-8")
    return segmenta_atto.pulisci_numeri_pagina(grezzo)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fase1", type=Path, required=True)
    parser.add_argument("--spazzata", type=Path, required=True)
    parser.add_argument("--atti", type=Path, required=True,
                        help="cartella degli atti originali, per il testo pulito")
    parser.add_argument("--uscita", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--senza-citabilita", action="store_true")
    parser.add_argument("--seme", type=int, default=1234)
    parser.add_argument("--temperature", type=float, default=0.0)
    argomenti = parser.parse_args()

    f1 = {p.name[: -len("_01_estrazione.json")]: p
          for p in argomenti.fase1.glob("*_01_estrazione.json")}
    sp = {p.name[: -len("_spazzata.json")]: p
          for p in argomenti.spazzata.glob("*_spazzata.json")}
    comuni = sorted(set(f1) & set(sp))
    if not comuni:
        print("nessun atto in comune fra le due cartelle")
        return 2

    atti = {p.stem: p for p in argomenti.atti.iterdir() if p.is_file()}
    argomenti.uscita.mkdir(parents=True, exist_ok=True)
    tot = Counter()
    print("%-44s %5s %5s %5s %5s" % ("atto", "voci", "zone", "sole", "rived"))
    for stem in comuni:
        if stem not in atti:
            print("  ! %s: manca l'atto originale, saltato" % stem[:60])
            continue
        esito = unisci(_carica(f1[stem]), _carica(sp[stem]),
                       testo_pulito_di(atti[stem]),
                       sorgenti={"fase1": f1[stem].name, "spazzata": sp[stem].name},
                       base_url=None if argomenti.senza_citabilita else argomenti.base_url,
                       seed=argomenti.seme, temperature=argomenti.temperature)
        (argomenti.uscita / (stem + "_unione.json")).write_text(
            json.dumps(esito, ensure_ascii=False, indent=2), encoding="utf-8")
        c = esito["conteggi"]
        print("%-44s %5d %5d %5d %5d"
              % (stem[:44], c["voci"], c["zone"], c["zone_con_una_voce_sola"],
                 c["da_rivedere"]))
        for chiave in ("voci", "zone", "zone_con_una_voce_sola",
                       "zone_con_piu_voci", "da_rivedere", "non_ancorate_di_fase1"):
            tot[chiave] += c[chiave]
        for chiave, quante in c["per_provenienza"].items():
            tot["da_" + chiave] += quante

    print("%-44s %5d %5d %5d %5d"
          % ("TOTALE", tot["voci"], tot["zone"], tot["zone_con_una_voce_sola"],
             tot["da_rivedere"]))
    print()
    for chiave in sorted(k for k in tot if k.startswith("da_")):
        print("  %-28s %d" % (chiave[3:], tot[chiave]))
    print("  %-28s %d" % ("zone con piu' voci", tot["zone_con_piu_voci"]))
    print("  %-28s %d" % ("non ancorate di Fase 1", tot["non_ancorate_di_fase1"]))
    print("\nscritto in %s" % argomenti.uscita)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# ------------------------------------------------- cosa passa a valle


#: Ordine di preferenza dentro una zona, e ognuno e' misurato:
#:
#:   1. le due fette IDENTICHE dei due metodi - 10 su 12 stanno in piedi
#:      da sole (83%), il segnale di qualita' piu' forte che abbiamo, e
#:      viene gratis dall'unione;
#:   2. le fette che il controllo di citabilita' dice complete - 73,5% per
#:      la spazzata, 52,3% per Fase 1 sulle zone a voce singola;
#:   3. nessuna delle due: si manda la piu' lunga e SI DICHIARA, perche'
#:      "la piu' lunga vince" e' l'euristica gia' bocciata in §7.36
#:      (concordava 19 su 19 col giudizio umano e non significava niente,
#:      perche' l'annotatore che vinceva era anche sistematicamente piu'
#:      lungo). Qui e' un ripiego dichiarato, non un criterio.
#:   0. nella zona non c'era niente da scegliere: una voce sola. Ha un
#:      motivo suo - `unica_nella_zona` - perche' etichettarla come
#:      "citabile" direbbe che una scelta e' stata fatta e che quella voce
#:      l'ha vinta, e la maggior parte delle zone e' di questo tipo: il
#:      conteggio dei motivi diventerebbe illeggibile proprio nella riga
#:      che si guarda per prima.
MOTIVI_DI_SCELTA = ("unica_nella_zona", "concordi", "citabile",
                    "ripiego_la_piu_lunga")


def _senza_sovrapposizioni(voci: list[dict]) -> list[dict]:
    """Il sottoinsieme piu' NUMEROSO di fette che non si sovrappongono.

    E' il problema classico dell'interval scheduling e ha una soluzione
    esatta - avido sulla fine - quindi qui non si sceglie una soglia: si
    calcola. Massimizzare il NUMERO, e non la lunghezza coperta, e' la
    decisione vera, e va nel verso della granularita' fine: fra un blocco
    da 2103 caratteri e le tre fette da ~300 che ci stanno dentro, manda a
    valle le tre. Tre argomenti confutati uno per uno valgono piu' di un
    blocco confutato in massa, ed e' il motivo per cui l'unione tiene
    entrambe le letture invece di fonderle."""
    scelte: list[dict] = []
    ultima_fine = -1
    for voce in sorted(voci, key=lambda v: (v["fine"], v["inizio"])):
        if voce["inizio"] >= ultima_fine:
            scelte.append(voce)
            ultima_fine = voce["fine"]
    return scelte


def seleziona_per_valle(voci: list[dict]) -> list[dict]:
    """Le voci da mandare a Fase 2, una scelta per zona.

    L'unione COMPLETA resta scritta a parte e non perde niente: questa e'
    la selezione di cio' che va confutato, non un filtro sul materiale.
    Senza di essa Fase 2 cercherebbe in memoria quattro volte per lo
    stesso punto e Fase 3 lo confuterebbe quattro volte - il che non e'
    un costo, e' un atto peggiore."""
    per_zona: dict[int, list[dict]] = {}
    for voce in voci:
        per_zona.setdefault(voce["zona"], []).append(voce)

    scelte: list[dict] = []
    for zona in sorted(per_zona):
        gruppo = per_zona[zona]
        if len(gruppo) == 1:
            scelte.append({**gruppo[0],
                           "motivo_della_scelta": "unica_nella_zona"})
            continue
        concordi = [v for v in gruppo if len(v["trovata_da"]) > 1]
        citabili = [v for v in gruppo
                    if v.get("citabilita", {}).get("categoria") == citabilita.CITABILE]
        for candidati, motivo in ((concordi, "concordi"), (citabili, "citabile")):
            if candidati:
                scelte += [{**v, "motivo_della_scelta": motivo}
                           for v in _senza_sovrapposizioni(candidati)]
                break
        else:
            piu_lunga = max(gruppo, key=lambda v: (v["fine"] - v["inizio"], -v["inizio"]))
            scelte.append({**piu_lunga, "motivo_della_scelta": "ripiego_la_piu_lunga"})
    return sorted(scelte, key=lambda v: (v["inizio"], v["fine"]))


#: Cosa si scrive in `specificita` quando la voce l'ha trovata la sola
#: spazzata: li' la domanda a nessuno e' stata posta.
#:
#: Fino alla 1.35 valeva `"specifica"`, perche' l'enum del contratto
#: conosceva due soli valori e bisognava sceglierne uno - e quello scelto
#: era esattamente il valore che fa dire a quattordici regole su venti
#: "l'eccezione regge". Un ripiego che decide l'esito e' un dato
#: inventato con l'aria di una misura.
#:
#: Dalla 1.36 il contratto sa dire "non si sa", ed e' questo. Le regole
#: lo trattano gia': ramo che NON decide, con la nota che dice cosa
#: guardare. Meno risposte, nessuna inventata.
SPECIFICITA_NON_CHIESTA = "non_desumibile"

#: Nome storico, tenuto perche' `RIPIEGO` diceva il vero fino alla 1.35 e
#: qualcuno potrebbe cercarlo. Non e' piu' un ripiego: e' un valore.
RIPIEGO_SPECIFICITA = SPECIFICITA_NON_CHIESTA


def come_eccezioni_di_fase1(scelte: list[dict], blocchi: list[dict],
                            estrazione_fase1: dict | None = None) -> list[dict]:
    """Le voci scelte nella forma che Fase 2 gia' conosce.

    Fase 2 e Fase 3 non devono sapere che l'unione esiste: leggono
    `eccezioni` come hanno sempre fatto. Cio' che cambia e' che alcune di
    quelle eccezioni non le ha trovate Fase 1, e **quello si dice**:
    `trovata_da` e `motivo_della_scelta` sono campi nuovi del contratto
    1.33, non un travestimento. Un'eccezione della spazzata presentata
    come se venisse da Fase 1 renderebbe impossibile accorgersi se un
    domani uno dei due metodi peggiora - ed e' l'unica cosa che questo
    aggancio poteva rompere in silenzio.

    `testo_letterale` prende lo stesso valore di `testo_verbatim`: il
    contratto dichiara il primo NON citabile dalla 1.25 (e' cio' che il
    MODELLO dice di aver citato) e per una voce della spazzata quella
    dichiarazione non esiste. Copiare il verbatim non aggiunge niente di
    falso - i due campi coincidono, che e' il caso migliore - mentre
    inventare una decorazione sarebbe peggio che lasciarlo vuoto.

    `blocco_id` viene CALCOLATO dall'offset con `localizza.blocco_di`, la
    stessa funzione che usa Fase 1. Il contratto lo vuole obbligatorio e
    con pattern `^B[0-9]{2}$`, e ha ragione: non e' un dato mancante per
    una voce della spazzata, e' un dato che si ricava dall'offset. Se
    l'offset non ricade in nessun blocco, `blocco_di` solleva - e va bene
    che sollevi, perche' vorrebbe dire che i blocchi e gli offset non
    parlano dello stesso testo.

    `specificita` e `conteggi_allegati` si RILEGGONO dall'estrazione di
    Fase 1 quando la voce viene da li' (`id_di_origine`). Prima erano due
    costanti - `"specifica"` e `False` - scritte per ogni voce, comprese
    quelle su cui il modello aveva risposto: misurato il 2026-09-03
    sull'atto ALFA, le 21 eccezioni arrivate a Fase 2 portavano
    `specificita: specifica` **21 volte su 21**, mentre l'estrazione di
    Fase 1 dello stesso atto ne aveva 12 su 17 `generica`.

    Non e' un dettaglio di travaso: `specificita` e' la precondizione su
    cui girano quattordici delle venti regole, e `specifica` e' il valore
    che le fa dire "l'eccezione regge". Sostituirlo a tappeto **spegneva
    il motore delle regole** senza che niente lo segnalasse - e il dossier
    ne usciva con zero confutazioni e l'aria di averle valutate.

    Per le voci della sola spazzata il valore non esiste: la domanda a
    nessuno e' stata posta, e dalla 1.36 il contratto sa dirlo -
    `non_desumibile` (vedi `SPECIFICITA_NON_CHIESTA`). Le regole lo
    trattano gia' come "non decido", che e' cio' che quel dato consente."""
    import localizza

    per_origine = {e.get("eccezione_id"): e
                   for e in ((estrazione_fase1 or {}).get("eccezioni") or [])}
    fuori = []
    for indice, voce in enumerate(scelte, start=1):
        origine = per_origine.get(voce.get("id_di_origine")) or {}
        fuori.append({
            #: `^X[0-9]{2}$` e' il pattern del contratto, non una
            #: convenzione: un prefisso "U" per distinguere le voci unite
            #: sarebbe fallito in validazione a Fase 1 gia' spesa. Da dove
            #: viene una voce lo dice `trovata_da`, che e' un campo, non
            #: un'iniziale nascosta dentro un identificatore.
            "eccezione_id": "X%02d" % indice,
            #: L'enum non ammette null e ha gia' la casella giusta. La
            #: spazzata una famiglia la propone sempre - le prende dallo
            #: stesso enum di Fase 1 - ma se un domani non ce l'avesse,
            #: `non_riconosciuta` dice il vero, mentre null farebbe fallire
            #: la validazione dopo aver speso l'intera Fase 1.
            "famiglia_probabile": voce.get("famiglia_probabile") or "non_riconosciuta",
            "testo_letterale": voce["testo"],
            "testo_verbatim": voce["testo"],
            "specificita": origine.get("specificita") or SPECIFICITA_NON_CHIESTA,
            "conteggi_allegati": bool(origine.get("conteggi_allegati", False)),
            "posizione_dichiarata": "zona %d" % voce["zona"],
            "ancora": {"stato": "ancorata",
                       "blocco_id": localizza.blocco_di(blocchi, voce["inizio"]),
                       "inizio": voce["inizio"], "fine": voce["fine"],
                       "corrispondenza": voce.get("corrispondenza") or "esatta",
                       "similarita": None},
            "trovata_da": sorted(voce["trovata_da"]),
            "motivo_della_scelta": voce["motivo_della_scelta"],
        })
    return fuori


def rinumerazione(scelte: list[dict]) -> list[dict]:
    """Da quale eccezione di Fase 1 viene ogni id che vede la Fase 2.

    `come_eccezioni_di_fase1` rinumera da capo: la voce n-esima diventa
    `X<n>` qualunque cosa fosse prima. E' voluto - il contratto vuole il
    pattern `^X[0-9]{2}$` e la Fase 2 non deve sapere che l'unione esiste -
    ma ha un effetto che non era voluto: **lo stesso identificatore vale
    due cose diverse in due file della stessa corsa**. Nella corsa ALFA del
    2026-09-02 `X07` era, in `01_estrazione.json`, "Piu' precisamente... in
    data 31 dicembre 1984 veniva acceso il conto"; in `02_dossier.json`
    era "Tali clausole, infatti, sono nulle, salvo che il corrispettivo per
    la messa a disposizione". Chi legge i due file affiancati incrocia
    righe che non parlano della stessa cosa e non ha modo di accorgersene,
    perche' la colonna che le lega ha lo stesso nome. E' successo davvero,
    a una revisione esterna e a me.

    Finche' il contratto non porta l'id di origine dentro l'eccezione
    (serve un bump: `additionalProperties` e' false su ogni oggetto),
    la corrispondenza si dichiara qui e finisce nella memoria. `None` in
    `da_fase1` non e' un dato mancante: e' una voce che Fase 1 non aveva
    trovato affatto, l'ha trovata la spazzata."""
    return [{"id": "X%02d" % indice, "da_fase1": voce.get("id_di_origine")}
            for indice, voce in enumerate(scelte, start=1)]


def nota_di_rinumerazione(scelte: list[dict]) -> str | None:
    """La riga da mettere fra i buchi. `None` quando la rinumerazione e'
    l'identita' su TUTTE le voci: li' i due file si possono leggere
    affiancati senza rischio, e un avviso che non avverte di niente
    insegna solo a saltare gli avvisi."""
    mappa = rinumerazione(scelte)
    spostate = [v for v in mappa if v["da_fase1"] != v["id"]]
    if not spostate:
        return None
    nuove = sum(1 for v in mappa if v["da_fase1"] is None)
    coppie = ", ".join(f"{v['id']}<-{v['da_fase1'] or 'nuova'}" for v in mappa)
    return (f"[rinumerazione] gli id delle eccezioni sono stati riassegnati dall'unione: "
            f"{len(spostate)} voci su {len(mappa)} hanno un id DIVERSO da quello di Fase 1 "
            f"({nuove} non vengono da Fase 1 ma dalla spazzata). Lo stesso identificatore "
            f"vale due cose diverse in 01_estrazione.json e in 02_dossier.json: NON leggerli "
            f"affiancati per id. Corrispondenza (id in Fase 2 <- id in Fase 1): {coppie}")
