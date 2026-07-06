"""Paper recipe book → recipes, via Claude vision.

Point it at a folder of page photos. Each photo is read by the LLM into zero or more
structured recipes; the original photo path is kept on every recipe so the agent can
show Mum the source page.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

from ..llm.client import LLMClient
from ..models import Recipe, SourceRef

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


class PaperBookSource:
    name = "paper_book"

    def __init__(self, photo_dir: str | Path, llm: LLMClient) -> None:
        self.photo_dir = Path(photo_dir)
        self.llm = llm

    def photos(self) -> list[Path]:
        return sorted(
            p
            for p in self.photo_dir.rglob("*")
            if p.is_file() and p.suffix.lower() in IMAGE_EXTS
        )

    def extract(self) -> Iterator[Recipe]:
        for photo in self.photos():
            extraction = self.llm.extract_recipes_from_image(photo)
            for er in extraction.recipes:
                yield Recipe(
                    title=er.title,
                    source=SourceRef(type="book", page_photo=str(photo)),
                    servings=er.servings,
                    time_minutes=er.time_minutes,
                    ingredients=er.ingredients,
                    steps=er.steps,
                    notes=er.notes,
                    tags=er.tags,
                    language=er.language,
                    raw_text=er.raw_text,
                )
