# EXPLANATION — SproutVibe-Shivansh (college project)

> This file is **not** the changelog. `SHIVANSH_CHANGELOG.md` tracks *what changed and when*.
> This file explains *what we did, why it matters, and how I can explain it in a viva* — in plain, precise words.

## 1. What is this project, in one paragraph?

SproutVibe is a self-hosted plant-care app: you add your plants, it reminds you to water/fertilise them, and you keep a journal with photos. My fork, SproutVibe-Shivansh, adapts it for Indian home gardeners: Indian plant and seed names first (not Latin), Hindi and Gujarati language support, a chatbot that answers about *your* plants, and a photo scan that guesses the plant and any disease.

## 2. What have we done so far? (honest status)

Three things:

1. **Read the full codebase** — backend (`FastAPI + SQLite/Postgres`), frontend (`React + Vite + Tailwind PWA`), species search (`Perenual + iNaturalist + FloraCodex`), one-shot AI care (`Anthropic/OpenAI`), photo upload with no analysis, all-English UI.
2. **Wrote planning docs** — `IDEATION_AND_PHASES.md` (what + why + build order for the 4 tasks) and `SHIVANSH_CHANGELOG.md` (version tracker).
3. **Built Phase 0 + Phase 1** — env placeholders + pinned Groq/Cerebras models, then the 62-entry Indian plants catalogue with enriched search (`tulsi`/`तुलसी`/`તુલસી` all work), category/seed filters, and Indian-first UI. 45 backend tests green.
4. **Built Phase 2** — full UI in English, Hindi, and Gujarati (`i18next`, ~150 keys, human-reviewed): language switcher in Settings that syncs to my account, species search answers in my language, dates and "3 days ago" also in Hindi/Gujarati. 21 frontend tests green. Phases 3–6 not started.

## 3. The 4 tasks, explained like I would in a viva

### Task 1 — Indian names instead of scientific names
Today the app searches by Latin names like `Ocimum tenuiflorum`. A user in Gujarat searches `Tulsi`, `તુલસી`, or `तुलसी`. So we keep Latin internally (it is still the correct join key across Perenual/iNaturalist), but we add a small curated catalogue `indian_plants` with Hindi name, Gujarati name, transliterations, category (vegetable/spice/medicinal/flower), and kind (plant vs seed). Search matches any of these, then shows the Indian name big and Latin small. Seeds get sowing hints. If no mapping exists, we fall back to English — we never break old data.

Example I can demo: type `tulsi`, `तुलसी`, `તુલસી` — all three return Tulsi with Hindi + Gujarati names.

### Task 2 — Chatbot (agent, not a generic chatbot)
Not a floating ChatGPT clone. Our agent only answers from three grounded sources: (a) your own plants/schedules/journals, (b) the Indian catalogue entry, (c) the last scan result if any. It has read-only tools first (`list my plants`, `what is due`, `search Indian catalogue`), and it must name which plant it is talking about. It replies in the language you chose (English/Hindi/Gujarati), in short steps, and says when it is unsure.

### Task 3 — Translation (English to Hindi + Gujarati)
All buttons and screens today are hardcoded English. We add `i18next` with three files (`en.json`, `hi.json`, `gu.json`), a language switch in Settings that syncs to the server, and we pass `?lang=` to species/chat/scan so dynamic text also follows. Journal entries stay as the user wrote them — we do not auto-translate personal notes.

### Task 4 — Scan and detect (Groq primary, Cerebras fallback)
You take a photo of a leaf. The backend compresses it, sends it to Groq's vision model, and if Groq fails or times out, retries once with Cerebras. The answer is strict JSON: plant guess + confidence, health (healthy/stressed/diseased/unknown) + disease guess, 2–4 care steps, and which provider answered. Low confidence or non-plant photos get an honest message (“send a clearer close-up”), not a fake confident answer. History is saved per user so you can attach a scan to a journal.

Fallback in one line: try Groq, on error try Cerebras, on total failure return a clear error — never silently wrong.

## 4. RAG / context — what we chose and why

RAG here does **not** mean a heavy vector database. For a working college demo that I can explain, we use **context-grounded generation** (RAG-lite):

- **What the agent sees:** your plants + due tasks + recent journal health + matched catalogue entry + last scan + a small curated knowledge file (`plant_knowledge.md`, ~30 short notes). All of this is injected into the prompt as facts, with a rule: “answer only from this context, cite the plant name.”
- **Why not embeddings yet:** SQLite full-text + catalogue lookup already answers “which of my plants need water?” precisely, runs on a laptop, needs no extra service, and I can trace every answer in the viva. Vector search (`sqlite-vec`, embeddings) is kept as an *optional* Phase 6 stretch, not core.
- **Why this is better:** precise (no hallucinated plants), humanised (short, in your language), anti-slop (no generic filler, admits uncertainty, shows confidence + disclaimer).

If a professor asks “where is the RAG?”, I point to `backend/ai/agent.py` (context builder) + `backend/data/indian_plants.json` + `plant_knowledge.md` + chat history tables — retrieval is SQL + catalogue lookup, generation is Groq/Cerebras. Simple, traceable, working.

## 5. Keys and safety (important)

A temporary Groq key was shared for development. It is **remembered for future phases only** — it is **not** committed to this repo, not in `.env.example`, not in any doc. At build time it will be used as `GROQ_API_KEY` env var or user Setting (same pattern the codebase already uses for Perenual/Anthropic keys), with demo users blocked from server keys. Cerebras key will be added the same way. No keys in logs, no images in logs, 10MB upload cap, EXIF stripped.

## 6. How I will demo it (2-minute script)

1. Add plant: search `methi` → shows `Methi / मेथी / મેથી`, kind = seed, sowing tip.
2. Switch language to Hindi → dashboard + result in Hindi.
3. Scan a Tulsi leaf photo → “Tulsi, early stress, water in 2 days, keep in morning sun” + confidence.
4. Ask chatbot in Gujarati: “મારા કયા છોડને પાણી જોઈએ?” → lists only my due plants by name.
5. Force Groq off (dev flag) → same answer with `provider: cerebras` badge.

## 7. File map (so I never get lost in viva)

- `IDEATION_AND_PHASES.md` — full technical plan, phases 0–6, acceptance criteria.
- `SHIVANSH_CHANGELOG.md` — version history (this explanation is not duplicated there).
- `EXPLANATION.md` — this file, the human story.
- Future code: `backend/data/indian_plants.json`, `backend/routes/chat.py`, `backend/routes/scan.py`, `backend/ai/providers.py`, `backend/ai/agent.py`, `backend/ai/vision.py`, `frontend/src/locales/{en,hi,gu}.json`, `frontend/src/pages/ChatPage.jsx`, `frontend/src/pages/ScanPage.jsx`.

## 8. Viva questions I am ready for

- *Why not just use scientific names?* Because our users don’t know them; Latin stays as internal key, Indian names are display + search.
- *Why Groq + Cerebras?* Fast inference, OpenAI-compatible API so one fallback chain works, free-tier friendly for college.
- *Why no vector DB?* Overkill for MVP; SQL + catalogue grounding is precise, offline-capable, and explainable. Vectors are optional later.
- *What if AI is wrong?* Confidence score + disclaimer + “clearer photo” path + advise local expert for edible/medicinal use.
- *What is not done?* Phases 3–6 (Groq/Cerebras chat + scan, polish). Phases 0–2 are built and tested.

## 9. Current limits (said openly)

Phase 0–2 done and tested. Model IDs must still be re-verified at Phase 3 build time (Groq/Cerebras change fast). Camera needs real-device testing. Perenual free limit (100/day) is why catalogue-first matters.
