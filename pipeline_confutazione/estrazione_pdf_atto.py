"""
Ingestione di un atto avversario in PDF nativo - il primo dei due buchi
identificati chiudendo la pipeline (l'altro e' assembla_report.py):
`estrazione_atto.py` (Fase 1) si aspettava gia' testo, non un PDF, e
nessun modulo del progetto faceva questo passaggio per un atto in
ingresso (bankit_parser.py/bdp_estrazione_pdf_pilota.py fanno PDF->testo
ma per un altro scopo, ingerire fonti nel grafo, non leggere un atto di
controparte).

Deliberatamente semplice: estrazione di testo grezzo, pagina per pagina,
senza il raggruppamento in paragrafi strutturati che bankit_parser.py fa
per le Disposizioni di Vigilanza (li' serve perche' la struttura a
paragrafi numerati e' nota e stabile; un atto di controparte reale ha una
struttura libera, non conviene assumerne una prima di aver visto un
esempio vero - stesso principio gia' seguito per redazione.py sull'atto
di controparte, mai ancora un esempio reale disponibile).

PDF nativo assunto (testo selezionabile, non scansione) - un PDF scansito
richiederebbe OCR, non gestito qui: se pdfplumber non estrae testo da
una pagina (pagina vuota nel risultato), viene segnalato esplicitamente
nel valore di ritorno, non ignorato in silenzio (stesso principio del
"fallire rumorosamente" gia' seguito in estrazione_atto.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class TestoEstrattoPdf:
    testo: str
    n_pagine: int
    pagine_senza_testo: list[int]  # indici 1-based delle pagine dove pdfplumber non ha trovato testo - probabile scansione, non PDF nativo

    @property
    def probabile_scansione(self) -> bool:
        """True se una frazione rilevante delle pagine e' vuota - segnale che
        il PDF e' (in tutto o in parte) una scansione, non testo nativo, e
        servirebbe OCR (non implementato qui). Soglia 30%, non 0%: qualche
        pagina di sola firma/timbro senza testo selezionabile e' normale
        anche in un atto altrimenti nativo, non deve far scattare un
        avviso per ogni singolo caso."""
        if self.n_pagine == 0:
            return False
        return len(self.pagine_senza_testo) / self.n_pagine > 0.3


def estrai_testo_da_pdf(percorso_pdf: str | Path) -> TestoEstrattoPdf:
    import pdfplumber

    percorso_pdf = Path(percorso_pdf)
    if not percorso_pdf.exists():
        raise FileNotFoundError(f"PDF non trovato: {percorso_pdf}")

    testi_pagina = []
    pagine_senza_testo = []
    with pdfplumber.open(str(percorso_pdf)) as pdf:
        for i, pagina in enumerate(pdf.pages, start=1):
            testo_pagina = pagina.extract_text() or ""
            if not testo_pagina.strip():
                pagine_senza_testo.append(i)
            testi_pagina.append(testo_pagina)
        n_pagine = len(pdf.pages)

    risultato = TestoEstrattoPdf(
        testo="\n\n".join(testi_pagina).strip(),
        n_pagine=n_pagine,
        pagine_senza_testo=pagine_senza_testo,
    )
    if risultato.probabile_scansione:
        print(
            f"ATTENZIONE: {len(pagine_senza_testo)}/{n_pagine} pagine senza testo estraibile - "
            "probabile PDF scansito, non nativo. OCR non implementato qui: il testo estratto "
            "sara' incompleto, non affidarsi al risultato senza controllo manuale."
        )
    return risultato


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        raise SystemExit("uso: python estrazione_pdf_atto.py <percorso.pdf>")
    risultato = estrai_testo_da_pdf(sys.argv[1])
    print(f"Pagine: {risultato.n_pagine}, pagine senza testo: {risultato.pagine_senza_testo}")
    print(f"Probabile scansione: {risultato.probabile_scansione}")
    print(f"\n--- Primi 500 caratteri ---\n{risultato.testo[:500]}")
