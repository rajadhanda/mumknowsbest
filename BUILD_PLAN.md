# mumknowsbest — Build Plan

A conversational assistant that holds all of Mum's recipes — from her paper book,
her Instagram saves, and her YouTube playlists — in one place she can **chat with
or talk to on her phone**.

> Status: planning. Nothing is built yet. This document is the blueprint.

### Decisions locked in (2026-06-17)
- **Language:** **Hindi + English mix (Hinglish)** — pages, speech, and replies may
  switch between English, Hindi (Devanagari), and romanized Hindi. This shapes OCR,
  speech-to-text, text-to-speech, and how the agent talks back.
- **First source to ingest:** the **paper recipe book** (photos) — it's the
  irreplaceable family content, so we capture it first.
- **Channel:** open to **WhatsApp, a web app, or an iOS app.** Recommendation below
  (§6): build an **installable web app (PWA)** first — it gives an iOS-app-like
  experience with no App Store overhead — and add **WhatsApp** as the zero-friction
  messaging channel. A true native iOS app stays an easy later option.

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
- **Voice (Hinglish):**
  - Speech-to-text: **Whisper** — handles Hindi and code-switched Hinglish, and works
    on WhatsApp voice notes. We'll test it on real samples of Mum's speech and tune.
  - Text-to-speech: a **multilingual / Hindi-capable** voice (e.g. ElevenLabs
    multilingual or OpenAI TTS, both speak Hindi) so spoken replies sound natural; the
    browser's built-in voice is a free fallback for the web version.
- **Talking back in her register:** the system prompt instructs the agent to **mirror
  Mum's language and script** — if she writes/speaks Hinglish, it replies in Hinglish;
  if she switches to Hindi, it follows. Recipes are stored with a `language` field and
  their original wording preserved.

> Hinglish touches every layer — **OCR** (mixed Devanagari + Latin on the book pages),
> **STT**, **TTS**, and the **agent's replies**. We bake it in from day one rather than
> bolting it on.

---

## 6. How Mum reaches it (the channel)

You're open to **WhatsApp, a web app, or an iOS app.** Recommendation:
**build channel-agnostic; ship an installable web app first, then add WhatsApp.**

| Option | Why / why not |
|---|---|
| **Web app (PWA)** ✅ *(build first)* | Free, full control over layout (big text, mic button, recipe photos), works on iPhone, and **"Add to Home Screen" makes it feel like a native app** — no App Store. Voice via Safari. This covers the "iOS app" wish without the App Store overhead. Downside: first launch is a link, not an icon (until she pins it). |
| **WhatsApp** ✅ *(add next)* | She already uses it; voice notes are native and ideal for "speak to it"; truly zero-friction. Needs WhatsApp Business API (Twilio or Meta Cloud API) — some setup + small cost. |
| Native iOS app | Nicest icon-on-homescreen + App Store presence, but adds real build/release overhead (Xcode, Apple Developer account, review). Keep as an easy upgrade once the PWA proves the experience. |
| Telegram / phone-call agent | Free/voice fallback and a "magical" voice option respectively — held in reserve. |

Plan: the recipe brain is shared by all channels, so **PWA first** (test with Mum
fast, get the iOS-app feel via Home Screen), then **WhatsApp**, and a native iOS app
only if she wants it in the App Store.

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
Repo scaffolding, Python project, `.env` for API keys, the recipe schema (with the
`language` field), and a SQLite store. Outcome: a place to put recipes.

**Phase 1 — Paper-book pipeline end-to-end** *(first source)*
Photos → Claude vision OCR (Hinglish: mixed Devanagari + Latin) → structured recipe →
quick review step → stored, with the source photo kept. Outcome: Mum's irreplaceable
book recipes are digitized first.

**Phase 2 — The recipe brain**
Hybrid search + the Claude agent with tools, usable over a CLI or tiny web page,
replying in Hinglish. Outcome: you can already *ask it questions* about the book recipes.

**Phase 3 — The other two pipelines**
Add YouTube (playlist → transcripts) and Instagram (captions first). Outcome: the full
collection is in.

**Phase 4 — Voice + installable web app**
Hinglish speech-in / speech-out and a phone-friendly PWA (Add-to-Home-Screen = iOS-app
feel). Outcome: Mum can talk to it.

**Phase 5 — Add WhatsApp**
Wire the brain to WhatsApp so it lives where she already is. Outcome: zero-friction
access via voice notes.

**Phase 6 — Polish**
"Add this recipe" by photo or link, a hands-free cooking mode, family sharing, and —
if wanted — a native iOS app.

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

1. **Get 5–10 clear photos of book pages** (a mix: printed *and* handwritten, English
   *and* Hindi if both exist) — this is the only input needed to start Phase 1.
2. One remaining choice: keep everything **local/private** (local Whisper + local
   embeddings, nothing leaves the house) vs use **hosted** services (a bit easier, very
   low cost). Sensible default: hosted to start, with privacy locked down to Mum +
   family; revisit if we want fully local.
3. Build **Phase 0 + Phase 1** so the first real recipes from the book are in the
   system within the first sitting — then point the agent (Phase 2) at them.

> Channel and language are decided (§ Decisions locked in). Paper book is the starting
> source, so the very next concrete thing is a folder of page photos to OCR.
