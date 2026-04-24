# Changelog

## Fixes & Improvements

### Backend
- **Fix:** `CREATE EXTENSION IF NOT EXISTS vector` wrapped with SQLAlchemy `text()` — raw strings are not executable in SQLAlchemy 2.x
- **Fix:** `DateTime` columns changed to `DateTime(timezone=True)` on all models — prevents `offset-naive vs offset-aware` asyncpg error on insert
- **Fix:** Duplicate grant protection in `POST /agents/{id}/grant` — returns `already_granted` instead of inserting a duplicate row
- **Feature:** `AgentResponse` now includes `source_ids: list[str]` — `GET /agents/` returns each agent's currently granted sources

### Frontend
- **Fix:** Installed `@tailwindcss/postcss` — required separately in Tailwind v4, was missing from `node_modules`
- **Fix:** Improved API error handling — `throwIfError()` extracts `detail` from FastAPI JSON errors instead of silently swallowing empty messages
- **Fix:** Create Agent button disabled when name field is empty, with loading state (`Creating...`) during request
- **Feature:** Agent cards in Agents tab show all sources as toggle buttons — indigo/checked when granted, grey/+ when not, click to revoke
- **Feature:** `revokeAccess` added to API client
- **Feature:** Search tab shows a yellow warning with a link to the Agents tab when the selected agent has no source access
