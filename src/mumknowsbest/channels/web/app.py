"""FastAPI app for the web channel.

`create_app(store, agent=...)` is a factory: tests inject an in-memory store and a fake
agent; production (`mumknowsbest serve`) passes the SQLite store and lets the real
`RecipeAgent` be built lazily on first use. Voice happens in the browser (Web Speech
API), so this server stays voice-free — it only moves text and recipes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ...config import Settings, get_settings
from ...storage.base import RecipeStore

STATIC_DIR = Path(__file__).parent / "static"

_HISTORY_LIMIT = 12  # plain-text turns the client may replay per request


class ChatTurn(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatTurn] = Field(default_factory=list)


class ChatResponse(BaseModel):
    reply: str


def create_app(
    store: RecipeStore,
    agent: Any = None,
    settings: Optional[Settings] = None,
) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="mumknowsbest", docs_url=None, redoc_url=None)
    state: dict[str, Any] = {"agent": agent}

    def _agent() -> Any:
        if state["agent"] is None:
            if not settings.anthropic_api_key:
                raise HTTPException(
                    status_code=503,
                    detail="ANTHROPIC_API_KEY is not set — the assistant can't reply yet.",
                )
            from ...agent.agent import RecipeAgent  # lazy: SDK only needed for real chat

            state["agent"] = RecipeAgent(store, settings)
        return state["agent"]

    # -- API ----------------------------------------------------------------
    @app.get("/api/health")
    def health() -> dict:
        return {
            "ok": True,
            "recipes": store.count(),
            "model": settings.agent_model,
            "chat_ready": bool(settings.anthropic_api_key or state["agent"]),
        }

    @app.get("/api/recipes")
    def list_recipes() -> list[dict]:
        return [
            {
                "id": r.id,
                "title": r.title,
                "tags": r.tags,
                "language": r.language,
                "source": r.source.type,
            }
            for r in store.all()
        ]

    @app.get("/api/recipes/{recipe_id}")
    def get_recipe(recipe_id: str) -> dict:
        recipe = store.get(recipe_id)
        if recipe is None:
            raise HTTPException(status_code=404, detail="recipe not found")
        return recipe.model_dump()

    @app.post("/api/chat")
    def chat(req: ChatRequest) -> ChatResponse:
        history = [
            {"role": t.role, "content": t.content}
            for t in req.history[-_HISTORY_LIMIT:]
            if t.role in ("user", "assistant") and t.content.strip()
        ]
        reply = _agent().ask(req.message, history=history)
        return ChatResponse(reply=reply)

    # -- Static PWA ----------------------------------------------------------
    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/", StaticFiles(directory=STATIC_DIR), name="static")

    return app
