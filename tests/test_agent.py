"""Agent tool-loop with a scripted fake Claude client — no network, no API key."""

from mumknowsbest.agent.agent import RecipeAgent
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


def test_agent_searches_then_answers(tmp_path):
    store = SqliteRecipeStore(tmp_path / "r.db")
    store.add(
        Recipe(
            title="Palak Paneer",
            source=SourceRef(type="book", page_photo="p.jpg"),
            ingredients=[Ingredient(item="paneer")],
            tags=["paneer"],
        )
    )

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
