# SproutVibe-Shivansh — Ideation & Phases

> Scope owner: Shivansh team (fork of `sproutvibe-main`)
> Date: 2026-09-14 (updated: Phase 0 + Phase 1 done)
> Status: **Phase 0 + Phase 1 implemented and tested — Phases 2–6 not started**
> Source codebase analysed: `backend/routes/plants.py`, `backend/ai/care.py`, `backend/core/config.py`, `frontend/src/api/plants.js`, `README.md`, `CHANGELOG.md`
> Key note: temporary Groq key shared by owner is **remembered for future phases only — never committed** (env/Setting at build time). See §5.
> Companion: `EXPLANATION.md` (human/viva story) + `SHIVANSH_CHANGELOG.md` (version tracker).

This document captures the **ideation** (what + why + how) and **phases** (build order) for the 4 requested tasks:

1. API-Category — Indian plants & seeds names instead of scientific names
2. Chatbot (Agent)
3. Translation — English to Hindi and English to Gujarati
4. Scan & detect plants and disease — Groq API primary, Cerebras API fallback

Related tracker: see `SHIVANSH_CHANGELOG.md` in repo root.

---

## 0. Current-state summary (what exists today)

- **Species search** (`GET /plants/species/search?q=`): merges Perenual (keyed, has care data) + iNaturalist (keyless) + FloraCodex (keyed), dedupes by lowercase `scientific_name`, returns `SpeciesResult{id, common_name (English), scientific_name (Latin), thumbnail, watering, watering_days, sunlight, cycle, description, source}`. See `backend/routes/plants.py:53-64,190-230`.
- **Species detail** (`GET /plants/species/{id}?source=`): Perenual / iNaturalist / FloraCodex branches, Wikipedia `en.wikipedia.org` summary via `scientific_name` for description. See `backend/routes/plants.py:308-427`.
- **AI care** (`POST /plants/species/ai-care`): one-shot JSON via `CareAdvisor` with Anthropic (`claude-haiku-4-5-20251001`) or OpenAI (`gpt-5.6-luna`) providers, keys from encrypted `Setting` then env. No chat history, no vision. See `backend/ai/care.py:232-283`.
- **Frontend**: hardcoded English strings, no `i18n` library, species UI shows `common_name + scientific_name`. API client in `frontend/src/api/plants.js:15-21`.
- **Photos**: `POST /plants/{id}/photo` saves to `uploads/` and serves `/uploads`, no analysis.
- **Config**: env-driven (`JWT_SECRET, AI_PROVIDER, ANTHROPIC_*, OPENAI_*, PERENUAL_API_KEY, ...`). No `GROQ_*` / `CEREBRAS_*` / language keys yet.

Implication: all 4 tasks are **additive** — no existing feature is removed, but species display order, AI provider abstraction, and frontend strings will be touched.

---

## 1. Task 1 — API-Category: Indian plants & seeds names

### 1.1 Problem
Indian users search for `Tulsi / Haldi / Dhaniya / Methi / Ashwagandha / Palak / Bhindi` or `तुलसी / હળદર`, not `Ocimum tenuiflorum / Curcuma longa`. Current API is Latin-centric and English-common-name-centric, with no seed-vs-plant category.

### 1.2 Ideation

**Data model (new):**
- New table or curated seed file `indian_plants`:
  - `scientific_name (unique, FK-like join key)` — keep Latin as internal dedupe key, but **demote in UI**.
  - `english_name`, `hindi_name (Devanagari + transliteration)`, `gujarati_name (Gujarati script + transliteration)`, `regional_names JSON {hi, gu, transliterations[]}`.
  - `category: vegetable | fruit | flower | herb_medicinal | spice | grain_pulse | tree | succulent | other`
  - `kind: plant | seed` (seeds: e.g. `Methi seeds, Dhaniya seeds, Palak seeds` with sowing info).
  - `sowing_season_in, care_notes_in (optional, short)`.
- Seed with ~50–100 MVP entries covering kitchen garden + medicinal + common ornamentals. Source: manual curation + Wikipedia interlanguage links + AI-assisted draft reviewed by human.
- Later: allow admin CRUD for this catalogue.

**API design (backward compatible):**
- Extend `SpeciesResult` with optional fields (do not break old clients):
  - `indian_names: {hi, gu, hi_translit, gu_translit} | None`
  - `display_name: str` (resolved Indian/English name per `?lang=` or `Accept-Language`)
  - `category: str | None`, `kind: plant | seed | None`
- Extend search:
  - `GET /plants/species/search?q=&lang=en|hi|gu&category=&kind=`
  - Normalise query: lowercase, trim, transliteration-insensitive (`tulsi == तुलसी == તુલસી` via lookup table, not ML for MVP).
  - Merge order stays Perenual → iNaturalist → FloraCodex, then **enrich each result with `indian_plants` join** on `scientific_name`.
  - If `q` matches only Indian name (no Latin hit), return catalogue hit directly with `source: indian_catalogue`.
- Extend detail:
  - `GET /plants/species/{id}?source=&lang=` returns same enrichment.
  - `GET /plants/species/wiki-description?scientific_name=&lang=hi|gu` — try `hi.wikipedia.org` / `gu.wikipedia.org` first, fallback to `en`.
- New read-only endpoints (MVP, cheap):
  - `GET /plants/categories` → list of categories with counts.
  - `GET /plants/indian-catalogue?category=&kind=&q=` → paged catalogue (works without Perenual key — important for offline/demo).

**Frontend:**
- `AddPlantPage`: search box placeholder shows example `e.g. Tulsi / तुलसी / Haldi`; result cards show `display_name` big, `scientific_name` small grey; filter chips for category + kind.
- `PlantDetailPage`: header shows Indian name + English + Latin; seed-kind plants show sowing tip box.
- No breaking change to `Plant.species` DB column — store `scientific_name` internally, display localised.

**Edge cases:**
- Multiple Indian names for one Latin name (e.g. `Brinjal = Baingan / Ringan`) → show primary + alias list.
- Same Hindi name for multiple species → return all, sort by catalogue priority.
- Missing mapping → `indian_names: null`, UI falls back to `common_name`.

### 1.3 Acceptance criteria
- [x] Search `tulsi`, `तुलसी`, `તુલસી` all return Tulsi with Hindi + Gujarati names.
- [x] `category` + `kind` filters work; catalogue works with no Perenual key.
- [x] Old clients ignoring new fields still work.
- [x] Tests: catalogue lookup, transliteration normalisation, enrichment merge.

---

## 2. Task 2 — Chatbot (Agent)

### 2.1 Problem
Current AI is one-shot care JSON. Users want: “My Tulsi leaves are yellowing, what to do?”, “When to water my 5 plants?”, in Hindi/Gujarati.

### 2.2 Ideation

**Experience:**
- Floating chat button (mobile bottom-nav safe) + full `/chat` page. PWA-compatible, works with existing auth (Bearer) + demo-mode guard (rate-limit demo).
- Chat understands user context: user’s plants, due/overdue schedules, recent journal health, current catalogue entry. Answers in user’s language (`en | hi | gu`).
- Suggested prompts on empty state: “Which of my plants need water?”, “My palak has spots, help”, “Sow methi now?”.

**Backend (new `backend/routes/chat.py` + `backend/ai/agent.py`):**
- `POST /chat/sessions` → create session; `GET /chat/sessions`, `GET /chat/sessions/{id}/messages`, `POST /chat/sessions/{id}/messages {text, lang, plant_ids?}` → assistant reply + tool calls trace.
- Provider abstraction reuses `CareAdvisor` pattern but new `ChatProvider` protocol with **Groq primary, Cerebras fallback** (both OpenAI-compatible `chat/completions`). Keep Anthropic/OpenAI as optional tertiary for care JSON only — chat defaults to Groq/Cerebras per requirement.
- Tool-calling (function-calling) MVP tools (read-only first):
  - `list_plants`, `get_plant`, `list_due_tasks`, `get_schedule_summary`, `search_species_indian`, `get_care_suggestion`.
- Write tools gated behind explicit confirm (`mark_task_done`, `add_journal`) — phase 2.
- Persist `ChatSession{id, user_id, title, lang, created_at}` + `ChatMessage{id, session_id, role, content, lang, tokens?}` in Postgres/SQLite.
- System prompt: plant expert, concise, safe (no pesticide dosage beyond label advice, advise local agri expert for severe disease), always cite which plant it refers to, respond in requested lang.
- Safety: max turns/session, max tokens, per-user rate limit, strip EXIF/PII, demo users blocked from server keys (`allow_env_fallback=False` pattern already in codebase).

**Frontend (new `src/pages/ChatPage.jsx` + `src/api/chat.js` + `src/components/ChatWidget.jsx`):**
- Message list, streaming (SSE or polling MVP → SSE later), language toggle, plant picker chips, markdown-lite rendering, error + retry, offline notice.
- Reuse `resolveMediaUrl`, auth client, Tailwind dark mode.

**MCP synergy:**
- Existing `mcp/` tools (`list_plants, list_due_tasks, ...`) map 1:1 to agent tools — reuse schemas.

### 2.2b RAG / context design (adopted — RAG-lite, explainable)

Decision: **no vector DB for MVP**. Retrieval = SQLite lookups + catalogue join + FTS-style keyword match; generation = Groq/Cerebras. This is precise, runs on a college laptop, and is viva-traceable.

- **Context builder** (`backend/ai/agent.py::build_context()`): per message, fetch (1) user plants + due/overdue schedules, (2) recent journal health (last 3 per plant), (3) matched `indian_plants` entry, (4) last `PlantScan` for referenced plant, (5) top-3 snippets from curated `backend/data/plant_knowledge.md` by keyword overlap. Cap context (~2k tokens), always include plant ids + names.
- **Grounding rule in system prompt:** “Answer ONLY from provided context + general care knowledge. Name the plant. If context is missing, say what is missing and ask for a photo or plant name. Never invent a plant the user does not have.”
- **Anti-slop guards:** short steps (max 4), confidence + disclaimer on disease, reply in requested `lang`, no pesticide dosage beyond label, refuse non-plant scope politely.
- **Optional stretch (Phase 6 only):** `sqlite-vec` or FTS5 over `plant_knowledge.md` + journals for semantic recall. Explicitly out of MVP to stay explainable.
- **New planned file:** `backend/data/plant_knowledge.md` (30–50 short human-reviewed notes, en + hi/gu terms inline).

### 2.3 Acceptance criteria
- [ ] Logged-in user can chat about own plants; agent lists due tasks correctly.
- [ ] Hindi + Gujarati replies are fluent; language toggle persists.
- [ ] Groq down → Cerebras answers (verified by forced-failure test).
- [ ] No cross-user data leak; demo isolation holds.
- [ ] Tests: session CRUD, tool routing, fallback, rate limit.

---

## 3. Task 3 — Translation: English → Hindi + Gujarati

### 3.1 Problem
All UI strings are hardcoded English. Target users need Hindi + Gujarati.

### 3.2 Ideation

**Scope decision (MVP):**
- Full UI chrome translated (nav, buttons, dashboard, add-plant, plant-detail, settings, auth, chat).
- Dynamic data: `display_name` + `care_summary` + chatbot replies translated; journal body stays user-written (no auto-translate MVP).
- Backend error `detail` strings stay English in API, frontend maps to localised friendly message.

**Stack (pinned per `CLAUDE.md`):**
- `i18next==<pinned> + react-i18next==<pinned> + i18next-browser-languagedetector==<pinned>` (exact versions chosen at implementation time, no `^`).
- Locale files: `frontend/src/locales/en.json, hi.json, gu.json` (namespaced: `common, dashboard, plants, chat, settings, errors`).
- Language source of truth: `localStorage: sprout_lang` + `Setting{key: language}` server sync (like theme). `Accept-Language` header sent by `api/client.js` interceptor.
- Backend: `?lang=` / `Accept-Language` on species + chat + scan endpoints; prompts include `Respond in {lang}`; Wikipedia lang subdomain switch.

**Process:**
- Extract strings via codemod/manual pass (no auto-machine-translate in repo — human-reviewed Hindi/Gujarati).
- Transliterated search aliases included in locale or catalogue (see Task 1).
- PWA + Capacitor safe-area + font check: Devanagari + Gujarati render on Android WebView (system fonts OK, verify).

### 3.3 Acceptance criteria
- [ ] Language switcher in Settings + persist across reload + server sync.
- [ ] All MVP screens render in en/hi/gu with no missing-key fallback visible.
- [ ] Species + chat + scan honour `lang`.
- [ ] Tests: locale key parity script (`en` keys ⊆ `hi,gu`), detector + fallback test.

---

## 4. Task 4 — Scan & detect plants and disease (Groq + Cerebras fallback)

### 4.1 Problem
Photo upload exists but gives zero intelligence. Users want: point camera at leaf → “This is Tulsi, early powdery mildew, do X”.

### 4.2 Ideation

**Important constraint:** Groq + Cerebras are **LLM inference APIs**, not custom vision-training platforms. MVP uses their **vision-capable chat models** (OpenAI-compatible image_url). If a provider lacks vision at build time, fallback chain handles it: try Groq vision → Cerebras vision → text-only fallback (caption + catalogue match) with honest low-confidence flag. Pin model IDs at implementation (e.g. Groq `meta-llama/llama-4-scout-...` or current vision model; Cerebras current vision/text model) — verify docs during Phase 3, do not hardcode blindly.

**API (new `backend/routes/scan.py` + `backend/ai/vision.py`):**
- `POST /plants/scan?lang= {file: image, plant_id?: int}` (auth required, 10MB limit like existing photo upload, JPEG/PNG/WEBP).
  - Steps: validate → downscale/compress (max 1600px, strip EXIF) → Groq vision call with JSON-schema prompt → on failure/timeout → Cerebras retry → parse → enrich with Indian catalogue → respond.
  - Response `ScanResult{plant_guess{display_name, scientific_name, confidence}, health{status: healthy|stressed|diseased|unknown, disease_guess?, confidence}, care_actions[{step, urgency}], disclaimer, provider_used: groq|cerebras, lang}`.
- `GET /plants/scans` + `GET /plants/{id}/scans` history (new `PlantScan{id, user_id, plant_id?, image_path, result_json, provider, lang, created_at}`).
- Optional `POST /plants/{id}/scans/{scan_id}/apply` → creates/updates plant + journal entry + schedules (reuses existing routes internally).
- Config: `GROQ_API_KEY, GROQ_VISION_MODEL, CEREBRAS_API_KEY, CEREBRAS_MODEL` via user `Setting` first then env (same `_resolve_api_key` pattern, demo-blocked). Never log keys or images to logs.
- Safety: plant-only scope refusal (“not a plant” → graceful message), human-readable disclaimer (AI guess, confirm with local expert for edible/medicinal use), rate limit + size limit.

**Frontend (extend `PlantDetailPage` + new `ScanPage/modal`):**
- “Scan plant” button (camera on Capacitor via file input `capture`, gallery fallback), preview + compress client-side, progress state (`Uploading → Analysing with Groq… → Result`), result card (guess + confidence bar + disease + steps in user lang), actions: Save as plant / Attach to journal / Create reminder.
- Offline/PWA: clear error if no network; queued upload is out-of-scope MVP.

**Prompt sketch (vision):**
- System: plant pathologist, return ONLY JSON `{plant_guess, health, care_actions[]}`, short steps, locale-aware, no dosage beyond label, ask for clearer photo if low confidence.

### 4.3 Acceptance criteria
- [ ] Leaf photo returns Indian name + disease guess + steps in en/hi/gu.
- [ ] Groq outage → Cerebras result with `provider_used: cerebras` (tested via mock).
- [ ] Non-plant image handled gracefully; no crash.
- [ ] Scan history persists per user; images served via `/uploads` auth-consistent.
- [ ] Tests: provider fallback, parser, size/type guards, history isolation.

---

## 5. Cross-cutting concerns (all tasks)

- **Keys & config**: add `GROQ_API_KEY/MODEL, CEREBRAS_API_KEY/MODEL, DEFAULT_LANGUAGE` to `.env.example` + `config.example.yml` + `SettingsPage` integrations section + `generate-secrets.sh` prompt (docs only, no secret values in repo). Temporary Groq key provided 2026-09-14 is for local/dev use only — set via `export GROQ_API_KEY=...` or user Setting at build time, never committed, never logged. Same `_resolve_api_key` + demo-block pattern as Perenual/Anthropic.
- **Demo/kiosk**: demo users use own keys; server keys hidden; chat/scan rate-limited stricter for demo.
- **MCP**: expose `scan_plant` + `chat_ask` tools later (phase 6).
- **A11y + mobile**: Devanagari/Gujarati font sizes, camera permissions, bottom-nav chat entry.
- **Observability**: provider_used + latency + lang logged (no PII/images), `/dev/trigger-*` style dev helpers for chat/scan when `DEV_MODE=true`.
- **Dependency pinning**: all new Python/npm/Docker deps pinned exactly (per `CLAUDE.md`).

---

## 6. Phases (build order — each phase shippable)

### Phase 0 — Foundations & docs (0.5–1 day) ✅ done 2026-09-14
- [x] This file + `SHIVANSH_CHANGELOG.md` + `EXPLANATION.md`.
- [x] File locations locked (no new top-level folders):
  - Catalogue + knowledge: `backend/data/indian_plants.json`, `backend/data/plant_knowledge.md` (Phase 5), loader `backend/data/__init__.py` + `backend/data/indian_plants.py`.
  - Backend: `backend/routes/chat.py`, `backend/routes/scan.py`, `backend/ai/providers.py`, `backend/ai/agent.py`, `backend/ai/vision.py`, `backend/models/chat.py`, `backend/models/plant_scan.py` (no `indian_plant.py` table — JSON-only MVP, Latin stays join key).
  - Frontend: `frontend/src/i18n.js`, `frontend/src/locales/{en,hi,gu}.json`, `frontend/src/api/chat.js`, `frontend/src/api/scan.js`, `frontend/src/pages/ChatPage.jsx`, `frontend/src/pages/ScanPage.jsx`, `frontend/src/components/ChatWidget.jsx`.
  - Tests: `backend/tests/test_indian_catalogue.py`, `test_chat.py`, `test_scan.py`.
- [x] Groq/Cerebras models pinned + verified 2026-09-14 from official docs:
  - Groq base `https://api.groq.com/openai/v1` — chat+vision `meta-llama/llama-4-scout-17b-16e-instruct` (alt `qwen/qwen3.6-27b`), JSON mode + tool use, 5 images.
  - Cerebras base `https://api.cerebras.ai/v1` — chat `qwen-3.8-27b` (`reasoning_effort=none`), vision `gemma-4-31b` (base64 data-URI only, no external URLs; fallback `qwen-3.8-27b`).
- [x] `.env.example` + `backend/.env.example` + `config.example.yml` placeholders added (no keys). Temp Groq key kept out of repo, for local/dev env only.

### Phase 1 — Indian names catalogue + API category ✅ done 2026-09-14
- Backend:
  - [x] `backend/data/indian_plants.json` (62 entries) + loader `backend/data/indian_plants.py` (JSON-only, no DB table — Latin stays join key).
  - [x] Extended `SpeciesResult` (+ `indian_names, display_name, category, kind`), enriched in `routes/plants.py`.
  - [x] `GET /plants/categories`, `GET /plants/indian-catalogue`, `?lang=&category=&kind=` on search/detail, Wikipedia hi/gu fallback.
- Frontend:
  - [x] `AddPlantPage` + `PlantDetailPage` display_name first, filter chips, placeholder examples.
- Tests: [x] `backend/tests/test_indian_catalogue.py` (11 tests) + full suite 45 passed + `ruff check`/`format` clean.
- Done: §1.3 all checked. Review 2026-09-14: fixed `find_by_id` direct lookup (no 100-item cap), moved imports top-level, frontend copy neutralised, `PlantDetail` whitespace-tolerant match.

### Phase 2 — i18n EN→HI/GU (2–3 days, can overlap Phase 1 frontend)
- Add `i18next + react-i18next + detector` (pinned), `src/locales/{en,hi,gu}.json`, `src/i18n.js`, `api/client.js` language header.
- `SettingsPage` language switcher + `Setting.language` sync; key-parity script.
- Translate chrome first, then species/chat/scan strings as those phases land.
- Done when §3.3 passes.

### Phase 3 — AI provider layer: Groq primary + Cerebras fallback (1–2 days)
- `backend/ai/providers.py`: `GroqProvider + CerebrasProvider` (OpenAI-compatible), `ProviderChain(primary=groq, fallback=cerebras)` with timeout + error classification.
- `backend/ai/care.py`: keep Anthropic/OpenAI for care JSON, add Groq/Cerebras for chat/vision; `CareAdvisor` untouched.
- Settings + env wiring + docs; mock-failure tests.
- Done when forced Groq failure yields Cerebras response.

### Phase 4 — Scan & detect (3–5 days, depends on Phase 1 + 3)
- `backend/routes/scan.py + ai/vision.py + models/plant_scan.py`, image preprocess, history endpoints, `POST /plants/scan` + apply action.
- Frontend scan modal/page + result card + save flows.
- Tests: fallback, guards, history.
- Done when §4.3 passes.

### Phase 5 — Chatbot agent (3–5 days, depends on Phase 2 + 3, benefits from Phase 1)
- `backend/routes/chat.py + ai/agent.py (incl. build_context RAG-lite) + models/chat.py`, tool-calling (read tools first), session persistence, rate limits.
- Curated `backend/data/plant_knowledge.md` (human-reviewed, versioned).
- Frontend `ChatPage + ChatWidget + api/chat.js`, streaming/polling MVP.
- Tests: tools, sessions, fallback, isolation + grounding test (agent names correct plant, refuses unknown plant).
- Done when §2.3 passes.

### Phase 6 — Polish, QA, release (1–2 days)
- MCP additions, kiosk/demo copy in hi/gu, docs (`README` + `docs/` updates), E2E (search→scan→chat→translate flow), pre-commit + pytest + vitest green, semantic-release notes.
- Update `SHIVANSH_CHANGELOG.md` to `Released`.

**Proposed new files (Phase 1 done, rest to be created in later phases):**
```
backend/data/indian_plants.json        ✅ Phase 1 (62 entries)
backend/data/indian_plants.py          ✅ Phase 1 (loader/search/enrich)
backend/data/__init__.py               ✅ Phase 1
backend/data/plant_knowledge.md        ⏳ Phase 5
backend/routes/chat.py                 ⏳ Phase 5
backend/routes/scan.py                 ⏳ Phase 4
backend/ai/providers.py                ⏳ Phase 3
backend/ai/agent.py                    ⏳ Phase 5
backend/ai/vision.py                   ⏳ Phase 4
backend/models/chat.py                 ⏳ Phase 5
backend/models/plant_scan.py           ⏳ Phase 4
backend/tests/test_indian_catalogue.py ✅ Phase 1 (11 tests)
backend/tests/test_chat.py             ⏳ Phase 5
backend/tests/test_scan.py             ⏳ Phase 4
frontend/src/i18n.js                   ⏳ Phase 2
frontend/src/locales/en.json           ⏳ Phase 2
frontend/src/locales/hi.json           ⏳ Phase 2
frontend/src/locales/gu.json           ⏳ Phase 2
frontend/src/api/chat.js               ⏳ Phase 5
frontend/src/api/scan.js               ⏳ Phase 4
frontend/src/pages/ChatPage.jsx        ⏳ Phase 5
frontend/src/pages/ScanPage.jsx        ⏳ Phase 4
frontend/src/components/ChatWidget.jsx ⏳ Phase 5
```

> Note: earlier drafts listed `backend/models/indian_plant.py` (DB table). Phase 1 review decision: JSON-only MVP, no table — Latin `scientific_name` is the join key, so no migration risk. A table can be revisited in Phase 6 if admin CRUD is needed.

---

## 7. Risks & open questions
- Groq/Cerebras vision support changes fast — verify model IDs + image_url support at Phase 3 start; keep fallback honest.
- Transliteration collisions — keep alias list, prefer catalogue priority sort.
- Hindi/Gujarati translation quality — needs human review, not raw MT.
- Camera + PWA on iOS/Android — test early in Phase 4.
- Perenual 100/day limit — catalogue-first path mitigates.

---

## 8. Build log
- 2026-09-14 docs: analysis + planning files only (no code).
- 2026-09-14 Phase 0: models pinned (Groq scout / Cerebras qwen-3.8 + gemma-4), env placeholders, file locations locked.
- 2026-09-14 Phase 1: catalogue (62 entries) + enriched API + frontend display + 10 new tests (44 total green). Temporary Groq key remembered privately, never stored in repo. Phases 2–6 not started.
