"""
Test di guardia dell'invariante architetturale (regola 3 di Claude.md):
LA FASE 3 NON HA ALCUN PERCORSO DI IMPORT VERSO LO STORE O IL GRAFO.

**Risoluzione STATICA del grafo degli import, mai a runtime.** Il modulo
risolve gli import leggendo i sorgenti con `ast`, senza importare niente:

1. importare `redazione` per ispezionarne le dipendenze significherebbe
   eseguire gli import - cioe' proprio la cosa che il test deve poter
   dichiarare impossibile. Un test che deve compiere l'azione vietata per
   verificare che sia vietata non e' un test;
2. l'invariante e' una proprieta' del CODICE, non di una esecuzione: deve
   valere anche per un ramo mai percorso, un `if` falso, un import dentro
   una funzione che nessuno chiama;
3. `store.py` non e' nemmeno presente in questo checkout (vive in `src/`,
   condiviso con gli script di costruzione del corpus): un test a runtime
   qui non fallirebbe, si limiterebbe a non poter concludere - il modo
   peggiore di passare.

Il confronto avviene sulla CHIUSURA TRANSITIVA: non basta che
`redazione.py` non nomini `store`, deve non raggiungerlo attraverso
nessuna catena di moduli locali. `redazione -> pipeline -> store` era
esattamente il percorso reale prima dello split del 2026-08-20, e nessun
controllo sul solo sorgente di redazione.py lo avrebbe visto.

Eseguibile con pytest o direttamente:
    python test_import_grafo_isolato.py
"""

from __future__ import annotations

import ast
from pathlib import Path

CARTELLA = Path(__file__).parent

#: Moduli che rappresentano il grafo o vi conducono. `retrieval` e' in
#: elenco per costruzione: e' il modulo che il grafo lo tocca per mestiere
#: (unico punto di riapertura per la migrazione temporale), quindi
#: raggiungerlo dalla Fase 3 equivale a raggiungere lo store.
MODULI_DEL_GRAFO = frozenset({"store", "retrieval", "build_graph", "parser", "references_grafo"})

#: I moduli della Fase 3. Nessuno di questi puo' raggiungere il grafo.
MODULI_FASE_3 = ("redazione", "constrained_decoding")

#: Chi puo' importare `retrieval`: la Fase 2 e l'orchestratore (per il
#: passo 1-bis di riformulazione della query, che e' una chiamata LLM e
#: quindi non puo' stare dentro la Fase 2 "solo Python, zero LLM").
#: I test sono ammessi: verificano, non compongono la pipeline.
IMPORTATORI_LECITI_DI_RETRIEVAL = frozenset({"assembla_report", "esegui_pipeline"})


def _moduli_importati(percorso: Path) -> set[str]:
    """Nomi di modulo di primo livello importati dal sorgente, presi
    dall'AST completo.

    Cammina TUTTO l'albero (`ast.walk`), non solo i nodi di livello
    superiore: un `from store import GraphStore` dentro il corpo di una
    funzione e' un percorso di import a tutti gli effetti, e sarebbe
    invisibile sia a una lettura dei soli import di testa sia a una
    ricerca testuale ancorata a inizio riga.

    `from . import x` e simili non compaiono in questo progetto (moduli
    piatti, nessun package): un import relativo verrebbe ignorato da
    `node.module is None`, quindi il test lo dichiara esplicitamente non
    supportato invece di fingere di averlo esaminato."""
    albero = ast.parse(percorso.read_text(encoding="utf-8"), filename=str(percorso))
    moduli: set[str] = set()
    for nodo in ast.walk(albero):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                moduli.add(alias.name.split(".")[0])
        elif isinstance(nodo, ast.ImportFrom):
            if nodo.level:
                raise AssertionError(
                    f"{percorso.name}: import relativo (livello {nodo.level}) non supportato da questo test - "
                    "il progetto usa moduli piatti; se cambia, va aggiornata la risoluzione qui"
                )
            if nodo.module:
                moduli.add(nodo.module.split(".")[0])
    return moduli


def _e_modulo_locale(nome: str) -> bool:
    """Locale = c'e' un file `<nome>.py` accanto a questo test. `store` e
    gli altri moduli di `src/` NON sono locali in questo senso (non sono
    in questa cartella) e non vanno seguiti: contano come foglia
    raggiunta, che e' esattamente cio' che il test cerca."""
    return (CARTELLA / f"{nome}.py").is_file()


def chiusura_import(modulo: str) -> dict[str, list[str]]:
    """Chiusura transitiva degli import a partire da un modulo locale.
    Ritorna {modulo_raggiunto: catena che ci ha portato}, cosi' un
    fallimento mostra IL PERCORSO e non solo il fatto."""
    percorso_di: dict[str, list[str]] = {modulo: [modulo]}
    da_visitare = [modulo]

    while da_visitare:
        corrente = da_visitare.pop()
        for importato in sorted(_moduli_importati(CARTELLA / f"{corrente}.py")):
            if importato in percorso_di:
                continue
            percorso_di[importato] = percorso_di[corrente] + [importato]
            if _e_modulo_locale(importato):
                da_visitare.append(importato)

    del percorso_di[modulo]
    return percorso_di


def test_fase3_non_raggiunge_il_grafo() -> None:
    """Il criterio di accettazione dello split."""
    for modulo in MODULI_FASE_3:
        raggiunti = chiusura_import(modulo)
        vietati = sorted(MODULI_DEL_GRAFO & raggiunti.keys())
        assert not vietati, (
            f"{modulo}.py raggiunge il grafo attraverso: "
            + "; ".join(" -> ".join(raggiunti[v]) for v in vietati)
        )


def test_fase3_non_manipola_sys_path_verso_src() -> None:
    """Nessun modulo di Fase 3 deve inserire `src/` in sys.path: sarebbe
    un import verso il grafo preparato ma non ancora scritto, invisibile
    alla chiusura degli import e pronto a diventare vero al primo
    `from store import ...` aggiunto per comodita'."""
    for modulo in MODULI_FASE_3:
        sorgente = (CARTELLA / f"{modulo}.py").read_text(encoding="utf-8")
        assert '"src"' not in sorgente and "'src'" not in sorgente, (
            f"{modulo}.py prepara sys.path verso src/ - la Fase 3 non deve poter raggiungere lo store, "
            "nemmeno predisponendosi a farlo"
        )


def test_redazione_dipende_solo_da_generazione_vincolata() -> None:
    """La forma positiva dell'invariante: non solo "non raggiunge il
    grafo", ma "raggiunge esattamente questo". Un test che elenca solo i
    divieti passa anche se redazione.py acquisisce una dipendenza nuova e
    inattesa che oggi non tocca il grafo ma domani si'."""
    raggiunti = chiusura_import("redazione")
    locali = {m for m in raggiunti if _e_modulo_locale(m)}
    assert locali == {"constrained_decoding", "llama_server_client"}, (
        f"redazione.py dipende da moduli locali inattesi: {sorted(locali)} "
        "(attesi: constrained_decoding, llama_server_client)"
    )


def test_retrieval_importato_solo_dalla_fase2_e_dall_orchestratore() -> None:
    """`retrieval.py` e' il modulo di Fase 2 che tocca il grafo: se lo
    importasse mezza pipeline, confinare la conoscenza dello schema del
    grafo in un solo posto non servirebbe a niente."""
    importatori = set()
    for percorso in sorted(CARTELLA.glob("*.py")):
        modulo = percorso.stem
        if modulo in ("retrieval", "test_import_grafo_isolato"):
            continue
        if "retrieval" in _moduli_importati(percorso):
            importatori.add(modulo)

    non_leciti = {m for m in importatori if not m.startswith("test_")} - IMPORTATORI_LECITI_DI_RETRIEVAL
    assert not non_leciti, (
        f"moduli che importano retrieval senza esserne autorizzati: {sorted(non_leciti)} "
        f"(leciti: {sorted(IMPORTATORI_LECITI_DI_RETRIEVAL)} piu' i test)"
    )


def test_orchestratore_importa_il_grafo_solo_dentro_le_funzioni() -> None:
    """`esegui_pipeline.py` deve poter essere importato su una macchina
    SENZA store.py.

    La modalita' `--solo-fase1 --batch`, che serve a costruire il golden
    set, non tocca il grafo: deve girare dove il grafo non c'e' - come
    questo workspace, dove `src/` non esiste. Basta un `import
    assembla_report` spostato in testa al modulo "per pulizia" perche'
    quella modalita' muoia all'avvio con un ImportError che non c'entra
    niente con quello che sta facendo.

    Percio' gli import di store/retrieval/assembla_report/pipeline stanno
    DENTRO le funzioni che li usano, ed e' un requisito, non uno stile."""
    percorso = CARTELLA / "esegui_pipeline.py"
    if not percorso.is_file():
        return  # l'entry point non esiste ancora: niente da controllare

    albero = ast.parse(percorso.read_text(encoding="utf-8"), filename=str(percorso))
    in_testa: set[str] = set()
    for nodo in albero.body:  # SOLO il corpo del modulo, non ast.walk
        if isinstance(nodo, ast.Import):
            in_testa.update(alias.name.split(".")[0] for alias in nodo.names)
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            in_testa.add(nodo.module.split(".")[0])

    vietati = sorted(MODULI_DEL_GRAFO & in_testa | {"assembla_report", "pipeline", "verify"} & in_testa)
    assert not vietati, (
        f"esegui_pipeline.py importa {vietati} a livello di modulo: la modalita' "
        "--solo-fase1 --batch non potrebbe piu' girare senza il grafo. Spostare l'import "
        "dentro la funzione che ne ha bisogno."
    )


def test_moduli_di_fase3_sono_analizzabili() -> None:
    """Rete di sicurezza contro il modo silenzioso in cui questo test
    potrebbe smettere di controllare qualcosa: se un file di Fase 3 viene
    rinominato o spostato, `chiusura_import` solleverebbe FileNotFoundError
    - meglio dirlo qui, con un messaggio che spiega cosa e' successo."""
    for modulo in MODULI_FASE_3:
        percorso = CARTELLA / f"{modulo}.py"
        assert percorso.is_file(), (
            f"{modulo}.py non trovato in {CARTELLA}: il test di guardia sta controllando un modulo "
            "che non esiste piu' - aggiornare MODULI_FASE_3 dopo averne verificato il motivo"
        )


if __name__ == "__main__":
    prove = [
        test_moduli_di_fase3_sono_analizzabili,
        test_fase3_non_raggiunge_il_grafo,
        test_fase3_non_manipola_sys_path_verso_src,
        test_redazione_dipende_solo_da_generazione_vincolata,
        test_retrieval_importato_solo_dalla_fase2_e_dall_orchestratore,
        test_orchestratore_importa_il_grafo_solo_dentro_le_funzioni,
    ]
    for prova in prove:
        prova()
        print(f"[OK] {prova.__name__}")

    print("\nChiusura transitiva degli import, per ispezione:")
    for modulo in MODULI_FASE_3:
        raggiunti = chiusura_import(modulo)
        locali = sorted(m for m in raggiunti if _e_modulo_locale(m))
        esterni = sorted(m for m in raggiunti if not _e_modulo_locale(m))
        print(f"  {modulo}.py")
        print(f"    moduli del progetto : {locali or '(nessuno)'}")
        print(f"    moduli esterni      : {esterni or '(nessuno)'}")
