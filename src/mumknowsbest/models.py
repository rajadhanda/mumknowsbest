"""Canonical recipe model.

Every source (paper book, Instagram, YouTube) normalizes into a `Recipe`, so the
storage layer and the agent never need to know where a recipe came from. This is
the contract that keeps the rest of the system decoupled.

`ExtractedRecipe` is the LLM-facing shape (no id/source — the pipeline adds those);
`Recipe` extends it, so content fields are declared exactly once and
`Recipe.from_extraction()` is the single place an extraction becomes a stored recipe.
"""

from __future__ import annotations

import uuid
from typing import Literal, Optional

from pydantic import BaseModel, Field

SourceType = Literal["book", "instagram", "youtube", "manual"]

_ID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "mumknowsbest")


class Ingredient(BaseModel):
    item: str
    qty: Optional[str] = None  # kept as text ("1/2", "a pinch", "andaaz") — recipes aren't all numeric
    unit: Optional[str] = None


class SourceRef(BaseModel):
    """Where a recipe came from, so the agent can point Mum back to the original."""

    type: SourceType
    url: Optional[str] = None
    page_photo: Optional[str] = None  # asset filename servable via /api/photos/{name}


class ExtractedRecipe(BaseModel):
    """What the vision/transcription models return for one recipe."""

    title: str
    servings: Optional[int] = None
    time_minutes: Optional[int] = None
    ingredients: list[Ingredient] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)  # cook's tips, variations, substitutions, garnish
    tags: list[str] = Field(default_factory=list)
    language: str = "en"  # "en" | "hi" | "hinglish" — preserve what the source actually used
    raw_text: str = ""  # original wording, for grounding and citations


class PageExtraction(BaseModel):
    """One photo/transcript may yield zero, one, or several recipes."""

    recipes: list[ExtractedRecipe] = Field(default_factory=list)


class Recipe(ExtractedRecipe):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source: SourceRef

    @classmethod
    def from_extraction(
        cls, er: ExtractedRecipe, source: SourceRef, *, identity: Optional[str] = None
    ) -> "Recipe":
        """Promote an extraction to a stored recipe.

        `identity` makes the id deterministic (uuid5), so re-ingesting the same
        source upserts instead of duplicating.
        """
        recipe = cls(source=source, **er.model_dump())
        if identity:
            recipe.id = str(uuid.uuid5(_ID_NAMESPACE, identity))
        return recipe

    def brief(self) -> dict:
        """The one compact summary shape used by both the agent tools and the API."""
        return {
            "id": self.id,
            "title": self.title,
            "tags": self.tags,
            "language": self.language,
            "source": self.source.type,
        }
