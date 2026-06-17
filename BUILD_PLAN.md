# mumknowsbest — Build Plan

A conversational assistant that holds all of Mum's recipes — from her paper book,
her Instagram saves, and her YouTube playlists — in one place she can **chat with
or talk to on her phone**.

> Status: planning. Nothing is built yet. This document is the blueprint.

---

## 1. What we're building (in one sentence)

Mum opens WhatsApp, sends a voice note — *"what was that paneer thing you make for
guests?"* — and gets back the recipe in her own words, with the option to open the
original video or the photo of the page it came from.

To get there we need three things:

1. **Get the recipes in** — digitize the paper book, pull recipes out of Instagram
   links and YouTube videos, and normalize them into one consistent format.
2. **A brain that can find and explain them** — store the recipes, search them well,
   and wrap a friendly Claude agent around them.
3. **A way for Mum to reach it** — a channel she already uses, that supports voice.

---

## 2. Architecture at a glance

```
   SOURCES                INGESTION                KNOWLEDGE BASE          AGENT                 CHANNEL
 ┌──────────┐         ┌──────────────────┐       ┌───────────────┐   ┌───────────────┐    ┌──────────────┐
 │ Paper     │ photos │ Vision OCR        │       │               │   │ Claude         │    │ WhatsApp      │
 │ book      ├───────►│ (Claude reads     ├──┐    │  Recipes DB    │   │ (opus-4-8)     │    │ voice + text  │
 └──────────┘         │  the page)        │  │    │  - structured  │◄──┤  + tools:      │◄──►│  (Mum)        │
 ┌──────────┐         ├──────────────────┤  │    │    fields      │   │   search       │    └──────────────┘
 │ Instagram │ links  │ Caption + audio   ├──┼───►│  - full text   │   │   get_recipe   │    ┌──────────────┐
 │ reels     ├───────►│ transcript        │  │    │  - embeddings  │   │   scale/sub    │    │ Web PWA       │
 └──────────┘         ├──────────────────┤  │    │  - media links │   │                │◄──►│ (dev + family │
 ┌──────────┐         │ YouTube transcript│  │    │               │   │ STT/TTS for     │    │  testing)     │
 │ YouTube   ├───────►│ + metadata        ├──┘    │               │   │ voice           │    └──────────────┘
 │ playlist  │ links  └──────────────────┘       └───────────────┘   └───────────────┘
 └──────────┘                    │
                                 ▼
                        ┌──────────────────┐
                        │ Claude structures │  every source → the SAME recipe schema
                        │ raw text → JSON   │  (title, ingredients[], steps[], tags…)
                        └──────────────────┘
```

The important design decision: **the recipe brain is decoupled from the channel.**
We build and test the brain first (over a CLI / simple web page), then bolt on
WhatsApp. That way the hard part (good recipes, good answers) is independent of the
plumbing.

---

## 3. Getting the recipes in (the real work)

Three pipelines, all ending in one canonical recipe record.

### 3a. Paper recipe book → digital
- **Capture:** Mum (or you) photographs each page with a phone. Even a stack of
  photos in a folder is fine to start.
- **Read:** Claude's vision capability reads each photo — printed *or* handwritten —
  and extracts a structured recipe (title, ingredients, steps, notes). Claude is
  strong at this and handles messy real-world pages.
- **Review:** A lightweight human-check step (especially for handwriting and
  quantities, where a wrong number matters). We keep the original photo linked to
  every recipe so Mum can always see the source.
- *Effort:* This is the largest manual-ish task, but it's a one-time batch and can be
  done a few pages at a time.

### 3b. Instagram links → recipes
- Most recipe reels put the full recipe **in the caption** — easiest path: pull the
  caption text and let Claude structure it.
- For reels where the recipe is only spoken, download the audio and transcribe it
  (Whisper), then structure that.
- We always store the original link so Mum can watch the reel.
- *Caveat:* Instagram is the most fragile source (they actively discourage scraping).
  We'll lean on captions first and treat full-video extraction as best-effort.

### 3c. YouTube playlist → recipes
- Enumerate the playlist and, for each video, grab the transcript (YouTube
  auto-captions, with Whisper as a fallback) plus title/channel/link.
- Claude turns the transcript into a clean recipe and keeps the link (ideally with a
  timestamp to where the cooking starts).

### Canonical recipe schema (what every source becomes)
```json
{
  "id": "uuid",
  "title": "Restaurant-style Paneer Butter Masala",
  "source": { "type": "book | instagram | youtube", "url": "...", "page_photo": "..." },
  "servings": 4,
  "time_minutes": 45,
  "ingredients": [ { "item": "paneer", "qty": "250", "unit": "g" } ],
  "steps": [ "Soak cashews...", "..." ],
  "tags": ["north-indian", "vegetarian", "dinner", "guests"],
  "language": "en",
  "raw_text": "original extracted text (for grounding/citations)",
  "embedding": "[vector]"
}
```

---

## 4. Storing & finding recipes

- **Database:** Start simple — **SQLite** (one file, zero ops) holding the structured
  fields + raw text. Move to Postgres only if it ever grows beyond a personal
  collection.
- **Search = hybrid:**
  - **Structured/keyword** filtering for "what can I make with paneer and peas?" or
    "show me the quick ones."
  - **Semantic (vector) search** for fuzzy asks like "that sweet thing you make at
    Diwali." This needs an embedding model — recommended: **Voyage AI** embeddings
    (Anthropic's recommended pairing) or a **local** model (`sentence-transformers`)
    if we want it fully private and free. For a few hundred–thousand recipes, either
    is plenty.
- The agent always grounds answers in real recipes and can cite the source, so Mum
  can jump to the original video or page photo.

---

## 5. The agent

- **Model:** `claude-opus-4-8` for the conversational agent (best quality for a
  warm, capable kitchen companion). Use the cheaper **Haiku 4.5** for the
  high-volume, behind-the-scenes ingestion structuring to keep costs down.
- **Pattern:** Claude with **tool use** (RAG). Tools we'll give it:
  - `search_recipes(query, filters)` — hybrid search over the knowledge base
  - `get_recipe(id)` — fetch the full recipe
  - `scale_recipe(id, servings)` and `suggest_substitution(...)` — handy kitchen helpers
- **Persona (system prompt):** warm, patient, talks like a helpful family cook.
  Reads steps **one at a time** in a hands-free "cooking mode," and answers in Mum's
  language.
- **Voice:**
  - Speech-to-text: **Whisper** (handles many languages well, incl. Hindi and
    Hinglish) — perfect for WhatsApp voice notes.
  - Text-to-speech: a natural TTS (e.g. ElevenLabs / OpenAI TTS) for spoken replies,
    or the browser's built-in voice for the web version.

> If Mum's recipes or speech are in Hindi / another language (or a mix), that's fully
> supported — it's a configuration choice we set early, because it affects OCR, STT,
> and TTS.

---

## 6. How Mum reaches it (the channel)

Recommendation: **build channel-agnostic, ship on WhatsApp.**

| Option | Why / why not |
|---|---|
| **WhatsApp** ✅ *(target)* | She already uses it daily; voice notes are native and perfect for "speak to it"; nothing to install. Needs WhatsApp Business API (via Twilio or Meta Cloud API) — some setup + small cost. |
| **Web PWA** ✅ *(dev + testing)* | Free, full control, works on any phone, browser mic/speaker for voice. Great for iterating quickly and for other family members. Downside: she has to open a link. |
| Telegram | Easiest/free bot API with voice — good fallback if WhatsApp setup is a hurdle, but she may not use Telegram. |
| Phone call agent | Most natural for a non-techy user (just call a number) but the most complex to build. A possible "v2" delight. |

Plan: **PWA first** (to test the brain with Mum fast), then **WhatsApp** for the
real, frictionless experience.

---

## 7. Tech stack summary

- **Language/backend:** Python + **FastAPI** — best ecosystem for the ingestion tools
  (`yt-dlp`, Whisper, Instagram fetchers) and the Anthropic SDK.
- **LLM:** Anthropic Claude via the official `anthropic` SDK. Agent on
  `claude-opus-4-8`; bulk ingestion on `claude-haiku-4-5`.
- **DB:** SQLite (+ a vector index; e.g. `sqlite-vec`) → Postgres + pgvector only if needed.
- **Embeddings:** Voyage AI (hosted) or `sentence-transformers` (local/private).
- **Voice:** Whisper (STT) + ElevenLabs/OpenAI TTS (or browser speech for the PWA).
- **Channel:** PWA (React or plain) for dev; WhatsApp via Twilio/Meta for production.
- **Hosting:** a small always-on host (Fly.io / Railway / Render) or a cheap VPS.

---

## 8. Roadmap (phased — each phase is independently useful)

**Phase 0 — Foundations (½ day)**
Repo scaffolding, Python project, `.env` for API keys, the recipe schema, and a
SQLite store. Outcome: a place to put recipes.

**Phase 1 — One ingestion pipeline end-to-end (YouTube first)**
YouTube is the most reliable source. Build playlist → transcript → Claude → stored
recipes. Outcome: the DB has real recipes to work with.

**Phase 2 — The recipe brain**
Hybrid search + the Claude agent with tools, usable over a CLI or tiny web page.
Outcome: you can already *ask it questions* about the YouTube recipes.

**Phase 3 — The other two pipelines**
Add Instagram (captions first) and the paper book (vision OCR + review step).
Outcome: the full collection is in.

**Phase 4 — Voice + PWA**
Add speech-in / speech-out and a phone-friendly web app. Outcome: Mum can talk to it.

**Phase 5 — Ship on WhatsApp**
Wire the brain to WhatsApp so it lives where she already is. Outcome: the real product.

**Phase 6 — Polish**
"Add this recipe" by photo or link, a hands-free cooking mode, family sharing.

---

## 9. Privacy, cost & risks

- **Privacy:** This is personal family data. Keep the knowledge base private; restrict
  the WhatsApp bot to Mum's (and family) numbers; if we want zero data leaving the
  house, use local Whisper + local embeddings.
- **Cost:** Mostly per-message Claude calls (cheap, and cheaper with Haiku for
  ingestion + prompt caching for the recipe context), plus transcription and a small
  hosting bill. A personal collection is inexpensive to run.
- **Main risks / unknowns:**
  - **Instagram fragility** — mitigate by preferring captions; accept partial coverage.
  - **Handwriting accuracy** — mitigate with the human-review step and source photos.
  - **Language** — confirm early (English vs Hindi/Hinglish/other); it shapes OCR/STT/TTS.

---

## 10. Immediate next steps

1. Confirm the few choices that shape the build: **channel** (WhatsApp target, PWA for
   dev — good default), **language(s)** of the recipes, and whether to keep everything
   **local/private** vs use hosted services.
2. Gather inputs: the **YouTube playlist link(s)**, a handful of **Instagram links**,
   and **5–10 photos** of book pages to test the OCR.
3. Build **Phase 0 + Phase 1** so there are real recipes in the system within the
   first sitting.

> Recommendation: start by pointing Phase 1 at the YouTube playlist — it's the
> fastest path to "wow, it actually knows Mum's recipes."
