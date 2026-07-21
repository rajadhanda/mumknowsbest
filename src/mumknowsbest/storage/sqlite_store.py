"""SQLite-backed recipe store (zero-ops: one file).

Search is keyword-based for now (term overlap over a denormalized text blob), which
is plenty for a personal collection and needs no extra services. Semantic / vector
search is a deliberate extension point: add an `embedding` column and rerank here, or
write a separate `RecipeStore` implementation — nothing else has to change.

Thread-safety: the web server runs handlers on a threadpool, so one shared connection
is guarded by an RLock (writes are commit-per-call; contention is negligible at
personal scale). Swap for a connection pool only if this ever grows real concurrency.
"""

from __future__ import annotations

import re
import sqlite3
import threading
from pathlib import Path
from typing import Optional

from ..models import Recipe

_SCHEMA = """
CREATE TABLE IF NOT EXISTS recipes (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    source_type TEXT,
    language    TEXT,
    search_text TEXT NOT NULL,
    data        TEXT NOT NULL   -- full Recipe as JSON (source of truth)
);
"""

_WORD = re.compile(r"\w+", re.UNICODE)


def _tokenize(text: str) -> list[str]:
    return [t for t in _WORD.findall(text.lower()) if t]


class SqliteRecipeStore:
    def __init__(self, path: str | Path = "recipes.db") -> None:
        self.path = str(path)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    # -- internal ----------------------------------------------------------
    @staticmethod
    def _search_text(recipe: Recipe) -> str:
        parts = [recipe.title, " ".join(recipe.tags), recipe.raw_text]
        parts += [f"{i.qty or ''} {i.unit or ''} {i.item}" for i in recipe.ingredients]
        parts += recipe.steps
        parts += recipe.notes
        return " ".join(parts).lower()

    # -- RecipeStore -------------------------------------------------------
    def add(self, recipe: Recipe) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO recipes "
                "(id, title, source_type, language, search_text, data) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    recipe.id,
                    recipe.title,
                    recipe.source.type,
                    recipe.language,
                    self._search_text(recipe),
                    recipe.model_dump_json(),
                ),
            )
            self._conn.commit()

    def get(self, recipe_id: str) -> Optional[Recipe]:
        with self._lock:
            row = self._conn.execute(
                "SELECT data FROM recipes WHERE id = ?", (recipe_id,)
            ).fetchone()
        return Recipe.model_validate_json(row["data"]) if row else None

    def all(self) -> list[Recipe]:
        with self._lock:
            rows = self._conn.execute("SELECT data FROM recipes ORDER BY title").fetchall()
        return [Recipe.model_validate_json(r["data"]) for r in rows]

    def search(self, query: str, limit: int = 10) -> list[Recipe]:
        terms = _tokenize(query)
        if not terms:
            with self._lock:
                rows = self._conn.execute(
                    "SELECT data FROM recipes ORDER BY title LIMIT ?", (limit,)
                ).fetchall()
            return [Recipe.model_validate_json(r["data"]) for r in rows]

        # Two phases so only the winners' JSON is pulled and validated:
        # score over (id, search_text), then fetch full data for the top hits.
        with self._lock:
            rows = self._conn.execute("SELECT id, search_text FROM recipes").fetchall()
        scored = []
        for row in rows:
            score = sum(row["search_text"].count(t) for t in terms)
            if score:
                scored.append((score, row["id"]))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        top_ids = [rid for _, rid in scored[:limit]]
        if not top_ids:
            return []
        placeholders = ",".join("?" * len(top_ids))
        with self._lock:
            data_rows = self._conn.execute(
                f"SELECT id, data FROM recipes WHERE id IN ({placeholders})", top_ids
            ).fetchall()
        by_id = {r["id"]: r["data"] for r in data_rows}
        return [Recipe.model_validate_json(by_id[rid]) for rid in top_ids if rid in by_id]

    def count(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM recipes").fetchone()[0]

    # -- lifecycle ---------------------------------------------------------
    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> "SqliteRecipeStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
