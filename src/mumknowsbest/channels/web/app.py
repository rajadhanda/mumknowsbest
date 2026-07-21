"""FastAPI app for the web channel — and the API contract any native (iOS) app uses.

`create_app(store, agent=..., llm=...)` is a factory: tests inject an in-memory store
and fakes; production (`mumknowsbest serve`) passes the SQLite store and lets the real
agent/LLM be built lazily on first use. Voice happens in the browser (Web Speech API),
so this server stays voice-free — it only moves text, recipes, and photos.

The API is the full product surface on purpose: everything the PWA can do (chat,
browse, add recipes by photo or link) goes through these routes, so a future iOS app
is a pure client — no server changes needed.

Auth: if `MKB_ACCESS_TOKEN` is set, every /api route requires it — as a
`Authorization: Bearer <token>` header, or `?token=` for resources loaded by <img>
tags. Unset = open (local development).
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ...config import Settings, get_settings
from ...ingestion.paper_book import archive_photo, recipes_from_photo_bytes
from ...llm.client import MEDIA_TYPES
from ...storage.base import RecipeStore

STATIC_DIR = Path(__file__).parent / "static"

_HISTORY_LIMIT = 12  # plain-text turns the client may replay per request

# Link ingestion registry: a URL is matched to a source kind here, and new sources
# (Phase 3) plug in by filling the builder — the endpoint contract never changes.
LINK_KINDS = {
    "youtube": ("youtube.com", "youtu.be"),
    "instagram": ("instagram.com",),
}
LINK_SOURCE_BUILDERS: dict[str, Any] = {}  # kind -> callable(url, llm) -> list[Recipe]


class ChatTurn(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatTurn] = Field(default_factory=list)


class ChatResponse(BaseModel):
    reply: str


class LinkRequest(BaseModel):
    url: str


def create_app(
    store: RecipeStore,
    agent: Any = None,
    settings: Optional[Settings] = None,
    llm: Any = None,
) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="mumknowsbest", docs_url=None, redoc_url=None)
    state: dict[str, Any] = {"agent": agent, "llm": llm}
    init_lock = threading.Lock()

    def _require_key() -> None:
        if not settings.anthropic_api_key:
            raise HTTPException(
                status_code=503,
                detail="ANTHROPIC_API_KEY is not set — the assistant can't do this yet.",
            )

    def _agent() -> Any:
        with init_lock:
            if state["agent"] is None:
                _require_key()
                from ...agent.agent import RecipeAgent  # lazy: SDK only needed for real use

                state["agent"] = RecipeAgent(store, settings)
            return state["agent"]

    def _llm() -> Any:
        with init_lock:
            if state["llm"] is None:
                _require_key()
                from ...llm.client import LLMClient

                state["llm"] = LLMClient(settings)
            return state["llm"]

    def auth(request: Request) -> None:
        if not settings.access_token:
            return
        header = request.headers.get("authorization", "")
        token = header.removeprefix("Bearer ").strip() or request.query_params.get("token")
        if token != settings.access_token:
            raise HTTPException(status_code=401, detail="missing or wrong access token")

    api = APIRouter(prefix="/api", dependencies=[Depends(auth)])

    # -- Read side -----------------------------------------------------------
    @api.get("/health")
    def health() -> dict:
        return {
            "ok": True,
            "recipes": store.count(),
            "model": settings.agent_model,
            "chat_ready": bool(settings.anthropic_api_key or state["agent"]),
        }

    @api.get("/recipes")
    def list_recipes() -> list[dict]:
        return [r.brief() for r in store.all()]

    @api.get("/recipes/{recipe_id}")
    def get_recipe(recipe_id: str) -> dict:
        recipe = store.get(recipe_id)
        if recipe is None:
            raise HTTPException(status_code=404, detail="recipe not found")
        return recipe.model_dump()

    @api.get("/photos/{name}")
    def get_photo(name: str) -> FileResponse:
        if Path(name).name != name:  # no traversal
            raise HTTPException(status_code=404, detail="photo not found")
        path = settings.photos_dir / name
        if not path.is_file():
            raise HTTPException(status_code=404, detail="photo not found")
        return FileResponse(path)

    # -- Chat ----------------------------------------------------------------
    @api.post("/chat")
    def chat(req: ChatRequest) -> ChatResponse:
        history = [
            {"role": t.role, "content": t.content}
            for t in req.history[-_HISTORY_LIMIT:]
            if t.role in ("user", "assistant") and t.content.strip()
        ]
        reply = _agent().ask(req.message, history=history)
        return ChatResponse(reply=reply)

    # -- Write side: add recipes from any client -----------------------------
    @api.post("/ingest/photos")
    def ingest_photos(files: list[UploadFile]) -> dict:
        """Upload page photos / screenshots; each becomes zero or more recipes.

        Synchronous by design for now (one page ≈ tens of seconds): the phone shows
        a spinner per photo. A job queue is the upgrade path if batches grow.
        """
        llm = _llm()
        added, failed = [], []
        for file in files:
            filename = file.filename or "photo"
            suffix = Path(filename).suffix.lower()
            if suffix not in MEDIA_TYPES:
                failed.append({"file": filename, "error": f"unsupported type {suffix or '?'}"})
                continue
            try:
                data = file.file.read()
                name = archive_photo(data, suffix, settings.photos_dir)
                recipes = recipes_from_photo_bytes(
                    data, MEDIA_TYPES[suffix], llm, page_photo=name
                )
                for recipe in recipes:
                    store.add(recipe)
                    added.append(recipe.brief())
                if not recipes:
                    failed.append({"file": filename, "error": "no recipe found on this photo"})
            except HTTPException:
                raise
            except Exception as exc:  # one bad upload must not fail the batch
                failed.append({"file": filename, "error": str(exc)})
        return {"added": added, "failed": failed}

    @api.post("/ingest/link")
    def ingest_link(req: LinkRequest) -> dict:
        """Add a recipe from an Instagram / YouTube link (contract live, sources Phase 3)."""
        url = req.url.strip()
        kind = next(
            (k for k, hosts in LINK_KINDS.items() if any(h in url for h in hosts)),
            None,
        )
        if not url.startswith(("http://", "https://")) or kind is None:
            raise HTTPException(
                status_code=400,
                detail="that doesn't look like an Instagram or YouTube link",
            )
        builder = LINK_SOURCE_BUILDERS.get(kind)
        if builder is None:
            raise HTTPException(
                status_code=501,
                detail=f"{kind} ingestion is coming soon — photos work already!",
            )
        recipes = builder(url, _llm())
        for recipe in recipes:
            store.add(recipe)
        return {"added": [r.brief() for r in recipes], "failed": []}

    app.include_router(api)

    # -- Static PWA ----------------------------------------------------------
    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/", StaticFiles(directory=STATIC_DIR), name="static")

    return app
