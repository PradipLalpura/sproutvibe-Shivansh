# SHIVANSH CHANGELOG

> Fork-specific tracker for `sproutvibe-Shivansh` custom work.
> Upstream releases remain in `CHANGELOG.md` (semantic-release, do not edit manually).
> Format: Keep a Changelog + Semantic Versioning. Dates in UTC (YYYY-MM-DD).

## [Unreleased]

### Added (docs only, 2026-09-14)
- `EXPLANATION.md`: viva-ready human explanation (what was done, 4 tasks in plain words, RAG-lite choice, Groq→Cerebras fallback, 2-minute demo script, file map, Q&A). Intentionally distinct from this changelog.
- RAG/context decision recorded in `IDEATION_AND_PHASES.md` §2.2b: RAG-lite via `build_context()` (plants + schedules + journals + catalogue + last scan + `plant_knowledge.md`), no vector DB for MVP, `sqlite-vec`/FTS5 as optional Phase 6 stretch.

### Planned
- **API-Category — Indian plants & seeds names**: `indian_plants` catalogue (hindi/gujarati + transliteration, `category`, `kind: plant|seed`), enrich `SpeciesResult` with `indian_names/display_name/category/kind`, `?lang=&category=&kind=` on search/detail, `GET /plants/categories`, `GET /plants/indian-catalogue`, Wikipedia hi/gu fallback. See `IDEATION_AND_PHASES.md` §1.
- **Chatbot (Agent)**: `POST/GET /chat/sessions*` with Groq primary + Cerebras fallback, tool-calling over own plants/schedules/species, `ChatPage + ChatWidget`, en/hi/gu replies. See `IDEATION_AND_PHASES.md` §2.
- **Translation en→hi/gu**: `i18next + react-i18next`, `src/locales/{en,hi,gu}.json`, Settings switcher + server `Setting.language` sync, `Accept-Language` / `?lang=` on species/chat/scan. See `IDEATION_AND_PHASES.md` §3.
- **Scan & detect (Groq + Cerebras fallback)**: `POST /plants/scan`, `PlantScan` history, vision JSON (`plant_guess/health/care_actions`), Indian-name enrichment, Scan UI with camera. See `IDEATION_AND_PHASES.md` §4.

### Changed
- None (planning only).

### Fixed
- None.

## [0.3.0] - 2026-09-14

### Added — Phase 2 (EN → HI/GU translation)
- `i18next==26.4.2 + react-i18next==17.0.14` (pinned exact; no detector package — 12-line custom detection: localStorage → navigator → en).
- `frontend/src/i18n.js` (sync resources, `normalizeLang`, `applyLanguage` + `<html lang>`), `src/hooks/useLanguage.js` (mirrors `useTheme`: local + `Setting.language` server sync + `auth:login` re-sync), `src/locales/{en,hi,gu}.json` (~150 human-reviewed keys, 9 sections).
- All 8 MVP screens translated + `LanguageSection` switcher (EN/हिं/ગુ) in Settings → Appearance; `Accept-Language` header on every API call; species search/detail/wiki default to stored lang; `date-fns` hi/gu locales for relative times and dates.
- No backend change needed (`/settings/` already generic key-value).
- **Tests**: `src/locales/__tests__/parity.test.js` (10 tests: exact key parity, no-empty, no-fallback render, plurals/interpolation, detector, persistence). Frontend suite: 21 passed, `eslint` 0 errors, `vite build` green.

### Notes
- Task-type data values (`water`, `fertilize`…) stay English (backend data, not UI chrome); journal bodies never auto-translated — deliberate.
- Next: Phase 3 Groq/Cerebras provider layer.

## [0.2.0] - 2026-09-14

### Added — Phase 0 + Phase 1
- **Phase 0**: Groq/Cerebras models pinned from official docs (Groq `meta-llama/llama-4-scout-17b-16e-instruct`, Cerebras `qwen-3.8-27b` chat / `gemma-4-31b` vision), placeholders in `.env.example` + `backend/.env.example` + `config.example.yml` (no keys), file locations locked in `IDEATION_AND_PHASES.md`.
- **Phase 1 — Indian catalogue**: `backend/data/indian_plants.json` (62 entries: Tulsi, Haldi, Methi, Palak, Ashwagandha…) + loader `backend/data/indian_plants.py` (transliteration-insensitive search, `display_name` per lang, category/kind). `SpeciesResult` extended (backward compatible), `GET /plants/species/search?q=&lang=&category=&kind=`, `GET /plants/categories`, `GET /plants/indian-catalogue`, `GET /plants/species/{id}?source=indian_catalogue&lang=`, Wikipedia hi/gu fallback.
- **Phase 1 — frontend**: `AddPlantPage` shows Indian name first + category/seed chips + filters, `PlantDetailPage` shows Hindi/Gujarati line; `api/plants.js` extended with defaults (old calls still work).
- **Tests**: `backend/tests/test_indian_catalogue.py` (11 tests: 3-script Tulsi, filters, validation, backward compat, catalogue detail). Full suite: 45 passed, `ruff check` + `ruff format` clean.

### Notes
- Temp Groq key (shared 2026-09-14) used for docs verification only — never committed.
- Next: Phase 2 i18n.

## [0.1.0] - 2026-09-14

### Added
- `IDEATION_AND_PHASES.md`: ideation + phased build plan for the 4 tasks (Indian names API, chatbot agent, hi/gu translation, Groq/Cerebras scan), grounded in current `backend/routes/plants.py`, `backend/ai/care.py`, `frontend/src/api/plants.js`.
- `SHIVANSH_CHANGELOG.md`: this file — fork changelog initialised, `Unreleased` section opened.

### Notes
- No code / dependency / migration / secret changes in this release. Docs only. Phases NOT executed per owner instruction.
- Temporary Groq key (shared 2026-09-14) remembered for future dev use only — never committed, to be supplied via env/Setting at build time.
- Next: Phase 0 close-out (verify Groq/Cerebras vision model IDs, `.env.example` placeholders), then Phase 1 catalogue.
