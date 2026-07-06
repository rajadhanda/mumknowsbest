"""Storage layer: the `RecipeStore` interface and its implementations."""

from .base import RecipeStore
from .sqlite_store import SqliteRecipeStore

__all__ = ["RecipeStore", "SqliteRecipeStore"]
