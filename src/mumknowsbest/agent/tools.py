"""Tools the agent uses to ground answers in Mum's actual recipes.

The tool *schemas* and the *dispatch* are defined against the `RecipeStore` interface,
so the agent works with any store and gains better search the moment the store does
(e.g. when semantic search lands). Channels (CLI, web, WhatsApp) reuse this unchanged.
"""

from __future__ import annotations

import json

from ..models import Recipe
from ..storage.base import RecipeStore

TOOLS = [
    {
        "name": "search_recipes",
        "description": (
            "Search Mum's recipe collection by ingredients, dish name, occasion, or vibe. "
            "Use this whenever she asks what to cook or about a particular dish."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to look for, e.g. 'paneer dinner for guests'.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return (default 5).",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_recipe",
        "description": (
            "Fetch one full recipe by its id — call this after search_recipes to read the "
            "complete ingredients and steps before answering."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
        },
    },
]


def _brief(recipe: Recipe) -> dict:
    """A compact view for search results (keeps the agent's context lean)."""
    return {
        "id": recipe.id,
        "title": recipe.title,
        "tags": recipe.tags,
        "source": recipe.source.type,
    }


def dispatch(store: RecipeStore, name: str, args: dict) -> str:
    """Execute a tool call and return a JSON string result."""
    if name == "search_recipes":
        results = store.search(args["query"], limit=int(args.get("limit", 5)))
        return json.dumps([_brief(r) for r in results], ensure_ascii=False)
    if name == "get_recipe":
        recipe = store.get(args["id"])
        return recipe.model_dump_json() if recipe else json.dumps({"error": "not found"})
    return json.dumps({"error": f"unknown tool: {name}"})
