"""The storage contract.

Anything that can persist and search recipes implements `RecipeStore`. Today that's
SQLite; tomorrow it could be Postgres + pgvector or an in-memory store for tests —
the ingestion pipelines and the agent only depend on this interface.
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from ..models import Recipe


@runtime_checkable
class RecipeStore(Protocol):
    def add(self, recipe: Recipe) -> None:
        """Insert or replace a recipe by id."""

    def get(self, recipe_id: str) -> Optional[Recipe]:
        """Fetch one recipe by id, or None."""

    def all(self) -> list[Recipe]:
        """Return every recipe."""

    def search(self, query: str, limit: int = 10) -> list[Recipe]:
        """Find recipes relevant to a free-text query, best first."""

    def count(self) -> int:
        """Number of stored recipes."""
