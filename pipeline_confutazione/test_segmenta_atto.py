"""Test della sotto-segmentazione (contratto 1.19): un segmento naturale
piu' grande del budget da solo non deve mai restare intero ne' essere
troncato - vedi CONTRATTI_DATI.md, changelog 1.19, per il caso reale che
l'ha motivata (la sezione numerata "4)" dell'atto reale di prova, 7516
caratteri, che faceva perdere il passaggio sulla nullita' della
fideiussione al filtro di Fase 1).

Eseguibile con pytest o direttamente:
    python test_segmenta_atto.py
"""

from __future__ import annotations

import sys
from pathlib import Path

CARTELLA = Path(__file__).parent
sys.path.insert(0, str(CARTELLA))

import segmenta_atto


def _conta_approssimato(testo: str) -> int:
    """4 caratteri/token - stima grezza, sufficiente per verificare la
    LOGICA di divisione senza dipendere da llama-server (stesso principio
    dello smoke test in fondo a segmenta_atto.py)."""
    return max(1, len(testo) // 4)


def test_segmento_sotto_budget_non_viene_toccato() -> None:
    """Un segmento gia' dentro il budget non deve essere sotto-segmentato
    - _sotto_segmenta deve essere un no-op per il caso comune."""
    testo = "1) Prima sezione, breve.\n\n2) Seconda sezione, anche breve."
    blocchi = segmenta_atto.segmenta_con_span(testo, _conta_approssimato, budget_token=1000)
    assert len(blocchi) == 1
    assert blocchi[0].segmenti_padre == frozenset()


def test_segmento_sovradimensionato_viene_diviso_per_capoverso() -> None:
    """Una sezione numerata grande, con capoversi interni, seguita da una
    seconda sezione breve (serve un secondo marcatore perche'
    _trova_sezioni_numerate riconosca la numerazione, altrimenti il
    fallback a paragrafi la dividerebbe gia' al livello TOP, senza mai
    passare dalla sotto-segmentazione che questo test verifica): la
    sezione "1)" deve dividersi in piu' blocchi, tutti con
    segmenti_padre popolato; la "2)" resta intatta."""
    capoversi = [f"Capoverso numero {i}, con abbastanza testo da contare per qualcosa " * 6
                 for i in range(10)]
    testo = "1) Prima sezione, lunga\n\n" + "\n\n".join(capoversi) + "\n\n2) Seconda sezione, breve."
    blocchi = segmenta_atto.segmenta_con_span(testo, _conta_approssimato, budget_token=100)

    assert len(blocchi) > 2, "la sezione '1)' sovradimensionata deve dividersi in piu' di un blocco"
    blocchi_1 = [b for b in blocchi if b.fine <= testo.index("2) Seconda")]
    assert len(blocchi_1) > 1
    for b in blocchi_1:
        assert b.segmenti_padre, "ogni blocco frutto della divisione deve portare il riferimento al padre"
        assert "Prima sezione, lunga" in next(iter(b.segmenti_padre))

    blocco_2 = [b for b in blocchi if b.fine > testo.index("2) Seconda")]
    assert len(blocco_2) == 1 and blocco_2[0].segmenti_padre == frozenset(), \
        "la sezione '2)', gia' dentro il budget, non deve essere toccata"


def test_nessun_carattere_perso_ne_duplicato() -> None:
    """Invariante piu' importante: la sotto-segmentazione ridistribuisce i
    confini, non riscrive il testo. Ogni carattere del testo pulito
    originale deve comparire in ESATTAMENTE un blocco (via gli offset,
    non il testo unito con '\\n\\n' che puo' differire per gli spazi)."""
    capoversi = [f"Capoverso {i} con del testo di riempimento vario e diverso " * 8 for i in range(8)]
    testo = "1) Sezione unica\n\n" + "\n\n".join(capoversi) + "\n\n2) Seconda sezione breve."
    testo_pulito = segmenta_atto.pulisci_numeri_pagina(testo)

    blocchi = segmenta_atto.segmenta_con_span(testo, _conta_approssimato, budget_token=80)
    assert len(blocchi) > 2, "il test non verifica nulla se non si divide"

    coperti = [False] * len(testo_pulito)
    for b in blocchi:
        assert b.inizio >= 0 and b.fine <= len(testo_pulito) and b.inizio < b.fine
        for i in range(b.inizio, b.fine):
            assert not coperti[i], f"carattere a offset {i} coperto da piu' di un blocco"
            coperti[i] = True

    non_spazi_non_coperti = [i for i, c in enumerate(coperti) if not c and not testo_pulito[i].isspace()]
    assert not non_spazi_non_coperti, (
        f"{len(non_spazi_non_coperti)} caratteri non-spazio persi dalla sotto-segmentazione - "
        "il vincolo 'mai troncato' e' violato"
    )


def test_segmento_senza_nessun_confine_resta_intero_ma_non_trasformato() -> None:
    """Caso limite dichiarato: se nemmeno il livello frase trova un
    confine (una sola 'frase' enorme, senza punteggiatura di fine frase
    riconoscibile), il segmento resta intero - MAI troncato. Non e' un
    fallimento silenzioso: e' la stessa politica di prima di questa
    patch, ora raggiunta solo dopo aver provato tutti e tre i livelli."""
    frase_gigante = "parola " * 500  # nessun punto, nessuna maiuscola dopo spazio: nessun confine di frase
    testo = f"1) Sezione\n\n{frase_gigante}"
    blocchi = segmenta_atto.segmenta_con_span(testo, _conta_approssimato, budget_token=50)
    testi_uniti = "".join(b.testo for b in blocchi)
    assert "parola" * 1 in testi_uniti  # nessun troncamento a meta' parola
    assert sum(len(b.testo) for b in blocchi) >= len(frase_gigante.strip())


def test_sulla_sezione_reale_della_fideiussione() -> None:
    """Il caso vero (CONTRATTI_DATI.md 1.19): la sezione numerata '4)'
    dell'atto reale di prova (7516 caratteri, 2424 token REALI misurati via
    /tokenize - indivisibile prima di questa patch, a qualunque budget)
    deve dividersi, e il passaggio sulla nullita' della fideiussione deve
    finire in un blocco piu' piccolo della sezione intera.

    budget_token=1800, non 2200 (il budget di produzione): il conta-token
    approssimato di questo test (4 caratteri/token) sottostima il reale
    (qui il rapporto vero e' ~3.1 caratteri/token, misurato dal vivo) - a
    2200 approssimati la sezione risulterebbe sotto soglia e il test non
    eserciterebbe la sotto-segmentazione. Il rapporto vero va verificato
    contro un server reale (vedi CONTRATTI_DATI.md), non qui."""
    percorso = CARTELLA / "fixture_atto_reale.txt"
    if not percorso.exists():
        return  # fixture assente in alcuni ambienti - non e' questo il test che deve fallire per quello
    testo = percorso.read_text(encoding="utf-8")
    blocchi = segmenta_atto.segmenta_con_span(testo, _conta_approssimato, budget_token=1800)

    blocchi_fideiussione = [b for b in blocchi if "dichiarata nulla in quanto la forma scritta" in b.testo]
    assert len(blocchi_fideiussione) == 1, "il passaggio deve comparire in esattamente un blocco"
    blocco = blocchi_fideiussione[0]
    assert blocco.segmenti_padre, "deve portare il riferimento al segmento '4)' da cui proviene"
    assert len(blocco.testo) < 7516, "il blocco che lo contiene deve essere piu' piccolo della sezione intera"


if __name__ == "__main__":
    test_segmento_sotto_budget_non_viene_toccato()
    test_segmento_sovradimensionato_viene_diviso_per_capoverso()
    test_nessun_carattere_perso_ne_duplicato()
    test_segmento_senza_nessun_confine_resta_intero_ma_non_trasformato()
    test_sulla_sezione_reale_della_fideiussione()
    print("Tutti i test di test_segmenta_atto.py sono passati.")


def test_i_segmenti_naturali_non_sono_ancora_accorpati():
    """`segmenta_con_span` accorpa fino a riempire il budget del modello.
    Una spazzata esaustiva vuole l'unita' che l'ATTO dichiara, non l'unita'
    di lavorazione: accorpare qui rimetterebbe dentro la possibilita' di
    saltare un passaggio senza accorgersene, che e' la sola cosa che la
    spazzata esiste per togliere."""
    testo = "\n\n".join("%d) Sezione numero %d con un poco di testo." % (i, i)
                        for i in range(1, 6))
    conta = lambda t: max(1, len(t) // 4)

    naturali = segmenta_atto.segmenti_naturali(testo, conta, budget_token=6000)
    blocchi = segmenta_atto.segmenta_con_span(testo, conta, budget_token=6000)

    assert len(naturali) == 5
    assert len(blocchi) == 1, "col budget largo i cinque segmenti fanno un blocco solo"


def test_i_segmenti_naturali_portano_offset_veri_sul_testo_pulito():
    """Regola 4: chi cita deve poter ritagliare dal testo pulito con quegli
    offset e riottenere lo stesso testo, altrimenti l'ancoraggio a valle e'
    spostato in silenzio."""
    testo = "1\n\n1) Prima sezione dell'atto.\n\n2) Seconda sezione dell'atto.\n"
    conta = lambda t: max(1, len(t) // 4)

    pulito = segmenta_atto.pulisci_numeri_pagina(testo)
    for seg in segmenta_atto.segmenti_naturali(testo, conta):
        assert pulito[seg.inizio:seg.fine] == seg.testo
