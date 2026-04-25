# Changelog

## Lattice Map, Revoke Access & Light Theme

### Frontend — Lattice Map *(new tab)*
- **Feature:** Force-directed graph visualization of all agents and sources
- **Feature:** Sources shown as circles (sized by chunk count, colored by classification)
- **Feature:** Agents shown as rounded rects (sized by grant count, colored by clearance)
- **Feature:** Solid indigo lines for granted access, dashed pulsing lines for recommendations
- **Feature:** Domain-based spatial clustering — nodes with shared domains gravitate together
- **Feature:** Hover any node → connected nodes highlight, unrelated nodes dim, glow effect
- **Feature:** Click any node → side panel with full DNA/profile, granted connections, and ranked recommendations
- **Feature:** Approve recommendations directly from the map side panel
- **Feature:** Revoke granted access from the map side panel (hover connection → Revoke)
- **Feature:** Drag nodes to rearrange, zoom/pan the canvas
- **Feature:** Legend with node types, link types, and classification colors

### Frontend — Revoke Access (everywhere)
- **Feature:** Map side panel — hover a granted connection → Revoke button appears
- **Feature:** Sources tab — expanded source shows "Agents with Access" list, hover → Revoke
- **Feature:** Agents tab — agent cards show "Granted Sources" list, hover → Revoke
- **Feature:** Recommendations auto-filter out already-granted pairs (no duplicate approvals)

### Frontend — Light Theme
- **Change:** Entire app switched from dark to warm light theme (`#faf5f0` base)
- **Change:** Cards use white backgrounds with `stone-200` borders
- **Change:** Badges use light tints (indigo-100, emerald-100, amber-100, red-100)
- **Change:** Map canvas uses warm radial gradient with white-filled nodes
- **Change:** All text updated to stone palette for readability

---

## Human-in-the-Loop Access Control & UI Improvements

### Backend — Access Model Change
- **Breaking:** Search no longer uses computed access. Agents can ONLY search sources they have been explicitly granted access to via the permissions table
- **Change:** Computed access (semantic match + clearance + domains) is now used exclusively for **recommendations**, not for search-time access resolution
- **Feature:** `DELETE /agents/{agent_id}` — delete an agent and cascade-delete all its permissions

### Frontend — Recommendation Approval Flow
- **Feature:** Recommendations ranked by relevance score (highest first) with visual score bars
- **Feature:** Checkbox per grantable recommendation — select which to approve individually
- **Feature:** Select-all checkbox — toggles all grantable recommendations at once
- **Feature:** Batch approve button — "Approve N" grants all selected in one action
- **Feature:** Non-grantable recommendations (clearance issues) shown without checkbox

### Frontend — Source & Agent Management
- **Feature:** Edit Source DNA inline (classification, domains, owner, org scope)
- **Feature:** Edit Agent Profile inline (purpose, clearance, domains, deployed by, org scope)
- **Feature:** Delete Agent — trash icon, removes agent and all permissions

---

## Trust Broker — Computed Access, Source DNA & Agent Identity Profiles

### Backend — Access Resolution (`engine/access.py`)
- **Feature:** Computed access resolution for recommendations — clearance + semantic match + domain overlap
- **Feature:** Classification hierarchy: `public < internal < confidential < restricted`
- **Feature:** Semantic matching — agent purpose vs source summary via cosine similarity
- **Feature:** Domain overlap scoring — weighted 30% alongside semantic match (70%)
- **Feature:** Manual overrides — grant/deny take priority over computed access
- **Feature:** Full audit logging (`AccessLog` model)

### Backend — Source DNA
- **Feature:** Auto-generated extractive summary on PDF upload — no external LLM required
- **Feature:** Summary embedding for semantic matching against agent purposes
- **Feature:** Auto-suggested domain tags from content
- **Feature:** Classification, owner, org_scope fields
- **Feature:** `PATCH /sources/{id}` — update source DNA

### Backend — Agent Identity Profiles
- **Feature:** Purpose field (required) with embedded vector for semantic matching
- **Feature:** Clearance, domains, org_scope, deployed_by fields
- **Feature:** `PATCH /agents/{id}` — update profile (re-embeds purpose)
- **Feature:** `POST /agents/{id}/deny` — manual deny override

### Backend — Recommendation Engine (`engine/recommendations.py`)
- **Feature:** `GET /sources/{id}/recommendations` — agent recommendations for a source
- **Feature:** `GET /agents/{id}/recommendations` — source recommendations for an agent
- **Feature:** Scored and ranked: strong_match ≥75%, moderate ≥50%, weak ≥20%, needs_clearance_upgrade

### Backend — Search
- **Feature:** Results include source classification and agent clearance
- **Feature:** Access audit logged for every search result

---

## Fixes & Improvements

### Backend
- **Fix:** `text()` wrapper on pgvector extension SQL for SQLAlchemy 2.x
- **Fix:** `DateTime(timezone=True)` on all models — prevents asyncpg naive/aware mismatch
- **Fix:** Duplicate grant protection — idempotent grants
- **Feature:** `AgentResponse` includes `source_ids`

### Frontend
- **Fix:** `@tailwindcss/postcss` installed for Tailwind v4
- **Fix:** API error handling extracts FastAPI `detail` field
- **Fix:** Create Agent button disabled/loading states
- **Feature:** `revokeAccess` API client method
