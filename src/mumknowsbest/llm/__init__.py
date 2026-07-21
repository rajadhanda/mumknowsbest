"""LLM access: a thin wrapper around the Anthropic SDK."""

from .client import MEDIA_TYPES, LLMClient, make_anthropic_client, media_type_for

__all__ = ["LLMClient", "MEDIA_TYPES", "media_type_for", "make_anthropic_client"]
