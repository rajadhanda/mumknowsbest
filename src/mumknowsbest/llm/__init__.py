"""LLM access: a thin wrapper around the Anthropic SDK."""

from .client import LLMClient, media_type_for

__all__ = ["LLMClient", "media_type_for"]
