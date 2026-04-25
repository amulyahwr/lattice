import { useState, useEffect, useRef, useCallback } from "react";
import * as d3 from "d3";
import {
  Search, User, Building2, Calendar, Hash, MapPin, FolderOpen,
  Lightbulb, ArrowRight, X, Sparkles, BarChart3,
} from "lucide-react";
import * as api from "../api";

const ENTITY_TYPE_CONFIG = {
  person:   { icon: User,       color: "#6366f1", label: "Person" },
  org:      { icon: Building2,  color: "#f59e0b", label: "Organization" },
  date:     { icon: Calendar,   color: "#10b981", label: "Date" },
  metric:   { icon: Hash,       color: "#ef4444", label: "Metric" },
  location: { icon: MapPin,     color: "#8b5cf6", label: "Location" },
  project:  { icon: FolderOpen, color: "#3b82f6", label: "Project" },
  concept:  { icon: Lightbulb,  color: "#ec4899", label: "Concept" },
};

function getEntityConfig(type) {
  return ENTITY_TYPE_CONFIG[type] || { icon: Lightbulb, color: "#78716c", label: type };
}

function EntityBadge({ type }) {
  const config = getEntityConfig(type);
  const Icon = config.icon;
  return (
    <span
      className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full font-medium"
      style={{ backgroundColor: config.color + "18", color: config.color }}
    >
      <Icon size={10} /> {config.label}
    </span>
  );
}

function RelationshipBadge({ type }) {
  return (
    <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-stone-100 text-stone-600 font-mono">
      {type.replace(/_/g, " ")}
    </span>
  );
}

export default function GraphExplorer({ graphStats }) {
  const [searchQuery, setSearchQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchResults, setSearchResults] = useState(null);
  const [selectedEntity, setSelectedEntity] = useState(null);
  const [neighborhood, setNeighborhood] = useState(null);
  const [loadingNeighborhood, setLoadingNeighborhood] = useState(false);
  const [filterType, setFilterType] = useState(null);

  const svgRef = useRef(null);
  const containerRef = useRef(null);

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    setSearching(true);
    try {
      const results = await api.searchEntities(searchQuery, filterType, 20);
      setSearchResults(results);
    } catch (e) {
      console.error(e);
    }
    setSearching(false);
  };

  const selectEntity = async (entity) => {
    setSelectedEntity(entity);
    setLoadingNeighborhood(true);
    try {
      const data = await api.getEntityNeighborhood(entity.id);
      setNeighborhood(data);
    } catch (e) {
      console.error(e);
    }
    setLoadingNeighborhood(false);
  };

  // Mini graph visualization for the neighborhood
  useEffect(() => {
    if (!neighborhood || !neighborhood.entity || !svgRef.current) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    const container = containerRef.current;
    const width = container ? container.offsetWidth : 500;
    const height = 350;

    svg.attr("width", width).attr("height", height);

    // Build nodes and links
    const centerNode = {
      id: neighborhood.entity.id,
      name: neighborhood.entity.name,
      type: neighborhood.entity.type,
      isCenter: true,
    };

    const nodes = [centerNode];
    const links = [];
    const nodeMap = new Set([centerNode.id]);

    neighborhood.connected_entities.forEach((e) => {
      if (!nodeMap.has(e.id)) {
        nodes.push({ id: e.id, name: e.name, type: e.type, isCenter: false });
        nodeMap.add(e.id);
      }
    });

    neighborhood.relationships.forEach((r) => {
      links.push({
        source: r.from_entity_id,
        target: r.to_entity_id,
        type: r.type,
        weight: r.weight,
      });
    });

    if (nodes.length <= 1) return;

    // Force simulation
    const simulation = d3.forceSimulation(nodes)
      .force("link", d3.forceLink(links).id((d) => d.id).distance(100).strength(0.5))
      .force("charge", d3.forceManyBody().strength(-250))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collision", d3.forceCollide().radius(35))
      .velocityDecay(0.4);

    const g = svg.append("g");

    // Zoom
    svg.call(
      d3.zoom()
        .scaleExtent([0.5, 3])
        .on("zoom", (event) => g.attr("transform", event.transform))
    );

    // Links
    const link = g.append("g")
      .selectAll("g")
      .data(links)
      .join("g");

    link.append("line")
      .attr("stroke", "#d6d3d1")
      .attr("stroke-width", (d) => Math.max(1, d.weight))
      .attr("stroke-opacity", 0.6);

    // Link labels
    link.append("text")
      .attr("text-anchor", "middle")
      .attr("fill", "#a8a29e")
      .attr("font-size", "8px")
      .attr("dy", -4)
      .text((d) => d.type.replace(/_/g, " "));

    // Nodes
    const node = g.append("g")
      .selectAll("g")
      .data(nodes)
      .join("g")
      .style("cursor", "pointer")
      .call(d3.drag()
        .on("start", (event, d) => {
          if (!event.active) simulation.alphaTarget(0.05).restart();
          d.fx = d.x; d.fy = d.y;
        })
        .on("drag", (event, d) => { d.fx = event.x; d.fy = event.y; })
        .on("end", (event, d) => {
          if (!event.active) simulation.alphaTarget(0);
          d.fx = null; d.fy = null;
        })
      );

    node.append("circle")
      .attr("r", (d) => d.isCenter ? 22 : 16)
      .attr("fill", "white")
      .attr("stroke", (d) => getEntityConfig(d.type).color)
      .attr("stroke-width", (d) => d.isCenter ? 3 : 2);

    // Node icons (emoji fallback)
    const typeEmoji = {
      person: "👤", org: "🏢", date: "📅", metric: "#",
      location: "📍", project: "📁", concept: "💡",
    };
    node.append("text")
      .attr("text-anchor", "middle")
      .attr("dy", "0.35em")
      .attr("font-size", (d) => d.isCenter ? "14px" : "11px")
      .text((d) => typeEmoji[d.type] || "•");

    // Labels
    node.append("text")
      .attr("dy", (d) => (d.isCenter ? 32 : 26))
      .attr("text-anchor", "middle")
      .attr("fill", "#57534e")
      .attr("font-size", (d) => d.isCenter ? "11px" : "9px")
      .attr("font-weight", (d) => d.isCenter ? "600" : "400")
      .text((d) => d.name.length > 18 ? d.name.slice(0, 16) + "…" : d.name);

    // Click connected nodes to navigate
    node.on("click", (event, d) => {
      if (!d.isCenter) {
        selectEntity({ id: d.id, name: d.name, type: d.type });
      }
    });

    simulation.on("tick", () => {
      link.select("line")
        .attr("x1", (d) => d.source.x).attr("y1", (d) => d.source.y)
        .attr("x2", (d) => d.target.x).attr("y2", (d) => d.target.y);
      link.select("text")
        .attr("x", (d) => (d.source.x + d.target.x) / 2)
        .attr("y", (d) => (d.source.y + d.target.y) / 2);
      node.attr("transform", (d) => `translate(${d.x},${d.y})`);
    });

    return () => simulation.stop();
  }, [neighborhood]);

  const entityTypes = Object.keys(ENTITY_TYPE_CONFIG);

  return (
    <div className="space-y-6">
      {/* Graph Stats Bar */}
      {graphStats && (
        <div className="flex items-center gap-6 bg-white border border-stone-200 rounded-lg p-4">
          <div className="flex items-center gap-2">
            <BarChart3 size={16} className="text-indigo-600" />
            <span className="text-sm font-medium text-stone-700">Knowledge Graph</span>
          </div>
          <div className="flex items-center gap-4 text-sm">
            <span className="text-stone-500">
              <span className="font-semibold text-stone-700">{graphStats.total_entities}</span> entities
            </span>
            <span className="text-stone-500">
              <span className="font-semibold text-stone-700">{graphStats.total_relationships}</span> relationships
            </span>
          </div>
          <div className="flex items-center gap-2 ml-auto">
            {Object.entries(graphStats.entities_by_type || {}).map(([type, count]) => {
              const config = getEntityConfig(type);
              return (
                <span
                  key={type}
                  className="text-[10px] px-2 py-0.5 rounded-full font-medium"
                  style={{ backgroundColor: config.color + "18", color: config.color }}
                >
                  {count} {config.label}
                </span>
              );
            })}
          </div>
        </div>
      )}

      {/* Search Bar */}
      <div className="space-y-2">
        <div className="flex gap-3">
          <input
            type="text"
            placeholder="Search entities... (people, orgs, dates, metrics)"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            className="flex-1 bg-white border border-stone-300 rounded-lg px-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none"
          />
          <button
            onClick={handleSearch}
            disabled={searching}
            className="bg-indigo-600 hover:bg-indigo-500 text-white disabled:opacity-50 px-5 py-2.5 rounded-lg text-sm font-medium transition-colors"
          >
            {searching ? "Searching..." : "Search"}
          </button>
        </div>
        {/* Type filters */}
        <div className="flex gap-1 flex-wrap">
          <button
            onClick={() => setFilterType(null)}
            className={`text-xs px-2.5 py-1 rounded-full transition-colors ${
              !filterType ? "bg-stone-800 text-white" : "bg-stone-100 text-stone-500 hover:bg-stone-200"
            }`}
          >
            All
          </button>
          {entityTypes.map((type) => {
            const config = getEntityConfig(type);
            const Icon = config.icon;
            return (
              <button
                key={type}
                onClick={() => setFilterType(filterType === type ? null : type)}
                className={`inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-full transition-colors ${
                  filterType === type
                    ? "text-white"
                    : "bg-stone-100 text-stone-500 hover:bg-stone-200"
                }`}
                style={filterType === type ? { backgroundColor: config.color, color: "white" } : {}}
              >
                <Icon size={10} /> {config.label}
              </button>
            );
          })}
        </div>
      </div>

      <div className="grid grid-cols-5 gap-6">
        {/* Search Results — left panel */}
        <div className="col-span-2 space-y-2">
          {searchResults && (
            <>
              <p className="text-xs text-stone-400">{searchResults.length} entities found</p>
              <div className="space-y-1 max-h-[500px] overflow-y-auto">
                {searchResults.map((entity) => (
                  <button
                    key={entity.id}
                    onClick={() => selectEntity(entity)}
                    className={`w-full text-left rounded-lg p-3 transition-colors border ${
                      selectedEntity?.id === entity.id
                        ? "bg-indigo-50 border-indigo-300"
                        : "bg-white border-stone-200 hover:border-stone-300"
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm font-medium text-stone-800">{entity.name}</span>
                      {entity.relevance_score != null && (
                        <span className="text-[10px] text-stone-400">
                          {(entity.relevance_score * 100).toFixed(0)}%
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <EntityBadge type={entity.type} />
                      {entity.mention_count > 1 && (
                        <span className="text-[10px] text-stone-400">
                          {entity.mention_count} mentions
                        </span>
                      )}
                    </div>
                  </button>
                ))}
              </div>
            </>
          )}

          {!searchResults && (
            <div className="text-center py-12 text-stone-400">
              <Search size={32} className="mx-auto mb-3 opacity-30" />
              <p className="text-sm">Search the knowledge graph</p>
              <p className="text-xs mt-1">Find people, organizations, dates, metrics, and how they connect</p>
            </div>
          )}
        </div>

        {/* Neighborhood — right panel */}
        <div className="col-span-3">
          {selectedEntity && (
            <div className="bg-white border border-stone-200 rounded-lg overflow-hidden">
              {/* Entity header */}
              <div className="p-4 border-b border-stone-100">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="font-semibold text-stone-800">{selectedEntity.name}</h3>
                    <div className="flex items-center gap-2 mt-1">
                      <EntityBadge type={selectedEntity.type} />
                      {selectedEntity.mention_count > 1 && (
                        <span className="text-xs text-stone-400">{selectedEntity.mention_count} mentions</span>
                      )}
                    </div>
                  </div>
                  <button
                    onClick={() => { setSelectedEntity(null); setNeighborhood(null); }}
                    className="text-stone-400 hover:text-stone-600"
                  >
                    <X size={16} />
                  </button>
                </div>
                {selectedEntity.properties && Object.keys(selectedEntity.properties).length > 0 && (
                  <div className="flex flex-wrap gap-2 mt-2">
                    {Object.entries(selectedEntity.properties).map(([k, v]) => (
                      <span key={k} className="text-[10px] bg-stone-50 text-stone-500 px-2 py-0.5 rounded">
                        {k}: {String(v)}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              {/* Mini graph */}
              {loadingNeighborhood ? (
                <div className="flex items-center justify-center py-16 text-stone-400 text-sm">
                  Loading neighborhood...
                </div>
              ) : neighborhood ? (
                <>
                  <div ref={containerRef} className="w-full" style={{ background: "radial-gradient(ellipse at center, #faf5f0 0%, #f0e6dc 100%)" }}>
                    <svg ref={svgRef} className="w-full" style={{ minHeight: "350px" }} />
                  </div>

                  {/* Relationships list */}
                  {neighborhood.relationships.length > 0 && (
                    <div className="p-4 border-t border-stone-100">
                      <p className="text-[10px] uppercase tracking-wider text-stone-400 mb-2">
                        Relationships ({neighborhood.relationships.length})
                      </p>
                      <div className="space-y-1.5">
                        {neighborhood.relationships.map((rel) => {
                          const fromName = rel.from_entity_id === neighborhood.entity.id
                            ? neighborhood.entity.name
                            : neighborhood.connected_entities.find((e) => e.id === rel.from_entity_id)?.name || "?";
                          const toName = rel.to_entity_id === neighborhood.entity.id
                            ? neighborhood.entity.name
                            : neighborhood.connected_entities.find((e) => e.id === rel.to_entity_id)?.name || "?";
                          return (
                            <div key={rel.id} className="flex items-center gap-2 text-xs">
                              <span className="text-stone-700 font-medium">{fromName}</span>
                              <ArrowRight size={10} className="text-stone-300" />
                              <RelationshipBadge type={rel.type} />
                              <ArrowRight size={10} className="text-stone-300" />
                              <span className="text-stone-700 font-medium">{toName}</span>
                              {rel.weight > 1 && (
                                <span className="text-[10px] text-stone-400">×{rel.weight}</span>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </>
              ) : null}
            </div>
          )}

          {!selectedEntity && (
            <div className="flex items-center justify-center h-full text-stone-400 bg-white border border-stone-200 rounded-lg py-20">
              <div className="text-center">
                <Sparkles size={32} className="mx-auto mb-3 opacity-30" />
                <p className="text-sm">Select an entity to explore</p>
                <p className="text-xs mt-1">See how it connects to other entities in the graph</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
