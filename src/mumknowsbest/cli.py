"""Command-line entry point — the first 'channel' for driving the recipe brain.

  mumknowsbest ingest-photos ./photos   # read book pages into the collection
  mumknowsbest list                     # show what's stored
  mumknowsbest ask "guests aa rahe hain, kuch paneer banau?"

Heavier imports (the SDK, ingestion, agent) are pulled in inside each command so
`list` works without an API key and `--help` is instant.
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional

from .config import Settings, get_settings
from .storage.sqlite_store import SqliteRecipeStore


def _require_key(settings: Settings) -> None:
    if not settings.anthropic_api_key:
        print(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key.",
            file=sys.stderr,
        )
        raise SystemExit(2)


def cmd_ingest_photos(args: argparse.Namespace) -> None:
    from .ingestion.base import ingest
    from .ingestion.paper_book import PaperBookSource
    from .llm.client import LLMClient

    settings = get_settings()
    _require_key(settings)
    store = SqliteRecipeStore(settings.db_path)
    source = PaperBookSource(
        args.photo_dir, LLMClient(settings), archive_dir=settings.photos_dir
    )
    photos = source.photos()
    print(f"Found {len(photos)} photo(s) in {args.photo_dir}. Reading with {settings.vision_model} ...")
    added = ingest(source, store)
    print(f"Added {added} recipe(s). Collection now holds {store.count()}.")
    if source.failures:
        print(f"\n{len(source.failures)} photo(s) failed (fix and re-run — already-added pages just update):")
        for photo, error in source.failures:
            print(f"  - {photo}: {error}")


def cmd_list(args: argparse.Namespace) -> None:
    store = SqliteRecipeStore(get_settings().db_path)
    for recipe in store.all():
        print(f"- {recipe.title}  [{recipe.source.type}]  ({recipe.id})")
    print(f"\n{store.count()} recipe(s).")


def cmd_serve(args: argparse.Namespace) -> None:
    try:
        import uvicorn

        from .channels.web import create_app
    except ImportError:
        print(
            'The web app needs extra packages: pip install -e ".[web]"',
            file=sys.stderr,
        )
        raise SystemExit(2)

    settings = get_settings()
    store = SqliteRecipeStore(settings.db_path)
    if not settings.anthropic_api_key:
        print("Note: ANTHROPIC_API_KEY not set — recipes will browse, chat will be offline.")
    print(f"Serving Mum's app on http://{args.host}:{args.port}  ({store.count()} recipes)")
    uvicorn.run(create_app(store, settings=settings), host=args.host, port=args.port)


def cmd_ask(args: argparse.Namespace) -> None:
    from .agent.agent import RecipeAgent

    settings = get_settings()
    _require_key(settings)
    store = SqliteRecipeStore(settings.db_path)
    print(RecipeAgent(store, settings).ask(args.question))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mumknowsbest", description="Mum's recipe assistant")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser(
        "ingest-photos", help="Read a folder of recipe-book page photos into the collection"
    )
    p_ingest.add_argument("photo_dir", help="Folder containing page photos")
    p_ingest.set_defaults(func=cmd_ingest_photos)

    p_list = sub.add_parser("list", help="List stored recipes")
    p_list.set_defaults(func=cmd_list)

    p_serve = sub.add_parser("serve", help="Run the web app (installable PWA: chat + voice)")
    p_serve.add_argument("--host", default="0.0.0.0")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.set_defaults(func=cmd_serve)

    p_ask = sub.add_parser("ask", help="Ask the assistant a question")
    p_ask.add_argument("question", help="Your question, in quotes")
    p_ask.set_defaults(func=cmd_ask)

    return parser


def main(argv: Optional[list[str]] = None) -> None:
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
