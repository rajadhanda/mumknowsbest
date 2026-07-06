"""The ingestion contract + a tiny driver.

A `RecipeSource` knows how to produce `Recipe`s from somewhere. `ingest()` just pumps
them into any `RecipeStore`. This is the seam where YouTube and Instagram sources will
slot in next — same interface, same `ingest()` driver.
"""

from __future__ import annotations

from typing import Iterable, Protocol, runtime_checkable

from ..models import Recipe
from ..storage.base import RecipeStore


@runtime_checkable
class RecipeSource(Protocol):
    name: str

    def extract(self) -> Iterable[Recipe]:
        """Yield recipes from this source (lazily where possible)."""


def ingest(source: RecipeSource, store: RecipeStore) -> int:
    """Load every recipe from `source` into `store`; return how many were added."""
    added = 0
    for recipe in source.extract():
        store.add(recipe)
        added += 1
    return added
