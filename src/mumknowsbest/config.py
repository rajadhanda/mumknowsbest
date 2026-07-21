"""Runtime settings, driven by environment variables (and an optional .env).

All tunables live here so model choices, paths, auth, and the language are configured
in one place rather than scattered through the code. The .env file is loaded on the
first `get_settings()` call (not at import), from the current directory first and the
project checkout as a fallback, so installed wheels behave the same as dev checkouts.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_dotenv_loaded = False


def _parse_env_line(line: str) -> tuple[str, str] | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if line.startswith("export "):
        line = line[len("export "):]
    if "=" not in line:
        return None
    key, _, val = line.partition("=")
    val = val.strip()
    if val[:1] in ("'", '"') and val[-1:] == val[:1]:
        val = val[1:-1]  # quoted: keep verbatim
    elif " #" in val:
        val = val.split(" #", 1)[0].rstrip()  # unquoted: drop inline comment
    return key.strip(), val


def _load_dotenv() -> None:
    """Load the first .env found (cwd, then repo checkout). Existing env vars win."""
    global _dotenv_loaded
    if _dotenv_loaded:
        return
    _dotenv_loaded = True
    for candidate in (Path.cwd() / ".env", _PROJECT_ROOT / ".env"):
        if candidate.is_file():
            for line in candidate.read_text(encoding="utf-8").splitlines():
                parsed = _parse_env_line(line)
                if parsed:
                    os.environ.setdefault(parsed[0], parsed[1])
            return


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str | None
    # Vision OCR of handwriting + Hinglish is accuracy-sensitive, so default to a
    # strong model. Swap to a cheaper one per-task once OCR quality is trusted.
    vision_model: str
    agent_model: str
    db_path: Path
    photos_dir: Path  # where source page photos are archived; served at /api/photos
    language: str  # Mum's register; threaded into both the OCR and chat prompts
    access_token: str | None  # if set, every /api route requires this bearer token


def get_settings() -> Settings:
    _load_dotenv()
    return Settings(
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
        vision_model=os.environ.get("MKB_VISION_MODEL", "claude-opus-4-8"),
        agent_model=os.environ.get("MKB_AGENT_MODEL", "claude-opus-4-8"),
        db_path=Path(os.environ.get("MKB_DB_PATH", "recipes.db")),
        photos_dir=Path(os.environ.get("MKB_PHOTOS_DIR", "photos")),
        language=os.environ.get("MKB_LANGUAGE", "a Hindi-English mix (Hinglish)"),
        access_token=os.environ.get("MKB_ACCESS_TOKEN"),
    )
