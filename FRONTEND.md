# Frontend Specification — Enterprise Context Engine

**Date:** 2026-04-27  
**Status:** Implemented with Knowledge Graph Visualization & Warm Theme

## Overview

The Lattice frontend is a React 19 + TypeScript application providing an intuitive interface for exploring enterprise knowledge atoms, managing agents, and visualizing the knowledge graph.

## Recent Major Updates

### 1. Full Knowledge Graph Visualization (2026-04-26)

**New Feature:** Interactive knowledge graph showing all atoms and their relationships

- **Component:** `FullAtomGraph.tsx` - Full graph visualization using React Flow
- **Endpoint:** `GET /api/v1/atoms/graph` - Fetches all atoms with relationships
- **Default View:** Atom Explorer now shows complete knowledge graph on load
- **Modal Detail:** Click any atom to see details in overlay modal (graph stays visible)

**Key Features:**

- Grid layout displaying all atoms
- Purple animated edges showing relationships
- Relation type labels on each edge
- Click nodes to navigate
- Modal overlay for atom details (doesn't hide graph)

### 2. Warm Skin Tone Theme (2026-04-26)

**Design Update:** Migrated from dark theme to warm, human-friendly color palette

**Color Palette:**

- Base Background: `#F5E6D3` (warm beige)
- Light Background: `#FFF5E6` (cream)
- Medium Background: `#E8D4BC` (light tan)
- Dark Background: `#D4BFA8` (tan)
- Primary Text: `#3D2817` (dark brown)
- Secondary Text: `#6B5744` (medium brown)
- Accent: `#8B5CF6` (purple for relationships)

**Applied To:**

- All layout components (Shell, Sidebar)
- All page components (Dashboard, Sources, Agents, Playground, Atom Explorer, Audit)
- All UI components (cards, buttons, inputs, modals)
- Graph visualization (nodes, backgrounds, edges)

## Page Structure

### 1. Dashboard (`pages/Dashboard.tsx`)

- System statistics overview
- Recent activity feed
- Atom count by kind chart
- Query timeline visualization

### 2. Sources (`pages/Sources.tsx`)

- List of ingested data sources
- Upload new documents (PDF, text, markdown)
- View compilation statistics
- Atom count per source

### 3. Agents (`pages/Agents.tsx`)

- Agent profile management
- Create/edit/delete agents
- Configure role masks and token budgets
- View agent domains and permissions

### 4. Playground (`pages/Playground.tsx`)

- Context query testing interface
- Compare results across multiple agents
- Side-by-side result columns
- Performance metrics display

### 5. Atom Explorer (`pages/AtomExplorer.tsx`) ⭐ NEW

**Primary Interface:** Full knowledge graph visualization

- **Default View:** Interactive graph showing all atoms and relationships
- **Graph Features:**
  - Grid layout with all atoms visible
  - Purple edges with relation labels
  - Click nodes to select
  - Pan and zoom controls
  - Animated relationship flows
- **Detail Modal:** Overlay panel showing selected atom details
  - Appears on right side
  - Semi-transparent backdrop
  - Graph remains visible underneath
  - Click backdrop or "Close" to dismiss
  - Navigate between atoms via links

**Removed:** List view, search bar, kind filters (simplified to focus on graph)

### 6. Audit Log (`pages/AuditLog.tsx`)

- Access control audit trail
- Paginated log entries
- Filter by decision type
- Latency and atom count metrics

## Component Library

### Atoms (`components/atoms/`)

- `AtomCard.tsx` - Compact atom display card
- `AtomDetail.tsx` - Full atom metadata view
- `AtomGraph.tsx` - Single atom neighborhood graph (legacy)
- `FullAtomGraph.tsx` - Full knowledge graph visualization ⭐ NEW
- `AccessMask.tsx` - Bitmask visualization

### Charts (`components/charts/`)

- `AtomsByKind.tsx` - Pie chart of atom distribution
- `QueryTimeline.tsx` - Time series of query latency

### Playground (`components/playground/`)

- `QueryBar.tsx` - Query input with agent selection
- `ResultColumn.tsx` - Single agent result display
- `PerfComparison.tsx` - Multi-agent comparison view

### Layout (`components/layout/`)

- `Shell.tsx` - Main app container with warm beige background
- `Sidebar.tsx` - Navigation menu with cream background

### Compiler (`components/compiler/`)

- `PipelineStatus.tsx` - Compilation progress indicator

## Design System

### Color Palette (Warm Skin Tone Theme)

```css
/* Backgrounds */
--color-skin-base: #f5e6d3 /* Main background */ --color-skin-light: #fff5e6
  /* Cards, panels */ --color-skin-medium: #e8d4bc /* Hover states */
  --color-skin-dark: #d4bfa8 /* Borders */ --color-skin-darker: #c4a888
  /* Accents */ /* Text */ --text-primary: #3d2817 /* Headings, primary text */
  --text-secondary: #6b5744 /* Body text */ --text-tertiary: #8b7355
  /* Muted text */ /* Atom Kind Colors (preserved) */ --color-atom-fact: #3b82f6
  --color-atom-metric: #10b981 --color-atom-decision: #f59e0b
  --color-atom-relationship: #8b5cf6 --color-atom-event: #f43f5e
  --color-atom-procedure: #64748b;
```

### Typography

- **Font:** Inter (system fallback)
- **Headings:** Bold, dark brown (#3D2817)
- **Body:** Regular, medium brown (#6B5744)
- **Captions:** Small, light brown (#8B7355)

### Spacing

- **Page padding:** 24px (px-6 py-6)
- **Component gaps:** 12px (gap-3)
- **Card padding:** 16-20px (p-4, p-5)

### Borders

- **Color:** Tan (#D4BFA8)
- **Radius:** 8-12px (rounded-lg, rounded-xl)
- **Width:** 1-2px

## Tech Stack

- **React 19** - Latest React with concurrent features
- **TypeScript** - Type safety
- **Vite** - Fast build tool
- **Tailwind CSS 4** - Utility-first styling
- **TanStack Query** - Server state management
- **React Router v7** - Client-side routing
- **Recharts** - Data visualization
- **Lucide React** - Icon library
- **React Flow (@xyflow/react)** - Graph visualization ⭐ NEW

## API Integration

All API calls go through `frontend/src/api/client.ts`:

```typescript
api.getStats(); // Dashboard stats
api.getSources(); // Source list
api.ingestSource(file); // Upload document — response includes atoms_created, cross_links_added, consolidation counts
api.getAgents(); // Agent list
api.createAgent(data); // Create agent
api.compareContext(q, ids); // Playground queries
api.getAtoms(params); // Atom search
api.getAtom(id); // Single atom
api.getFullGraph(limit); // Full knowledge graph ⭐ NEW
api.getAtomNeighborhood(id); // Atom neighborhood
api.getAuditLog(page); // Audit entries
```

**Atom link relations in the graph** — edges now carry consolidation relation types in addition to cross-source and within-source relations: `confirms`, `subsumes`, `supersedes`, `contradicts`. The graph visualization renders all of these as purple edges with relation labels; no frontend code change required since relation labels are pulled directly from the `links[].relation` field.

## State Management

- **TanStack Query** for server state (caching, refetching)
- **React useState** for local UI state
- **No global state** - each page manages its own state
- **Query keys** for cache invalidation

## Routing

```
/                 → Dashboard
/sources          → Sources
/agents           → Agents
/playground       → Playground
/atoms            → Atom Explorer (Knowledge Graph) ⭐ UPDATED
/audit            → Audit Log
```

## Development

```bash
cd frontend
npm install
npm run dev
```

- **Dev server:** http://localhost:5173
- **Hot reload:** Enabled
- **Mock data:** Available for standalone demos

## Build

```bash
npm run build
```

Outputs to `frontend/dist/` for production deployment.

## Key UX Patterns

### 1. Knowledge Graph Exploration ⭐ NEW

- Full graph visible on load
- Click nodes to see details in modal
- Modal overlays graph (doesn't hide it)
- Navigate between atoms via links
- Purple edges show relationships clearly

### 2. Agent-Aware Context

- Same query, different results per agent
- Side-by-side comparison in Playground
- Visual distinction of access control

### 3. Real-time Feedback

- Loading states for async operations
- Error boundaries for graceful failures
- Toast notifications for actions

### 4. Responsive Design

- Optimized for desktop (1440px+)
- Sidebar navigation
- Flexible layouts with Tailwind

## Accessibility

- Semantic HTML elements
- ARIA labels on interactive elements
- Keyboard navigation support
- Color contrast ratios meet WCAG AA

## Performance

- Code splitting by route
- Lazy loading for heavy components
- TanStack Query caching (30-60s stale time)
- Optimized re-renders with React 19

---

**Bottom Line:** The frontend provides a clean, intuitive interface for exploring enterprise knowledge through an interactive graph visualization with a warm, human-friendly design aesthetic.
