"""Paper-book ingestion with a fake LLM — proves the source→store seam, no network."""

from pathlib import Path

from mumknowsbest.ingestion.base import ingest
from mumknowsbest.ingestion.paper_book import PaperBookSource
from mumknowsbest.models import ExtractedRecipe, PageExtraction
from mumknowsbest.storage import SqliteRecipeStore


class _FakeLLM:
    """Stands in for LLMClient — same `extract_recipes_from_image` shape."""

    def __init__(self, mapping: dict[str, PageExtraction]):
        self.mapping = mapping

    def extract_recipes_from_image(self, path) -> PageExtraction:
        return self.mapping.get(Path(path).name, PageExtraction())


def test_paper_book_picks_up_only_images(tmp_path):
    (tmp_path / "a.jpg").write_bytes(b"x")
    (tmp_path / "b.png").write_bytes(b"y")
    (tmp_path / "notes.txt").write_text("ignore me")
    source = PaperBookSource(tmp_path, _FakeLLM({}))
    assert [p.name for p in source.photos()] == ["a.jpg", "b.png"]


def test_paper_book_ingests_into_store(tmp_path):
    (tmp_path / "a.jpg").write_bytes(b"x")
    (tmp_path / "b.png").write_bytes(b"y")
    fake = _FakeLLM(
        {
            "a.jpg": PageExtraction(
                recipes=[ExtractedRecipe(title="Chai", language="hinglish")]
            ),
            "b.png": PageExtraction(
                recipes=[ExtractedRecipe(title="Poha"), ExtractedRecipe(title="Upma")]
            ),
        }
    )
    store = SqliteRecipeStore(tmp_path / "r.db")
    added = ingest(PaperBookSource(tmp_path, fake), store)

    assert added == 3
    assert sorted(r.title for r in store.all()) == ["Chai", "Poha", "Upma"]

    chai = next(r for r in store.all() if r.title == "Chai")
    assert chai.source.type == "book"
    assert chai.source.page_photo.endswith("a.jpg")
    assert chai.language == "hinglish"
