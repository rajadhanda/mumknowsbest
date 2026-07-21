"""Tools the agent uses to ground answers in Mum's actual recipes.

The tool *schemas* and the *dispatch* are defined against the `RecipeStore` interface,
so the agent works with any store and gains better search the moment the store does
(e.g. when semantic search lands). Channels (CLI, web, WhatsApp) reuse this unchanged.
"""

from __future__ import annotations

import json

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


def _err(message: str) -> tuple[str, bool]:
    return json.dumps({"error": message}), True


def dispatch(store: RecipeStore, name: str, args: dict) -> tuple[str, bool]:
    """Execute a tool call. Returns (json_result, is_error).

    Tool inputs come from the model and are not schema-guaranteed, so bad or missing
    arguments become error results the model can recover from — never exceptions that
    would 500 the whole chat request.
    """
    try:
        if name == "search_recipes":
            query = args.get("query")
            if not isinstance(query, str) or not query.strip():
                return _err("search_recipes needs a non-empty 'query' string")
            try:
                limit = max(1, min(20, int(args.get("limit") or 5)))
            except (TypeError, ValueError):
                limit = 5
            results = store.search(query, limit=limit)
            return json.dumps([r.brief() for r in results], ensure_ascii=False), False
        if name == "get_recipe":
            recipe_id = args.get("id")
            if not isinstance(recipe_id, str) or not recipe_id:
                return _err("get_recipe needs an 'id' string from search_recipes results")
            recipe = store.get(recipe_id)
            if recipe is None:
                return _err(f"no recipe with id {recipe_id!r}")
            # raw_text duplicates the structured fields and can be 1-2K tokens of OCR —
            # keep it out of the context the model re-sends on every loop iteration.
            payload = recipe.model_dump(exclude={"raw_text"})
            return json.dumps(payload, ensure_ascii=False), False
        return _err(f"unknown tool: {name}")
    except Exception as exc:  # defensive: a store hiccup shouldn't kill the turn
        return _err(f"{name} failed: {exc}")
