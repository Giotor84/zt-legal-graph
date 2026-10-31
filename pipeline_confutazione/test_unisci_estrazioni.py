# -*- coding: utf-8 -*-
"""L'unione delle due estrazioni.

Cio' che i test difendono e' che l'unione non perda niente e non inventi
niente: nessuna voce sparisce, nessuna delimitazione viene scelta da una
soglia, e due sistemi di coordinate diversi non si fondono mai in silenzio.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import unisci_estrazioni as ue  # noqa: E402


def _f1(*voci) -> dict:
    return {"eccezioni": [
        {"eccezione_id": "X%02d" % i, "testo_verbatim": t,
         "famiglia_probabile": "prescrizione",
         "ancora": {"stato": "ancorata", "inizio": a, "fine": b,
                    "corrispondenza": "esatta"}}
        for i, (t, a, b) in enumerate(voci, 1)]}


def _sp(*voci) -> dict:
    return {"eccezioni": [{"verbatim": t, "inizio": a, "fine": b,
                           "famiglia_probabile": "vizi_fideiussione",
                           "corrispondenza": "esatta"}
                          for t, a, b in voci]}


# ------------------------------------------------------- niente si perde

def test_cio_che_trova_uno_solo_dei_due_resta_nell_unione() -> None:
    """E' la ragione per cui il modulo esiste: misurato su cinque atti, il
    75% di cio' che ciascun metodo trova da solo e' materiale vero che
    l'altro perde."""
    testo = "AAAA" + "B" * 20 + "CCCC" + "D" * 20
    esito = ue.unisci(_f1(("B" * 20, 4, 24)), _sp(("D" * 20, 28, 48)), testo)

    assert esito["conteggi"]["voci"] == 2
    assert {v["testo"] for v in esito["voci"]} == {"B" * 20, "D" * 20}


def test_un_eccezione_che_fase1_non_ha_saputo_collocare_non_sparisce() -> None:
    """Senza offset non puo' entrare in nessuna zona, ma resta un'eccezione
    trovata: esce a parte invece di essere buttata."""
    f1 = {"eccezioni": [{"eccezione_id": "X01", "testo_verbatim": "una tesi",
                         "ancora": {"stato": "non_ancorata"}}]}

    esito = ue.unisci(f1, _sp(), "un testo qualsiasi")

    assert esito["conteggi"]["non_ancorate_di_fase1"] == 1
    assert esito["non_ancorate"][0]["stato_ancora"] == "non_ancorata"


def test_nessuna_voce_viene_tolta_dal_controllo_di_citabilita(monkeypatch) -> None:
    """Il controllo SEGNALA e non blocca: misurato su 58 fette giudicate a
    mano, bloccare su `frammento_sospeso` avrebbe salvato 4 scarti al
    prezzo di 3 frasi vere, e in un atto difensivo un'eccezione persa costa
    piu' di una da scartare a mano."""
    monkeypatch.setattr(ue.citabilita, "valuta", lambda *a, **k: {
        "categoria": "frammento_sospeso", "motivo": "si interrompe",
        "citabile": False, "azione": "blocca"})
    testo = "AAAA" + "B" * 20

    esito = ue.unisci(_f1(("B" * 20, 4, 24)), _sp(), testo, base_url="http://x")

    assert esito["conteggi"]["voci"] == 1, "una voce segnalata resta una voce"
    voce = esito["voci"][0]
    assert voce["citabilita"]["da_rivedere"] is True
    assert voce["citabilita"]["azione_del_controllo"] == "blocca", (
        "l'azione misurata resta scritta anche se non viene applicata")
    assert "blocca" not in ue.AZIONI_ATTIVE


# --------------------------------------------- niente viene scelto a caso

def test_si_fondono_solo_le_fette_identiche() -> None:
    """Jaccard fonderebbe anche le quasi-identiche, ma li' il continuo c'e'
    davvero (misurato: 6 coppie sotto 0,1, poi 5, 8, 9, fino alle 12
    identiche) e ogni taglio sarebbe un numero inventato."""
    testo = "AAAA" + "B" * 30
    identiche = ue.unisci(_f1(("B" * 20, 4, 24)), _sp(("B" * 20, 4, 24)), testo)
    quasi = ue.unisci(_f1(("B" * 20, 4, 24)), _sp(("B" * 19, 4, 23)), testo)

    assert identiche["conteggi"]["voci"] == 1
    assert sorted(identiche["voci"][0]["trovata_da"]) == ["fase1", "spazzata"]
    assert quasi["conteggi"]["voci"] == 2, (
        "due delimitazioni diverse restano due proposte, non una media")


def test_una_zona_con_piu_voci_non_diventa_una_voce_sola() -> None:
    """Il caso dal vivo: Fase 1 [16337:18440] 2103 caratteri contro tre
    fette della spazzata dentro di esso. Non e' un'eccezione delimitata
    male: e' una zona su cui i due non concordano su QUANTE ne stiano
    leggendo, e fonderla distruggerebbe la granularita' fine - cioe'
    esattamente il materiale che si e' deciso di non buttare."""
    testo = "X" * 10 + "Y" * 90
    esito = ue.unisci(_f1(("Y" * 90, 10, 100)),
                      _sp(("Y" * 30, 10, 40), ("Y" * 30, 40, 70),
                          ("Y" * 30, 70, 100)), testo)

    assert esito["conteggi"]["voci"] == 4, "le quattro proposte restano quattro"
    assert esito["conteggi"]["zone"] == 1, "ma stanno tutte nella stessa zona"
    assert {v["voci_nella_zona"] for v in esito["voci"]} == {4}


def test_la_soglia_della_zona_non_cambia_il_risultato() -> None:
    """Sulle 54 coppie misurate la distribuzione del contenimento e'
    bimodale - 45 a contenimento pieno, 5 sopra 0,9, 4 in tutto il resto -
    quindi qualunque valore fra 0,50 e 0,90 seleziona 52 o 50 coppie delle
    stesse 54. Se un giorno questo test fallisse, vorrebbe dire che la
    forma dei dati e' cambiata e che SOGLIA_ZONA e' tornata a essere una
    decisione."""
    voci = [{"trovata_da": "fase1", "testo": "a", "inizio": 0, "fine": 100},
            {"trovata_da": "spazzata", "testo": "b", "inizio": 10, "fine": 90},
            {"trovata_da": "spazzata", "testo": "c", "inizio": 200, "fine": 260}]

    zone = {s: len({v["zona"] for v in ue.raggruppa_in_zone(
        [dict(v) for v in voci], soglia=s)}) for s in (0.5, 0.7, 0.9)}

    assert set(zone.values()) == {2}, "il raggruppamento non dipende dalla soglia"


def test_due_eccezioni_adiacenti_non_finiscono_nella_stessa_zona() -> None:
    """Il rischio dell'altro verso: con un contenimento troppo permissivo
    due eccezioni distinte che si sfiorano diventerebbero una zona sola, e
    chi rivede le giudicherebbe insieme."""
    testo = "A" * 100
    esito = ue.unisci(_f1(("A" * 50, 0, 50)), _sp(("A" * 49, 51, 100)), testo)

    assert esito["conteggi"]["zone"] == 2


# ------------------------------------------------- niente si fonde al buio

def test_due_sistemi_di_coordinate_diversi_non_si_uniscono() -> None:
    """L'unico errore che questo modulo solleva invece di dichiarare. I due
    metodi ancorano sullo stesso testo ripulito per costruzione, ma quella
    e' una proprieta' di due moduli scritti in momenti diversi: se uno
    cambiasse pulizia, gli offset resterebbero numeri plausibili che
    puntano al posto sbagliato, e la regola 4 poggia su quegli offset."""
    with pytest.raises(ue.CoordinateIncoerenti):
        ue.unisci(_f1(("una frase che non sta li'", 0, 25)), _sp(),
                  "un testo completamente diverso da quello atteso")


def test_gli_offset_non_vengono_ne_ricalcolati_ne_spostati() -> None:
    """Regola 4: gli offset li ha gia' calcolati Python a monte
    (`localizza.localizza`, la stessa procedura per entrambi i metodi).
    Qui si uniscono, non si rifanno."""
    testo = "AAAA" + "B" * 20 + "CCCC"
    esito = ue.unisci(_f1(("B" * 20, 4, 24)), _sp(), testo)

    assert (esito["voci"][0]["inizio"], esito["voci"][0]["fine"]) == (4, 24)


def test_si_sa_sempre_quale_metodo_ha_trovato_cosa() -> None:
    """Se un domani uno dei due peggiorasse, senza questo campo non si
    potrebbe accorgersene senza rifare tutto il confronto."""
    testo = "AAAA" + "B" * 20 + "CC" + "D" * 20
    esito = ue.unisci(_f1(("B" * 20, 4, 24)), _sp(("D" * 20, 26, 46)), testo)

    assert esito["conteggi"]["per_provenienza"] == {"fase1": 1, "spazzata": 1}


def test_l_uscita_dichiara_cio_che_non_sta_dicendo() -> None:
    """Una zona con piu' voci ha tutta l'aria di essere un'eccezione con
    delle varianti, e non lo e'. Chi legge il JSON senza aver letto il
    modulo deve trovarcelo scritto."""
    esito = ue.unisci(_f1(), _sp(), "")

    assert "NON e' un'eccezione sola" in esito["cosa_non_dice"]
    assert esito["meta"]["versione_contratto"] == ue.VERSIONE_CONTRATTO


# --------------------------------------------- l'uscita rispetta il contratto

def _valida(esito: dict) -> None:
    import json as _json

    import jsonschema

    schema = _json.loads(
        (Path(__file__).parent.parent / "contratti" /
         "unione_estrazioni.schema.json").read_text(encoding="utf-8"))
    errori = sorted(jsonschema.Draft202012Validator(schema).iter_errors(esito),
                    key=lambda e: list(e.path))
    assert not errori, "\n".join(
        "%s: %s" % (list(e.path), e.message) for e in errori[:5])


def test_l_uscita_valida_contro_lo_schema() -> None:
    """Regola 1: `contratti/` e' la specifica vincolante. Se l'uscita
    divergesse dallo schema, sbaglierebbe l'uscita."""
    testo = "AAAA" + "B" * 20 + "CC" + "D" * 20
    _valida(ue.unisci(_f1(("B" * 20, 4, 24)), _sp(("D" * 20, 26, 46)), testo,
                      sorgenti={"fase1": "x_01_estrazione.json",
                                "spazzata": "x_spazzata.json"}))


def test_valida_anche_con_i_giudizi_di_citabilita(monkeypatch) -> None:
    """Il ramo con il modello acceso ha campi che l'altro non ha, ed e'
    quello che finisce in produzione: validarne solo uno dei due
    lascerebbe scoperto proprio quello che si usa."""
    monkeypatch.setattr(ue.citabilita, "valuta", lambda *a, **k: {
        "categoria": "dipende_dal_contesto", "motivo": "rimanda a `tale`",
        "citabile": False, "azione": "segnala"})
    testo = "AAAA" + "B" * 20

    _valida(ue.unisci(_f1(("B" * 20, 4, 24)), _sp(), testo,
                      base_url="http://x",
                      sorgenti={"fase1": "a.json", "spazzata": "b.json"}))


def test_valida_anche_l_atto_che_fase1_non_ha_saputo_leggere() -> None:
    """Il caso dal vivo del 2026-09-01: 0 eccezioni da un lato, decine
    dall'altro, e delle non ancorate in mezzo. Un contratto che regge solo
    sul caso normale non serve a niente il giorno in cui qualcosa rompe."""
    f1 = {"eccezioni": [{"eccezione_id": "X01", "testo_verbatim": "una tesi",
                         "ancora": {"stato": "ancora_parziale"}}]}
    testo = "Z" * 40

    _valida(ue.unisci(f1, _sp(("Z" * 20, 0, 20)), testo,
                      sorgenti={"fase1": "a.json", "spazzata": "b.json"}))


# --------------------------------------------- cosa passa a valle, e perche'

def _voce(inizio, fine, categoria="sta_in_piedi_da_sola", da=("spazzata",),
          zona=1) -> dict:
    return {"trovata_da": list(da), "testo": "x" * (fine - inizio),
            "inizio": inizio, "fine": fine, "zona": zona,
            "voci_nella_zona": 1, "famiglie_proposte": [None],
            "famiglia_probabile": None, "corrispondenza": "esatta",
            "citabilita": {"categoria": categoria, "motivo": "",
                           "azione_del_controllo": "passa",
                           "da_rivedere": categoria != "sta_in_piedi_da_sola"}}


def test_a_valle_va_la_granularita_fine_non_il_blocco() -> None:
    """Il caso dal vivo: un blocco Fase 1 da 2103 caratteri e tre fette
    della spazzata dentro di esso. Mandare tutte e quattro farebbe cercare
    in memoria quattro volte per lo stesso punto e confutarlo quattro
    volte; mandare solo il blocco confuterebbe tre argomenti in massa.
    Vanno le tre, ed e' il motivo per cui `_senza_sovrapposizioni`
    massimizza il NUMERO di fette e non la lunghezza coperta."""
    zona = [_voce(0, 900), _voce(0, 300), _voce(300, 600), _voce(600, 900)]

    scelte = ue.seleziona_per_valle(zona)

    assert [(v["inizio"], v["fine"]) for v in scelte] == [(0, 300), (300, 600), (600, 900)]


def test_una_zona_senza_niente_di_citabile_dichiara_il_ripiego() -> None:
    """"La piu' lunga vince" e' l'euristica gia' bocciata in §7.36:
    concordava 19 su 19 col giudizio umano e non significava niente,
    perche' l'annotatore che vinceva era anche sistematicamente piu'
    lungo. Qui resta come ultima risorsa, ma deve DIRSI: senza
    l'etichetta sarebbe indistinguibile da una scelta motivata."""
    zona = [_voce(0, 100, "frammento_sospeso"),
            _voce(10, 400, "dipende_dal_contesto")]

    scelte = ue.seleziona_per_valle(zona)

    assert len(scelte) == 1
    assert scelte[0]["motivo_della_scelta"] == "ripiego_la_piu_lunga"
    assert (scelte[0]["inizio"], scelte[0]["fine"]) == (10, 400)


def test_la_fetta_su_cui_i_due_concordano_batte_le_altre() -> None:
    """Misurato: le 12 fette identiche prodotte dai due metodi stanno in
    piedi da sole 10 volte su 12 (83%), la percentuale piu' alta di
    qualunque altro gruppo. E' il solo segnale di qualita' che l'unione
    produce da se', e va speso."""
    zona = [_voce(0, 300, da=("fase1", "spazzata")), _voce(0, 900)]

    scelte = ue.seleziona_per_valle(zona)

    assert [v["motivo_della_scelta"] for v in scelte] == ["concordi"]
    assert (scelte[0]["inizio"], scelte[0]["fine"]) == (0, 300)


def test_una_zona_con_una_voce_sola_non_dichiara_una_scelta_mai_fatta() -> None:
    """La maggior parte delle zone e' di questo tipo (173 su 202 misurate):
    etichettarle "citabile" direbbe che una scelta e' stata fatta e che
    quella voce l'ha vinta, e renderebbe illeggibile il conteggio dei
    motivi proprio nella riga che si guarda per prima."""
    scelte = ue.seleziona_per_valle([_voce(0, 300)])

    assert scelte[0]["motivo_della_scelta"] == "unica_nella_zona"


def test_ogni_motivo_dichiarato_e_uno_di_quelli_previsti() -> None:
    zone = [_voce(0, 100, "frammento_sospeso", zona=1),
            _voce(10, 400, "dipende_dal_contesto", zona=1),
            _voce(500, 800, zona=2),
            _voce(900, 1000, da=("fase1", "spazzata"), zona=3),
            _voce(900, 1200, zona=3)]

    for voce in ue.seleziona_per_valle(zone):
        assert voce["motivo_della_scelta"] in ue.MOTIVI_DI_SCELTA


def test_le_eccezioni_per_fase2_dicono_da_dove_vengono() -> None:
    """Senza `trovata_da` un'eccezione della spazzata sarebbe
    indistinguibile da una di Fase 1, e non ci sarebbe modo di accorgersi
    che uno dei due metodi e' peggiorato senza rifare da capo tutto il
    confronto. E' l'unica cosa che questo aggancio poteva rompere in
    silenzio."""
    blocchi = [{"blocco_id": "B01", "inizio": 0, "fine": 1000}]
    scelte = ue.seleziona_per_valle([_voce(0, 300, da=("fase1", "spazzata"))])

    eccezioni = ue.come_eccezioni_di_fase1(scelte, blocchi)

    assert eccezioni[0]["trovata_da"] == ["fase1", "spazzata"]
    assert eccezioni[0]["motivo_della_scelta"] in ue.MOTIVI_DI_SCELTA
    assert eccezioni[0]["ancora"]["blocco_id"] == "B01", (
        "il blocco si CALCOLA dall'offset: non e' un dato mancante")
    assert eccezioni[0]["testo_verbatim"] == eccezioni[0]["testo_letterale"]


def test_le_eccezioni_per_fase2_valgono_contro_il_contratto_di_fase1() -> None:
    """Fase 2 e Fase 3 non sanno che l'unione esiste: leggono `eccezioni`
    come hanno sempre fatto. Se la forma divergesse dal contratto di Fase 1
    se ne accorgerebbero a Fase 1 gia' spesa."""
    import json as _json

    import jsonschema

    schema = _json.loads(
        (Path(__file__).parent.parent / "contratti" /
         "fase1_estrazione.schema.json").read_text(encoding="utf-8"))
    sotto = {**schema["properties"]["eccezioni"]["items"],
             "$defs": schema.get("$defs", {})}
    blocchi = [{"blocco_id": "B01", "inizio": 0, "fine": 1000}]

    for eccezione in ue.come_eccezioni_di_fase1(
            ue.seleziona_per_valle([_voce(0, 300)]), blocchi):
        errori = list(jsonschema.Draft202012Validator(sotto).iter_errors(eccezione))
        assert not errori, errori[0].message


# ---------------- la precondizione che l'unione stava buttando via -------

#: Trovato il 2026-09-03 rieseguendo la Fase 2 sull'atto ALFA con tutte e
#: venti le regole: le 21 eccezioni arrivate al dossier portavano
#: `specificita: specifica` 21 volte su 21, mentre l'estrazione di Fase 1
#: dello stesso atto ne aveva 12 su 17 `generica`. L'unione le
#: sovrascriveva con una costante, e `specifica` e' il valore che fa dire
#: a quattordici regole su venti "l'eccezione regge": il motore restava
#: acceso e non attaccava mai. Zero confutazioni, con l'aria di averle
#: valutate.

def _estrazione(*eccezioni: dict) -> dict:
    return {"eccezioni": list(eccezioni)}


def _origine(id_eccezione: str, specificita: str, conteggi: bool = False) -> dict:
    return {"eccezione_id": id_eccezione, "specificita": specificita,
            "conteggi_allegati": conteggi}


def test_la_specificita_di_fase1_arriva_a_fase2() -> None:
    blocchi = [{"blocco_id": "B01", "inizio": 0, "fine": 1000}]
    voce = {**_voce(0, 300, da=("fase1",)), "id_di_origine": "X07"}

    (eccezione,) = ue.come_eccezioni_di_fase1(
        ue.seleziona_per_valle([voce]), blocchi,
        _estrazione(_origine("X07", "generica")))

    assert eccezione["specificita"] == "generica"


def test_i_conteggi_allegati_di_fase1_arrivano_a_fase2() -> None:
    blocchi = [{"blocco_id": "B01", "inizio": 0, "fine": 1000}]
    voce = {**_voce(0, 300, da=("fase1",)), "id_di_origine": "X07"}

    (eccezione,) = ue.come_eccezioni_di_fase1(
        ue.seleziona_per_valle([voce]), blocchi,
        _estrazione(_origine("X07", "specifica", conteggi=True)))

    assert eccezione["conteggi_allegati"] is True


def test_la_voce_della_sola_spazzata_dice_che_nessuno_ha_chiesto() -> None:
    """Dalla 1.36 il contratto sa dire 'non si sa', e le voci della sola
    spazzata lo dicono. Fino alla 1.35 valeva `specifica`, che e' il
    valore che fa dire a quattordici regole su venti che l'eccezione
    regge: un ripiego che decide l'esito."""
    blocchi = [{"blocco_id": "B01", "inizio": 0, "fine": 1000}]

    (eccezione,) = ue.come_eccezioni_di_fase1(
        ue.seleziona_per_valle([_voce(0, 300, da=("spazzata",))]), blocchi,
        _estrazione(_origine("X07", "generica")))

    assert eccezione["specificita"] == "non_desumibile"
    assert eccezione["conteggi_allegati"] is False


def test_senza_l_estrazione_di_fase1_nessuno_ha_chiesto() -> None:
    """La firma resta compatibile con i chiamanti che non la passano, e
    il valore che ne esce dice il vero: senza l'estrazione, la risposta
    del modello non e' raggiungibile da qui."""
    blocchi = [{"blocco_id": "B01", "inizio": 0, "fine": 1000}]

    (eccezione,) = ue.come_eccezioni_di_fase1(
        ue.seleziona_per_valle([{**_voce(0, 300, da=("fase1",)),
                                 "id_di_origine": "X07"}]), blocchi)

    assert eccezione["specificita"] == "non_desumibile"


def _enum_del_contratto(nome: str) -> list[str]:
    import json as _json

    schema = _json.loads(
        (Path(__file__).parent.parent / "contratti" /
         "fase1_estrazione.schema.json").read_text(encoding="utf-8"))
    return schema["properties"]["eccezioni"]["items"]["properties"][nome]["enum"]


def test_il_valore_di_chi_non_ha_chiesto_e_nel_contratto() -> None:
    """Un valore fuori enum farebbe fallire la validazione a Fase 1 gia'
    spesa."""
    assert ue.SPECIFICITA_NON_CHIESTA in _enum_del_contratto("specificita")


def test_la_grammatica_della_chiamata_resta_binaria() -> None:
    """`non_desumibile` NON e' un terzo giudizio che il modello puo'
    dare: significa che la domanda a nessuno e' stata posta. Se entrasse
    nell'enum della chiamata, "il modello non sa" e "nessuno ha chiesto"
    diventerebbero lo stesso valore, e le quattordici regole che ci
    girano sopra non potrebbero piu' distinguerli."""
    import estrazione_atto

    ammessi = (estrazione_atto.SCHEMA_ECCEZIONI["properties"]["eccezioni_sollevate"]
               ["items"]["properties"]["specificita"]["enum"])

    assert ammessi == ["specifica", "generica"]
    assert ue.SPECIFICITA_NON_CHIESTA not in ammessi
