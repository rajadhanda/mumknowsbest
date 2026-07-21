"""The kitchen-helper agent: Claude + tools, grounded in Mum's collection.

Channel-agnostic on purpose. `ask()` takes a message (and optional history) and returns
text — a CLI, a web app, or a WhatsApp webhook can all drive it the same way. Voice is
handled at the channel edge (speech-to-text in, text-to-speech out), not here.
"""

from __future__ import annotations

from typing import Any, Optional

from ..config import Settings, get_settings
from ..llm.client import make_anthropic_client
from ..storage.base import RecipeStore
from . import tools as tool_mod


def _system_prompt(settings: Settings) -> str:
    return (
        "You are Mum's warm, patient kitchen helper. You answer ONLY from her own recipe "
        "collection, using the search_recipes and get_recipe tools to ground every answer.\n"
        f"Mum speaks {settings.language}. Mirror her language and script: reply in whatever "
        "mix of Hindi, English, or Hinglish she uses, and follow when she switches.\n"
        "Always say which recipe you're using so she can open the original page or video. When "
        "she's cooking, offer to read the steps one at a time. If something isn't in her "
        "collection, say so kindly — never invent a recipe."
    )


class RecipeAgent:
    def __init__(
        self,
        store: RecipeStore,
        settings: Optional[Settings] = None,
        client: Any = None,
    ) -> None:
        self.store = store
        self.settings = settings or get_settings()
        self._client = client if client is not None else make_anthropic_client(self.settings)

    def ask(self, message: str, history: Optional[list[dict]] = None, max_steps: int = 6) -> str:
        """Answer one user message, running the tool loop until Claude is done."""
        messages: list[dict] = list(history or [])
        messages.append({"role": "user", "content": message})

        response = None
        for _ in range(max_steps):
            response = self._client.messages.create(
                model=self.settings.agent_model,
                max_tokens=2000,
                system=_system_prompt(self.settings),
                tools=tool_mod.TOOLS,
                messages=messages,
            )

            # Branch on the actual content, not stop_reason: a turn cut off by
            # max_tokens (or paused) can still carry complete tool_use blocks,
            # and dropping them would silently skip the lookup.
            tool_blocks = [b for b in response.content if b.type == "tool_use"]
            if not tool_blocks:
                break

            messages.append({"role": "assistant", "content": response.content})
            results = []
            for block in tool_blocks:
                output, is_error = tool_mod.dispatch(self.store, block.name, dict(block.input))
                result: dict = {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": output,
                }
                if is_error:
                    result["is_error"] = True
                results.append(result)
            messages.append({"role": "user", "content": results})

        text = "".join(
            b.text for b in (response.content if response else []) if b.type == "text"
        ).strip()
        if text:
            return text
        return "Sorry, I got a little lost there — could you ask me again?"
