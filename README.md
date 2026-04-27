# Lattice

**Enterprise Context Layer** — Right context. Right time. Right agent.

Lattice is a context broker for AI agents. It sits between your enterprise knowledge (documents, databases, APIs, communication tools) and your AI agents, delivering the right context with the right permissions in milliseconds.

## Why Lattice?

Every enterprise deploying AI agents hits the same wall: agents are either **context-starved** (hallucinate, give generic answers) or **context-flooded** (slow, expensive, no access control). Lattice solves this.

| Problem                              | How Lattice Solves It                                                                        |
| ------------------------------------ | -------------------------------------------------------------------------------------------- |
| Agents get raw document chunks       | Lattice compiles knowledge into **atomic facts** — concise, typed, linked                    |
| Every query does expensive retrieval | Compiler does the heavy work at ingest; serving is **pgvector search (~50ms)**               |
| No access control on context         | **Bitmask access control** — every atom tagged, every agent profiled, checked in nanoseconds |
| Every team builds their own RAG      | **Single context layer** for all agents across the enterprise                                |
| No visibility into what agents see   | **Full audit trail** — every access decision logged for compliance                           |

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     ENTERPRISE DATA                     │
│  Confluence  Slack  Jira  Salesforce  DBs  APIs  Docs   │
└────────────────────────┬────────────────────────────────┘
                         │
                ┌────────▼─────────┐
                │    CONNECTORS    │   Pluggable source adapters
                └────────┬─────────┘
                         │
                ┌────────▼─────────┐
                │     COMPILER     │   Atomize → Distill → Embed → Link → Tag → Index → Cross-link
                └────────┬─────────┘
                         │
                ┌────────▼─────────┐
                │   ATOM STORE     │   PostgreSQL + pgvector
                └────────┬─────────┘
                         │
                ┌────────▼─────────┐
                │   SERVING (L3)   │   Query → Embed → pgvector search → Bitmask filter → Return
                └────────┬─────────┘
                         │
           ┌─────────────┼─────────────┐
           ▼             ▼             ▼
       Agent A       Agent B       Agent N
       (Sales)       (Eng)        (Custom)
```

### Key Concepts

- **Context Atoms** — The smallest meaningful unit of knowledge. Not document chunks — discrete facts, decisions, metrics, relationships. Each atom is typed, distilled, embedded, access-tagged, and linked to related atoms.
- **Compiler Pipeline** — Ingested content goes through: Atomize → Distill → Embed → Link → Tag → Index → Cross-link. Heavy work happens once at ingest, not at query time.
- **Bitmask Access Control** — Every atom carries an access mask. Every agent carries a role mask. Access check: `role_mask & access_mask != 0`. One CPU instruction.
- **Cross-Source Linking** — The compiler automatically finds and links related atoms across different sources using domain-aware similarity search.
- **Data Residency** — Lattice is a broker, not a data lake. Source data stays where it lives. Lattice stores only compiled atoms, embeddings, and metadata.

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL with pgvector extension

### Backend

```bash
# Start Postgres with pgvector
docker compose up db -d

# Install Python deps
cd lattice
pip install -e ".[dev]"

# Run the API server
uvicorn backend.main:app --reload --port 8001
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

- **Frontend:** http://localhost:5173
- **Backend API:** http://localhost:8001
- **API Docs:** http://localhost:8001/docs

## Demo

### The Killer Demo: Context Playground

Type a query like _"What's our Q2 outlook?"_ and run it as two different agents:

| Sales Assistant                     | Engineering Bot                  |
| ----------------------------------- | -------------------------------- |
| EMEA Q2 pipeline: $4.2M, up 12%     | Platform uptime Q2: 99.97%       |
| Board approved EMEA expansion       | 3 P1 incidents, all resolved <4h |
| Top deals: Acme $800K, Globex $650K | K8s migration prioritized for Q3 |
| 🔍 **47ms**, 8 atoms                | 🔍 **41ms**, 6 atoms             |

**Same question. Completely different — and appropriate — context.** Each agent only sees what it's allowed to see.

## API

All endpoints at `/api/v1/`:

### Ingestion

| Method | Endpoint              | Description                              |
| ------ | --------------------- | ---------------------------------------- |
| POST   | `/sources/ingest`     | Upload and compile a document into atoms |
| GET    | `/sources/`           | List all sources with atom counts        |
| GET    | `/sources/{id}/atoms` | List atoms from a source                 |
| DELETE | `/sources/{id}`       | Delete a source and its atoms            |

### Context Query

| Method | Endpoint           | Description                                        |
| ------ | ------------------ | -------------------------------------------------- |
| POST   | `/context/query`   | Query context as an agent (L3 vector search)       |
| POST   | `/context/compare` | Same query, multiple agents — side-by-side results |

### Agents

| Method | Endpoint             | Description                                |
| ------ | -------------------- | ------------------------------------------ |
| POST   | `/agents/`           | Register an agent with profile + role mask |
| GET    | `/agents/`           | List agents with stats                     |
| PATCH  | `/agents/{id}`       | Update agent profile                       |
| GET    | `/agents/{id}/stats` | Per-agent performance stats                |
| DELETE | `/agents/{id}`       | Delete an agent                            |

### Atoms & Graph

| Method | Endpoint                    | Description                              |
| ------ | --------------------------- | ---------------------------------------- |
| GET    | `/atoms/graph`              | Full knowledge graph (atoms + links)     |
| GET    | `/atoms/{id}/neighborhood`  | Single atom neighborhood (1-hop)         |

### Admin & Audit

| Method | Endpoint          | Description                                 |
| ------ | ----------------- | ------------------------------------------- |
| GET    | `/admin/stats`    | Atom/agent/source counts                    |
| GET    | `/admin/activity` | Recent queries, compilations, access events |
| POST   | `/admin/relink`   | Re-run cross-source linking across all atoms|
| GET    | `/audit/log`      | Paginated access audit log                  |
| GET    | `/audit/stats`    | Access denied breakdown                     |

## Tech Stack

### Backend

- **FastAPI** — async Python API framework
- **PostgreSQL + pgvector** — atom storage + vector similarity search
- **SQLAlchemy** (async) — ORM
- **sentence-transformers** — embedding generation (384-dim)
- **tiktoken** — accurate token counting

### Frontend

- **React 19** + TypeScript + Vite
- **Tailwind CSS** + shadcn/ui
- **React Flow** — interactive knowledge graph visualization
- **Recharts** — charts and visualizations
- **TanStack Query** — API state management
- **React Router v7** — routing

## Project Structure

```
lattice/
├── backend/
│   ├── compiler/          # Atomize → Distill → Embed → Link → Tag → Index → Cross-link
│   ├── serving/           # Query router, L3 vector search
│   ├── connectors/        # PDF, Text/Markdown (more coming)
│   ├── models/            # Atom, AgentProfile, Source, AccessLog
│   ├── engine/            # Embedding generation
│   └── api/               # REST endpoints (ingest, context, agents, admin, audit)
│
├── frontend/
│   └── src/
│       ├── pages/         # Dashboard, Sources, Agents, Playground, Audit, AtomExplorer
│       ├── components/    # AtomCard, AccessMask, PipelineStatus, QueryBar, AtomGraph, etc.
│       ├── hooks/         # TanStack Query hooks
│       └── api/           # API client
│
├── ARCHITECTURE.md        # Full system architecture
├── ROADMAP.md             # Phase 1–5 feature roadmap
```

## Roadmap

| Phase               | Focus                                                                              | Status      |
| ------------------- | ---------------------------------------------------------------------------------- | ----------- |
| **1: MVP**          | Atom model, compiler pipeline, L3 serving, bitmask access control, demo UI        | ✅ Complete |
| **2: Production**   | Temporal knowledge layer, graph-traversal serving, agent session memory, async compiler | 📋 Planned  |
| **3: Enterprise**   | Push/streaming, event bus, Confluence/Slack/Jira connectors, observability        | 📋 Planned  |
| **4: Scale**        | Multi-tenancy, distributed store, gRPC, Python/TS SDKs, GDPR controls             | 📋 Planned  |
| **5: Intelligence** | Feedback loops, predictive pre-warming, cross-domain insights                     | 💡 Vision   |

See [ROADMAP.md](./ROADMAP.md) for details.

## Documentation

- [ARCHITECTURE.md](./ARCHITECTURE.md) — System architecture, data model, compiler pipeline, serving layer
- [ROADMAP.md](./ROADMAP.md) — Phase 1–5 feature roadmap

## License

MIT
