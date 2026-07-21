"""Paper recipe book → recipes, via Claude vision.

Point it at a folder of page photos. Each photo is read by the LLM into zero or more
structured recipes. When an `archive_dir` is given (the CLI passes the shared photos
dir), the source photo is copied there under a content-addressed name and every recipe
keeps that filename, so any client can fetch the original page via /api/photos/{name}.

Design points learned from real pages:
- Recipe ids are deterministic (photo content + title), so re-running ingestion on the
  same folder upserts instead of duplicating the whole book.
- One unreadable/failed photo doesn't abort the run: it's recorded in `self.failures`
  and extraction continues with the next page.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterator, Optional

from ..llm.client import MEDIA_TYPES, LLMClient, media_type_for
from ..models import Recipe, SourceRef

IMAGE_EXTS = set(MEDIA_TYPES)  # one source of truth for "image types we ingest"


def archive_photo(data: bytes, suffix: str, archive_dir: Path) -> str:
    """Store photo bytes under a content-addressed name; returns the filename."""
    name = hashlib.sha256(data).hexdigest()[:16] + suffix.lower()
    archive_dir.mkdir(parents=True, exist_ok=True)
    target = archive_dir / name
    if not target.exists():
        target.write_bytes(data)
    return name


def recipes_from_photo_bytes(
    data: bytes,
    media_type: str,
    llm: LLMClient,
    *,
    page_photo: Optional[str] = None,
) -> list[Recipe]:
    """Extract every recipe from one photo's bytes. Shared by folder ingest and uploads."""
    digest = hashlib.sha256(data).hexdigest()[:16]
    extraction = llm.extract_recipes_from_image_bytes(data, media_type)
    return [
        Recipe.from_extraction(
            er,
            SourceRef(type="book", page_photo=page_photo),
            identity=f"book:{digest}:{er.title}",
        )
        for er in extraction.recipes
    ]


class PaperBookSource:
    name = "paper_book"

    def __init__(
        self,
        photo_dir: str | Path,
        llm: LLMClient,
        archive_dir: Optional[str | Path] = None,
    ) -> None:
        self.photo_dir = Path(photo_dir)
        self.llm = llm
        self.archive_dir = Path(archive_dir) if archive_dir else None
        self.failures: list[tuple[str, str]] = []  # (photo path, error) from the last extract()

    def photos(self) -> list[Path]:
        return sorted(
            p
            for p in self.photo_dir.rglob("*")
            if p.is_file() and p.suffix.lower() in IMAGE_EXTS
        )

    def extract(self) -> Iterator[Recipe]:
        self.failures = []
        for photo in self.photos():
            try:
                data = photo.read_bytes()
                if self.archive_dir:
                    page_photo = archive_photo(data, photo.suffix, self.archive_dir)
                else:
                    page_photo = str(photo)
                yield from recipes_from_photo_bytes(
                    data, media_type_for(photo), self.llm, page_photo=page_photo
                )
            except Exception as exc:  # one bad page must not kill a 200-photo run
                self.failures.append((str(photo), str(exc)))
