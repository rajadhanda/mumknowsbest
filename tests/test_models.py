"""Model tests — no network, no API key needed."""

from mumknowsbest.models import ExtractedRecipe, Ingredient, PageExtraction, Recipe, SourceRef


def test_recipe_gets_an_id_and_defaults():
    r = Recipe(title="Aloo Paratha", source=SourceRef(type="book", page_photo="p1.jpg"))
    assert r.id  # auto-generated uuid
    assert r.ingredients == [] and r.steps == [] and r.notes == [] and r.tags == []
    assert r.language == "en"


def test_recipe_json_round_trip():
    r = Recipe(
        title="Paneer Butter Masala",
        source=SourceRef(type="book", page_photo="page_12.jpg"),
        servings=4,
        ingredients=[Ingredient(item="paneer", qty="250", unit="g")],
        steps=["Soak cashews", "Blend", "Simmer"],
        notes=["Garnish with cream", "Can swap paneer for tofu"],
        tags=["north-indian", "vegetarian"],
        language="hinglish",
    )
    restored = Recipe.model_validate_json(r.model_dump_json())
    assert restored == r
    assert restored.notes == ["Garnish with cream", "Can swap paneer for tofu"]


def test_page_extraction_holds_many_recipes():
    page = PageExtraction(
        recipes=[ExtractedRecipe(title="Chai"), ExtractedRecipe(title="Poha")]
    )
    assert [er.title for er in page.recipes] == ["Chai", "Poha"]
    assert PageExtraction().recipes == []  # a blank page yields nothing


def test_from_extraction_carries_every_content_field():
    er = ExtractedRecipe(
        title="Handvo",
        time_minutes=60,
        ingredients=[Ingredient(item="rice", qty="2", unit="cups")],
        steps=["Soak", "Bake"],
        notes=["Add soda last"],
        tags=["gujarati"],
        language="hinglish",
        raw_text="original words",
    )
    r = Recipe.from_extraction(er, SourceRef(type="book", page_photo="h.jpg"))
    # A single dump comparison means a future field can't be silently dropped.
    assert r.model_dump(exclude={"id", "source"}) == er.model_dump()
    assert r.source.page_photo == "h.jpg"


def test_from_extraction_identity_is_deterministic():
    er = ExtractedRecipe(title="Chai")
    src = SourceRef(type="book")
    a = Recipe.from_extraction(er, src, identity="book:abc:Chai")
    b = Recipe.from_extraction(er, src, identity="book:abc:Chai")
    c = Recipe.from_extraction(er, src, identity="book:other:Chai")
    assert a.id == b.id != c.id


def test_brief_shape():
    r = Recipe(
        title="Chai",
        source=SourceRef(type="book"),
        tags=["drink"],
        language="hinglish",
        steps=["boil"],
    )
    assert r.brief() == {
        "id": r.id,
        "title": "Chai",
        "tags": ["drink"],
        "language": "hinglish",
        "source": "book",
    }
