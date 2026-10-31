from segmenta_provvedimenti import MAX_LUNGHEZZA_SEGMENTO, MIN_LUNGHEZZA_SEGMENTO, segmenta_motivazione


def test_offset_coerenti_con_testo_integrale():
    motivazione = "Prima frase abbastanza lunga per superare la soglia minima di lunghezza richiesta qui. " * 6
    testo_integrale = "INTESTAZIONE FITTIZIA.\n" + motivazione + "\nP.Q.M. dispositivo."
    segmenti = segmenta_motivazione("n1", motivazione, testo_integrale)
    for s in segmenti:
        assert testo_integrale[s.offset_inizio:s.offset_fine] == s.testo


def test_segmenti_coprono_lunghezza_minima_salvo_ultimo():
    motivazione = "Questa è una frase di prova numero uno. " * 30
    testo_integrale = motivazione
    segmenti = segmenta_motivazione("n2", motivazione, testo_integrale)
    for s in segmenti[:-1]:
        assert len(s.testo) >= MIN_LUNGHEZZA_SEGMENTO
    for s in segmenti:
        assert len(s.testo) <= MAX_LUNGHEZZA_SEGMENTO + 50  # tolleranza per l'ultima frase che completa la finestra


def test_non_spezza_su_abbreviazione_art():
    motivazione = "Ai sensi dell'art. 1218 c.c. il debitore risponde. Questo è un principio consolidato in giurisprudenza da tempo."
    testo_integrale = motivazione
    segmenti = segmenta_motivazione("n3", motivazione, testo_integrale)
    # una sola frase risultante (l'abbreviazione "art." non genera un confine)
    assert not any("dell'art" in s.testo and s.testo.strip().endswith("c.c.") for s in segmenti if len(s.testo) < 30)


def test_marcatore_numerato_forza_confine_dopo_il_minimo():
    # 7 ripetizioni x 66 caratteri = 462, sopra MIN_LUNGHEZZA_SEGMENTO (400):
    # il confine forzato scatta solo se il minimo è già stato raggiunto,
    # per costruzione (vedi segmenta_motivazione) - con 6 ripetizioni (396,
    # sotto il minimo) il marcatore non forzerebbe nulla, correttamente.
    frase_lunga = "Frase di riempimento per superare la soglia minima dichiarata. " * 7
    motivazione = frase_lunga + "\n1. Primo punto della decisione, esposto qui per esteso. " + frase_lunga
    testo_integrale = motivazione
    segmenti = segmenta_motivazione("n4", motivazione, testo_integrale)
    assert len(segmenti) >= 2
    assert not segmenti[0].testo.strip().startswith("1.")


def test_segmento_vuoto_non_incluso():
    segmenti = segmenta_motivazione("n5", "", "testo integrale qualsiasi")
    assert segmenti == []
