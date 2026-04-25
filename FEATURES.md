# Lattice — Feature Walkthrough

Use this as a demo script. Each section is a self-contained feature you can show.

---

## 1. Upload a Data Source

**Where:** Sources tab → "Upload PDF" button

**What happens:**
- Upload any PDF → Lattice extracts text, splits into chunks, generates embeddings
- Auto-generates a **summary** of the document (no LLM needed — runs locally)
- Auto-suggests **domain tags** based on content (finance, engineering, legal, etc.)
- Assigns a default **classification** (internal)

**Demo tip:** Upload 2-3 different PDFs (a financial report, a technical doc, a legal contract) to show domain diversity.

---

## 2. Source DNA

**Where:** Sources tab → click any source to expand

**What it shows:**
- **Summary** — auto-generated from document content
- **Classification** — public / internal / confidential / restricted
- **Domains** — auto-tagged topics
- **Owner** and **Org Scope**
- **Edit DNA** button to update any field

**Key message:** Every source carries its own identity. Lattice knows what the data is about.

---

## 3. Create an Agent

**Where:** Agents tab → "Create Agent" form

**Required fields:**
- **Name** — what to call the agent
- **Purpose** — what this agent does (this is the key field)
- **Clearance** — max classification level it can access
- **Domains** — what topics it works with

**What happens:** Lattice embeds the purpose for semantic matching, then immediately shows **recommendations** for which existing sources are relevant.

**Demo tip:** Create a "FinanceBot" with purpose "Analyze financial data and generate revenue insights" and clearance "confidential" — watch it recommend finance-related sources.

---

## 4. Smart Recommendations

**Where:** Appears automatically after uploading a source or creating an agent. Also via ✨ sparkle button on any source or agent.

**How it works:**
- Computes **semantic similarity** between agent purpose and source summary (70% weight)
- Checks **domain overlap** (30% weight)
- Verifies **clearance level** — agent must have sufficient clearance
- Ranks results: 🟢 strong match (≥75%) / 🟡 moderate (≥50%) / ⚪ weak (≥20%) / 🔴 needs clearance upgrade

**Key message:** Lattice understands which agents need which data and proactively recommends — no manual hunting.

---

## 5. Human-in-the-Loop Approval

**Where:** Recommendations panel (appears on Sources, Agents, or Map tabs)

**Features:**
- Each recommendation has a **checkbox** — select individually
- **Select all** checkbox at the top — one click to select everything
- **"Approve N"** button — batch approve all selected
- Recommendations that need a clearance upgrade shown but **not selectable**

**Key message:** Lattice recommends, humans decide. No auto-access. Full control.

---

## 6. Revoke Access

**Where:** Available on every tab

- **Map tab** — click a node, hover a granted connection in the side panel → "Revoke"
- **Sources tab** — expand a source, see "Agents with Access" list, hover → "Revoke"
- **Agents tab** — agent card shows "Granted Sources" list, hover → "Revoke"

**Key message:** Granting is easy, revoking is just as easy. Access is always reviewable.

---

## 7. Lattice Map

**Where:** Map tab (default view)

**What it shows:**
- **Visual graph** of all agents and sources
- **Solid lines** = granted access
- **Circles** = sources (colored by classification)
- **Rounded rectangles** = agents (colored by clearance)
- Node **size** reflects chunk count (sources) or grant count (agents)
- Nodes **cluster by domain** — finance nodes near finance nodes

**Interactions:**
- **Hover** a node → connections highlight, everything else dims
- **Click** a node → side panel with full details, connections, and recommendations
- **Approve** recommendations directly from the map
- **Revoke** access directly from the map
- **Drag** nodes to rearrange, scroll to zoom

**Demo tip:** This is the "wow" moment. Show the map, hover over a node, watch the graph light up, click to see the side panel, approve a recommendation and watch the line appear.

---

## 8. Search with Access Control

**Where:** Search tab

**How it works:**
1. Select an agent from the dropdown
2. Type a natural language query
3. Lattice searches **only the sources that agent has been granted access to**
4. Returns ranked results with relevance scores and source attribution

**What to demonstrate:**
- Search as FinanceBot → sees finance sources
- Search as EngineeringBot → sees engineering sources, NOT finance
- Same query, different agents, different results

**Key message:** Access control isn't bolted on — it's embedded in the query. An agent literally cannot see data it hasn't been granted.

---

## 9. Classification & Clearance

**How it works:**
- Sources have a **classification**: public → internal → confidential → restricted
- Agents have a **clearance**: same scale
- Agent clearance must **meet or exceed** source classification
- If a source is "confidential" and an agent only has "internal" clearance → recommendation shows "needs clearance upgrade" and can't be approved

**Demo tip:** Create a restricted source and show that a low-clearance agent can't be granted access to it.

---

## 10. Edit Everything

**Where:** Sources tab (expand → Edit DNA) and Agents tab (Edit Profile)

**What you can edit:**
- Source: classification, domains, owner, org scope
- Agent: purpose, clearance, domains, deployed by, org scope

**What happens on edit:**
- Updating an agent's **purpose** re-generates its embedding → changes which sources are recommended
- Updating a source's **classification** → may affect which agents can access it

---

## Architecture (if asked)

```
Frontend (React + Vite)
    ↓
Agent API (FastAPI) — REST + API key auth
    ↓
Context Engine — Vector search (pgvector)
    ↓
Connector Framework — Pluggable (PDF built, more coming)
    ↓
Postgres + pgvector — Unified storage
```

**What makes Lattice different:**
- Sources and agents **understand each other** via semantic matching
- Access is **recommended by AI, approved by humans**
- No manual permission wiring — the system does the matching
- Full **audit trail** of every access decision

---

## Roadmap (what's next)

- [ ] Knowledge Graph — relationship-aware retrieval
- [ ] More connectors — Postgres tables, Gmail, Snowflake, Notion
- [ ] Audio/video modality support
- [ ] Auto-grant mode — for trusted environments
- [ ] Timeline view — see how access evolved over time
- [ ] Policy engine — declarative access rules (allow/deny by tag, connector, org)
