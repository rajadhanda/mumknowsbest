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
├── channels/
│   └── web/             # installable PWA (chat + voice via the browser)  ← Mum's app
└── cli.py               # dev "channel"; WhatsApp will reuse the same brain
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

# Ask from the terminal
mumknowsbest ask "guests aa rahe hain, kuch paneer banau?"

# Run Mum's app (chat + voice, installable)
mumknowsbest serve            # then open http://<your-ip>:8000 on her phone
```

### The web app

`mumknowsbest serve` runs an installable PWA: a big-text Hinglish chat with a 🎤 button
(speech-to-text in the browser, `hi-IN`), a 🔊 toggle that reads replies aloud, and a
📖 drawer that browses the full recipe collection. On an iPhone, **Share → Add to Home
Screen** gives it an icon and a full-screen, app-like feel.

Voice runs entirely in the browser (Web Speech API) — the server only moves text, so
the same brain will plug into WhatsApp untouched. Note: iOS Safari needs HTTPS (or
localhost) for the mic; for testing on her phone, tunnel with something like
`tailscale`/`ngrok`, or use text first.

New recipes can be added straight from the app (➕): snap/upload **photos of book
pages or screenshots** (works today), or paste an **Instagram / YouTube link** (the
endpoint and UI are live; those extractors land in Phase 3).

## The API is the product surface (iOS-ready)

Everything the PWA does goes through the HTTP API — nothing is web-only — so a native
iOS (SwiftUI) app is a pure client of the same server, no backend changes needed:

| Route | What it does |
|---|---|
| `GET /api/health` | recipe count, chat readiness |
| `GET /api/recipes`, `GET /api/recipes/{id}` | browse the collection |
| `GET /api/photos/{name}` | the archived original page photo for a recipe |
| `POST /api/chat` `{message, history[]}` | talk to the assistant |
| `POST /api/ingest/photos` (multipart) | add recipes from page photos / screenshots |
| `POST /api/ingest/link` `{url}` | add from an Instagram / YouTube link (501 until Phase 3) |

Auth: set `MKB_ACCESS_TOKEN` and every `/api` route requires `Authorization: Bearer
<token>` (or `?token=` for `<img>` loads). Recipe photos are archived
content-addressed under `MKB_PHOTOS_DIR` and referenced by bare filename, so recipes
carry no server paths. Ingestion is idempotent — re-sending the same photo updates
rather than duplicates.

Two known deferrals for a multi-device future (documented, not blockers): chat history
is client-replayed rather than a server-owned conversation resource, and photo
ingestion is synchronous rather than a job queue. Both are additive API changes.

## Tests

The model, storage, ingestion, and agent seams are covered without any network or API
key (fake LLM + scripted Claude client):

```bash
pytest
```

## Status

Built and tested: foundations (Phase 0), the paper-book pipeline (Phase 1), the recipe
brain (Phase 2), and the voice-capable web app (Phase 4) — the schema is validated
against real handwritten Hinglish/Hindi pages. Next: YouTube/Instagram sources
(Phase 3), WhatsApp (Phase 5) — see the roadmap in `BUILD_PLAN.md`.
