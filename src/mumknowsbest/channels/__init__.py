"""Channels: the ways Mum reaches the recipe brain.

Each channel (CLI, web app, later WhatsApp) is a thin adapter over `RecipeAgent.ask()`
and a `RecipeStore` — no recipe logic lives here.
"""
