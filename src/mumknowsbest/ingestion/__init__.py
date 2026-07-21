"""Ingestion: turn a source into `Recipe`s and load them into a store.

Each source (paper book, YouTube, Instagram) implements `RecipeSource`. New sources
plug in without touching storage or the agent.
"""

from .base import RecipeSource, ingest
from .paper_book import PaperBookSource, recipes_from_photo_bytes

__all__ = ["RecipeSource", "ingest", "PaperBookSource", "recipes_from_photo_bytes"]
