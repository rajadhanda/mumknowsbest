"""Runtime settings, driven by environment variables (and an optional .env).

All tunables live here so model choices, the database location, and the language
are configured in one place rather than scattered through the code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (no dependency). Existing env vars win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


_load_dotenv(_PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str | None
    # Vision OCR of handwriting + Hinglish is accuracy-sensitive, so default to a
    # strong model. Swap to a cheaper one per-task once OCR quality is trusted.
    vision_model: str
    agent_model: str
    bulk_model: str  # for high-volume text structuring (YouTube/Instagram) later
    db_path: Path
    language: str  # Mum's register; the agent mirrors it


def get_settings() -> Settings:
    return Settings(
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
        vision_model=os.environ.get("MKB_VISION_MODEL", "claude-opus-4-8"),
        agent_model=os.environ.get("MKB_AGENT_MODEL", "claude-opus-4-8"),
        bulk_model=os.environ.get("MKB_BULK_MODEL", "claude-haiku-4-5"),
        db_path=Path(os.environ.get("MKB_DB_PATH", "recipes.db")),
        language=os.environ.get("MKB_LANGUAGE", "Hindi-English mix (Hinglish)"),
    )
