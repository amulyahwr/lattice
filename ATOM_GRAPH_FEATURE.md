# Atom Graph Visualization Feature

**Date:** 2026-04-26  
**Status:** Implemented

## Overview

Added an interactive graph visualization feature to the Atom Explorer that allows users to visualize how atoms are connected through their relationships. This complements the existing list-based detail view with a visual network representation.

## What Was Added

### 1. Frontend Components

**`frontend/src/components/atoms/AtomGraph.tsx`**

- Interactive graph visualization using React Flow
- Custom atom nodes showing:
  - Atom kind badge with icon
  - Content preview (3 lines max)
  - Domain tags (up to 3)
  - Visual distinction for center atom (blue border, "CENTER" badge)
- Circular layout algorithm arranging neighbors around center atom
- Animated edges with relation labels
- Interactive features:
  - Click nodes to navigate to different atoms
  - Pan and zoom controls
  - Mini-map for navigation
  - Smooth transitions

### 2. Enhanced Atom Explorer

**`frontend/src/pages/AtomExplorer.tsx`**

- Added view mode toggle (Detail View / Graph View)
- Integrated `useAtomNeighborhood` hook for fetching atom relationships
- Shows connection count when atom is selected
- Seamless switching between detail and graph views
- Graph view automatically loads when switching modes

### 3. Dependencies

**Added:** `@xyflow/react` (React Flow v12)

- Modern, performant graph visualization library
- Built-in controls, minimap, and background
- TypeScript support
- Customizable node and edge rendering

## How It Works

### Data Flow

```
User selects atom → useAtomNeighborhood hook → GET /api/v1/atoms/{id}/neighborhood
                                                ↓
                                    { center: Atom, neighbors: [{ atom, relation }] }
                                                ↓
                                    AtomGraph component renders interactive visualization
```

### Backend API

Uses existing endpoint: `GET /api/v1/atoms/{atom_id}/neighborhood`

Returns:

- `center`: The selected atom with full metadata
- `neighbors`: Array of connected atoms with their relation types

Relation types include:

- `topical` - Related by topic/domain
- `causal` - Cause-effect relationship
- `temporal` - Time-based relationship
- `hierarchical` - Parent-child relationship
- Custom relations defined during linking stage

### Graph Layout

- **Center node**: Positioned at (400, 300) with blue border
- **Neighbor nodes**: Arranged in a circle with 250px radius
- **Edges**: Smooth curved lines with animated flow
- **Labels**: Relation type displayed on each edge

## User Experience

### Accessing Graph View

1. Navigate to **Atom Explorer** page
2. Search or browse atoms in the left panel
3. Click an atom to select it
4. Click **"Graph View"** button in the top toolbar
5. Interactive graph appears showing the atom and its connections

### Interacting with Graph

- **Click nodes** to navigate to connected atoms
- **Drag nodes** to rearrange layout
- **Scroll** to zoom in/out
- **Click and drag background** to pan
- **Use minimap** for quick navigation
- **Use controls** (bottom-left) for zoom/fit view

### Switching Views

- Toggle between **Detail View** (traditional) and **Graph View** (network)
- Connection count displayed in toolbar
- State preserved when switching views

## Technical Details

### Component Architecture

```
AtomExplorer (page)
├── Left Panel: Atom List
│   ├── Search bar
│   ├── Kind filters
│   └── Results list
└── Right Panel: View Container
    ├── View Mode Toggle (Detail | Graph)
    └── Content Area
        ├── AtomDetail (detail mode)
        └── AtomGraph (graph mode)
            ├── Custom AtomNode components
            ├── Animated edges
            ├── Background grid
            ├── Controls
            └── MiniMap
```

### Performance Considerations

- Graph only loads when view is activated
- Neighborhood data cached by TanStack Query (30s stale time)
- React Flow handles rendering optimization
- Limited to 1-hop neighbors (prevents overwhelming visualizations)

### Styling

- Dark theme matching Lattice design system
- Zinc color palette for consistency
- Blue accent for selected/center atoms
- Smooth animations and transitions
- Responsive layout

## Future Enhancements

### Phase 2 Improvements

- [ ] **Multi-hop exploration** - Expand graph to show 2-3 hops
- [ ] **Relation filtering** - Show/hide specific relation types
- [ ] **Layout algorithms** - Force-directed, hierarchical, radial options
- [ ] **Atom clustering** - Group related atoms by domain/kind
- [ ] **Export graph** - Save as PNG/SVG
- [ ] **Full-screen mode** - Dedicated graph exploration view

### Phase 3 Advanced Features

- [ ] **Path finding** - Highlight shortest path between two atoms
- [ ] **Subgraph extraction** - Select and export portions of graph
- [ ] **Time-based animation** - Show how graph evolved over time
- [ ] **Collaborative annotations** - Add notes to nodes/edges
- [ ] **Graph metrics** - Centrality, clustering coefficient, etc.

## Benefits

### For Users

✅ **Visual understanding** - See knowledge structure at a glance  
✅ **Relationship discovery** - Find unexpected connections  
✅ **Navigation efficiency** - Jump between related atoms quickly  
✅ **Context awareness** - Understand atom's role in knowledge graph

### For Enterprise

✅ **Knowledge mapping** - Visualize organizational knowledge structure  
✅ **Gap identification** - Spot missing connections or isolated atoms  
✅ **Quality assurance** - Verify linking accuracy  
✅ **Onboarding** - Help new users understand knowledge organization

## Testing

### Manual Testing Checklist

- [ ] Graph renders correctly with center atom and neighbors
- [ ] Clicking nodes navigates to selected atom
- [ ] View toggle switches between detail and graph
- [ ] Connection count displays correctly
- [ ] Graph controls (zoom, pan, fit) work properly
- [ ] Minimap reflects current viewport
- [ ] Loading state shows when fetching neighborhood
- [ ] Empty state shows when atom has no connections
- [ ] Layout algorithm positions nodes without overlap

### Test Scenarios

1. **Atom with many connections** (>10 neighbors)
2. **Atom with no connections** (isolated)
3. **Atom with single connection**
4. **Different relation types** (verify labels)
5. **Rapid navigation** (click multiple nodes quickly)

## Documentation

- Component documented with JSDoc comments
- TypeScript types ensure type safety
- Inline comments explain layout algorithm
- This document serves as feature specification

---

**Implementation Time:** ~2 hours  
**Lines of Code:** ~250 (component) + ~50 (integration)  
**Dependencies Added:** 1 (@xyflow/react)  
**Breaking Changes:** None
