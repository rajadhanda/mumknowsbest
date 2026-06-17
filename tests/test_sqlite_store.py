"""SQLite store tests — exercise the RecipeStore contract end-to-end, no network."""

from mumknowsbest.models import Ingredient, Recipe, SourceRef
from mumknowsbest.storage import RecipeStore, SqliteRecipeStore


def _recipe(title, *, ingredients=(), tags=(), steps=()):
    return Recipe(
        title=title,
        source=SourceRef(type="book", page_photo=f"{title}.jpg"),
        ingredients=[Ingredient(item=i) for i in ingredients],
        tags=list(tags),
        steps=list(steps),
    )


def test_store_satisfies_the_interface(tmp_path):
    store = SqliteRecipeStore(tmp_path / "r.db")
    assert isinstance(store, RecipeStore)


def test_add_get_count_round_trip(tmp_path):
    store = SqliteRecipeStore(tmp_path / "r.db")
    r = _recipe("Rajma", ingredients=["rajma", "onion"])
    store.add(r)
    assert store.count() == 1
    assert store.get(r.id) == r
    assert store.get("missing") is None


def test_add_is_upsert(tmp_path):
    store = SqliteRecipeStore(tmp_path / "r.db")
    r = _recipe("Dal")
    store.add(r)
    r.title = "Dal Tadka"
    store.add(r)  # same id
    assert store.count() == 1
    assert store.get(r.id).title == "Dal Tadka"


def test_search_ranks_by_term_overlap(tmp_path):
    store = SqliteRecipeStore(tmp_path / "r.db")
    store.add(_recipe("Paneer Tikka", ingredients=["paneer"], tags=["paneer", "starter"]))
    store.add(_recipe("Aloo Gobi", ingredients=["potato", "cauliflower"]))
    store.add(_recipe("Palak Paneer", ingredients=["paneer", "spinach"], tags=["paneer"]))

    results = store.search("paneer")
    titles = [r.title for r in results]
    assert "Aloo Gobi" not in titles
    assert set(titles) == {"Paneer Tikka", "Palak Paneer"}


def test_search_empty_query_returns_some(tmp_path):
    store = SqliteRecipeStore(tmp_path / "r.db")
    store.add(_recipe("Idli"))
    assert len(store.search("")) == 1
