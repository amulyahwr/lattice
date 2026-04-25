# Lattice Frontend — Demo UI

**Goal:** A polished demo that makes enterprise CTOs and AI leads say *"we need this."*

---

## 1. The Demo Story (5-Minute Flow)

The frontend is designed around a scripted demo narrative:

### Act 1: "Here's your enterprise knowledge" (30s)
→ **Sources page.** Upload a few PDFs (financial report, engineering runbook, HR policy). Show the compiler atomizing them in real-time — raw doc goes in, typed atoms come out. The audience sees: *this isn't just chunking, it's understanding.*

### Act 2: "Here are your agents" (30s)
→ **Agents page.** Create two agents: "Sales Assistant" (clearance: sales + finance) and "Engineering Bot" (clearance: engineering). Each gets a role bitmask. The audience sees: *agents have identity, not just API keys.*

### Act 3: "Same question, different context" (60s) ⭐ THE AHA MOMENT
→ **Context Playground.** Type a query like "What's our Q2 outlook?" Run it as Sales Assistant — gets financial atoms, pipeline metrics. Run it as Engineering Bot — gets infra stability atoms, deployment metrics. Same query, completely different context. Show the latency: L2 cache hit at 3ms vs first-time L3 at 45ms. The audience sees: *right context, right agent, right speed.*

### Act 4: "Full visibility" (60s)
→ **Dashboard.** Atom counts, frame stats, cache hit rates, access audit trail. Click an atom → see its links, source lineage, which agents accessed it. The audience sees: *enterprise-grade observability, not a black box.*

### Act 5: "The knowledge graph" (30s)
→ **Graph Explorer.** Interactive visualization of atoms and their relationships. Click a metric atom → see it linked to a decision, a person, a date. The audience sees: *structured knowledge, not a bag of vectors.*

---

## 2. Pages

### 2.1 Dashboard (`/`)

The landing page. At-a-glance health of the context engine.

```
┌─────────────────────────────────────────────────────────────────┐
│  LATTICE                                            [dark mode] │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐   │
│  │  1,247   │ │    38    │ │   12     │ │   94.2%          │   │
│  │  Atoms   │ │  Frames  │ │  Agents  │ │  Cache Hit Rate  │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────┐ ┌─────────────────────────┐   │
│  │  Atoms by Kind              │ │  Queries (last 24h)     │   │
│  │  ██████ fact (412)          │ │  ┌─────────────────┐    │   │
│  │  ████ metric (298)          │ │  │  ╱╲  ╱╲         │    │   │
│  │  ███ decision (187)         │ │  │ ╱  ╲╱  ╲  ╱╲    │    │   │
│  │  ██ relationship (156)      │ │  │╱        ╲╱  ╲╱  │    │   │
│  │  █ event (104)              │ │  └─────────────────┘    │   │
│  │  █ procedure (90)           │ │  L2: 340  L3: 22       │   │
│  └─────────────────────────────┘ └─────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Recent Activity                                        │   │
│  │  ● Sales-Bot queried "Q2 pipeline"     L2  3ms    12s  │   │
│  │  ● Eng-Bot queried "infra incidents"   L3  41ms   45s  │   │
│  │  ● Compiled: Q2-Report.pdf → 84 atoms         2m ago   │   │
│  │  ● HR-Bot access filtered: 12 atoms            5m ago  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Stats cards:** Total atoms, frames, agents, cache hit rate
**Charts:** Atoms by kind (bar), query volume over time (line) with L2/L3 breakdown
**Activity feed:** Real-time log of queries, compilations, access events

### 2.2 Sources (`/sources`)

Upload and manage data sources. Shows the compiler in action.

```
┌─────────────────────────────────────────────────────────────────┐
│  Sources                                      [+ Upload Source] │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  📄 Q2-Financial-Report.pdf                             │   │
│  │  Uploaded: 2m ago  │  84 atoms  │  3 frames             │   │
│  │  Domains: finance, sales  │  Classification: confidential│   │
│  │                                                         │   │
│  │  Compilation Summary:                                   │   │
│  │  ┌────────┬────────┬─────────┬────────┬──────┬───────┐  │   │
│  │  │Atomize │Distill │ Embed   │ Link   │ Tag  │ Index │  │   │
│  │  │  ✅    │  ✅    │   ✅    │  ✅    │  ✅  │  ✅   │  │   │
│  │  │ 1.2s   │ 3.4s   │  0.8s   │ 1.1s   │0.2s  │ 0.3s │  │   │
│  │  └────────┴────────┴─────────┴────────┴──────┴───────┘  │   │
│  │                                                         │   │
│  │  Atoms extracted:                                       │   │
│  │  fact(32) metric(28) decision(12) relationship(8) ...   │   │
│  │                                          [View Atoms →] │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  📄 Engineering-Runbook.pdf                             │   │
│  │  Uploaded: 1h ago  │  156 atoms  │  5 frames            │   │
│  │  Domains: engineering  │  Classification: internal       │   │
│  │                                          [View Atoms →] │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Upload:** Drag-and-drop zone with progress
**Compiler pipeline:** Visual stage indicator (atomize → distill → embed → link → tag → index) with per-stage timing
**Source cards:** Name, atom count, frames generated, domains, classification
**Atom preview:** Expandable list of atoms generated from each source

### 2.3 Agents (`/agents`)

Register and manage agent profiles.

```
┌─────────────────────────────────────────────────────────────────┐
│  Agents                                       [+ Create Agent]  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌───────────────────────────┐ ┌───────────────────────────┐   │
│  │  🤖 Sales Assistant       │ │  🤖 Engineering Bot       │   │
│  │                           │ │                           │   │
│  │  Purpose:                 │ │  Purpose:                 │   │
│  │  Help sales team with     │ │  Assist engineers with    │   │
│  │  pipeline & forecasting   │ │  oncall & infra questions │   │
│  │                           │ │                           │   │
│  │  Domains: sales, finance  │ │  Domains: engineering     │   │
│  │  Token budget: 4,000      │ │  Token budget: 8,000      │   │
│  │                           │ │                           │   │
│  │  Access mask:             │ │  Access mask:             │   │
│  │  ██████░░ (sales+finance) │ │  ████░░░░ (engineering)   │   │
│  │                           │ │                           │   │
│  │  Stats:                   │ │  Stats:                   │   │
│  │  Queries: 142             │ │  Queries: 89              │   │
│  │  Avg latency: 4.2ms      │ │  Avg latency: 6.1ms       │   │
│  │  Cache hit: 96%           │ │  Cache hit: 91%           │   │
│  │                           │ │                           │   │
│  │  [Edit] [View Access Log] │ │  [Edit] [View Access Log] │   │
│  └───────────────────────────┘ └───────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Agent cards:** Purpose, domains, access mask visualization, usage stats
**Create modal:** Name, purpose, domains, role mask (checkboxes for department bits), token budget
**Access bitmask visualizer:** Shows which bits are set, maps to readable labels (sales, engineering, hr...)

### 2.4 Context Playground (`/playground`) ⭐ HERO PAGE

The demo killer. Side-by-side context comparison across agents.

```
┌─────────────────────────────────────────────────────────────────┐
│  Context Playground                                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Query: [What's our Q2 outlook?                    ] 🔍 │   │
│  │                                                         │   │
│  │  Run as:  [Sales Assistant ▼]  [Engineering Bot ▼]      │   │
│  │           [+ Add Agent Column]                          │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌────────────────────────┐ ┌──────────────────────────────┐   │
│  │ 🤖 Sales Assistant     │ │ 🤖 Engineering Bot           │   │
│  │ ⚡ L2 cache │ 3ms      │ │ ⚡ L3 search │ 41ms          │   │
│  │ 8 atoms │ 1,840 tokens │ │ 6 atoms │ 1,220 tokens      │   │
│  │ 2 filtered (no access) │ │ 5 filtered (no access)      │   │
│  │                        │ │                              │   │
│  │ ┌────────────────────┐ │ │ ┌──────────────────────────┐ │   │
│  │ │ 📊 metric          │ │ │ │ 📊 metric                │ │   │
│  │ │ EMEA Q2 pipeline:  │ │ │ │ Platform uptime Q2:      │ │   │
│  │ │ $4.2M (up 12%)     │ │ │ │ 99.97% (target: 99.95%) │ │   │
│  │ │ confidence: 0.94   │ │ │ │ confidence: 0.91         │ │   │
│  │ └────────────────────┘ │ │ └──────────────────────────┘ │   │
│  │                        │ │                              │   │
│  │ ┌────────────────────┐ │ │ ┌──────────────────────────┐ │   │
│  │ │ 📋 decision        │ │ │ │ 📋 fact                  │ │   │
│  │ │ Board approved     │ │ │ │ 3 P1 incidents in Q2,    │ │   │
│  │ │ EMEA expansion     │ │ │ │ all resolved < 4h MTTR   │ │   │
│  │ │ budget in April    │ │ │ │ confidence: 0.88         │ │   │
│  │ │ confidence: 0.89   │ │ │ └──────────────────────────┘ │   │
│  │ └────────────────────┘ │ │                              │   │
│  │                        │ │ ┌──────────────────────────┐ │   │
│  │ ┌────────────────────┐ │ │ │ 📋 decision              │ │   │
│  │ │ 📊 metric          │ │ │ │ Infra team prioritizing  │ │   │
│  │ │ Top 3 deals: Acme  │ │ │ │ K8s migration over new   │ │   │
│  │ │ ($800K), Globex    │ │ │ │ feature work in Q3       │ │   │
│  │ │ ($650K), Initech   │ │ │ │ confidence: 0.85         │ │   │
│  │ │ ($500K)            │ │ │ └──────────────────────────┘ │   │
│  │ └────────────────────┘ │ │                              │   │
│  │         ...            │ │          ...                 │   │
│  └────────────────────────┘ └──────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Performance Comparison                                 │   │
│  │  Sales Assistant: L2 hit │ 3ms  │ 8 atoms │ 1,840 tok  │   │
│  │  Eng Bot:         L3 hit │ 41ms │ 6 atoms │ 1,220 tok  │   │
│  │  Speedup: 13.6x (L2 vs L3)                             │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Query bar:** Natural language input + multi-agent selector
**Side-by-side columns:** Each agent's context results shown in parallel
**Atom cards:** Typed (color-coded by kind), show content + confidence + source link
**Performance bar:** Cache tier, latency, atom count, token count, filtered count per agent
**The punchline:** Same query, completely different — and appropriate — context

### 2.5 Atom Explorer (`/atoms`)

Browse, search, and inspect individual atoms.

```
┌─────────────────────────────────────────────────────────────────┐
│  Atom Explorer                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Search: [revenue growth              ] Kind: [All ▼] 🔍       │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  ATOM-a3f2 │ 📊 metric │ finance │ relevance: 0.94     │   │
│  │                                                         │   │
│  │  "EMEA Q2 pipeline stands at $4.2M, representing a     │   │
│  │   12% increase from Q1 driven by enterprise expansion"  │   │
│  │                                                         │   │
│  │  Source: Q2-Financial-Report.pdf                        │   │
│  │  Freshness: 2h ago │ Version: 3 │ TTL: 24h             │   │
│  │  Access: ██████░░ (sales, finance, executive)           │   │
│  │                                                         │   │
│  │  Links:                                                 │   │
│  │  → ATOM-b1c4 (decision) "Board approved EMEA expansion"│   │
│  │  → ATOM-d8e2 (metric) "Enterprise deal count: 14"      │   │
│  │  ← ATOM-f3a1 (event) "Q1 EMEA review meeting"         │   │
│  │                                                         │   │
│  │  Accessed by: Sales-Bot (42x), Exec-Bot (12x)          │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Search:** Semantic search across atoms with kind filter
**Atom detail:** Full content, metadata, source lineage, access mask, links to other atoms
**Link navigation:** Click a linked atom to navigate to it

### 2.6 Graph Explorer (`/graph`)

Interactive visualization of atom relationships.

```
┌─────────────────────────────────────────────────────────────────┐
│  Knowledge Graph                    [Filter: domain ▼] [Depth] │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│              ┌──────────┐                                       │
│         ┌───►│ $4.2M    │◄────┐                                 │
│         │    │ (metric) │     │                                  │
│         │    └──────────┘     │                                  │
│    has_value              has_value                              │
│         │                     │                                  │
│   ┌─────┴──────┐    ┌────────┴───────┐                          │
│   │ EMEA Q2    │    │ Enterprise     │                          │
│   │ Pipeline   │───►│ Expansion      │                          │
│   │ (fact)     │    │ (decision)     │                          │
│   └────────────┘    └────────┬───────┘                          │
│                         approved_by                              │
│                              │                                  │
│                      ┌───────▼──────┐                           │
│                      │ April Board  │                           │
│                      │ Meeting      │                           │
│                      │ (event)      │                           │
│                      └──────────────┘                           │
│                                                                 │
│  ── Selected: "EMEA Q2 Pipeline" ──────────────────────────┐   │
│  │ Kind: fact │ Domain: sales, finance                      │   │
│  │ 3 outgoing links │ 2 incoming links                      │   │
│  │ Accessed 54 times │ Last: 12m ago                        │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Interactive graph:** Force-directed layout, nodes colored by atom kind
**Filters:** By domain, kind, time range, access level
**Click interaction:** Select node → show detail panel, highlight connections
**Depth control:** 1-hop, 2-hop, 3-hop neighborhood

### 2.7 Audit Log (`/audit`)

Enterprise compliance view.

```
┌─────────────────────────────────────────────────────────────────┐
│  Audit Trail                    [Agent ▼] [Date Range] [Export] │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  TIME       AGENT            QUERY              RESULT    TIER  │
│  ─────────────────────────────────────────────────────────────  │
│  14:32:01   Sales-Bot        "Q2 pipeline"      8/10 ✓   L2    │
│  14:32:01   Sales-Bot        (2 atoms filtered — no access)     │
│  14:31:45   Eng-Bot          "infra incidents"   6/11 ✓   L3    │
│  14:31:45   Eng-Bot          (5 atoms filtered — no access)     │
│  14:30:12   HR-Bot           "hiring plan"       0/4  ✗   L3    │
│  14:30:12   HR-Bot           (4 atoms filtered — clearance)     │
│  ...                                                            │
│                                                                 │
│  Access Denied Breakdown (last 24h):                            │
│  ┌──────────────────────────────────┐                           │
│  │  Role mismatch:          67%    │                            │
│  │  Classification level:   28%    │                            │
│  │  Domain irrelevant:       5%    │                            │
│  └──────────────────────────────────┘                           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Tech Stack

| Layer | Choice | Why |
|-------|--------|-----|
| Framework | **React 19 + Vite** | Fast dev, ecosystem |
| Styling | **Tailwind CSS + shadcn/ui** | Clean enterprise look, no design system overhead |
| Charts | **Recharts** | Simple, React-native charting |
| Graph Viz | **React Flow** or **D3-force** | Interactive node graphs |
| State | **TanStack Query (React Query)** | API state management, caching, auto-refresh |
| Router | **React Router v7** | Standard routing |
| Icons | **Lucide React** | Clean, consistent iconography |

**No auth for MVP.** Demo assumes single-user / demo mode.

---

## 4. Project Structure

```
lattice/
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   │
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx                    # Router + layout
│   │   │
│   │   ├── api/
│   │   │   ├── client.ts             # Axios/fetch wrapper
│   │   │   ├── sources.ts            # Source API calls
│   │   │   ├── agents.ts             # Agent API calls
│   │   │   ├── context.ts            # Context query API calls
│   │   │   └── admin.ts              # Stats + frames API calls
│   │   │
│   │   ├── components/
│   │   │   ├── layout/
│   │   │   │   ├── Sidebar.tsx        # Navigation
│   │   │   │   ├── Header.tsx         # Top bar
│   │   │   │   └── Shell.tsx          # App shell wrapper
│   │   │   │
│   │   │   ├── atoms/
│   │   │   │   ├── AtomCard.tsx       # Single atom display (kind-colored)
│   │   │   │   ├── AtomList.tsx       # Scrollable atom list
│   │   │   │   ├── AtomDetail.tsx     # Full atom with links + metadata
│   │   │   │   └── AccessMask.tsx     # Bitmask visual (colored bars)
│   │   │   │
│   │   │   ├── compiler/
│   │   │   │   └── PipelineStatus.tsx # Stage progress indicator
│   │   │   │
│   │   │   ├── charts/
│   │   │   │   ├── AtomsByKind.tsx    # Bar chart
│   │   │   │   ├── QueryTimeline.tsx  # Line chart with L2/L3
│   │   │   │   └── CacheHitGauge.tsx  # Radial gauge
│   │   │   │
│   │   │   ├── graph/
│   │   │   │   └── GraphView.tsx      # Interactive atom graph
│   │   │   │
│   │   │   └── playground/
│   │   │       ├── QueryBar.tsx       # Search input + agent selector
│   │   │       ├── ResultColumn.tsx   # Single agent's results
│   │   │       └── PerfComparison.tsx # Latency/token comparison bar
│   │   │
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx
│   │   │   ├── Sources.tsx
│   │   │   ├── Agents.tsx
│   │   │   ├── Playground.tsx         # ⭐ Hero page
│   │   │   ├── AtomExplorer.tsx
│   │   │   ├── GraphExplorer.tsx
│   │   │   └── AuditLog.tsx
│   │   │
│   │   ├── hooks/
│   │   │   ├── useAtoms.ts
│   │   │   ├── useAgents.ts
│   │   │   ├── useSources.ts
│   │   │   └── useContextQuery.ts
│   │   │
│   │   └── lib/
│   │       ├── constants.ts           # Atom kind colors, labels
│   │       └── utils.ts               # Formatting helpers
│   │
│   └── public/
│       └── lattice-logo.svg
│
├── backend/
│   └── ...
```

---

## 5. Visual Design Language

### Color Palette

**Atom kind colors** (consistent everywhere — cards, graph nodes, charts):
| Kind | Color | Hex |
|------|-------|-----|
| fact | Blue | `#3B82F6` |
| metric | Emerald | `#10B981` |
| decision | Amber | `#F59E0B` |
| relationship | Purple | `#8B5CF6` |
| event | Rose | `#F43F5E` |
| procedure | Slate | `#64748B` |

**Cache tier colors:**
| Tier | Color | Label |
|------|-------|-------|
| L2 | Green | ⚡ Cache hit |
| L3 | Yellow | 🔍 Index search |

**Access mask:** Green bars for allowed bits, gray for unset. Hoverable to show role labels.

### Design Principles
- **Dark mode default** — enterprise AI products look better dark
- **Data-dense but not cluttered** — every pixel earns its place
- **Numbers front and center** — latency, atom counts, cache rates visible at a glance
- **Color = meaning** — atom kinds, cache tiers, access status all have consistent colors

---

## 6. API Endpoints the Frontend Needs

The frontend drives the backend API surface:

```
# Dashboard
GET  /v1/admin/stats              → atom count, frame count, agent count, cache hit rate
GET  /v1/admin/activity           → recent queries, compilations, access events

# Sources
POST /v1/sources/ingest           → upload + compile (returns compilation stats)
GET  /v1/sources                  → list sources with atom counts
GET  /v1/sources/{id}/atoms       → list atoms from a source

# Agents
POST /v1/agents                   → create agent with profile
GET  /v1/agents                   → list agents with stats
PATCH /v1/agents/{id}             → update profile
GET  /v1/agents/{id}/stats        → query count, avg latency, cache hit rate

# Context Playground
POST /v1/context/query            → query as agent → returns atoms + metadata
POST /v1/context/compare          → same query, multiple agents → parallel results

# Atom Explorer
GET  /v1/atoms                    → search/list atoms with filters
GET  /v1/atoms/{id}               → atom detail with links
GET  /v1/atoms/{id}/neighborhood  → linked atoms for graph view

# Audit
GET  /v1/audit/log                → paginated access log
GET  /v1/audit/stats              → access denied breakdown
```

---

## 7. MVP Frontend Scope

### Phase 1 (Demo-Ready)
- [x] Dashboard with stat cards + charts
- [x] Sources page (upload + compiler viz)
- [x] Agents page (create + cards)
- [x] **Context Playground** (the hero page)
- [x] Audit log (basic table)

### Phase 2 (Polish)
- [ ] Atom Explorer (search + detail view)
- [ ] Graph Explorer (interactive viz)
- [ ] Real-time activity feed (WebSocket)
- [ ] Export (PDF report of demo session)

---

*The Playground page is the product. Everything else supports it.*
