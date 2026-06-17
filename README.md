# mumknowsbest

A conversational assistant for Mum's recipes — from her **paper book**, **Instagram**,
and **YouTube** — that she can **chat with or talk to on her phone** (in Hinglish).

See [`BUILD_PLAN.md`](./BUILD_PLAN.md) for the full design and roadmap. This README
covers the code that exists today.

## Where things are (modular by design)

The recipe "brain" is decoupled from where recipes come *from* and how Mum *reaches*
it. Each layer talks to the next only through a small interface, so pieces swap out
without touching the rest:

```
src/mumknowsbest/
├── models.py            # Recipe — the one shape every source normalizes into
├── config.py            # all settings (model IDs, language, db path) from env/.env
├── storage/
│   ├── base.py          # RecipeStore  (interface)
│   └── sqlite_store.py  #   └ SQLite implementation (swap for Postgres/pgvector later)
├── llm/
│   └── client.py        # the only place that calls Claude (vision OCR, etc.)
├── ingestion/
│   ├── base.py          # RecipeSource (interface) + ingest() driver
│   └── paper_book.py    #   └ photos → recipes via Claude vision  ← built first
├── agent/
│   ├── tools.py         # search_recipes / get_recipe, bound to RecipeStore
│   └── agent.py         # Claude + tools, Hinglish, channel-agnostic
└── cli.py               # first "channel"; web app & WhatsApp reuse the same brain
```

**Adding things later is a drop-in:**
- A new source (YouTube, Instagram) → implement `RecipeSource`; `ingest()` and storage are unchanged.
- Better search (semantic/vector) → extend `sqlite_store` or add a new `RecipeStore`; the agent improves for free.
- A new channel (web PWA, WhatsApp) → call `RecipeAgent.ask()`; the brain doesn't change.

Importing the package pulls in **only** the data model — no SDK, no network — so it's
cheap to import and easy to test. The Anthropic SDK is imported lazily, behind the LLM
client and the agent.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env          # add your ANTHROPIC_API_KEY

# Read a folder of recipe-book page photos into the collection
mumknowsbest ingest-photos ./photos

# See what's stored
mumknowsbest list

# Ask (chat). Voice is added at the channel edge later.
mumknowsbest ask "guests aa rahe hain, kuch paneer banau?"
```

## Tests

The model, storage, ingestion, and agent seams are covered without any network or API
key (fake LLM + scripted Claude client):

```bash
pytest
```

## Status

Phase 0 (foundations) and the Phase 1 paper-book pipeline are scaffolded and wired
end-to-end. Next: point it at real page photos, then YouTube/Instagram sources, voice,
and the web/WhatsApp channels — see the roadmap in `BUILD_PLAN.md`.
