# Lattice

Enterprise contextual layer for unifying structured, unstructured, and multi-modal data sources.

## What is Lattice?

Lattice gives AI agents the right context at the right time. Connect your data sources — PDFs, databases, and more — and let agents query across all of them through a single API with built-in access control.

## Architecture

```
┌─────────────────────────────┐
│   Frontend (React + Vite)   │  ← Visual demo UI
├─────────────────────────────┤
│   Agent API (FastAPI)       │  ← REST + API key auth
├─────────────────────────────┤
│   Context Engine            │  ← Vector search (KG coming)
├─────────────────────────────┤
│   Connector Framework       │  ← Pluggable data adapters
├─────────────────────────────┤
│   Postgres + pgvector       │  ← Storage
└─────────────────────────────┘
```

## Quick Start

### With Docker Compose (recommended)

```bash
docker compose up --build
```

- **Frontend:** http://localhost:5173
- **Backend API:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs

### Local Development

**Backend:**

```bash
# Start Postgres with pgvector
docker compose up db -d

# Install Python deps
pip install -e ".[dev]"

# Run the API server
uvicorn backend.main:app --reload
```

**Frontend:**

```bash
cd frontend
npm install
npm run dev
```

## Usage

1. **Upload a PDF** → Sources tab → Upload PDF
2. **Create an agent** → Agents tab → name it, get an API key
3. **Grant access** → Agents tab → grant the agent access to your source
4. **Search** → Search tab → select agent, ask a question

## API

All endpoints at `/api/v1/`:

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/sources/upload/pdf` | Upload and ingest a PDF |
| GET | `/sources/` | List all sources |
| DELETE | `/sources/{id}` | Delete a source |
| POST | `/search/` | Search context (requires `X-Api-Key` header) |
| POST | `/agents/` | Create an agent |
| GET | `/agents/` | List agents |
| POST | `/agents/{id}/grant` | Grant source access |
| DELETE | `/agents/{id}/revoke/{source_id}` | Revoke access |

## Roadmap

- [x] PDF connector
- [x] Vector search (pgvector)
- [x] Agent access control
- [x] Visual demo UI
- [ ] Knowledge Graph (Neo4j)
- [ ] Hybrid retrieval (vector + graph)
- [ ] More connectors (Postgres tables, Gmail, Snowflake)
- [ ] Audio/video modality support

## License

MIT
