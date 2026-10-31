"""Famiglia, rango e natura del rapporto ricavati dal grafo (contratto 1.29).

Questi test difendono tre proprieta', tutte imparate sbagliando:

1. cio' che il grafo non dice non viene inventato;
2. un articolo che il corpus usa come ARMA non qualifica il contratto;
3. quando due strati discordano si dichiara, non si sceglie.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import famiglie_grafo as fg  # noqa: E402

#: Profili finti, minimi ma della stessa FORMA di quelli veri: cosi' i test
#: non dipendono dal grafo (che sulla macchina del golden set non c'e') ne'
#: dai numeri di una particolare promozione.
PROFILI = {
    "rango_per_articolo": {
        "codice_civile::1283": "merito",
        "codice_civile::1815": "merito",
        "codice_civile::1842": "merito",
        "codice_civile::1845": "merito",
        "codice_civile::2946": "preliminare_di_merito",
        "codice_procedura_civile::645": "rito",
        "codice_procedura_civile::166": "rito",
        "tub::50": "merito",
    },
    "istituto_per_articolo": {
        "codice_civile::1815": "Del mutuo",
        "codice_civile::1842": "Dell'apertura di credito bancario",
        "codice_civile::1845": "Dell'apertura di credito bancario",
        "codice_civile::1283": "Delle obbligazioni pecuniarie",
    },
    "comunita_per_articolo": {
        "codice_civile::1283": 1,
        "codice_civile::1815": 1,
        "tub::50": 5,
        "codice_procedura_civile::645": 5,
        "codice_civile::2946": 2,
    },
    "comunita": [
        {"comunita": 1, "rango_dominante": "merito",
         "lessico": [["anatocismo", 2.0], ["capitalizzazione", 1.8], ["trimestrale", 1.5]]},
        {"comunita": 2, "rango_dominante": "non_classificato",
         "lessico": [["prescrizionale", 2.0], ["postali", 1.4]]},
        {"comunita": 5, "rango_dominante": "rito",
         "lessico": [["certificazione", 1.9], ["monitoria", 1.2]]},
    ],
}


# --- lo strato delle norme citate ----------------------------------------

def test_una_norma_citata_da_rango_e_comunita():
    esito = fg.classifica("nullita' della clausola ex art. 1283 c.c.", PROFILI)

    assert esito["articoli"] == ["codice_civile::1283"]
    assert esito["rango"] == "merito"
    assert esito["famiglia"] == 1


def test_la_prescrizione_e_preliminare_di_merito():
    esito = fg.classifica("il credito e' prescritto ex art. 2946 c.c.", PROFILI)

    assert esito["rango"] == "preliminare_di_merito"


def test_il_merito_vince_sul_rito_quando_ci_sono_entrambi():
    """Un'eccezione che tocca il merito E' di merito anche se cita l'art.
    645 c.p.c. per inquadrare il giudizio. E' anche cio' che neutralizza
    l'impalcatura processuale senza doverla elencare."""
    esito = fg.classifica(
        "nell'opposizione ex art. 645 c.p.c. si eccepisce la nullita' ex art. 1283 c.c.",
        PROFILI)

    assert esito["rango"] == "merito"


def test_solo_rito_resta_rito():
    esito = fg.classifica("nullita' della citazione ex art. 166 c.p.c.", PROFILI)

    assert esito["rango"] == "rito"


def test_una_citazione_senza_codice_non_univoca_non_viene_assegnata():
    """"art. 645" senza qualificatore: l'estrattore assume il codice
    civile. Se il numero esiste in piu' codici del grafo non si sceglie -
    stesso principio del BUG-GRAFO-4 sulle citazioni brevi ambigue."""
    profili = dict(PROFILI)
    profili["rango_per_articolo"] = dict(PROFILI["rango_per_articolo"])
    profili["rango_per_articolo"]["codice_civile::645"] = "merito"

    _, ambigue = fg.articoli_dal_testo("si veda l'art. 645", profili)

    assert ambigue == ["645"]


# --- lo strato del lessico del corpus ------------------------------------

def test_il_lessico_del_corpus_classifica_chi_non_cita_norme():
    """Il 69,8% delle eccezioni reali non cita nessuna norma: senza questo
    strato resterebbero tutte senza famiglia."""
    esito = fg.classifica(
        "la capitalizzazione trimestrale degli interessi costituisce anatocismo", PROFILI)

    assert esito["strati"]["norme_citate"] == []
    assert esito["famiglia"] == 1
    assert esito["rango"] == "merito", "il rango arriva dalla comunita' quando non c'e' norma"


def test_una_comunita_mista_non_presta_il_proprio_rango():
    """La comunita' 2 tiene insieme la prescrizione e la procedura
    d'appello: non ha un rango dominante, e non ne inventa uno."""
    esito = fg.classifica("termine prescrizionale dei buoni postali", PROFILI)

    assert esito["famiglia"] == 2
    assert esito["rango"] == fg.NON_CLASSIFICATO


def test_due_comunita_che_pesano_uguale_non_producono_una_famiglia():
    esito = fg.classifica("anatocismo e certificazione", PROFILI)

    assert esito["famiglia"] is None
    assert len(esito["strati"]["punteggi_lessico"]) == 2


def test_la_norma_citata_batte_il_lessico_ma_il_disaccordo_si_dichiara():
    esito = fg.classifica(
        "la certificazione monitoria non prova il credito, art. 1283 c.c.", PROFILI)

    assert esito["famiglia"] == 1, "vince la norma citata"
    assert any("lessico del corpus" in d for d in esito["disaccordi"])


# --- la natura del rapporto ----------------------------------------------

def test_gli_articoli_dell_apertura_di_credito_qualificano_il_rapporto():
    esito = fg.natura_del_rapporto(
        "il contratto ex art. 1842 c.c. del 1998, revocato ex art. 1845 c.c.", PROFILI)

    assert esito["natura_rapporto"] == "apertura_credito_cc"
    assert esito["da_norme"] == "apertura_credito_cc"


def test_un_articolo_di_battaglia_non_qualifica_il_contratto():
    """L'art. 1815 c.c. sta nel capo "Del mutuo" ma il corpus lo colloca
    nella comunita' dell'anatocismo e dell'usura: e' citato per
    argomentare, non per dire che contratto sia. Senza questa regola
    qualificava come "mutuo" un'opposizione di conto corrente - lo stesso
    errore del modello, commesso da noi."""
    esito = fg.natura_del_rapporto(
        "interessi usurari ex art. 1815 c.c., ex art. 1815 c.c., ex art. 1815 c.c.", PROFILI)

    assert esito["natura_rapporto"] == fg.NON_DESUMIBILE
    assert esito["da_norme"] is None


def test_un_solo_articolo_non_basta_a_qualificare():
    esito = fg.natura_del_rapporto("si veda l'art. 1842 c.c.", PROFILI)

    assert esito["natura_rapporto"] == fg.NON_DESUMIBILE


def test_il_nome_dell_istituto_nel_testo_qualifica_quando_le_norme_tacciono():
    """Il vocabolario e' quello del codice civile - "Dell'apertura di
    credito bancario" e' un titolo di sezione, non una parola scelta da
    noi."""
    esito = fg.natura_del_rapporto(
        "il rapporto di apertura di credito, apertura di credito concessa nel 1998", PROFILI)

    assert esito["natura_rapporto"] == "apertura_credito_cc"
    assert esito["da_nomi"] == "apertura_credito_cc"


def test_piu_istituti_nominati_senza_margine_danno_non_desumibile():
    """E' il caso dell'atto Verdi: una fideiussione su apertura di
    credito in conto corrente che nomina anche un mutuo. Il modello scelse
    `finanziamento_rateale` e quel valore decise il merito di quattro
    eccezioni."""
    # Le occorrenze misurate sull'atto vero: apertura 2, conto corrente 2,
    # mutuo 3. Nessuna stacca l'altra del doppio, quindi non si sceglie.
    esito = fg.natura_del_rapporto(
        "apertura di credito ... apertura di credito ... del conto corrente ... "
        "del conto corrente ... del mutuo ... del mutuo ... del mutuo", PROFILI)

    assert esito["natura_rapporto"] == fg.NON_DESUMIBILE
    assert len(esito["occorrenze"]) >= 2


# --- l'invariante: senza profili non si fallisce, ci si astiene -----------

def test_senza_profili_il_modulo_si_astiene_e_lo_dice():
    """`--solo-fase1 --batch` gira dove il grafo non c'e': l'assenza dei
    profili non puo' fermare l'estrazione."""
    esito = fg.classifica("art. 1283 c.c.", None)

    assert esito["famiglia"] is None
    assert esito["rango"] == fg.NON_CLASSIFICATO
    assert esito["disaccordi"], "l'astensione va dichiarata, non taciuta"

    natura = fg.natura_del_rapporto("apertura di credito", None)
    assert natura["natura_rapporto"] == fg.NON_DESUMIBILE


def test_un_percorso_inesistente_non_solleva():
    assert fg.carica_profili("questo/file/non/esiste.json") is None


def test_i_profili_veri_hanno_la_forma_che_il_runtime_si_aspetta():
    """Contratto fra `src/profili_famiglia.py` e questo modulo: se il
    generatore cambia forma, qui si rompe subito invece che in corsa."""
    profili = fg.carica_profili()
    if profili is None:
        return  # macchina senza grafo: legittimo, vedi il docstring

    for chiave in ("rango_per_articolo", "istituto_per_articolo",
                   "comunita_per_articolo", "comunita"):
        assert chiave in profili, f"i profili non hanno piu' '{chiave}'"
    for profilo in profili["comunita"]:
        assert profilo["rango_dominante"] in fg.RANGHI
        assert all(isinstance(t, str) and isinstance(peso, (int, float))
                   for t, peso in profilo["lessico"])
    assert set(profili["rango_per_articolo"].values()) <= set(fg.RANGHI)


# --- lo strato vettoriale e la regola di concordanza (1.29) --------------

def test_il_voto_dei_vicini_richiede_il_quorum():
    """Uno strato che risponde sempre non puo' entrare in una regola di
    concordanza: concorderebbe per caso."""
    etichette = {"0": 1, "1": 1, "2": 1, "3": 1, "4": 3, "5": 3}
    simili = [0.9, 0.8, 0.7, 0.6, 0.5, 0.4]

    assert fg.famiglia_da_vettori(simili, etichette) == 1

    sparsi = {"0": 1, "1": 3, "2": 4, "3": 5, "4": 0, "5": 2}
    assert fg.famiglia_da_vettori(simili, sparsi) is None, "senza quorum si tace"


def test_il_voto_ignora_le_righe_fuori_dalla_matrice():
    """I profili e la matrice possono disallinearsi (grafo sostituito a
    mano): un indice oltre la fine non deve far esplodere la corsa. Con
    un solo vicino superstite il quorum non c'e' e si tace - che e' la
    risposta giusta, non un ripiego."""
    assert fg.famiglia_da_vettori([0.9], {"0": 1, "99": 3}) is None

    simili = [0.9, 0.8, 0.7, 0.6, 0.5]
    etichette = {"0": 1, "1": 1, "2": 1, "3": 1, "999": 3}
    assert fg.famiglia_da_vettori(simili, etichette) == 1


def test_senza_etichette_lo_strato_vettoriale_si_astiene():
    assert fg.famiglia_da_vettori([0.9, 0.8], {}) is None


def test_quando_i_due_strati_concordano_la_fiducia_e_dichiarata():
    """Misurato su 965 eccezioni del golden set: dove concordano la
    precisione e' 0,804, contro 0,523 del solo lessico."""
    esito = fg.concorda(1, 1)

    assert esito["comunita"] == 1
    assert esito["fiducia"] == "concordi"


def test_quando_discordano_non_si_sceglie():
    """Dove i due discordano crollano entrambi (0,224 il lessico, 0,418 i
    vettori): il disaccordo non e' un pareggio da sciogliere, e' il
    segnale che l'eccezione va letta a mano."""
    esito = fg.concorda(1, 3)

    assert esito["comunita"] is None
    assert esito["fiducia"] == "discordi"
    assert esito["nota"] and "1" in esito["nota"] and "3" in esito["nota"]


def test_un_solo_strato_risponde_e_lo_si_dice():
    """Non e' la stessa cosa di una concordanza, e il file deve poterle
    distinguere: la precisione e' 0,464 contro 0,804."""
    assert fg.concorda(2, None)["fiducia"] == "uno_solo"
    assert fg.concorda(None, 2)["fiducia"] == "uno_solo"
    assert fg.concorda(None, 2)["comunita"] == 2


def test_nessuno_strato_parla():
    esito = fg.concorda(None, None)

    assert esito["comunita"] is None
    assert esito["fiducia"] == "nessuno"
    assert esito["nota"] is None, "non sapere non e' un disaccordo"


# --- la concordanza dentro classifica() (1.29) ---------------------------

def test_senza_strato_vettoriale_la_fiducia_e_uno_solo_e_niente_si_revoca():
    """In Fase 1 l'indice dei segmenti non c'e'. Un votante che non si
    presenta non degrada il risultato: non c'e' stato nessun voto."""
    esito = fg.classifica("capitalizzazione trimestrale e anatocismo", PROFILI)

    assert esito["famiglia"] == 1
    assert esito["fiducia"] == "uno_solo"
    assert esito["strati"]["famiglia_da_vettori"] is None


def test_concordi_conferma_la_comunita_e_lo_dichiara():
    esito = fg.classifica("capitalizzazione trimestrale e anatocismo", PROFILI,
                          famiglia_dai_vettori=1)

    assert esito["famiglia"] == 1
    assert esito["fiducia"] == "concordi"
    assert esito["disaccordi"] == []


def test_discordi_revoca_la_comunita_che_poggiava_sul_lessico():
    """Dove lessico e vettori discordano la precisione crolla a 0,224 e
    0,418: la comunita' che poggiava su quel voto non regge."""
    esito = fg.classifica("capitalizzazione trimestrale e anatocismo", PROFILI,
                          famiglia_dai_vettori=5)

    assert esito["strati"]["famiglia_da_lessico"] == 1
    assert esito["famiglia"] is None, "sul disaccordo non si sceglie"
    assert esito["fiducia"] == "discordi"
    assert any("discordano" in d for d in esito["disaccordi"])


def test_una_norma_citata_non_si_annulla_per_un_voto_a_cui_non_partecipava():
    """E' il punto delicato della 1.29. L'art. 1283 c.c. e' CITATO
    dall'eccezione: la sua comunita' non viene dal voto lessico/vettori e
    non puo' essere revocata da quel voto. Il disaccordo resta dichiarato."""
    esito = fg.classifica("nullita' della clausola ex art. 1283 c.c., "
                          "capitalizzazione trimestrale", PROFILI,
                          famiglia_dai_vettori=5)

    assert esito["strati"]["famiglia_da_norme"] == 1
    assert esito["famiglia"] == 1, "la norma citata regge"
    assert esito["fiducia"] == "discordi", "ma il disaccordo si dichiara lo stesso"
    assert len(esito["disaccordi"]) >= 1


def test_i_vettori_coprono_dove_nessun_altro_strato_parla():
    """Lo strato vettoriale sta in CODA alla precedenza: non cambia i casi
    gia' decisi, aggiunge solo copertura dove uscivano senza comunita'."""
    muta = "il termine e' spirato senza che nulla fosse dedotto"
    senza = fg.classifica(muta, PROFILI)
    assert senza["famiglia"] is None

    con = fg.classifica(muta, PROFILI, famiglia_dai_vettori=2)
    assert con["famiglia"] == 2
    assert con["fiducia"] == "uno_solo"
    assert con["rango"] == "non_classificato", (
        "la comunita' 2 non ha rango dominante: non se ne inventa uno")


def test_il_rango_non_sopravvive_alla_comunita_revocata():
    """Se la comunita' cade, il rango che si sarebbe preso da lei non puo'
    restare: sarebbe l'ordine dei motivi deciso da una classificazione
    ritirata."""
    esito = fg.classifica("certificazione monitoria", PROFILI,
                          famiglia_dai_vettori=1)

    assert esito["fiducia"] == "discordi"
    assert esito["famiglia"] is None
    assert esito["rango"] == "non_classificato"


def test_i_profili_veri_portano_le_etichette_dei_segmenti():
    profili = fg.carica_profili()
    if profili is None:
        return
    etichette = profili.get("comunita_per_segmento")

    assert etichette, "senza etichette dei segmenti lo strato vettoriale non esiste"
    assert all(isinstance(v, int) for v in etichette.values())
    assert all(k.isdigit() for k in etichette)
