"""Canonical recipe model.

Every source (paper book, Instagram, YouTube) normalizes into a `Recipe`, so the
storage layer and the agent never need to know where a recipe came from. This is
the contract that keeps the rest of the system decoupled.
"""

from __future__ import annotations

import uuid
from typing import Literal, Optional

from pydantic import BaseModel, Field

SourceType = Literal["book", "instagram", "youtube", "manual"]


class Ingredient(BaseModel):
    item: str
    qty: Optional[str] = None  # kept as text ("1/2", "a pinch") — recipes aren't all numeric
    unit: Optional[str] = None


class SourceRef(BaseModel):
    """Where a recipe came from, so the agent can point Mum back to the original."""

    type: SourceType
    url: Optional[str] = None
    page_photo: Optional[str] = None  # path/filename of the source image (book pages)


class Recipe(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    source: SourceRef
    servings: Optional[int] = None
    time_minutes: Optional[int] = None
    ingredients: list[Ingredient] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    language: str = "en"  # "en" | "hi" | "hinglish" — preserve what the source actually used
    raw_text: str = ""  # original wording, for grounding and citations


# --- Structured-output shapes for extraction --------------------------------
# The vision/transcription models return these (no id/source — the pipeline adds
# those). Keeping them separate from `Recipe` means the LLM schema and the stored
# schema can evolve independently.


class ExtractedRecipe(BaseModel):
    title: str
    servings: Optional[int] = None
    time_minutes: Optional[int] = None
    ingredients: list[Ingredient] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    language: str = "en"
    raw_text: str = ""


class PageExtraction(BaseModel):
    """One photo/transcript may yield zero, one, or several recipes."""

    recipes: list[ExtractedRecipe] = Field(default_factory=list)
