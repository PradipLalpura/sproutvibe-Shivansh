# SHIVANSH CHANGELOG

> Fork-specific tracker for `sproutvibe-Shivansh` custom work.
> Upstream releases remain in `CHANGELOG.md` (semantic-release, do not edit manually).
> Format: Keep a Changelog + Semantic Versioning. Dates in UTC (YYYY-MM-DD).

## [Unreleased]

### Planned
- **API-Category — Indian plants & seeds names**: `indian_plants` catalogue (hindi/gujarati + transliteration, `category`, `kind: plant|seed`), enrich `SpeciesResult` with `indian_names/display_name/category/kind`, `?lang=&category=&kind=` on search/detail, `GET /plants/categories`, `GET /plants/indian-catalogue`, Wikipedia hi/gu fallback. See `IDEATION_AND_PHASES.md` §1.
- **Chatbot (Agent)**: `POST/GET /chat/sessions*` with Groq primary + Cerebras fallback, tool-calling over own plants/schedules/species, `ChatPage + ChatWidget`, en/hi/gu replies. See `IDEATION_AND_PHASES.md` §2.
- **Translation en→hi/gu**: `i18next + react-i18next`, `src/locales/{en,hi,gu}.json`, Settings switcher + server `Setting.language` sync, `Accept-Language` / `?lang=` on species/chat/scan. See `IDEATION_AND_PHASES.md` §3.
- **Scan & detect (Groq + Cerebras fallback)**: `POST /plants/scan`, `PlantScan` history, vision JSON (`plant_guess/health/care_actions`), Indian-name enrichment, Scan UI with camera. See `IDEATION_AND_PHASES.md` §4.

### Changed
- None (planning only).

### Fixed
- None.

## [0.1.0] - 2026-09-14

### Added
- `IDEATION_AND_PHASES.md`: ideation + phased build plan for the 4 tasks (Indian names API, chatbot agent, hi/gu translation, Groq/Cerebras scan), grounded in current `backend/routes/plants.py`, `backend/ai/care.py`, `frontend/src/api/plants.js`.
- `SHIVANSH_CHANGELOG.md`: this file — fork changelog initialised, `Unreleased` section opened.

### Notes
- No code / dependency / migration / secret changes in this release. Docs only.
- Next: Phase 0 close-out (verify Groq/Cerebras vision model IDs, `.env.example` placeholders), then Phase 1 catalogue.
