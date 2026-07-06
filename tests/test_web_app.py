"""Web channel tests — FastAPI app with a fake agent and a temp store. No key needed."""

import pytest
from fastapi.testclient import TestClient

from mumknowsbest.channels.web import create_app
from mumknowsbest.config import Settings
from mumknowsbest.models import Ingredient, Recipe, SourceRef
from mumknowsbest.storage import SqliteRecipeStore


class _FakeAgent:
    def __init__(self):
        self.calls = []

    def ask(self, message, history=None, **kw):
        self.calls.append((message, history))
        return f"echo: {message}"


def _settings(key=None):
    from pathlib import Path

    return Settings(
        anthropic_api_key=key,
        vision_model="v", agent_model="a", bulk_model="b",
        db_path=Path("unused.db"), language="hinglish",
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


def test_health_and_recipe_endpoints(store):
    client = TestClient(create_app(store, agent=_FakeAgent(), settings=_settings()))

    health = client.get("/api/health").json()
    assert health["ok"] and health["recipes"] == 1

    briefs = client.get("/api/recipes").json()
    assert [b["title"] for b in briefs] == ["Handvo"]
    assert "steps" not in briefs[0]  # list stays lean

    full = client.get("/api/recipes/r1").json()
    assert full["steps"] == ["Soak overnight", "Bake at 180C"]
    assert full["notes"] == ["Add soda just before pouring"]

    assert client.get("/api/recipes/nope").status_code == 404


def test_chat_uses_agent_and_replays_history(store):
    agent = _FakeAgent()
    client = TestClient(create_app(store, agent=agent, settings=_settings()))

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


def test_chat_without_key_or_agent_is_503(store):
    client = TestClient(create_app(store, settings=_settings(key=None)))
    res = client.post("/api/chat", json={"message": "hello"})
    assert res.status_code == 503
    assert "ANTHROPIC_API_KEY" in res.json()["detail"]


def test_serves_pwa_shell(store):
    client = TestClient(create_app(store, agent=_FakeAgent(), settings=_settings()))
    index = client.get("/")
    assert index.status_code == 200 and "Mum Knows Best" in index.text
    assert client.get("/manifest.json").status_code == 200
    assert client.get("/sw.js").status_code == 200
    assert client.get("/icon-180.png").status_code == 200
