# Changelog

## Trust Broker — Computed Access, Source DNA & Agent Identity Profiles

### Backend — Access Resolution (`engine/access.py`) *(new)*
- **Feature:** Computed access resolution — agents no longer need manual per-source grants. Access is determined dynamically by clearance check + semantic match + domain overlap
- **Feature:** Classification hierarchy: `public < internal < confidential < restricted` — agent clearance must meet or exceed source classification
- **Feature:** Semantic matching — agent `purpose_embedding` compared against source `summary_embedding` via cosine similarity
- **Feature:** Domain overlap scoring — weighted 30% alongside semantic match (70%) for combined relevance
- **Feature:** Manual overrides — `grant` and `deny` overrides take priority over computed access. Deny blocks even if computed access would allow
- **Feature:** Full audit logging (`AccessLog` model) — every access decision logged with agent, source, query, decision, reason, and relevance score

### Backend — Source DNA
- **Feature:** Auto-generated extractive summary on PDF upload (`engine/summarize.py`) — no external LLM required
- **Feature:** Summary embedding stored for semantic matching against agent purposes
- **Feature:** Auto-suggested domain tags based on summary content (finance, engineering, legal, sales, etc.)
- **Feature:** Source classification field — defaults to `internal`, user can update
- **Feature:** Owner and `org_scope` fields on sources
- **Feature:** `PATCH /sources/{id}` — update source DNA (classification, domains, owner, org_scope)

### Backend — Agent Identity Profiles
- **Feature:** `purpose` field (required on create) — describes what the agent does
- **Feature:** Purpose embedding stored for semantic matching against source summaries
- **Feature:** `clearance`, `domains`, `org_scope`, `deployed_by` fields on agents
- **Feature:** `PATCH /agents/{id}` — update agent profile (re-embeds purpose on change)
- **Feature:** `POST /agents/{id}/deny` — manually deny an agent access to a source

### Backend — Recommendation Engine (`engine/recommendations.py`) *(new)*
- **Feature:** `GET /sources/{id}/recommendations` — which agents would benefit from a new source?
- **Feature:** `GET /agents/{id}/recommendations` — which existing sources are relevant to a new agent?
- **Feature:** Recommendations scored and ranked: `strong_match` (≥75%), `moderate_match` (≥50%), `weak_match` (≥20%), `needs_clearance_upgrade`
- **Feature:** `DELETE /agents/{id}/revoke/{source_id}` — remove manual override, revert to computed access

### Backend — Search Updates
- **Feature:** Search now uses computed access resolution instead of permission table lookups
- **Feature:** Search results include `source_classification` field
- **Feature:** Search response includes `agent_clearance` for the querying agent
- **Feature:** Access audit logged for every source returned in search results

### Frontend
- **Feature:** Agent creation form — purpose (required), clearance dropdown, domains (comma-separated), deployed by
- **Feature:** Source cards expandable — click to see DNA (summary, classification, domains, owner)
- **Feature:** Recommendations panel — appears automatically after uploading a source or creating an agent
- **Feature:** One-click grant from recommendation panel with match percentage and status badges
- **Feature:** Classification badges color-coded throughout (green=public, gray=internal, yellow=confidential, red=restricted)
- **Feature:** Domain badges on source and agent cards
- **Feature:** Sparkles button on sources and agents to manually trigger recommendations
- **Feature:** Search tab shows agent clearance level and purpose alongside results

---

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
