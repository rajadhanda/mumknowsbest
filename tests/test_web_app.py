"""Web channel tests — FastAPI app with fakes and a temp store. No key needed."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mumknowsbest.channels.web import create_app
from mumknowsbest.config import Settings
from mumknowsbest.models import ExtractedRecipe, Ingredient, PageExtraction, Recipe, SourceRef
from mumknowsbest.storage import SqliteRecipeStore


class _FakeAgent:
    def __init__(self):
        self.calls = []

    def ask(self, message, history=None, **kw):
        self.calls.append((message, history))
        return f"echo: {message}"


class _FakeLLM:
    def extract_recipes_from_image_bytes(self, data, media_type):
        if data == b"BOOM":
            raise RuntimeError("unreadable photo")
        if data == b"EMPTY":
            return PageExtraction()
        return PageExtraction(recipes=[ExtractedRecipe(title="Chai", language="hinglish")])


def _settings(tmp_path, key=None, token=None):
    return Settings(
        anthropic_api_key=key,
        vision_model="v",
        agent_model="a",
        db_path=Path("unused.db"),
        photos_dir=tmp_path / "photos",
        language="hinglish",
        access_token=token,
    )


@pytest.fixture()
def store(tmp_path):
    s = SqliteRecipeStore(tmp_path / "r.db")
    s.add(
        Recipe(
            id="r1",
            title="Handvo",
            source=SourceRef(type="book", page_photo="handvo.jpeg"),
            time_minutes=60,
            ingredients=[Ingredient(item="rice", qty="2", unit="cups")],
            steps=["Soak overnight", "Bake at 180C"],
            notes=["Add soda just before pouring"],
            tags=["gujarati"],
            language="hinglish",
        )
    )
    return s


def _client(store, tmp_path, **kw):
    kw.setdefault("agent", _FakeAgent())
    kw.setdefault("llm", _FakeLLM())
    settings = kw.pop("settings", None) or _settings(tmp_path)
    return TestClient(create_app(store, settings=settings, **kw))


def test_health_and_recipe_endpoints(store, tmp_path):
    client = _client(store, tmp_path)

    health = client.get("/api/health").json()
    assert health["ok"] and health["recipes"] == 1

    briefs = client.get("/api/recipes").json()
    assert [b["title"] for b in briefs] == ["Handvo"]
    assert "steps" not in briefs[0]  # list stays lean

    full = client.get("/api/recipes/r1").json()
    assert full["steps"] == ["Soak overnight", "Bake at 180C"]
    assert full["notes"] == ["Add soda just before pouring"]

    assert client.get("/api/recipes/nope").status_code == 404


def test_chat_uses_agent_and_replays_history(store, tmp_path):
    agent = _FakeAgent()
    client = _client(store, tmp_path, agent=agent)

    res = client.post(
        "/api/chat",
        json={
            "message": "kya banau?",
            "history": [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "namaste"},
                {"role": "system", "content": "should be dropped"},
            ],
        },
    )
    assert res.json() == {"reply": "echo: kya banau?"}
    message, history = agent.calls[0]
    assert message == "kya banau?"
    assert history == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "namaste"},
    ]


def test_chat_without_key_or_agent_is_503(store, tmp_path):
    client = TestClient(create_app(store, settings=_settings(tmp_path)))
    res = client.post("/api/chat", json={"message": "hello"})
    assert res.status_code == 503
    assert "ANTHROPIC_API_KEY" in res.json()["detail"]


def test_upload_photo_creates_recipe_and_serves_page_photo(store, tmp_path):
    client = _client(store, tmp_path)

    res = client.post(
        "/api/ingest/photos",
        files=[
            ("files", ("page1.jpg", b"good bytes", "image/jpeg")),
            ("files", ("weird.txt", b"nope", "text/plain")),
            ("files", ("broken.jpg", b"BOOM", "image/jpeg")),
        ],
    )
    assert res.status_code == 200
    data = res.json()
    assert [r["title"] for r in data["added"]] == ["Chai"]
    assert len(data["failed"]) == 2  # unsupported type + unreadable photo
    assert store.count() == 2  # Handvo + Chai

    # The stored page photo is a bare filename, archived and servable.
    chai = next(r for r in store.all() if r.title == "Chai")
    name = chai.source.page_photo
    assert "/" not in name
    photo = client.get(f"/api/photos/{name}")
    assert photo.status_code == 200 and photo.content == b"good bytes"


def test_upload_same_photo_twice_does_not_duplicate(store, tmp_path):
    client = _client(store, tmp_path)
    for _ in range(2):
        client.post(
            "/api/ingest/photos",
            files=[("files", ("p.jpg", b"good bytes", "image/jpeg"))],
        )
    assert store.count() == 2  # deterministic identity -> upsert


def test_photo_endpoint_rejects_traversal(store, tmp_path):
    client = _client(store, tmp_path)
    assert client.get("/api/photos/%2e%2e%2fsecret.txt").status_code in (404, 400)


def test_link_ingest_contract(store, tmp_path):
    client = _client(store, tmp_path)
    # Recognized source, not yet implemented -> 501 with a friendly message
    res = client.post("/api/ingest/link", json={"url": "https://youtu.be/abc123"})
    assert res.status_code == 501 and "coming soon" in res.json()["detail"]
    res = client.post("/api/ingest/link", json={"url": "https://www.instagram.com/p/xyz/"})
    assert res.status_code == 501
    # Not a supported link at all -> 400
    res = client.post("/api/ingest/link", json={"url": "gibberish"})
    assert res.status_code == 400


def test_access_token_guards_every_api_route(store, tmp_path):
    settings = _settings(tmp_path, token="sekrit")
    client = _client(store, tmp_path, settings=settings)

    assert client.get("/api/recipes").status_code == 401
    assert client.post("/api/chat", json={"message": "hi"}).status_code == 401

    ok = client.get("/api/recipes", headers={"Authorization": "Bearer sekrit"})
    assert ok.status_code == 200
    # Query-param form for <img> tags
    assert client.get("/api/health", params={"token": "sekrit"}).status_code == 200
    # The PWA shell itself stays open
    assert client.get("/").status_code == 200


def test_serves_pwa_shell(store, tmp_path):
    client = _client(store, tmp_path)
    index = client.get("/")
    assert index.status_code == 200 and "Mum Knows Best" in index.text
    assert client.get("/manifest.json").status_code == 200
    assert client.get("/sw.js").status_code == 200
    assert client.get("/icon-180.png").status_code == 200
