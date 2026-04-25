import { useEffect, useRef, useState, useCallback } from "react";
import * as d3 from "d3";
import { X, Check, Lock, Sparkles } from "lucide-react";

/**
 * LatticeMap — force-directed graph visualization of agents ↔ sources.
 *
 * Nodes:
 *   - Sources (circles) colored by classification, sized by chunk count
 *   - Agents (rounded rects) colored by clearance, sized by grant count
 *
 * Edges:
 *   - Solid = granted access
 *   - Dashed + pulsing = recommended (not yet granted)
 */

const CLASSIFICATION_COLORS = {
  public: "#22c55e",
  internal: "#6b7280",
  confidential: "#eab308",
  restricted: "#ef4444",
};

const DOMAIN_COLORS = [
  "#818cf8", "#f472b6", "#34d399", "#fbbf24", "#60a5fa",
  "#a78bfa", "#fb923c", "#2dd4bf", "#f87171", "#a3e635",
];

export default function LatticeMap({ sources, agents, onGrant, onRevoke, onRefresh }) {
  const svgRef = useRef(null);
  const containerRef = useRef(null);
  const simulationRef = useRef(null);
  const [selectedNode, setSelectedNode] = useState(null);
  const [recommendations, setRecommendations] = useState([]);
  const [dimensions, setDimensions] = useState({ width: 900, height: 600 });

  // Use refs for hover state to avoid re-renders that shake the simulation
  const tooltipRef = useRef(null);

  // Collect all unique domains
  const allDomains = [...new Set([
    ...sources.flatMap((s) => s.domains || []),
    ...agents.flatMap((a) => a.domains || []),
  ])];

  // Build graph data
  const buildGraph = useCallback(() => {
    const nodes = [];
    const links = [];

    sources.forEach((s) => {
      nodes.push({
        id: `source:${s.id}`,
        type: "source",
        data: s,
        label: s.name.length > 20 ? s.name.slice(0, 18) + "…" : s.name,
        radius: Math.max(14, Math.min(30, 10 + (s.chunk_count || 0) * 0.8)),
        color: CLASSIFICATION_COLORS[s.classification] || CLASSIFICATION_COLORS.internal,
        domains: s.domains || [],
      });
    });

    agents.forEach((a) => {
      const grantCount = (a.source_ids || []).length;
      nodes.push({
        id: `agent:${a.id}`,
        type: "agent",
        data: a,
        label: a.name.length > 16 ? a.name.slice(0, 14) + "…" : a.name,
        radius: Math.max(16, Math.min(32, 12 + grantCount * 4)),
        color: CLASSIFICATION_COLORS[a.clearance] || CLASSIFICATION_COLORS.internal,
        domains: a.domains || [],
      });

      (a.source_ids || []).forEach((sourceId) => {
        links.push({
          source: `agent:${a.id}`,
          target: `source:${sourceId}`,
          type: "granted",
        });
      });
    });

    return { nodes, links };
  }, [sources, agents]);

  // Fetch recommendations for selected node
  const fetchRecs = useCallback(async (node) => {
    try {
      const id = node.data.id;
      const url = node.type === "source"
        ? `/api/v1/sources/${id}/recommendations`
        : `/api/v1/agents/${id}/recommendations`;
      const res = await fetch(url);
      if (res.ok) {
        const recs = await res.json();
        setRecommendations(recs);
      }
    } catch {
      setRecommendations([]);
    }
  }, []);

  // Resize observer
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const observer = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      setDimensions({ width: Math.max(width, 400), height: Math.max(height, 400) });
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  // D3 force simulation
  useEffect(() => {
    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    const { width, height } = dimensions;
    const { nodes, links } = buildGraph();

    if (nodes.length === 0) return;

    const defs = svg.append("defs");

    // Glow filter
    const filter = defs.append("filter").attr("id", "glow");
    filter.append("feGaussianBlur").attr("stdDeviation", "3").attr("result", "blur");
    filter.append("feMerge").selectAll("feMergeNode")
      .data(["blur", "SourceGraphic"]).join("feMergeNode")
      .attr("in", (d) => d);

    // Pulsing animation
    svg.append("style").text(`
      @keyframes pulse-dash {
        0% { stroke-opacity: 0.3; }
        50% { stroke-opacity: 0.8; }
        100% { stroke-opacity: 0.3; }
      }
      .link-recommended {
        animation: pulse-dash 2s ease-in-out infinite;
      }
    `);

    // Domain clustering centers
    const domainCenters = {};
    allDomains.forEach((d, i) => {
      const angle = (2 * Math.PI * i) / Math.max(allDomains.length, 1);
      const r = Math.min(width, height) * 0.22;
      domainCenters[d] = {
        x: width / 2 + r * Math.cos(angle),
        y: height / 2 + r * Math.sin(angle),
      };
    });

    function domainForce(alpha) {
      nodes.forEach((node) => {
        if (node.domains && node.domains.length > 0) {
          let cx = 0, cy = 0, count = 0;
          node.domains.forEach((d) => {
            if (domainCenters[d]) {
              cx += domainCenters[d].x;
              cy += domainCenters[d].y;
              count++;
            }
          });
          if (count > 0) {
            cx /= count;
            cy /= count;
            node.vx += (cx - node.x) * alpha * 0.06;
            node.vy += (cy - node.y) * alpha * 0.06;
          }
        }
      });
    }

    function typeForce(alpha) {
      nodes.forEach((node) => {
        const target = node.type === "source" ? width * 0.38 : width * 0.62;
        node.vx += (target - node.x) * alpha * 0.03;
      });
    }

    const simulation = d3.forceSimulation(nodes)
      .force("link", d3.forceLink(links).id((d) => d.id).distance(160).strength(0.3))
      .force("charge", d3.forceManyBody().strength(-350))
      .force("center", d3.forceCenter(width / 2, height / 2).strength(0.05))
      .force("collision", d3.forceCollide().radius((d) => d.radius + 20).strength(0.8))
      .force("domain", domainForce)
      .force("type", typeForce)
      .force("x", d3.forceX(width / 2).strength(0.015))
      .force("y", d3.forceY(height / 2).strength(0.015))
      .alphaDecay(0.03)
      .velocityDecay(0.4);

    simulationRef.current = simulation;

    // Zoom
    const g = svg.append("g");
    const zoom = d3.zoom()
      .scaleExtent([0.3, 3])
      .on("zoom", (event) => g.attr("transform", event.transform));
    svg.call(zoom);



    // Links
    const link = g.append("g")
      .selectAll("line")
      .data(links)
      .join("line")
      .attr("stroke", (d) => d.type === "granted" ? "#6366f1" : "#a8a29e")
      .attr("stroke-width", (d) => d.type === "granted" ? 2 : 1.5)
      .attr("stroke-dasharray", (d) => d.type === "granted" ? "none" : "6,4")
      .attr("class", (d) => d.type === "recommended" ? "link-recommended" : "")
      .attr("stroke-opacity", 0.6);

    // Node groups
    const node = g.append("g")
      .selectAll("g")
      .data(nodes)
      .join("g")
      .style("cursor", "pointer")
      .call(d3.drag()
        .on("start", (event, d) => {
          if (!event.active) simulation.alphaTarget(0.05).restart();
          d.fx = d.x;
          d.fy = d.y;
        })
        .on("drag", (event, d) => {
          d.fx = event.x;
          d.fy = event.y;
        })
        .on("end", (event, d) => {
          if (!event.active) simulation.alphaTarget(0);
          d.fx = null;
          d.fy = null;
        })
      );

    // Source nodes — circles
    node.filter((d) => d.type === "source")
      .append("circle")
      .attr("r", (d) => d.radius)
      .attr("fill", "white")
      .attr("fill-opacity", 0.9)
      .attr("stroke", (d) => d.color)
      .attr("stroke-width", 2.5);

    // Agent nodes — rounded rects
    node.filter((d) => d.type === "agent")
      .append("rect")
      .attr("x", (d) => -d.radius)
      .attr("y", (d) => -d.radius * 0.7)
      .attr("width", (d) => d.radius * 2)
      .attr("height", (d) => d.radius * 1.4)
      .attr("rx", 6)
      .attr("fill", "white")
      .attr("fill-opacity", 0.9)
      .attr("stroke", (d) => d.color)
      .attr("stroke-width", 2.5);

    // Type icons
    node.filter((d) => d.type === "source")
      .append("text")
      .attr("text-anchor", "middle")
      .attr("dy", "0.35em")
      .attr("font-size", (d) => Math.max(10, d.radius * 0.7))
      .text("📄");

    node.filter((d) => d.type === "agent")
      .append("text")
      .attr("text-anchor", "middle")
      .attr("dy", "0.35em")
      .attr("font-size", (d) => Math.max(10, d.radius * 0.7))
      .text("🤖");

    // Labels
    node.append("text")
      .attr("dy", (d) => d.radius + 14)
      .attr("text-anchor", "middle")
      .attr("fill", "#78716c")
      .attr("font-size", "10px")
      .attr("pointer-events", "none")
      .text((d) => d.label);

    // Hover effects — using DOM directly to avoid React re-renders
    node.on("mouseenter", function (event, d) {
      // Show tooltip via DOM (no React setState)
      const tooltip = tooltipRef.current;
      if (tooltip) {
        const name = d.data.name;
        const desc = d.type === "source" ? (d.data.summary || "") : (d.data.purpose || "");
        const truncDesc = desc.length > 100 ? desc.slice(0, 97) + "…" : desc;
        tooltip.innerHTML = `
          <div class="flex items-center gap-2 mb-1">
            <span>${d.type === "source" ? "📄" : "🤖"}</span>
            <span class="font-medium text-stone-700">${name}</span>
          </div>
          ${truncDesc ? `<p class="text-stone-500">${truncDesc}</p>` : ""}
        `;
        tooltip.style.display = "block";
      }

      // Highlight connected links
      link
        .transition().duration(150)
        .attr("stroke-opacity", (l) => {
          const sid = typeof l.source === "object" ? l.source.id : l.source;
          const tid = typeof l.target === "object" ? l.target.id : l.target;
          return (sid === d.id || tid === d.id) ? 1 : 0.06;
        })
        .attr("stroke-width", (l) => {
          const sid = typeof l.source === "object" ? l.source.id : l.source;
          const tid = typeof l.target === "object" ? l.target.id : l.target;
          return (sid === d.id || tid === d.id) ? 3.5 : l.type === "granted" ? 2 : 1.5;
        });

      // Dim unconnected nodes
      const connectedIds = new Set([d.id]);
      links.forEach((l) => {
        const sid = typeof l.source === "object" ? l.source.id : l.source;
        const tid = typeof l.target === "object" ? l.target.id : l.target;
        if (sid === d.id) connectedIds.add(tid);
        if (tid === d.id) connectedIds.add(sid);
      });
      node.transition().duration(150)
        .attr("opacity", (n) => connectedIds.has(n.id) ? 1 : 0.12);

      // Glow on hovered node
      d3.select(this).select("circle, rect").attr("filter", "url(#glow)");

    }).on("mouseleave", function () {
      // Hide tooltip
      const tooltip = tooltipRef.current;
      if (tooltip) tooltip.style.display = "none";

      // Restore all
      link.transition().duration(200)
        .attr("stroke-opacity", 0.6)
        .attr("stroke-width", (l) => l.type === "granted" ? 2 : 1.5);
      node.transition().duration(200).attr("opacity", 1);
      d3.select(this).select("circle, rect").attr("filter", null);
    });

    // Click to select — use d3 event handling only
    node.on("click", function (event, d) {
      event.stopPropagation();
      setSelectedNode(d);
      fetchRecs(d);
    });

    // Click SVG background to deselect
    svg.on("click.deselect", (event) => {
      // Only deselect if clicking the SVG itself (not a node)
      if (event.target === svgRef.current) {
        setSelectedNode(null);
        setRecommendations([]);
      }
    });

    // Let simulation settle then stop
    simulation.on("tick", () => {
      link
        .attr("x1", (d) => d.source.x)
        .attr("y1", (d) => d.source.y)
        .attr("x2", (d) => d.target.x)
        .attr("y2", (d) => d.target.y);
      node.attr("transform", (d) => `translate(${d.x},${d.y})`);
    });

    return () => simulation.stop();
  }, [dimensions, sources, agents, buildGraph, allDomains, fetchRecs]);

  // Handle approve from side panel
  const handleApprove = async (agentId, sourceId) => {
    await onGrant(agentId, sourceId);
    if (selectedNode) {
      setTimeout(() => fetchRecs(selectedNode), 300);
    }
  };

  // Handle revoke from side panel
  const handleRevoke = async (agentId, sourceId) => {
    await onRevoke(agentId, sourceId);
    if (selectedNode) {
      setTimeout(() => fetchRecs(selectedNode), 300);
    }
  };

  // Build connection info for selected node
  const getConnections = () => {
    if (!selectedNode) return { granted: [], notGranted: [] };

    if (selectedNode.type === "agent") {
      const agent = selectedNode.data;
      const grantedIds = new Set(agent.source_ids || []);
      return {
        granted: sources.filter((s) => grantedIds.has(s.id)),
        notGranted: sources.filter((s) => !grantedIds.has(s.id)),
      };
    } else {
      const sourceId = selectedNode.data.id;
      return {
        granted: agents.filter((a) => (a.source_ids || []).includes(sourceId)),
        notGranted: agents.filter((a) => !(a.source_ids || []).includes(sourceId)),
      };
    }
  };

  const connections = getConnections();

  return (
    <div className="relative w-full h-full" ref={containerRef} style={{ minHeight: "600px" }}>
      {/* Legend */}
      <div className="absolute top-3 left-3 z-10 bg-white/90 border border-stone-200 rounded-lg p-3 text-xs space-y-2 pointer-events-none">
        <div className="font-medium text-stone-700 mb-1">Legend</div>
        <div className="flex items-center gap-2">
          <span>📄</span> <span className="text-stone-500">Source</span>
          <span className="ml-2">🤖</span> <span className="text-stone-500">Agent</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-6 h-0.5 bg-indigo-500" /> <span className="text-stone-500">Granted</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-6 h-0.5 border-t-2 border-dashed border-stone-400" /> <span className="text-stone-500">Recommended</span>
        </div>
        <div className="space-y-1 mt-1">
          {Object.entries(CLASSIFICATION_COLORS).map(([key, color]) => (
            <div key={key} className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full" style={{ backgroundColor: color, opacity: 0.6 }} />
              <span className="text-stone-400">{key}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Hover tooltip — managed via DOM ref, not React state */}
      <div
        ref={tooltipRef}
        className="absolute top-3 right-3 z-10 bg-white/95 border border-stone-300 rounded-lg p-3 text-xs max-w-64 pointer-events-none"
        style={{ display: "none" }}
      />

      {/* SVG Canvas */}
      <svg
        ref={svgRef}
        width={dimensions.width}
        height={dimensions.height}
        className="w-full h-full"
        style={{ background: "radial-gradient(ellipse at center, #faf5f0 0%, #f0e6dc 100%)" }}
      />

      {/* Side Panel */}
      {selectedNode && (
        <div className="absolute top-0 right-0 z-20 w-80 h-full bg-[#faf5f0]/98 border-l border-stone-200 overflow-y-auto">
          <div className="p-4 space-y-4">
            {/* Header */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-lg">{selectedNode.type === "source" ? "📄" : "🤖"}</span>
                <h3 className="font-semibold text-stone-800 text-sm">{selectedNode.data.name}</h3>
              </div>
              <button
                onClick={() => { setSelectedNode(null); setRecommendations([]); }}
                className="text-stone-400 hover:text-stone-700"
              >
                <X size={16} />
              </button>
            </div>

            {/* DNA / Profile */}
            {selectedNode.type === "source" ? (
              <div className="space-y-3">
                <div>
                  <p className="text-[10px] uppercase tracking-wider text-stone-500 mb-1">Classification</p>
                  <span
                    className="text-xs px-2 py-0.5 rounded-full"
                    style={{
                      backgroundColor: CLASSIFICATION_COLORS[selectedNode.data.classification] + "20",
                      color: CLASSIFICATION_COLORS[selectedNode.data.classification],
                    }}
                  >
                    {selectedNode.data.classification}
                  </span>
                </div>
                {selectedNode.data.summary && (
                  <div>
                    <p className="text-[10px] uppercase tracking-wider text-stone-500 mb-1">Summary</p>
                    <p className="text-xs text-stone-500 leading-relaxed">{selectedNode.data.summary}</p>
                  </div>
                )}
                {selectedNode.data.domains?.length > 0 && (
                  <div>
                    <p className="text-[10px] uppercase tracking-wider text-stone-500 mb-1">Domains</p>
                    <div className="flex flex-wrap gap-1">
                      {selectedNode.data.domains.map((d) => (
                        <span key={d} className="text-xs px-2 py-0.5 rounded-full bg-indigo-900/40 text-indigo-300">{d}</span>
                      ))}
                    </div>
                  </div>
                )}
                <div className="flex gap-4 text-xs text-stone-400">
                  <span>{selectedNode.data.chunk_count} chunks</span>
                  <span>{selectedNode.data.source_type}</span>
                  {selectedNode.data.owner && <span>{selectedNode.data.owner}</span>}
                </div>
              </div>
            ) : (
              <div className="space-y-3">
                <div>
                  <p className="text-[10px] uppercase tracking-wider text-stone-500 mb-1">Clearance</p>
                  <span
                    className="text-xs px-2 py-0.5 rounded-full"
                    style={{
                      backgroundColor: CLASSIFICATION_COLORS[selectedNode.data.clearance] + "20",
                      color: CLASSIFICATION_COLORS[selectedNode.data.clearance],
                    }}
                  >
                    {selectedNode.data.clearance}
                  </span>
                </div>
                {selectedNode.data.purpose && (
                  <div>
                    <p className="text-[10px] uppercase tracking-wider text-stone-500 mb-1">Purpose</p>
                    <p className="text-xs text-stone-500 leading-relaxed">{selectedNode.data.purpose}</p>
                  </div>
                )}
                {selectedNode.data.domains?.length > 0 && (
                  <div>
                    <p className="text-[10px] uppercase tracking-wider text-stone-500 mb-1">Domains</p>
                    <div className="flex flex-wrap gap-1">
                      {selectedNode.data.domains.map((d) => (
                        <span key={d} className="text-xs px-2 py-0.5 rounded-full bg-indigo-900/40 text-indigo-300">{d}</span>
                      ))}
                    </div>
                  </div>
                )}
                {selectedNode.data.deployed_by && (
                  <div className="text-xs text-stone-400">Deployed by {selectedNode.data.deployed_by}</div>
                )}
              </div>
            )}

            {/* Granted Connections */}
            <div>
              <p className="text-[10px] uppercase tracking-wider text-stone-500 mb-2 flex items-center gap-1">
                <Check size={10} /> Granted Access ({connections.granted.length})
              </p>
              {connections.granted.length === 0 ? (
                <p className="text-xs text-stone-500 italic">No connections yet</p>
              ) : (
                <div className="space-y-1">
                  {connections.granted.map((item) => {
                    const agentId = selectedNode.type === "agent" ? selectedNode.data.id : item.id;
                    const sourceId = selectedNode.type === "agent" ? item.id : selectedNode.data.id;
                    return (
                      <div key={item.id} className="flex items-center gap-2 bg-stone-50 rounded px-2 py-1.5 group">
                        <span className="text-xs">{selectedNode.type === "agent" ? "📄" : "🤖"}</span>
                        <span className="text-xs text-stone-700 flex-1 truncate">{item.name}</span>
                        <div
                          className="w-2 h-2 rounded-full group-hover:hidden"
                          style={{ backgroundColor: CLASSIFICATION_COLORS[item.classification || item.clearance] }}
                        />
                        <button
                          onClick={() => handleRevoke(agentId, sourceId)}
                          className="hidden group-hover:flex items-center gap-1 text-[10px] text-red-500 hover:text-red-600 transition-colors"
                        >
                          <X size={10} /> Revoke
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Recommendations — filter out already-granted pairs */}
            {recommendations.length > 0 && (() => {
              const grantedPairs = new Set();
              agents.forEach((a) => {
                (a.source_ids || []).forEach((sid) => {
                  grantedPairs.add(`${a.id}:${sid}`);
                });
              });
              const filteredRecs = recommendations
                .filter((rec) => !grantedPairs.has(`${rec.agent_id}:${rec.source_id}`))
                .sort((a, b) => b.relevance_score - a.relevance_score);
              if (filteredRecs.length === 0) return null;
              return (
              <div>
                <p className="text-[10px] uppercase tracking-wider text-stone-500 mb-2 flex items-center gap-1">
                  <Sparkles size={10} /> Recommendations ({filteredRecs.length})
                </p>
                <div className="space-y-1.5">
                  {filteredRecs
                    .map((rec) => {
                      const name = selectedNode.type === "source" ? rec.agent_name : rec.source_name;
                      const canGrant = rec.clearance_ok && rec.relevance_score >= 0.2;
                      return (
                        <div key={`${rec.agent_id}-${rec.source_id}`} className="bg-stone-50 rounded px-2 py-2 space-y-1">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                              <span className="text-xs">{selectedNode.type === "source" ? "🤖" : "📄"}</span>
                              <span className="text-xs text-stone-700 truncate">{name}</span>
                            </div>
                            <span className={`text-[10px] ${
                              rec.relevance_score >= 0.75 ? "text-green-400" :
                              rec.relevance_score >= 0.5 ? "text-yellow-400" : "text-stone-400"
                            }`}>
                              {(rec.relevance_score * 100).toFixed(0)}%
                            </span>
                          </div>
                          <div className="w-full h-1 bg-stone-200 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full ${
                                rec.relevance_score >= 0.75 ? "bg-green-500" :
                                rec.relevance_score >= 0.5 ? "bg-yellow-500" : "bg-stone-400"
                              }`}
                              style={{ width: `${Math.max(rec.relevance_score * 100, 5)}%` }}
                            />
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-[10px] text-stone-500">
                              {rec.status.replace(/_/g, " ")}
                            </span>
                            {canGrant ? (
                              <button
                                onClick={() => handleApprove(rec.agent_id, rec.source_id)}
                                className="flex items-center gap-1 bg-indigo-600 hover:bg-indigo-500 px-2 py-0.5 rounded text-[10px] font-medium transition-colors"
                              >
                                <Check size={10} /> Approve
                              </button>
                            ) : (
                              <span className="flex items-center gap-1 text-[10px] text-red-400">
                                <Lock size={10} /> No clearance
                              </span>
                            )}
                          </div>
                        </div>
                      );
                    })}
                </div>
              </div>
              );
            })()}
          </div>
        </div>
      )}
    </div>
  );
}
