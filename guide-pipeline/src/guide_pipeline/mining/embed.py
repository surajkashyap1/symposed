"""Local semantic similarity for overlap retrieval (no API cost).

Titles of the same question can be worded very differently ("paediatric ICU"
and "critically ill children"), which lexical search misses. A small open
source embedding model (BAAI/bge-small-en-v1.5 through fastembed, ONNX on the
CPU, about 200 texts a second) puts records with a similar meaning close
together. It only widens and orders what the overlap judge reads: the judge,
not the similarity score, decides whether a record is a duplicate.

`VectorIndex` keeps one vector per mirror record (PROSPERO, OSF) in SQLite,
embedded once and topped up after each refresh, so a run never re-embeds a
mirror.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Callable, Optional, Protocol

import numpy as np

Progress = Callable[[str], None]


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str]) -> np.ndarray:
        """One unit length row per text (float32)."""
        ...


def _unit(rows: np.ndarray) -> np.ndarray:
    rows = np.asarray(rows, dtype=np.float32)
    norms = np.linalg.norm(rows, axis=1, keepdims=True)
    return rows / np.where(norms == 0, 1, norms)


class LocalEmbedder:
    """fastembed, loaded on first use and cached in `models_dir`."""

    def __init__(self, name: str = "BAAI/bge-small-en-v1.5", *,
                 models_dir: str | Path = "data/models", batch_size: int = 256):
        self.name, self.models_dir, self.batch_size = name, Path(models_dir), batch_size
        self._model = None
        self._memo: dict[str, np.ndarray] = {}

    def _load(self):
        if self._model is None:
            from fastembed import TextEmbedding

            self.models_dir.mkdir(parents=True, exist_ok=True)
            self._model = TextEmbedding(self.name, cache_dir=str(self.models_dir))
        return self._model

    def embed(self, texts: list[str]) -> np.ndarray:
        todo = [t for t in dict.fromkeys(texts) if t not in self._memo]
        if todo:
            rows = _unit(np.array(list(self._load().embed(todo, batch_size=self.batch_size))))
            self._memo.update(zip(todo, rows))
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        return np.stack([self._memo[t] for t in texts])


_SCHEMA = """
CREATE TABLE IF NOT EXISTS vectors (
    source TEXT NOT NULL,
    id     TEXT NOT NULL,
    model  TEXT NOT NULL,
    vec    BLOB NOT NULL,
    PRIMARY KEY (source, id, model)
);
"""


class VectorIndex:
    """Stored vectors for mirror records, searched by cosine similarity."""

    def __init__(self, path: str | Path, embedder: Embedder) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path)
        self._db.executescript(_SCHEMA)
        self.embedder = embedder
        self._loaded: dict[str, tuple[list[str], np.ndarray]] = {}

    def close(self) -> None:
        self._db.close()

    def count(self, source: str) -> int:
        return self._db.execute("SELECT COUNT(*) FROM vectors WHERE source = ? AND model = ?",
                                (source, self.embedder.name)).fetchone()[0]

    def sync(self, source: str, texts: dict[str, str], *, chunk: int = 2048,
             progress: Optional[Progress] = None) -> int:
        """Embed every record not yet indexed; drop records no longer present."""
        have = {r[0] for r in self._db.execute(
            "SELECT id FROM vectors WHERE source = ? AND model = ?", (source, self.embedder.name))}
        gone = have - texts.keys()
        todo = sorted(texts.keys() - have)
        with self._db:
            self._db.executemany("DELETE FROM vectors WHERE source = ? AND id = ? AND model = ?",
                                 [(source, i, self.embedder.name) for i in gone])
        for start in range(0, len(todo), chunk):
            ids = todo[start:start + chunk]
            rows = self.embedder.embed([texts[i] for i in ids]).astype(np.float16)
            with self._db:
                self._db.executemany(
                    "INSERT OR REPLACE INTO vectors (source, id, model, vec) VALUES (?, ?, ?, ?)",
                    [(source, i, self.embedder.name, r.tobytes()) for i, r in zip(ids, rows)])
            if progress:
                progress(f"{source}: embedded {min(start + chunk, len(todo)):,} of {len(todo):,}")
        self._loaded.pop(source, None)
        return len(todo)

    def _matrix(self, source: str) -> tuple[list[str], np.ndarray]:
        if source not in self._loaded:
            rows = self._db.execute("SELECT id, vec FROM vectors WHERE source = ? AND model = ? "
                                    "ORDER BY id", (source, self.embedder.name)).fetchall()
            ids = [r[0] for r in rows]
            mat = (np.stack([np.frombuffer(r[1], dtype=np.float16) for r in rows])
                   if rows else np.zeros((0, 1), dtype=np.float16))
            self._loaded[source] = (ids, mat)
        return self._loaded[source]

    def search(self, source: str, queries: np.ndarray, *, k: int = 50,
               block: int = 100_000) -> list[tuple[str, float]]:
        """The k records most similar to any of the query vectors, best first."""
        ids, mat = self._matrix(source)
        if not ids or len(queries) == 0:
            return []
        q = queries.astype(np.float32).T
        best = np.empty(len(ids), dtype=np.float32)
        for start in range(0, len(ids), block):  # bounded memory on 500k records
            best[start:start + block] = (mat[start:start + block].astype(np.float32) @ q).max(axis=1)
        top = np.argsort(-best, kind="stable")[:k]
        return [(ids[i], float(best[i])) for i in top]
