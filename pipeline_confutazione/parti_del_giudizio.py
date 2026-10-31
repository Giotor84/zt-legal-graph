# -*- coding: utf-8 -*-
"""Chi e' il creditore e chi il debitore, letto dal testo del provvedimento.

## Perche' esiste

Finora il lato di una parte lo decideva una TABELLA scritta a mano
(opponente -> debitore, appellante -> debitore, ...). Quella tabella e' un
giudizio giuridico travestito da normalizzazione: e' vera quasi sempre in
materia bancaria e falsa quando non lo e', e quando e' falsa produce una
controdeduzione presa dalla parte sbagliata, che sembra perfettamente
sensata. Su 1285 attribuzioni della corsa sul corpus, 220 risultavano del
creditore.

Qui il lato NON si assume: si legge dal dispositivo e dall'intestazione,
provvedimento per provvedimento, con la fetta di testo che lo prova.

## I criteri, in ordine di forza

1. **Ruolo nel monitorio** - `opposto` e' chi ha ottenuto il decreto
   ingiuntivo, cioe' il creditore ricorrente; `opponente` e' l'ingiunto.
   Non e' un'inferenza, e' la struttura del procedimento monitorio.
2. **Condanna nel merito al pagamento** - "condanna X al pagamento in
   favore di Y della somma di ...": X deve, Y ha diritto. Le condanne alle
   SPESE sono escluse: quelle individuano il soccombente, che e' un'altra
   cosa dal debitore.
3. **Condanna alla restituzione** - "condanna X alla restituzione in favore
   di Y": qui il verso si ROVESCIA rispetto all'intuizione. Chi restituisce
   e' chi ha incassato indebitamente - tipicamente la banca. X e' il
   creditore del rapporto, Y il cliente.

Quando due criteri dicono cose diverse sulla stessa parte, il lato NON si
sceglie: si dichiara `discordi` e si tengono entrambe le prove. E' la
stessa regola gia' adottata per lessico e vettori.

## L'ancoraggio

Ogni prova porta `(campo, inizio, fine)` calcolati da Python e la fetta
verbatim a quegli offset (regola 4). Nessuna prova viene da un modello:
qui non c'e' nessun modello.

Nessun import verso il grafo o lo store: queste funzioni prendono stringhe.
"""

from __future__ import annotations

import re

#: Gli pseudonimi dell'anonimizzazione del corpus. Non sono nomi: sono
#: identificatori STABILI dentro un documento, e questo li rende
#: risolvibili contro l'intestazione dello stesso documento.
_STELI = ("Controparte", "Parte", "Persona", "CP", "Pt", "PT")


def _tollerante(parola: str) -> str:
    """Lo stelo con uno spazio facoltativo fra una lettera e l'altra.

    L'estrazione dal PDF spezza le parole a meta' quando nel PDF c'e' un
    a capo o una crenatura larga: `Controp arte_1` e' 38 coppie da solo.
    Il suffisso `_<numero>` obbligatorio e' cio' che tiene lo schema
    stretto: senza di quello, lettere separate da spazi combacerebbero
    con mezza pagina."""
    return r"[\s]?".join(parola)


#: Lo stelo piu' lungo per primo: `Controparte` prima di `Parte`, o
#: l'alternanza si fermerebbe al prefisso sbagliato.
PSEUDONIMO = re.compile(
    r"\b(?:" + "|".join(_tollerante(s) for s in _STELI) + r")[\s]?_[\s]?\d+\b")


def canonico(grezzo: str) -> str:
    """La chiave di una parte: lo pseudonimo senza gli spazi intrusi.

    E' la sola normalizzazione applicata, e non tocca il testo: serve a
    far combaciare `Controp arte_1` letto nel dispositivo con
    `Controparte_1` letto nell'epigrafe. Gli offset delle prove restano
    quelli del testo originale."""
    return "".join(grezzo.split())

#: I marcatori di ruolo processuale. Ognuno chiude il blocco di parti che
#: lo precede: e' la forma delle epigrafi ("DA ... - appellante - CONTRO
#: ... appellata").
RUOLO = re.compile(
    r"\b(appellant[ei]|appellat[aoei]|opponent[ei]|opposti|opposto|opposta"
    r"|attric[ei]|attor[ei]|convenut[aoei]|ricorrent[ei]|resistent[ei]"
    r"|reclamant[ei]|reclamat[aoei])\b",
    re.IGNORECASE,
)

#: "opposto" e' tanto un ruolo di parte quanto un aggettivo del decreto:
#: "il decreto ingiuntivo opposto" non nomina nessuno. Letto come ruolo,
#: attribuisce al creditore la parte che gli sta accanto - che nel
#: monitorio e' quasi sempre l'OPPONENTE, cioe' l'esatto contrario.
#: Trovato guardando i disaccordi con la tabella a mano, non a tavolino.
COSA_OPPOSTA = re.compile(
    r"\b(decreto|decr\.?|d\.?i\.?|provvedimento|monitorio|sentenza|ordinanza"
    r"|ingiunzione|atto)\b[\s\W\w]{0,30}?$",
    re.IGNORECASE,
)

#: Quanto indietro si guarda per capire se "opposto" qualifica una cosa.
CONTESTO_OPPOSTO = 40

#: Cio' che separa chi e' condannato da chi incassa. "In favore di" non
#: basta: "condanna l'opposta al pagamento all'opponente delle spese"
#: usa un semplice dativo, e leggendo solo "favore" finivano obbligate
#: TUTTE E DUE le parti - compresa quella che aveva vinto.
A_FAVORE_DI = re.compile(
    r"(?:in\s+|a\s+)?favore\s+(?:di\s+)?"
    r"|\bverso\s+(?:l\W\s*|il\s+|la\s+)?"
    r"|\bnei\s+confronti\s+(?:di\s+)?"
    r"|pagament\w*\s+(?:a|ad|al|alla|all\W)\s*"
    r"|restitu\w+\s+(?:a|ad|al|alla|all\W)\s*",
    re.IGNORECASE,
)

_RADICI = {
    "appellant": "appellante", "appellat": "appellato",
    "opponent": "opponente", "oppost": "opposto",
    "attric": "attore", "attor": "attore",
    "convenut": "convenuto", "ricorrent": "ricorrente",
    "resistent": "resistente", "reclamant": "reclamante",
    "reclamat": "reclamato",
}

#: Il solo ruolo da cui il lato si deduce senza aggiungere nulla: nel
#: monitorio il decreto lo chiede il creditore, e lo subisce l'ingiunto.
LATO_DAL_RUOLO = {"opposto": "creditore", "opponente": "debitore"}

#: Distanza massima, in caratteri, fra il verbo di condanna e il suo
#: complemento. Oltre, la frase e' quasi sempre un'altra.
FINESTRA_CONDANNA = 200

#: Distanza massima fra il nome di una parte e il marcatore di ruolo che
#: le si attribuisce. Misurata sulle 4045 associazioni delle epigrafi:
#: mediana 242 caratteri, nove su dieci sotto 1100. Oltre, in mezzo c'e'
#: quasi sempre un'altra parte, e l'associazione e' un caso.
DISTANZA_MASSIMA_RUOLO = 1200

#: Quanto puo' distare un SECONDO marcatore di ruolo dal blocco che lo
#: precede per descrivere ancora quella parte ("Controparte_1 appellata,
#: gia' opposto"). Stretto di proposito: dove l'epigrafe manca si legge la
#: testa del testo integrale, e li' le conclusioni sono piene di parole di
#: ruolo in prosa. Senza questo limite una sola parte finiva con sei ruoli
#: incompatibili.
DISTANZA_SECONDO_RUOLO = 80

CREDITORE = "creditore"
DEBITORE = "debitore"


def _normalizza_ruolo(parola: str) -> str:
    """Riduce le varianti di genere e numero alla forma di riferimento."""
    p = parola.lower()
    for radice, forma in _RADICI.items():
        if p.startswith(radice):
            return forma
    return p


def qualifica_una_cosa(testo: str, posizione: int) -> bool:
    """Vero se "opposto" a quella posizione descrive un atto, non una parte."""
    prima = testo[max(0, posizione - CONTESTO_OPPOSTO):posizione]
    return bool(COSA_OPPOSTA.search(prima))


def marcatori_di_ruolo(testo: str):
    """I marcatori di ruolo veri, saltati quelli che qualificano un atto."""
    for trovato in RUOLO.finditer(testo):
        if (trovato.group(1).lower().startswith("oppost")
                and qualifica_una_cosa(testo, trovato.start())):
            continue
        yield trovato


def _prova(campo: str, testo: str, inizio: int, fine: int, tipo: str) -> dict:
    """Una prova e' la fetta agli offset, calcolata qui, mai riscritta."""
    return {
        "tipo": tipo,
        "campo": campo,
        "inizio": inizio,
        "fine": fine,
        "verbatim": testo[inizio:fine],
    }


def ruoli_delle_parti(intestazione: str) -> dict[str, dict]:
    """Ogni pseudonimo con i ruoli che l'epigrafe gli attribuisce.

    Una parte puo' averne piu' d'uno, ed e' un'informazione, non un
    conflitto: `appellata` in questo grado e `opposto` nel monitorio di
    primo grado descrivono la stessa parte in due momenti."""
    if not intestazione:
        return {}
    trovati: dict[str, dict] = {}
    ultimo = 0
    blocco_precedente: list[str] = []
    for marcatore in marcatori_di_ruolo(intestazione):
        segmento = intestazione[ultimo:marcatore.start()]
        ruolo = _normalizza_ruolo(marcatore.group(1))
        parti_nel_blocco = [canonico(p.group(0))
                            for p in PSEUDONIMO.finditer(segmento)]
        if not parti_nel_blocco and len(segmento) > DISTANZA_SECONDO_RUOLO:
            # Troppo lontano per descrivere ancora la parte precedente: e'
            # prosa, non un secondo ruolo.
            ultimo = marcatore.end()
            continue
        if not parti_nel_blocco:
            # Due marcatori di fila descrivono la stessa parte in due
            # momenti: "Controparte_1 appellata, gia' opposto". Il secondo
            # ruolo appartiene al blocco che lo precede, ed e' proprio
            # quello che porta il criterio del monitorio.
            for nome in blocco_precedente:
                voce = trovati[nome]
                if ruolo not in voce["ruoli"]:
                    voce["ruoli"].append(ruolo)
                    voce["prove"].append(_prova(
                        "intestazione", intestazione,
                        ultimo, marcatore.end(), "ruolo:" + ruolo))
            ultimo = marcatore.end()
            continue
        blocco_precedente = parti_nel_blocco
        for parte in PSEUDONIMO.finditer(segmento):
            voce = trovati.setdefault(canonico(parte.group(0)),
                                      {"ruoli": [], "prove": []})
            if len(segmento) - parte.end() > DISTANZA_MASSIMA_RUOLO:
                continue
            if ruolo not in voce["ruoli"]:
                voce["ruoli"].append(ruolo)
                voce["prove"].append(_prova(
                    "intestazione", intestazione,
                    ultimo + parte.start(), marcatore.end(), "ruolo:" + ruolo))
        ultimo = marcatore.end()
    # Le parti nominate dopo l'ultimo marcatore esistono comunque.
    for parte in PSEUDONIMO.finditer(intestazione):
        trovati.setdefault(canonico(parte.group(0)), {"ruoli": [], "prove": []})
    return trovati


def nomi_di_parte(frammento: str) -> list[str]:
    """Come una parte viene chiamata: lo pseudonimo, oppure il ruolo.

    Un dispositivo dice tanto "condanna Parte_1" quanto "condanna
    l'appellante": leggere solo il primo caso butta via meta' delle
    condanne. Il ruolo e' una chiave meno precisa - vale per tutti quelli
    che lo rivestono - e chi la usa deve tenerne conto."""
    trovati = [canonico(m.group(0)) for m in PSEUDONIMO.finditer(frammento)]
    trovati += ["ruolo:" + _normalizza_ruolo(m.group(1))
                for m in marcatori_di_ruolo(frammento)]
    visti, unici = set(), []
    for nome in trovati:
        if nome not in visti:
            visti.add(nome)
            unici.append(nome)
    return unici


def condanne(dispositivo: str) -> list[dict]:
    """Le condanne del dispositivo, con chi paga e chi incassa.

    Le condanne alle spese sono tenute ma marcate `spese`: individuano il
    soccombente, e confonderle con il debito significa dare del debitore a
    chiunque perda una causa."""
    if not dispositivo:
        return []
    esito = []
    for verbo in re.finditer(r"[Cc]ondann\w+", dispositivo):
        coda = dispositivo[verbo.end():verbo.end() + FINESTRA_CONDANNA]
        taglio = re.search(r"[;\n]", coda)
        if taglio:
            coda = coda[:taglio.start()]
        # "rimborso" sta con le spese nel 73% dei dispositivi (307 su 422):
        # trattarlo come restituzione dell'indebito ROVESCEREBBE il lato
        # delle parti in tre casi su quattro. Misurato, non stimato.
        e_spese = bool(re.search(
            r"spes[ea]|compens\w+|[ri]fusion\w*|rimbors\w+|contributo unificato",
            coda, re.IGNORECASE))
        restituzione = bool(re.search(r"restitu\w+|ripetizion\w*",
                                      coda, re.IGNORECASE))
        pagamento = bool(re.search(r"pagament\w*|pagare|versare|corrisponder\w+",
                                   coda, re.IGNORECASE))
        # Una condanna alle spese si tiene anche senza verbo di pagamento
        # ("condanna X alle spese di lite"): serve alla soccombenza.
        if not (pagamento or restituzione or e_spese):
            continue
        favore = A_FAVORE_DI.search(coda)
        prima = coda[:favore.start()] if favore else coda
        dopo = coda[favore.end():] if favore else ""
        esito.append({
            "obbligati": nomi_di_parte(prima),
            "beneficiari": nomi_di_parte(dopo),
            "spese": e_spese,
            "restituzione": restituzione and not e_spese,
            "prova": _prova("dispositivo", dispositivo, verbo.start(),
                            verbo.end() + len(coda),
                            "condanna_spese" if e_spese
                            else "condanna_restituzione" if restituzione
                            else "condanna_pagamento"),
        })
    return esito


def _aggiungi(lati: dict, parte: str, lato: str, criterio: str, prova: dict) -> None:
    lati.setdefault(parte, []).append(
        {"lato": lato, "criterio": criterio, "prova": prova})


def lati_delle_parti(intestazione: str, dispositivo: str) -> dict[str, dict]:
    """Il lato di ogni parte, con il criterio e la prova che lo reggono.

    Dove i criteri discordano il lato resta `None`: una controdeduzione
    presa dalla parte sbagliata e' un errore invisibile, e vale meno di
    un'astensione dichiarata."""
    ruoli = ruoli_delle_parti(intestazione)
    lati: dict[str, list] = {}

    for parte, voce in ruoli.items():
        for ruolo in voce["ruoli"]:
            lato = LATO_DAL_RUOLO.get(ruolo)
            if lato:
                prova = next((p for p in voce["prove"] if p["tipo"] == "ruolo:" + ruolo), None)
                _aggiungi(lati, parte, lato, "ruolo_nel_monitorio", prova)

    # Una condanna a pagare prova chi deve QUELLA somma, che non e' sempre
    # chi subisce la pretesa di credito: la banca condannata a risarcire e'
    # debitrice di quell'obbligazione e resta creditrice del rapporto. La
    # condanna vale come posizione nel credito solo quando in causa c'e' un
    # decreto ingiuntivo, che dice qual e' il credito preteso. Altrimenti si
    # registra e non decide.
    monitorio = bool(re.search(r"decreto\s+ingiuntivo|ingiunzion", dispositivo, re.IGNORECASE))
    for condanna in condanne(dispositivo):
        if condanna["spese"]:
            continue
        if not condanna["restituzione"] and not monitorio:
            for nome in condanna["obbligati"]:
                _aggiungi(lati, nome, None, "obbligazione_decisa_senza_monitorio",
                          condanna["prova"])
            continue
        if condanna["restituzione"]:
            # Chi restituisce ha incassato: e' il creditore del rapporto.
            di_debito, di_credito = condanna["beneficiari"], condanna["obbligati"]
            criterio = "condanna_alla_restituzione"
        else:
            di_debito, di_credito = condanna["obbligati"], condanna["beneficiari"]
            criterio = "condanna_al_pagamento"
        for parte in di_debito:
            _aggiungi(lati, parte, DEBITORE, criterio, condanna["prova"])
        for parte in di_credito:
            _aggiungi(lati, parte, CREDITORE, criterio, condanna["prova"])

    # Una condanna che nomina un RUOLO vale per ogni parte che lo riveste
    # in epigrafe: e' li' che la chiave imprecisa torna precisa.
    for chiave in [k for k in lati if k.startswith("ruolo:")]:
        ruolo = chiave.split(":", 1)[1]
        for parte, voce in ruoli.items():
            if ruolo in voce["ruoli"]:
                for proposta in lati[chiave]:
                    _aggiungi(lati, parte, proposta["lato"],
                              proposta["criterio"] + "_per_ruolo", proposta["prova"])

    # 4) Soccombenza composta con la direzione. Preso da solo, "condanna X
    #    alle spese" dice solo che X ha perso. Ma se il dispositivo dice
    #    anche da che parte e' caduta la causa, i due fatti insieme danno
    #    il lato: chi perde una causa finita in favore del creditore e' il
    #    debitore, e viceversa. Nessuno dei due pezzi e' un'inferenza.
    verso = direzione(dispositivo)
    if verso["verso"] and verso["fiducia"] != "misto":
        lato_del_perdente = DEBITORE if verso["verso"] == CREDITORE else CREDITORE
        for condanna in condanne(dispositivo):
            if not condanna["spese"]:
                continue
            for nome in condanna["obbligati"]:
                _aggiungi(lati, nome, lato_del_perdente,
                          "soccombenza_e_direzione", condanna["prova"])
        for chiave in [k for k in lati if k.startswith("ruolo:")]:
            ruolo = chiave.split(":", 1)[1]
            for parte, voce in ruoli.items():
                if ruolo in voce["ruoli"]:
                    for proposta in lati[chiave]:
                        if proposta["criterio"] == "soccombenza_e_direzione":
                            _aggiungi(lati, parte, proposta["lato"],
                                      "soccombenza_e_direzione_per_ruolo",
                                      proposta["prova"])

    esito = {}
    for parte in set(ruoli) | set(lati):
        proposte = [p for p in lati.get(parte, []) if p["lato"]]
        registrate = [p for p in lati.get(parte, []) if not p["lato"]]
        distinti = {p["lato"] for p in proposte}
        if not distinti:
            lato, fiducia = None, "nessun_criterio"
        elif len(distinti) == 1:
            lato = distinti.pop()
            fiducia = "concordi" if len(proposte) > 1 else "un_solo_criterio"
        else:
            lato, fiducia = None, "discordi"
        ruoli_della_parte = ruoli.get(parte, {}).get("ruoli", [])
        if parte.startswith("ruolo:") and not ruoli_della_parte:
            ruoli_della_parte = [parte.split(":", 1)[1]]
        esito[parte] = {
            "ruoli": ruoli_della_parte,
            "lato": lato,
            "fiducia": fiducia,
            "criteri": sorted({p["criterio"] for p in proposte}),
            "prove": [p["prova"] for p in proposte if p["prova"]],
            "solo_registrato": sorted({p["criterio"] for p in registrate}),
        }
    return esito


#: Le formule del dispositivo che dicono da che parte e' andata. Ognuna e'
#: letterale: nessuna di queste e' una valutazione del merito.
FORMULE_DIREZIONE = (
    (r"revoc\w*\W+(?:\w+\W+){0,6}?decreto", DEBITORE, "revoca_del_decreto"),
    (r"(?:conferm\w*|dichiara\s+esecutiv\w*)\W+(?:\w+\W+){0,6}?decreto",
     CREDITORE, "conferma_del_decreto"),
    (r"accogli\w*\W+(?:\w+\W+){0,6}?opposizion", DEBITORE, "accoglie_opposizione"),
    (r"(?:rigett|respin)\w*\W+(?:\w+\W+){0,6}?opposizion",
     CREDITORE, "rigetta_opposizione"),
)


def direzione(dispositivo: str) -> dict:
    """Favor debitoris o favor creditoris, dalle formule del dispositivo.

    Non dice se la decisione e' giusta: dice da che parte e' caduta. Serve
    a sapere se una motivazione di rigetto e' materiale utile o un'arma
    della controparte."""
    if not dispositivo:
        return {"verso": None, "fiducia": "nessun_criterio", "prove": []}
    prove, versi = [], []
    for schema, verso, nome in FORMULE_DIREZIONE:
        for trovato in re.finditer(schema, dispositivo, re.IGNORECASE | re.DOTALL):
            versi.append(verso)
            prove.append(_prova("dispositivo", dispositivo,
                                trovato.start(), trovato.end(), nome))
    distinti = set(versi)
    if not distinti:
        return {"verso": None, "fiducia": "nessun_criterio", "prove": []}
    if len(distinti) > 1:
        # Accade davvero: accoglimento parziale, o piu' decreti nella
        # stessa causa. Dichiararlo misto e' l'unica lettura onesta.
        return {"verso": None, "fiducia": "misto", "prove": prove}
    return {"verso": distinti.pop(),
            "fiducia": "concordi" if len(versi) > 1 else "un_solo_criterio",
            "prove": prove}


def risolvi_parte(descrizione: str, parti: dict[str, dict]) -> dict:
    """Da come il modello ha chiamato la parte, al suo lato nel giudizio.

    Accetta lo pseudonimo ("Parte_1") o il ruolo ("l'appellante"). Sul
    ruolo risponde solo se in quel giudizio una sola parte lo riveste: se
    gli appellanti sono due con lati diversi, la frase e' ambigua e resta
    tale."""
    if not descrizione:
        return {"lato": None, "motivo": "parte_non_indicata"}

    #: Un'eccezione puo' essere attribuita a piu' parti insieme
    #: ("Parte_1 Parte_2 e Parte_3"): 150 coppie sulle 4807. Rispondere
    #: con il lato della prima e' una scelta travestita da lettura.
    nominati, visti = [], set()
    for trovato in PSEUDONIMO.finditer(descrizione):
        nome = canonico(trovato.group(0))
        if nome not in visti:
            visti.add(nome)
            nominati.append(nome)

    if nominati:
        ignoti = [n for n in nominati if n not in parti]
        if ignoti:
            return {"lato": None, "motivo": "pseudonimo_non_in_epigrafe",
                    "parte": ignoti[0], "parti": nominati}
        voci = [parti[n] for n in nominati]
        distinti = {v["lato"] for v in voci if v["lato"]}
        if len(distinti) > 1:
            return {"lato": None, "motivo": "parti_di_lati_diversi",
                    "parti": nominati}
        if not distinti:
            return {"lato": None, "motivo": voci[0]["fiducia"],
                    "parte": nominati[0], "parti": nominati,
                    "criteri": voci[0]["criteri"]}
        #: Il lato e' uno solo, ma se qualcuna delle parti nominate non ha
        #: criteri il silenzio di quella non contraddice: dice solo che
        #: non risulta. Si risponde, e si dichiara su quante parti.
        return {"lato": distinti.pop(),
                "motivo": voci[0]["fiducia"] if len(nominati) == 1
                          else "piu_parti_concordi",
                "parte": nominati[0], "parti": nominati,
                "criteri": sorted({c for v in voci for c in v["criteri"]})}

    marcatore = RUOLO.search(descrizione)
    if not marcatore:
        return {"lato": None, "motivo": "descrizione_non_riconosciuta"}
    ruolo = _normalizza_ruolo(marcatore.group(1))
    # Le voci `ruolo:` sono chiavi di lavoro: servono a portare una
    # condanna espressa per ruolo fino alle parti che quel ruolo lo
    # rivestono davvero. Se una parte vera c'e', risponde lei; la chiave
    # di lavoro parla solo quando l'epigrafe non nomina nessuno.
    nominate = [v for chiave, v in parti.items()
                if ruolo in v["ruoli"] and not chiave.startswith("ruolo:")]
    candidate = nominate or [v for chiave, v in parti.items()
                             if chiave == "ruolo:" + ruolo]
    lati = {v["lato"] for v in candidate if v["lato"]}
    if len(lati) == 1:
        return {"lato": lati.pop(), "motivo": "dal_ruolo:" + ruolo, "ruolo": ruolo}

    # "l'opponente" dice gia' tutto: e' l'ingiunto, e lo e' anche quando
    # l'epigrafe lo chiama attore. Pretendere l'epigrafe qui non aggiunge
    # rigore, toglie soltanto risposte che il testo dava.
    dal_monitorio = LATO_DAL_RUOLO.get(ruolo)
    if dal_monitorio and len(lati) <= 1:
        return {"lato": dal_monitorio, "motivo": "dal_ruolo_nel_monitorio:" + ruolo,
                "ruolo": ruolo}

    if len(lati) > 1:
        return {"lato": None, "motivo": "ruolo_ambiguo:" + ruolo, "ruolo": ruolo}
    if not candidate:
        return {"lato": None, "motivo": "ruolo_assente_in_epigrafe:" + ruolo,
                "ruolo": ruolo}
    return {"lato": None, "motivo": "ruolo_senza_lato:" + ruolo, "ruolo": ruolo}


def registro(intestazione: str, dispositivo: str) -> dict:
    """Tutto quello che il provvedimento dice di se stesso sulle parti."""
    return {
        "parti": lati_delle_parti(intestazione, dispositivo),
        "direzione": direzione(dispositivo),
    }
