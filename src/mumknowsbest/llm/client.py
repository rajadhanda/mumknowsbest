"""Anthropic client wrapper — the one place that talks to Claude.

Keeping all model calls behind this class means the ingestion pipelines and the agent
don't import the SDK directly, model IDs come from `Settings`, and the whole thing is
easy to fake in tests (pass any object with a compatible `.messages` to `client=`).
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Optional

from ..config import Settings, get_settings
from ..models import PageExtraction

_MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


def media_type_for(path: str | Path) -> str:
    return _MEDIA_TYPES.get(Path(path).suffix.lower(), "image/jpeg")


_EXTRACT_SYSTEM = """\
You read photos of pages from a home cook's recipe book and turn them into structured recipes.

The pages are a Hindi-English mix (Hinglish): text may be English, Hindi (Devanagari), or
romanized Hindi, and is sometimes handwritten.

Rules:
- Transcribe faithfully. Preserve the cook's own wording and language in `raw_text`, and keep
  ingredient and step text in the original language/script.
- Set `language` to what the page actually uses: "en", "hi", or "hinglish".
- If a photo shows more than one recipe, return each one separately. If it shows none, return an
  empty list.
- Quantities matter: capture `qty` and `unit` exactly as written (including "to taste",
  "andaaz", "स्वादानुसार"). Do not invent numbers you cannot read — leave them out instead.
- Put the cook's tips, variations, substitutions, and garnish lines in `notes` (e.g. a
  "नोट:" line, or "garnish with ..."), not in `steps`.
- Add a few helpful tags (cuisine, meal type, dietary) only when they're obvious.
- If a word is unclear, transcribe your best guess and keep going — don't drop the recipe.
"""


class LLMClient:
    def __init__(
        self,
        settings: Optional[Settings] = None,
        client: Any = None,
    ) -> None:
        self.settings = settings or get_settings()
        if client is not None:
            self._client = client
        else:
            import anthropic  # imported lazily so the package imports without the SDK

            self._client = anthropic.Anthropic(api_key=self.settings.anthropic_api_key)

    @property
    def raw(self) -> Any:
        """The underlying Anthropic client, for callers that need full control."""
        return self._client

    def extract_recipes_from_image(self, image_path: str | Path) -> PageExtraction:
        """Read one recipe-book page photo into structured recipes."""
        image_path = Path(image_path)
        data = base64.standard_b64encode(image_path.read_bytes()).decode("ascii")
        response = self._client.messages.parse(
            model=self.settings.vision_model,
            max_tokens=8000,
            system=_EXTRACT_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type_for(image_path),
                                "data": data,
                            },
                        },
                        {"type": "text", "text": "Extract every recipe on this page."},
                    ],
                }
            ],
            output_format=PageExtraction,
        )
        return response.parsed_output or PageExtraction()
