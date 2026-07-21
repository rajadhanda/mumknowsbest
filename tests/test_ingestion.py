"""Paper-book ingestion with a fake LLM — proves the source→store seam, no network."""

from mumknowsbest.ingestion.base import ingest
from mumknowsbest.ingestion.paper_book import PaperBookSource
from mumknowsbest.models import ExtractedRecipe, PageExtraction
from mumknowsbest.storage import SqliteRecipeStore


class _FakeLLM:
    """Stands in for LLMClient — keyed by photo bytes, like the real vision call."""

    def __init__(self, mapping: dict[bytes, PageExtraction]):
        self.mapping = mapping

    def extract_recipes_from_image_bytes(self, data: bytes, media_type: str) -> PageExtraction:
        if data == b"BOOM":
            raise RuntimeError("unreadable photo")
        return self.mapping.get(data, PageExtraction())


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
            b"x": PageExtraction(
                recipes=[ExtractedRecipe(title="Chai", language="hinglish")]
            ),
            b"y": PageExtraction(
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
    assert chai.source.page_photo.endswith("a.jpg")  # no archive dir -> original path
    assert chai.language == "hinglish"


def test_reingesting_same_folder_does_not_duplicate(tmp_path):
    (tmp_path / "a.jpg").write_bytes(b"x")
    fake = _FakeLLM({b"x": PageExtraction(recipes=[ExtractedRecipe(title="Chai")])})
    store = SqliteRecipeStore(tmp_path / "r.db")

    ingest(PaperBookSource(tmp_path, fake), store)
    ingest(PaperBookSource(tmp_path, fake), store)  # e.g. re-run after adding new pages

    assert store.count() == 1  # deterministic id -> upsert, not duplicate


def test_one_bad_photo_does_not_abort_the_run(tmp_path):
    (tmp_path / "a.jpg").write_bytes(b"BOOM")  # fake raises on this content
    (tmp_path / "b.jpg").write_bytes(b"x")
    fake = _FakeLLM({b"x": PageExtraction(recipes=[ExtractedRecipe(title="Chai")])})
    store = SqliteRecipeStore(tmp_path / "r.db")
    source = PaperBookSource(tmp_path, fake)

    added = ingest(source, store)

    assert added == 1  # the good photo still landed
    assert len(source.failures) == 1
    assert source.failures[0][0].endswith("a.jpg")


def test_archive_dir_stores_copy_and_relative_name(tmp_path):
    photo_dir, archive = tmp_path / "in", tmp_path / "photos"
    photo_dir.mkdir()
    (photo_dir / "page1.jpg").write_bytes(b"x")
    fake = _FakeLLM({b"x": PageExtraction(recipes=[ExtractedRecipe(title="Chai")])})
    store = SqliteRecipeStore(tmp_path / "r.db")

    ingest(PaperBookSource(photo_dir, fake, archive_dir=archive), store)

    (recipe,) = store.all()
    # page_photo is a bare filename (servable via /api/photos/{name}), not a server path
    assert "/" not in recipe.source.page_photo
    assert (archive / recipe.source.page_photo).read_bytes() == b"x"
