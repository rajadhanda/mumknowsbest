"""mumknowsbest — a conversational assistant for Mum's recipes.

Importing the package pulls in only the lightweight data model (no network/SDK
imports), so it's cheap to import and easy to test. The LLM client, ingestion
sources, and agent live in submodules you import explicitly.
"""

from .models import ExtractedRecipe, Ingredient, PageExtraction, Recipe, SourceRef

__version__ = "0.1.0"

__all__ = [
    "Recipe",
    "Ingredient",
    "SourceRef",
    "ExtractedRecipe",
    "PageExtraction",
    "__version__",
]
