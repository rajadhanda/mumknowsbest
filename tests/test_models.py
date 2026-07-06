"""Model tests — no network, no API key needed."""

from mumknowsbest.models import ExtractedRecipe, Ingredient, PageExtraction, Recipe, SourceRef


def test_recipe_gets_an_id_and_defaults():
    r = Recipe(title="Aloo Paratha", source=SourceRef(type="book", page_photo="p1.jpg"))
    assert r.id  # auto-generated uuid
    assert r.ingredients == [] and r.steps == [] and r.tags == []
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
