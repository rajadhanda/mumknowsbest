"""Agent tool-loop with a scripted fake Claude client — no network, no API key."""

import json

from mumknowsbest.agent.agent import RecipeAgent
from mumknowsbest.agent import tools as tool_mod
from mumknowsbest.models import Ingredient, Recipe, SourceRef
from mumknowsbest.storage import SqliteRecipeStore


class _Block:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Resp:
    def __init__(self, stop_reason, content):
        self.stop_reason = stop_reason
        self.content = content


class _Messages:
    def __init__(self, scripted):
        self._scripted = list(scripted)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._scripted.pop(0)


class _FakeClient:
    def __init__(self, scripted):
        self.messages = _Messages(scripted)


def _store_with_palak(tmp_path):
    store = SqliteRecipeStore(tmp_path / "r.db")
    store.add(
        Recipe(
            title="Palak Paneer",
            source=SourceRef(type="book", page_photo="p.jpg"),
            ingredients=[Ingredient(item="paneer")],
            tags=["paneer"],
        )
    )
    return store


def test_agent_searches_then_answers(tmp_path):
    store = _store_with_palak(tmp_path)
    scripted = [
        _Resp(
            "tool_use",
            [_Block(type="tool_use", name="search_recipes", input={"query": "paneer"}, id="t1")],
        ),
        _Resp("end_turn", [_Block(type="text", text="Try Palak Paneer!")]),
    ]
    fake = _FakeClient(scripted)
    agent = RecipeAgent(store, client=fake)

    answer = agent.ask("kuch paneer banau?")

    assert answer == "Try Palak Paneer!"
    # The second model call must carry the real tool_result from the store.
    second_call = fake.messages.calls[1]["messages"]
    tool_result_msg = second_call[-1]
    assert tool_result_msg["role"] == "user"
    assert "Palak Paneer" in tool_result_msg["content"][0]["content"]


def test_agent_runs_tools_even_when_turn_hit_max_tokens(tmp_path):
    """A truncated turn can still carry complete tool_use blocks — they must run."""
    store = _store_with_palak(tmp_path)
    scripted = [
        _Resp(
            "max_tokens",  # not "tool_use" — the old stop_reason check would drop this
            [_Block(type="tool_use", name="search_recipes", input={"query": "paneer"}, id="t1")],
        ),
        _Resp("end_turn", [_Block(type="text", text="Palak Paneer!")]),
    ]
    agent = RecipeAgent(store, client=_FakeClient(scripted))
    assert agent.ask("paneer?") == "Palak Paneer!"


def test_agent_bad_tool_args_become_error_result_not_500(tmp_path):
    """Model-supplied tool input isn't schema-guaranteed; bad args must not raise."""
    store = _store_with_palak(tmp_path)
    scripted = [
        _Resp(
            "tool_use",
            [_Block(type="tool_use", name="search_recipes", input={}, id="t1")],  # no query
        ),
        _Resp("end_turn", [_Block(type="text", text="Sorry, phir se?")]),
    ]
    fake = _FakeClient(scripted)
    agent = RecipeAgent(store, client=fake)

    assert agent.ask("??") == "Sorry, phir se?"
    result = fake.messages.calls[1]["messages"][-1]["content"][0]
    assert result["is_error"] is True


def test_dispatch_get_recipe_excludes_raw_text(tmp_path):
    store = SqliteRecipeStore(tmp_path / "r.db")
    r = Recipe(
        title="Chai",
        source=SourceRef(type="book"),
        steps=["boil"],
        raw_text="huge OCR blob " * 100,
    )
    store.add(r)
    output, is_error = tool_mod.dispatch(store, "get_recipe", {"id": r.id})
    assert not is_error
    payload = json.loads(output)
    assert payload["title"] == "Chai" and payload["steps"] == ["boil"]
    assert "raw_text" not in payload


def test_dispatch_unknown_tool_and_missing_recipe(tmp_path):
    store = SqliteRecipeStore(tmp_path / "r.db")
    out, err = tool_mod.dispatch(store, "cook_dinner", {})
    assert err and "unknown tool" in out
    out, err = tool_mod.dispatch(store, "get_recipe", {"id": "nope"})
    assert err and "no recipe" in out
