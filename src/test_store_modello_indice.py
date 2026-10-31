# -*- coding: utf-8 -*-
"""Il modello va con l'INDICE, non con il progetto.

Il difetto che questi test difendono non fallisce da solo. Fino al
2026-09-03 c'era una costante sola, `EMBEDDING_MODEL_NAME`, per DUE
indici: quello degli articoli e quello dei segmenti di provvedimento.
Riaddestrando il modello degli articoli e cambiando quella costante, le
query sull'indice dei segmenti sarebbero state calcolate con un modello
diverso da quello che lo ha costruito.

Misurato prima di scrivere il codice, non supposto: sulla stessa query, il
punteggio massimo sull'indice dei segmenti passa da **0,910 a 0,489**, e i
segmenti sopra la soglia 0,856 passano da 147 a **zero**. La quota di
giurisprudenza si sarebbe svuotata a ogni query, con la pipeline che
continuava a girare e nessun errore da nessuna parte.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

import store


def _indice_finto(tmp_path: Path, nome: str = "prova") -> tuple[Path, Path]:
    emb = tmp_path / f"{nome}.npy"
    idx = tmp_path / f"{nome}_index.json"
    np.save(emb, np.zeros((3, 4), dtype="float32"))
    idx.write_text(json.dumps(["a", "b", "c"]), encoding="utf-8")
    return emb, idx


def test_i_due_indici_non_condividono_piu_una_costante_sola():
    """Il modello dei segmenti resta il base, con la sua soglia. Quello
    degli articoli e' riaddestrato quando sta sul disco."""
    assert store.EMBEDDING_MODEL_BASE == "intfloat/multilingual-e5-small"
    assert store.EMBEDDING_MODEL_NAME == store.EMBEDDING_MODEL_BASE
    if store.MODELLO_ARTICOLI_ADDESTRATO.exists():
        assert store.EMBEDDING_MODEL_ARTICOLI != store.EMBEDDING_MODEL_BASE
    else:
        assert store.EMBEDDING_MODEL_ARTICOLI == store.EMBEDDING_MODEL_BASE


def test_senza_il_modello_addestrato_si_ripiega_sul_base():
    """Chi clona il repository senza i dati deve poter far girare tutto:
    `data/` non e' in git, e il modello riaddestrato ci vive dentro."""
    assert store.EMBEDDING_MODEL_ARTICOLI  # mai vuoto
    assert isinstance(store.EMBEDDING_MODEL_ARTICOLI, str)


def test_il_modello_si_dichiara_accanto_all_indice(tmp_path: Path):
    emb, _ = _indice_finto(tmp_path)
    store.scrivi_modello_dichiarato(emb, "un/modello")
    assert store.leggi_modello_dichiarato(emb) == "un/modello"
    assert store.percorso_modello_dichiarato(emb).name == "prova_modello.json"


def test_un_indice_interrogato_dal_modello_sbagliato_alza_un_errore(tmp_path: Path):
    """E' il test che conta: senza questo controllo la discordanza non
    produce un errore ma punteggi bassi e credibili."""
    emb, idx = _indice_finto(tmp_path)
    store.scrivi_modello_dichiarato(emb, "modello/che/lo/ha/costruito")
    with pytest.raises(store.IndiceDiUnAltroModello, match="punteggi bassi e credibili"):
        store.EmbeddingIndex.load(emb, idx, nome_modello="un/altro/modello")


def test_lo_stesso_modello_non_alza_niente(tmp_path: Path):
    emb, idx = _indice_finto(tmp_path)
    store.scrivi_modello_dichiarato(emb, "lo/stesso")
    indice = store.EmbeddingIndex.load(emb, idx, nome_modello="lo/stesso")
    assert indice.nome_modello == "lo/stesso"
    assert indice.node_ids == ["a", "b", "c"]


def test_un_indice_senza_dichiarazione_si_accetta(tmp_path: Path):
    """Rifiutarlo bloccherebbe chi ha indici anteriori a questa modifica.
    Il controllo si accende da solo quando l'indice viene ricostruito."""
    emb, idx = _indice_finto(tmp_path)
    assert store.leggi_modello_dichiarato(emb) is None
    indice = store.EmbeddingIndex.load(emb, idx, nome_modello="qualunque")
    assert indice.nome_modello == "qualunque"


def test_ogni_indice_porta_con_se_il_proprio_modello(tmp_path: Path):
    """Due indici, due modelli, nello stesso processo: e' la situazione
    di oggi e deve poter esistere."""
    a_emb, a_idx = _indice_finto(tmp_path, "articoli")
    s_emb, s_idx = _indice_finto(tmp_path, "segmenti")
    store.scrivi_modello_dichiarato(a_emb, "riaddestrato")
    store.scrivi_modello_dichiarato(s_emb, "base")
    articoli = store.EmbeddingIndex.load(a_emb, a_idx, nome_modello="riaddestrato")
    segmenti = store.EmbeddingIndex.load(s_emb, s_idx, nome_modello="base")
    assert articoli.nome_modello != segmenti.nome_modello


# --- l'indice vero, se c'e' ---

_EMB_VERO = store.GRAPH_DIR / "embeddings.npy"


@pytest.mark.skipif(not _EMB_VERO.exists(), reason="indice non costruito")
def test_l_indice_vero_degli_articoli_dichiara_il_suo_modello():
    """Se un giorno qualcuno ricostruisse l'indice con un modello e
    lasciasse la costante puntata a un altro, questo test lo direbbe."""
    dichiarato = store.leggi_modello_dichiarato(_EMB_VERO)
    assert dichiarato is not None, (
        "l'indice degli articoli non dichiara il modello: ricostruirlo con "
        "build_embeddings.py")
    assert dichiarato == store.EMBEDDING_MODEL_ARTICOLI


@pytest.mark.skipif(not _EMB_VERO.exists(), reason="indice non costruito")
def test_l_indice_vero_si_carica_senza_errori():
    indice = store.EmbeddingIndex.load(
        _EMB_VERO, store.GRAPH_DIR / "embeddings_index.json")
    assert len(indice.node_ids) == indice.embeddings.shape[0]
