"""The web channel: an installable PWA (chat + voice) served by FastAPI."""

from .app import create_app

__all__ = ["create_app"]
