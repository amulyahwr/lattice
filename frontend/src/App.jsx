import { useState, useEffect } from "react";
import {
  Upload, Search, Shield, Database, Trash2, Plus, Key, Sparkles,
  ChevronDown, ChevronUp, AlertTriangle, Check, X, Zap,
} from "lucide-react";
import * as api from "./api";

const CLASSIFICATIONS = ["public", "internal", "confidential", "restricted"];

function Badge({ children, color = "gray" }) {
  const colors = {
    gray: "bg-gray-800 text-gray-400",
    indigo: "bg-indigo-900/50 text-indigo-300",
    green: "bg-green-900/50 text-green-300",
    yellow: "bg-yellow-900/50 text-yellow-300",
    red: "bg-red-900/50 text-red-300",
  };
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full ${colors[color]}`}>{children}</span>
  );
}

function classificationColor(c) {
  return { public: "green", internal: "gray", confidential: "yellow", restricted: "red" }[c] || "gray";
}

function App() {
  const [tab, setTab] = useState("search");
  const [sources, setSources] = useState([]);
  const [agents, setAgents] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState(null);
  const [selectedAgent, setSelectedAgent] = useState(null);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState(null);

  // Agent creation form
  const [newAgent, setNewAgent] = useState({ name: "", purpose: "", clearance: "internal", domains: "", deployed_by: "" });
  const [creatingAgent, setCreatingAgent] = useState(false);

  // Recommendations
  const [recommendations, setRecommendations] = useState(null);
  const [recsFor, setRecsFor] = useState(null); // { type: "source"|"agent", id, name }

  // Expandable source details
  const [expandedSource, setExpandedSource] = useState(null);

  const refresh = async () => {
    try {
      const [s, a] = await Promise.all([api.listSources(), api.listAgents()]);
      setSources(s);
      setAgents(a);
      if (!selectedAgent && a.length > 0) setSelectedAgent(a[0]);
    } catch (e) {
      setError(e.message);
    }
  };

  useEffect(() => { refresh(); }, []);

  const handleUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const source = await api.uploadPDF(file);
      await refresh();
      // Auto-show recommendations for the new source
      const recs = await api.getSourceRecommendations(source.id);
      if (recs.length > 0) {
        setRecommendations(recs);
        setRecsFor({ type: "source", id: source.id, name: source.name });
      }
    } catch (e) {
      setError(e.message);
    }
    setUploading(false);
  };

  const handleSearch = async () => {
    if (!searchQuery.trim() || !selectedAgent) return;
    setSearching(true);
    setError(null);
    try {
      const results = await api.search(searchQuery, selectedAgent.api_key);
      setSearchResults(results);
    } catch (e) {
      setError(e.message);
    }
    setSearching(false);
  };

  const handleCreateAgent = async () => {
    if (!newAgent.name.trim() || !newAgent.purpose.trim()) return;
    setCreatingAgent(true);
    setError(null);
    try {
      const agentData = {
        name: newAgent.name,
        purpose: newAgent.purpose,
        clearance: newAgent.clearance,
        domains: newAgent.domains ? newAgent.domains.split(",").map((d) => d.trim()).filter(Boolean) : [],
        deployed_by: newAgent.deployed_by || undefined,
      };
      const agent = await api.createAgent(agentData);
      setNewAgent({ name: "", purpose: "", clearance: "internal", domains: "", deployed_by: "" });
      await refresh();
      setSelectedAgent(agent);
      // Auto-show recommendations
      const recs = await api.getAgentRecommendations(agent.id);
      if (recs.length > 0) {
        setRecommendations(recs);
        setRecsFor({ type: "agent", id: agent.id, name: agent.name });
      }
    } catch (e) {
      setError(e.message);
    }
    setCreatingAgent(false);
  };

  const handleGrant = async (agentId, sourceId) => {
    try {
      await api.grantAccess(agentId, sourceId);
      await refresh();
    } catch (e) {
      setError(e.message);
    }
  };

  const handleDelete = async (sourceId) => {
    try {
      await api.deleteSource(sourceId);
      await refresh();
    } catch (e) {
      setError(e.message);
    }
  };

  const showRecsForSource = async (source) => {
    try {
      const recs = await api.getSourceRecommendations(source.id);
      setRecommendations(recs);
      setRecsFor({ type: "source", id: source.id, name: source.name });
    } catch (e) {
      setError(e.message);
    }
  };

  const showRecsForAgent = async (agent) => {
    try {
      const recs = await api.getAgentRecommendations(agent.id);
      setRecommendations(recs);
      setRecsFor({ type: "agent", id: agent.id, name: agent.name });
    } catch (e) {
      setError(e.message);
    }
  };

  const tabs = [
    { id: "search", label: "Search", icon: Search },
    { id: "sources", label: "Sources", icon: Database },
    { id: "agents", label: "Agents", icon: Shield },
  ];

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      {/* Header */}
      <header className="border-b border-gray-800 px-6 py-4">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-indigo-600 rounded-lg flex items-center justify-center font-bold text-sm">L</div>
            <h1 className="text-xl font-semibold tracking-tight">Lattice</h1>
            <Badge color="indigo">Trust Broker</Badge>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-8">
        {/* Error */}
        {error && (
          <div className="mb-4 p-3 bg-red-900/30 border border-red-800 rounded-lg text-red-300 text-sm">
            {error}
            <button onClick={() => setError(null)} className="ml-2 underline">dismiss</button>
          </div>
        )}

        {/* Recommendations Panel */}
        {recommendations && recommendations.length > 0 && (
          <div className="mb-6 bg-indigo-950/30 border border-indigo-800 rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Sparkles size={16} className="text-indigo-400" />
                <span className="text-sm font-medium text-indigo-300">
                  Recommendations for {recsFor?.name}
                </span>
              </div>
              <button onClick={() => { setRecommendations(null); setRecsFor(null); }} className="text-gray-500 hover:text-gray-300">
                <X size={16} />
              </button>
            </div>
            <div className="space-y-2">
              {recommendations.map((rec) => (
                <div key={`${rec.agent_id}-${rec.source_id}`} className="flex items-center justify-between bg-gray-900/50 rounded-lg p-3">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-sm font-medium">
                        {recsFor?.type === "source" ? rec.agent_name : rec.source_name}
                      </span>
                      <Badge color={rec.status === "strong_match" ? "green" : rec.status === "moderate_match" ? "yellow" : rec.status === "needs_clearance_upgrade" ? "red" : "gray"}>
                        {rec.status.replace(/_/g, " ")}
                      </Badge>
                      <span className="text-xs text-gray-500">
                        {(rec.relevance_score * 100).toFixed(0)}% match
                      </span>
                    </div>
                    <p className="text-xs text-gray-400">{rec.note}</p>
                  </div>
                  {rec.clearance_ok && rec.relevance_score >= 0.3 && (
                    <button
                      onClick={() => handleGrant(rec.agent_id, rec.source_id)}
                      className="ml-3 flex items-center gap-1 bg-indigo-600 hover:bg-indigo-500 px-3 py-1.5 rounded-md text-xs font-medium transition-colors"
                    >
                      <Check size={12} /> Grant
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Tabs */}
        <div className="flex gap-1 mb-8 bg-gray-900 p-1 rounded-lg w-fit">
          {tabs.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                tab === id ? "bg-gray-800 text-white" : "text-gray-400 hover:text-gray-200"
              }`}
            >
              <Icon size={16} />
              {label}
            </button>
          ))}
        </div>

        {/* ── Search Tab ── */}
        {tab === "search" && (
          <div className="space-y-6">
            <div className="flex gap-3">
              <select
                value={selectedAgent?.id || ""}
                onChange={(e) => setSelectedAgent(agents.find((a) => a.id === e.target.value))}
                className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none"
              >
                {agents.map((a) => (
                  <option key={a.id} value={a.id}>{a.name} ({a.clearance})</option>
                ))}
                {agents.length === 0 && <option>No agents — create one first</option>}
              </select>
              <input
                type="text"
                placeholder="Ask a question..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                className="flex-1 bg-gray-900 border border-gray-700 rounded-lg px-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none"
              />
              <button
                onClick={handleSearch}
                disabled={searching || !selectedAgent}
                className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 px-5 py-2.5 rounded-lg text-sm font-medium transition-colors"
              >
                {searching ? "Searching..." : "Search"}
              </button>
            </div>

            {selectedAgent && (
              <div className="flex items-center gap-3 text-xs text-gray-500">
                <span>Agent: <span className="text-gray-300">{selectedAgent.name}</span></span>
                <Badge color={classificationColor(selectedAgent.clearance)}>{selectedAgent.clearance} clearance</Badge>
                {selectedAgent.purpose && (
                  <span className="text-gray-600">— {selectedAgent.purpose}</span>
                )}
              </div>
            )}

            {searchResults && (
              <div className="space-y-3">
                <p className="text-sm text-gray-400">
                  {searchResults.total} results for "<span className="text-gray-200">{searchResults.query}</span>"
                  {" "}as <span className="text-indigo-400">{searchResults.agent}</span>
                  {searchResults.agent_clearance && (
                    <Badge color={classificationColor(searchResults.agent_clearance)}>{searchResults.agent_clearance}</Badge>
                  )}
                </p>
                {searchResults.results.map((r, i) => (
                  <div key={r.chunk_id} className="bg-gray-900 border border-gray-800 rounded-lg p-4">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-mono text-gray-500">#{i + 1}</span>
                        <span className="text-sm font-medium text-indigo-400">{r.source_name}</span>
                        <Badge>{r.source_type}</Badge>
                        {r.source_classification && (
                          <Badge color={classificationColor(r.source_classification)}>{r.source_classification}</Badge>
                        )}
                      </div>
                      <span className="text-xs text-gray-500">
                        relevance: <span className="text-green-400">{(r.relevance_score * 100).toFixed(1)}%</span>
                      </span>
                    </div>
                    <p className="text-sm text-gray-300 leading-relaxed">{r.content}</p>
                  </div>
                ))}
                {searchResults.total === 0 && (
                  <div className="text-center py-8 text-gray-500">
                    <AlertTriangle size={32} className="mx-auto mb-2 opacity-50" />
                    <p>No results. The agent may lack clearance or relevant source access.</p>
                  </div>
                )}
              </div>
            )}

            {!searchResults && (
              <div className="text-center py-16 text-gray-500">
                <Search size={48} className="mx-auto mb-4 opacity-30" />
                <p>Search across your connected data sources</p>
                <p className="text-sm mt-1">Access is computed dynamically based on agent identity + source DNA</p>
              </div>
            )}
          </div>
        )}

        {/* ── Sources Tab ── */}
        {tab === "sources" && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-medium">Data Sources</h2>
              <label className={`flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 px-4 py-2 rounded-lg text-sm font-medium cursor-pointer transition-colors ${uploading ? "opacity-50" : ""}`}>
                <Upload size={16} />
                {uploading ? "Uploading..." : "Upload PDF"}
                <input type="file" accept=".pdf" onChange={handleUpload} className="hidden" disabled={uploading} />
              </label>
            </div>

            {sources.length === 0 ? (
              <div className="text-center py-16 text-gray-500">
                <Database size={48} className="mx-auto mb-4 opacity-30" />
                <p>No sources yet</p>
                <p className="text-sm mt-1">Upload a PDF to get started — Lattice auto-generates its DNA</p>
              </div>
            ) : (
              <div className="space-y-2">
                {sources.map((s) => (
                  <div key={s.id} className="bg-gray-900 border border-gray-800 rounded-lg">
                    <div
                      className="flex items-center justify-between p-4 cursor-pointer"
                      onClick={() => setExpandedSource(expandedSource === s.id ? null : s.id)}
                    >
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1">
                          <p className="font-medium">{s.name}</p>
                          <Badge>{s.source_type}</Badge>
                          <Badge color={classificationColor(s.classification)}>{s.classification}</Badge>
                          <span className="text-xs text-gray-500">{s.chunk_count} chunks</span>
                        </div>
                        {s.domains && s.domains.length > 0 && (
                          <div className="flex gap-1 mt-1">
                            {s.domains.map((d) => (
                              <Badge key={d} color="indigo">{d}</Badge>
                            ))}
                          </div>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={(e) => { e.stopPropagation(); showRecsForSource(s); }}
                          className="text-indigo-400 hover:text-indigo-300 transition-colors"
                          title="Show recommendations"
                        >
                          <Sparkles size={16} />
                        </button>
                        <button
                          onClick={(e) => { e.stopPropagation(); handleDelete(s.id); }}
                          className="text-gray-500 hover:text-red-400 transition-colors"
                        >
                          <Trash2 size={16} />
                        </button>
                        {expandedSource === s.id ? <ChevronUp size={16} className="text-gray-500" /> : <ChevronDown size={16} className="text-gray-500" />}
                      </div>
                    </div>
                    {expandedSource === s.id && (
                      <div className="border-t border-gray-800 p-4 space-y-3">
                        {s.summary && (
                          <div>
                            <p className="text-xs font-medium text-gray-500 mb-1">Summary</p>
                            <p className="text-sm text-gray-300">{s.summary}</p>
                          </div>
                        )}
                        <div className="grid grid-cols-3 gap-4">
                          <div>
                            <p className="text-xs font-medium text-gray-500 mb-1">Classification</p>
                            <Badge color={classificationColor(s.classification)}>{s.classification}</Badge>
                          </div>
                          <div>
                            <p className="text-xs font-medium text-gray-500 mb-1">Domains</p>
                            <div className="flex flex-wrap gap-1">
                              {(s.domains || []).map((d) => <Badge key={d} color="indigo">{d}</Badge>)}
                              {(!s.domains || s.domains.length === 0) && <span className="text-xs text-gray-600">none</span>}
                            </div>
                          </div>
                          <div>
                            <p className="text-xs font-medium text-gray-500 mb-1">Owner</p>
                            <span className="text-sm text-gray-400">{s.owner || "unset"}</span>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ── Agents Tab ── */}
        {tab === "agents" && (
          <div className="space-y-6">
            <h2 className="text-lg font-medium">Agents & Identity Profiles</h2>

            {/* Create Agent Form */}
            <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 space-y-3">
              <p className="text-sm font-medium text-gray-400">Create Agent</p>
              <div className="grid grid-cols-2 gap-3">
                <input
                  type="text"
                  placeholder="Agent name *"
                  value={newAgent.name}
                  onChange={(e) => setNewAgent({ ...newAgent, name: e.target.value })}
                  className="bg-gray-950 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 outline-none"
                />
                <input
                  type="text"
                  placeholder="Deployed by (email)"
                  value={newAgent.deployed_by}
                  onChange={(e) => setNewAgent({ ...newAgent, deployed_by: e.target.value })}
                  className="bg-gray-950 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 outline-none"
                />
              </div>
              <textarea
                placeholder="Purpose — what does this agent do? *"
                value={newAgent.purpose}
                onChange={(e) => setNewAgent({ ...newAgent, purpose: e.target.value })}
                rows={2}
                className="w-full bg-gray-950 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 outline-none resize-none"
              />
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="text-xs text-gray-500 mb-1 block">Clearance</label>
                  <select
                    value={newAgent.clearance}
                    onChange={(e) => setNewAgent({ ...newAgent, clearance: e.target.value })}
                    className="w-full bg-gray-950 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 outline-none"
                  >
                    {CLASSIFICATIONS.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
                <div className="col-span-2">
                  <label className="text-xs text-gray-500 mb-1 block">Domains (comma-separated)</label>
                  <input
                    type="text"
                    placeholder="finance, sales, engineering..."
                    value={newAgent.domains}
                    onChange={(e) => setNewAgent({ ...newAgent, domains: e.target.value })}
                    className="w-full bg-gray-950 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 outline-none"
                  />
                </div>
              </div>
              <button
                onClick={handleCreateAgent}
                disabled={creatingAgent || !newAgent.name.trim() || !newAgent.purpose.trim()}
                className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 px-4 py-2 rounded-lg text-sm font-medium transition-colors"
              >
                <Plus size={16} /> {creatingAgent ? "Creating..." : "Create Agent"}
              </button>
            </div>

            {/* Agent List */}
            {agents.map((agent) => (
              <div key={agent.id} className="bg-gray-900 border border-gray-800 rounded-lg p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="font-medium">{agent.name}</h3>
                      <Badge color={classificationColor(agent.clearance)}>{agent.clearance} clearance</Badge>
                    </div>
                    {agent.purpose && (
                      <p className="text-sm text-gray-400">{agent.purpose}</p>
                    )}
                  </div>
                  <div className="flex items-center gap-3">
                    <button
                      onClick={() => showRecsForAgent(agent)}
                      className="flex items-center gap-1 text-xs text-indigo-400 hover:text-indigo-300 transition-colors"
                    >
                      <Sparkles size={14} /> Recommendations
                    </button>
                    <div className="flex items-center gap-1 text-xs text-gray-500">
                      <Key size={12} />
                      <code className="bg-gray-800 px-2 py-0.5 rounded">{agent.api_key.slice(0, 12)}...</code>
                    </div>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  {agent.domains && agent.domains.map((d) => (
                    <Badge key={d} color="indigo">{d}</Badge>
                  ))}
                  {agent.deployed_by && (
                    <span className="text-xs text-gray-500">deployed by {agent.deployed_by}</span>
                  )}
                </div>
              </div>
            ))}

            {agents.length === 0 && (
              <div className="text-center py-16 text-gray-500">
                <Shield size={48} className="mx-auto mb-4 opacity-30" />
                <p>No agents yet</p>
                <p className="text-sm mt-1">Create an agent with a purpose to get started</p>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
