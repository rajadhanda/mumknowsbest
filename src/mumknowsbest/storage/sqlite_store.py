"""SQLite-backed recipe store (zero-ops: one file).

Search is keyword-based for now (term overlap over a denormalized text blob), which
is plenty for a personal collection and needs no extra services. Semantic / vector
search is a deliberate extension point: add an `embedding` column and rerank here, or
write a separate `RecipeStore` implementation — nothing else has to change.
"""

from __future__ import annotations

import re
import sqlite3
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
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
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
        row = self._conn.execute(
            "SELECT data FROM recipes WHERE id = ?", (recipe_id,)
        ).fetchone()
        return Recipe.model_validate_json(row["data"]) if row else None

    def all(self) -> list[Recipe]:
        rows = self._conn.execute("SELECT data FROM recipes ORDER BY title").fetchall()
        return [Recipe.model_validate_json(r["data"]) for r in rows]

    def search(self, query: str, limit: int = 10) -> list[Recipe]:
        terms = _tokenize(query)
        rows = self._conn.execute("SELECT search_text, data FROM recipes").fetchall()
        if not terms:
            return [Recipe.model_validate_json(r["data"]) for r in rows[:limit]]
        scored: list[tuple[int, str]] = []
        for row in rows:
            text = row["search_text"]
            score = sum(text.count(t) for t in terms)
            if score:
                scored.append((score, row["data"]))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [Recipe.model_validate_json(data) for _, data in scored[:limit]]

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM recipes").fetchone()[0]

    # -- lifecycle ---------------------------------------------------------
    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "SqliteRecipeStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
