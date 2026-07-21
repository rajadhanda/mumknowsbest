"""Anthropic client wrapper — the one place that talks to Claude.

Keeping all model calls behind this module means the ingestion pipelines and the agent
don't configure the SDK themselves, model IDs come from `Settings`, and the whole thing
is easy to fake in tests (pass any object with a compatible `.messages` to `client=`).
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Optional

from ..config import Settings, get_settings
from ..models import PageExtraction

MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


def media_type_for(path: str | Path) -> str:
    return MEDIA_TYPES.get(Path(path).suffix.lower(), "image/jpeg")


def make_anthropic_client(settings: Settings) -> Any:
    """Single construction point for the SDK client (agent + ingestion share it)."""
    import anthropic  # imported lazily so the package imports without the SDK

    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _extract_system(language: str) -> str:
    return f"""\
You read photos of pages from a home cook's recipe book and turn them into structured recipes.

The cook writes in {language}: text may be English, Hindi (Devanagari), or romanized Hindi,
and is sometimes handwritten.

Rules:
- Transcribe faithfully. Preserve the cook's own wording and language in `raw_text`, and keep
  ingredient and step text in the original language/script.
- Set `language` to what the page actually uses: "en", "hi", or "hinglish".
- If a photo shows more than one recipe, return each one separately. If it shows none, return an
  empty list.
- Quantities matter: capture `qty` and `unit` exactly as written (including "to taste", "andaaz",
  "स्वादानुसार"). Do not invent numbers you cannot read — leave them out instead.
- Put the cook's tips, variations, substitutions, and garnish lines in `notes` (e.g. a "नोट:"
  line, or "garnish with ..."), not in `steps`.
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
        self._client = client if client is not None else make_anthropic_client(self.settings)

    def extract_recipes_from_image(self, image_path: str | Path) -> PageExtraction:
        """Read one recipe-book page photo into structured recipes."""
        image_path = Path(image_path)
        return self.extract_recipes_from_image_bytes(
            image_path.read_bytes(), media_type_for(image_path)
        )

    def extract_recipes_from_image_bytes(
        self, data: bytes, media_type: str
    ) -> PageExtraction:
        """Same extraction, from raw bytes (uploads from the web/iOS app land here)."""
        response = self._client.messages.parse(
            model=self.settings.vision_model,
            max_tokens=16000,  # a dense multi-recipe page can be long; truncation breaks parsing
            system=_extract_system(self.settings.language),
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": base64.standard_b64encode(data).decode("ascii"),
                            },
                        },
                        {"type": "text", "text": "Extract every recipe on this page."},
                    ],
                }
            ],
            output_format=PageExtraction,
        )
        # parsed_output lives on the text *block*, not the message.
        for block in response.content:
            parsed = getattr(block, "parsed_output", None)
            if parsed is not None:
                return parsed
        return PageExtraction()
