import { useState, useEffect } from "react";
import {
  Upload, Search, Shield, Database, Trash2, Plus, Key, Sparkles,
  ChevronDown, ChevronUp, AlertTriangle, Check, X, Zap, Save, Pencil, Map,
} from "lucide-react";
import * as api from "./api";
import LatticeMap from "./components/LatticeMap";

const CLASSIFICATIONS = ["public", "internal", "confidential", "restricted"];

function Badge({ children, color = "gray" }) {
  const colors = {
    gray: "bg-stone-200 text-stone-600",
    indigo: "bg-indigo-100 text-indigo-700",
    green: "bg-emerald-100 text-emerald-700",
    yellow: "bg-amber-100 text-amber-700",
    red: "bg-red-100 text-red-700",
  };
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full ${colors[color]}`}>{children}</span>
  );
}

function classificationColor(c) {
  return { public: "green", internal: "gray", confidential: "yellow", restricted: "red" }[c] || "gray";
}

function App() {
  const [tab, setTab] = useState("map");
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
  const [recsFor, setRecsFor] = useState(null);
  const [selectedRecs, setSelectedRecs] = useState(new Set()); // set of "agentId:sourceId"

  // Expandable source details
  const [expandedSource, setExpandedSource] = useState(null);

  // Source editing
  const [editingSource, setEditingSource] = useState(null); // source id being edited
  const [sourceEdit, setSourceEdit] = useState({});
  const [savingSource, setSavingSource] = useState(false);

  // Agent editing
  const [editingAgent, setEditingAgent] = useState(null);
  const [agentEdit, setAgentEdit] = useState({});
  const [savingAgent, setSavingAgent] = useState(false);

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
      const recs = await api.getSourceRecommendations(source.id);
      if (recs.length > 0) {
        setRecommendations(recs);
        setRecsFor({ type: "source", id: source.id, name: source.name });
        setSelectedRecs(new Set());
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
      const recs = await api.getAgentRecommendations(agent.id);
      if (recs.length > 0) {
        setRecommendations(recs);
        setRecsFor({ type: "agent", id: agent.id, name: agent.name });
        setSelectedRecs(new Set());
      }
    } catch (e) {
      setError(e.message);
    }
    setCreatingAgent(false);
  };

  const handleDeleteAgent = async (agentId) => {
    try {
      await api.deleteAgent(agentId);
      if (selectedAgent?.id === agentId) setSelectedAgent(null);
      await refresh();
    } catch (e) {
      setError(e.message);
    }
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

  const startEditSource = (s) => {
    setEditingSource(s.id);
    setSourceEdit({
      classification: s.classification || "internal",
      domains: (s.domains || []).join(", "),
      owner: s.owner || "",
      org_scope: (s.org_scope || []).join(", "),
    });
  };

  const handleSaveSource = async (sourceId) => {
    setSavingSource(true);
    setError(null);
    try {
      await api.updateSource(sourceId, {
        classification: sourceEdit.classification,
        domains: sourceEdit.domains ? sourceEdit.domains.split(",").map((d) => d.trim()).filter(Boolean) : [],
        owner: sourceEdit.owner || null,
        org_scope: sourceEdit.org_scope ? sourceEdit.org_scope.split(",").map((d) => d.trim()).filter(Boolean) : [],
      });
      setEditingSource(null);
      await refresh();
    } catch (e) {
      setError(e.message);
    }
    setSavingSource(false);
  };

  const startEditAgent = (agent) => {
    setEditingAgent(agent.id);
    setAgentEdit({
      purpose: agent.purpose || "",
      clearance: agent.clearance || "internal",
      domains: (agent.domains || []).join(", "),
      deployed_by: agent.deployed_by || "",
      org_scope: (agent.org_scope || []).join(", "),
    });
  };

  const handleSaveAgent = async (agentId) => {
    setSavingAgent(true);
    setError(null);
    try {
      await api.updateAgent(agentId, {
        purpose: agentEdit.purpose || undefined,
        clearance: agentEdit.clearance,
        domains: agentEdit.domains ? agentEdit.domains.split(",").map((d) => d.trim()).filter(Boolean) : [],
        deployed_by: agentEdit.deployed_by || undefined,
        org_scope: agentEdit.org_scope ? agentEdit.org_scope.split(",").map((d) => d.trim()).filter(Boolean) : [],
      });
      setEditingAgent(null);
      await refresh();
    } catch (e) {
      setError(e.message);
    }
    setSavingAgent(false);
  };

  const showRecsForSource = async (source) => {
    try {
      const recs = await api.getSourceRecommendations(source.id);
      setRecommendations(recs);
      setRecsFor({ type: "source", id: source.id, name: source.name });
      setSelectedRecs(new Set());
    } catch (e) {
      setError(e.message);
    }
  };

  const showRecsForAgent = async (agent) => {
    try {
      const recs = await api.getAgentRecommendations(agent.id);
      setRecommendations(recs);
      setRecsFor({ type: "agent", id: agent.id, name: agent.name });
      setSelectedRecs(new Set());
    } catch (e) {
      setError(e.message);
    }
  };

  // Build set of already-granted agent:source pairs
  const grantedPairs = new Set();
  agents.forEach((a) => {
    (a.source_ids || []).forEach((sid) => {
      grantedPairs.add(`${a.id}:${sid}`);
    });
  });

  // Filter out already-granted recommendations
  const activeRecs = (recommendations || []).filter(
    (r) => !grantedPairs.has(`${r.agent_id}:${r.source_id}`)
  );
  const grantableRecs = activeRecs.filter((r) => r.clearance_ok && r.relevance_score >= 0.2);

  const toggleRec = (rec) => {
    const key = `${rec.agent_id}:${rec.source_id}`;
    setSelectedRecs((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const toggleAllRecs = () => {
    if (selectedRecs.size === grantableRecs.length) {
      setSelectedRecs(new Set());
    } else {
      setSelectedRecs(new Set(grantableRecs.map((r) => `${r.agent_id}:${r.source_id}`)));
    }
  };

  const [approvingRecs, setApprovingRecs] = useState(false);

  const approveSelected = async () => {
    if (selectedRecs.size === 0) return;
    setApprovingRecs(true);
    setError(null);
    try {
      for (const key of selectedRecs) {
        const [agentId, sourceId] = key.split(":");
        await api.grantAccess(agentId, sourceId);
      }
      setSelectedRecs(new Set());
      setRecommendations(null);
      setRecsFor(null);
      await refresh();
    } catch (e) {
      setError(e.message);
    }
    setApprovingRecs(false);
  };

  const tabs = [
    { id: "map", label: "Map", icon: Map },
    { id: "search", label: "Search", icon: Search },
    { id: "sources", label: "Sources", icon: Database },
    { id: "agents", label: "Agents", icon: Shield },
  ];

  return (
    <div className="min-h-screen bg-[#faf5f0] text-stone-800">
      {/* Header */}
      <header className="border-b border-stone-200 px-6 py-4 bg-white/60">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-indigo-600 rounded-lg flex items-center justify-center font-bold text-sm text-white">L</div>
            <h1 className="text-xl font-semibold tracking-tight text-stone-800">Lattice</h1>
            <Badge color="indigo">Trust Broker</Badge>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-8">
        {/* Error */}
        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
            {error}
            <button onClick={() => setError(null)} className="ml-2 underline">dismiss</button>
          </div>
        )}

        {/* Recommendations Panel */}
        {activeRecs.length > 0 && (
          <div className="mb-6 bg-indigo-50 border border-indigo-200 rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Sparkles size={16} className="text-indigo-600" />
                <span className="text-sm font-medium text-indigo-700">
                  Recommendations for {recsFor?.name}
                </span>
                <span className="text-xs text-stone-500">
                  {activeRecs.length} found · {selectedRecs.size} selected
                </span>
              </div>
              <div className="flex items-center gap-3">
                {selectedRecs.size > 0 && (
                  <button
                    onClick={approveSelected}
                    disabled={approvingRecs}
                    className="flex items-center gap-1 bg-emerald-600 hover:bg-emerald-500 text-white disabled:opacity-50 px-3 py-1.5 rounded-md text-xs font-medium transition-colors"
                  >
                    <Check size={12} /> {approvingRecs ? "Approving..." : `Approve ${selectedRecs.size}`}
                  </button>
                )}
                <button onClick={() => { setRecommendations(null); setRecsFor(null); setSelectedRecs(new Set()); }} className="text-stone-400 hover:text-stone-600">
                  <X size={16} />
                </button>
              </div>
            </div>

            {/* Select all header */}
            {grantableRecs.length > 0 && (
              <div className="flex items-center gap-3 mb-2 px-3 py-2 bg-stone-100 rounded-md">
                <input
                  type="checkbox"
                  checked={selectedRecs.size === grantableRecs.length && grantableRecs.length > 0}
                  onChange={toggleAllRecs}
                  className="w-4 h-4 rounded border-stone-300 text-indigo-600 focus:ring-indigo-500 cursor-pointer accent-indigo-600"
                />
                <span className="text-xs text-stone-500">
                  {selectedRecs.size === grantableRecs.length ? "Deselect all" : "Select all"} ({grantableRecs.length} grantable)
                </span>
              </div>
            )}

            <div className="space-y-2">
              {activeRecs
                .sort((a, b) => b.relevance_score - a.relevance_score)
                .map((rec) => {
                  const key = `${rec.agent_id}:${rec.source_id}`;
                  const isGrantable = rec.clearance_ok && rec.relevance_score >= 0.2;
                  const isSelected = selectedRecs.has(key);
                  return (
                    <div
                      key={key}
                      className={`flex items-center gap-3 rounded-lg p-3 transition-colors ${
                        isSelected ? "bg-indigo-50 border border-indigo-300" : "bg-white border border-stone-200"
                      }`}
                    >
                      {isGrantable ? (
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggleRec(rec)}
                          className="w-4 h-4 rounded border-stone-300 text-indigo-600 focus:ring-indigo-500 cursor-pointer accent-indigo-600 shrink-0"
                        />
                      ) : (
                        <div className="w-4 h-4 shrink-0" />
                      )}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-sm font-medium text-stone-800 truncate">
                            {recsFor?.type === "source" ? rec.agent_name : rec.source_name}
                          </span>
                          <Badge color={rec.status === "strong_match" ? "green" : rec.status === "moderate_match" ? "yellow" : rec.status === "needs_clearance_upgrade" ? "red" : "gray"}>
                            {rec.status.replace(/_/g, " ")}
                          </Badge>
                        </div>
                        <p className="text-xs text-stone-500 truncate">{rec.note}</p>
                      </div>
                      {/* Score bar */}
                      <div className="flex items-center gap-2 shrink-0">
                        <div className="w-20 h-1.5 bg-stone-200 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full ${
                              rec.relevance_score >= 0.75 ? "bg-green-500" :
                              rec.relevance_score >= 0.5 ? "bg-yellow-500" :
                              rec.relevance_score >= 0.2 ? "bg-stone-400" : "bg-red-400"
                            }`}
                            style={{ width: `${Math.max(rec.relevance_score * 100, 5)}%` }}
                          />
                        </div>
                        <span className="text-xs text-stone-500 w-10 text-right">
                          {(rec.relevance_score * 100).toFixed(0)}%
                        </span>
                      </div>
                    </div>
                  );
                })}
            </div>
          </div>
        )}

        {/* Tabs */}
        <div className="flex gap-1 mb-8 bg-stone-200/60 p-1 rounded-lg w-fit">
          {tabs.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                tab === id ? "bg-white text-stone-800 shadow-sm" : "text-stone-500 hover:text-stone-700"
              }`}
            >
              <Icon size={16} />
              {label}
            </button>
          ))}
        </div>

        {/* ── Map Tab ── */}
        {tab === "map" && (
          <div className="-mx-6 -mt-2" style={{ height: "calc(100vh - 200px)" }}>
            <LatticeMap
              sources={sources}
              agents={agents}
              onGrant={async (agentId, sourceId) => {
                await api.grantAccess(agentId, sourceId);
                await refresh();
              }}
              onRevoke={async (agentId, sourceId) => {
                await api.revokeAccess(agentId, sourceId);
                await refresh();
              }}
              onRefresh={refresh}
            />
          </div>
        )}

        {/* ── Search Tab ── */}
        {tab === "search" && (
          <div className="space-y-6">
            <div className="flex gap-3">
              <select
                value={selectedAgent?.id || ""}
                onChange={(e) => setSelectedAgent(agents.find((a) => a.id === e.target.value))}
                className="bg-white border border-stone-300 rounded-lg px-3 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none"
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
                className="flex-1 bg-white border border-stone-300 rounded-lg px-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none"
              />
              <button
                onClick={handleSearch}
                disabled={searching || !selectedAgent}
                className="bg-indigo-600 hover:bg-indigo-500 text-white disabled:opacity-50 px-5 py-2.5 rounded-lg text-sm font-medium transition-colors"
              >
                {searching ? "Searching..." : "Search"}
              </button>
            </div>

            {selectedAgent && (
              <div className="flex items-center gap-3 text-xs text-stone-400">
                <span>Agent: <span className="text-stone-700">{selectedAgent.name}</span></span>
                <Badge color={classificationColor(selectedAgent.clearance)}>{selectedAgent.clearance} clearance</Badge>
                {selectedAgent.purpose && (
                  <span className="text-stone-500">— {selectedAgent.purpose}</span>
                )}
              </div>
            )}

            {searchResults && (
              <div className="space-y-3">
                <p className="text-sm text-stone-500">
                  {searchResults.total} results for "<span className="text-stone-700">{searchResults.query}</span>"
                  {" "}as <span className="text-indigo-600">{searchResults.agent}</span>
                  {searchResults.agent_clearance && (
                    <> <Badge color={classificationColor(searchResults.agent_clearance)}>{searchResults.agent_clearance}</Badge></>
                  )}
                </p>
                {searchResults.results.map((r, i) => (
                  <div key={r.chunk_id} className="bg-white border border-stone-200 rounded-lg p-4">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-mono text-stone-400">#{i + 1}</span>
                        <span className="text-sm font-medium text-indigo-600">{r.source_name}</span>
                        <Badge>{r.source_type}</Badge>
                        {r.source_classification && (
                          <Badge color={classificationColor(r.source_classification)}>{r.source_classification}</Badge>
                        )}
                      </div>
                      <span className="text-xs text-stone-400">
                        relevance: <span className="text-emerald-600">{(r.relevance_score * 100).toFixed(1)}%</span>
                      </span>
                    </div>
                    <p className="text-sm text-stone-700 leading-relaxed">{r.content}</p>
                  </div>
                ))}
                {searchResults.total === 0 && (
                  <div className="text-center py-8 text-stone-400">
                    <AlertTriangle size={32} className="mx-auto mb-2 opacity-50" />
                    <p>No results. The agent may lack clearance or relevant source access.</p>
                  </div>
                )}
              </div>
            )}

            {!searchResults && (
              <div className="text-center py-16 text-stone-400">
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
              <label className={`flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2 rounded-lg text-sm font-medium cursor-pointer transition-colors ${uploading ? "opacity-50" : ""}`}>
                <Upload size={16} />
                {uploading ? "Uploading..." : "Upload PDF"}
                <input type="file" accept=".pdf" onChange={handleUpload} className="hidden" disabled={uploading} />
              </label>
            </div>

            {sources.length === 0 ? (
              <div className="text-center py-16 text-stone-400">
                <Database size={48} className="mx-auto mb-4 opacity-30" />
                <p>No sources yet</p>
                <p className="text-sm mt-1">Upload a PDF to get started — Lattice auto-generates its DNA</p>
              </div>
            ) : (
              <div className="space-y-2">
                {sources.map((s) => (
                  <div key={s.id} className="bg-white border border-stone-200 rounded-lg">
                    <div
                      className="flex items-center justify-between p-4 cursor-pointer"
                      onClick={() => { setExpandedSource(expandedSource === s.id ? null : s.id); setEditingSource(null); }}
                    >
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1">
                          <p className="font-medium">{s.name}</p>
                          <Badge>{s.source_type}</Badge>
                          <Badge color={classificationColor(s.classification)}>{s.classification}</Badge>
                          <span className="text-xs text-stone-400">{s.chunk_count} chunks</span>
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
                          className="text-indigo-600 hover:text-indigo-500 transition-colors"
                          title="Show recommendations"
                        >
                          <Sparkles size={16} />
                        </button>
                        <button
                          onClick={(e) => { e.stopPropagation(); handleDelete(s.id); }}
                          className="text-stone-400 hover:text-red-500 transition-colors"
                        >
                          <Trash2 size={16} />
                        </button>
                        {expandedSource === s.id ? <ChevronUp size={16} className="text-stone-400" /> : <ChevronDown size={16} className="text-stone-400" />}
                      </div>
                    </div>

                    {/* Expanded source details */}
                    {expandedSource === s.id && (
                      <div className="border-t border-stone-200 p-4 space-y-4">
                        {s.summary && (
                          <div>
                            <p className="text-xs font-medium text-stone-400 mb-1">Summary</p>
                            <p className="text-sm text-stone-700">{s.summary}</p>
                          </div>
                        )}

                        {editingSource === s.id ? (
                          /* Edit mode */
                          <div className="space-y-3 bg-stone-50 rounded-lg p-3">
                            <p className="text-xs font-medium text-indigo-600">Edit Source DNA</p>
                            <div className="grid grid-cols-2 gap-3">
                              <div>
                                <label className="text-xs text-stone-400 mb-1 block">Classification</label>
                                <select
                                  value={sourceEdit.classification}
                                  onChange={(e) => setSourceEdit({ ...sourceEdit, classification: e.target.value })}
                                  className="w-full bg-white border border-stone-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 outline-none"
                                >
                                  {CLASSIFICATIONS.map((c) => <option key={c} value={c}>{c}</option>)}
                                </select>
                              </div>
                              <div>
                                <label className="text-xs text-stone-400 mb-1 block">Owner</label>
                                <input
                                  type="text"
                                  placeholder="owner@company.com"
                                  value={sourceEdit.owner}
                                  onChange={(e) => setSourceEdit({ ...sourceEdit, owner: e.target.value })}
                                  className="w-full bg-white border border-stone-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 outline-none"
                                />
                              </div>
                            </div>
                            <div>
                              <label className="text-xs text-stone-400 mb-1 block">Domains (comma-separated)</label>
                              <input
                                type="text"
                                placeholder="finance, sales, engineering..."
                                value={sourceEdit.domains}
                                onChange={(e) => setSourceEdit({ ...sourceEdit, domains: e.target.value })}
                                className="w-full bg-white border border-stone-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 outline-none"
                              />
                            </div>
                            <div>
                              <label className="text-xs text-stone-400 mb-1 block">Org Scope (comma-separated)</label>
                              <input
                                type="text"
                                placeholder="finance-team, exec..."
                                value={sourceEdit.org_scope}
                                onChange={(e) => setSourceEdit({ ...sourceEdit, org_scope: e.target.value })}
                                className="w-full bg-white border border-stone-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 outline-none"
                              />
                            </div>
                            <div className="flex gap-2">
                              <button
                                onClick={() => handleSaveSource(s.id)}
                                disabled={savingSource}
                                className="flex items-center gap-1 bg-indigo-600 hover:bg-indigo-500 text-white disabled:opacity-50 px-3 py-1.5 rounded-md text-xs font-medium transition-colors"
                              >
                                <Save size={12} /> {savingSource ? "Saving..." : "Save"}
                              </button>
                              <button
                                onClick={() => setEditingSource(null)}
                                className="flex items-center gap-1 bg-stone-200 hover:bg-stone-300 px-3 py-1.5 rounded-md text-xs font-medium transition-colors"
                              >
                                Cancel
                              </button>
                            </div>
                          </div>
                        ) : (
                          /* View mode */
                          <>
                            <div className="grid grid-cols-3 gap-4">
                              <div>
                                <p className="text-xs font-medium text-stone-400 mb-1">Classification</p>
                                <Badge color={classificationColor(s.classification)}>{s.classification}</Badge>
                              </div>
                              <div>
                                <p className="text-xs font-medium text-stone-400 mb-1">Domains</p>
                                <div className="flex flex-wrap gap-1">
                                  {(s.domains || []).map((d) => <Badge key={d} color="indigo">{d}</Badge>)}
                                  {(!s.domains || s.domains.length === 0) && <span className="text-xs text-stone-500">none</span>}
                                </div>
                              </div>
                              <div>
                                <p className="text-xs font-medium text-stone-400 mb-1">Owner</p>
                                <span className="text-sm text-stone-500">{s.owner || "unset"}</span>
                              </div>
                            </div>
                            {s.org_scope && s.org_scope.length > 0 && (
                              <div>
                                <p className="text-xs font-medium text-stone-400 mb-1">Org Scope</p>
                                <div className="flex flex-wrap gap-1">
                                  {s.org_scope.map((o) => <Badge key={o}>{o}</Badge>)}
                                </div>
                              </div>
                            )}
                            {/* Agents with access to this source */}
                            {(() => {
                              const grantedAgents = agents.filter((a) => (a.source_ids || []).includes(s.id));
                              if (grantedAgents.length === 0) return null;
                              return (
                                <div>
                                  <p className="text-xs font-medium text-stone-400 mb-1">Agents with Access ({grantedAgents.length})</p>
                                  <div className="space-y-1">
                                    {grantedAgents.map((a) => (
                                      <div key={a.id} className="flex items-center justify-between bg-stone-50 rounded px-2 py-1.5 group">
                                        <div className="flex items-center gap-2">
                                          <span className="text-xs">🤖</span>
                                          <span className="text-xs text-stone-700">{a.name}</span>
                                          <Badge color={classificationColor(a.clearance)}>{a.clearance}</Badge>
                                        </div>
                                        <button
                                          onClick={async (e) => { e.stopPropagation(); await api.revokeAccess(a.id, s.id); await refresh(); }}
                                          className="hidden group-hover:flex items-center gap-1 text-[10px] text-red-500 hover:text-red-600"
                                        >
                                          <X size={10} /> Revoke
                                        </button>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              );
                            })()}
                            <button
                              onClick={(e) => { e.stopPropagation(); startEditSource(s); }}
                              className="flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-500 transition-colors"
                            >
                              <Pencil size={12} /> Edit Source Details
                            </button>
                          </>
                        )}
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
            <div className="bg-white border border-stone-200 rounded-lg p-4 space-y-3">
              <p className="text-sm font-medium text-stone-500">Create Agent</p>
              <div className="grid grid-cols-2 gap-3">
                <input
                  type="text"
                  placeholder="Agent name *"
                  value={newAgent.name}
                  onChange={(e) => setNewAgent({ ...newAgent, name: e.target.value })}
                  className="bg-stone-50 border border-stone-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 outline-none"
                />
                <input
                  type="text"
                  placeholder="Deployed by (email)"
                  value={newAgent.deployed_by}
                  onChange={(e) => setNewAgent({ ...newAgent, deployed_by: e.target.value })}
                  className="bg-stone-50 border border-stone-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 outline-none"
                />
              </div>
              <textarea
                placeholder="Purpose — what does this agent do? *"
                value={newAgent.purpose}
                onChange={(e) => setNewAgent({ ...newAgent, purpose: e.target.value })}
                rows={2}
                className="w-full bg-stone-50 border border-stone-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 outline-none resize-none"
              />
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="text-xs text-stone-400 mb-1 block">Clearance</label>
                  <select
                    value={newAgent.clearance}
                    onChange={(e) => setNewAgent({ ...newAgent, clearance: e.target.value })}
                    className="w-full bg-stone-50 border border-stone-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 outline-none"
                  >
                    {CLASSIFICATIONS.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
                <div className="col-span-2">
                  <label className="text-xs text-stone-400 mb-1 block">Domains (comma-separated)</label>
                  <input
                    type="text"
                    placeholder="finance, sales, engineering..."
                    value={newAgent.domains}
                    onChange={(e) => setNewAgent({ ...newAgent, domains: e.target.value })}
                    className="w-full bg-stone-50 border border-stone-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 outline-none"
                  />
                </div>
              </div>
              <button
                onClick={handleCreateAgent}
                disabled={creatingAgent || !newAgent.name.trim() || !newAgent.purpose.trim()}
                className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white disabled:opacity-50 px-4 py-2 rounded-lg text-sm font-medium transition-colors"
              >
                <Plus size={16} /> {creatingAgent ? "Creating..." : "Create Agent"}
              </button>
            </div>

            {/* Agent List */}
            {agents.map((agent) => (
              <div key={agent.id} className="bg-white border border-stone-200 rounded-lg p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="font-medium">{agent.name}</h3>
                      <Badge color={classificationColor(agent.clearance)}>{agent.clearance} clearance</Badge>
                    </div>
                    {editingAgent === agent.id ? null : (
                      agent.purpose && <p className="text-sm text-stone-500">{agent.purpose}</p>
                    )}
                  </div>
                  <div className="flex items-center gap-3">
                    <button
                      onClick={() => showRecsForAgent(agent)}
                      className="flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-500 transition-colors"
                    >
                      <Sparkles size={14} /> Recommendations
                    </button>
                    <div className="flex items-center gap-1 text-xs text-stone-400">
                      <Key size={12} />
                      <code className="bg-stone-100 px-2 py-0.5 rounded">{agent.api_key.slice(0, 12)}...</code>
                    </div>
                    <button
                      onClick={() => handleDeleteAgent(agent.id)}
                      className="text-stone-400 hover:text-red-500 transition-colors"
                      title="Delete agent"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                </div>

                {editingAgent === agent.id ? (
                  /* Edit mode */
                  <div className="space-y-3 bg-stone-50 rounded-lg p-3">
                    <p className="text-xs font-medium text-indigo-600">Edit Identity Profile</p>
                    <textarea
                      placeholder="Purpose — what does this agent do?"
                      value={agentEdit.purpose}
                      onChange={(e) => setAgentEdit({ ...agentEdit, purpose: e.target.value })}
                      rows={2}
                      className="w-full bg-white border border-stone-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 outline-none resize-none"
                    />
                    <div className="grid grid-cols-3 gap-3">
                      <div>
                        <label className="text-xs text-stone-400 mb-1 block">Clearance</label>
                        <select
                          value={agentEdit.clearance}
                          onChange={(e) => setAgentEdit({ ...agentEdit, clearance: e.target.value })}
                          className="w-full bg-white border border-stone-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 outline-none"
                        >
                          {CLASSIFICATIONS.map((c) => <option key={c} value={c}>{c}</option>)}
                        </select>
                      </div>
                      <div>
                        <label className="text-xs text-stone-400 mb-1 block">Domains</label>
                        <input
                          type="text"
                          value={agentEdit.domains}
                          onChange={(e) => setAgentEdit({ ...agentEdit, domains: e.target.value })}
                          className="w-full bg-white border border-stone-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 outline-none"
                        />
                      </div>
                      <div>
                        <label className="text-xs text-stone-400 mb-1 block">Deployed by</label>
                        <input
                          type="text"
                          value={agentEdit.deployed_by}
                          onChange={(e) => setAgentEdit({ ...agentEdit, deployed_by: e.target.value })}
                          className="w-full bg-white border border-stone-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 outline-none"
                        />
                      </div>
                    </div>
                    <div>
                      <label className="text-xs text-stone-400 mb-1 block">Org Scope (comma-separated)</label>
                      <input
                        type="text"
                        placeholder="finance-team, exec..."
                        value={agentEdit.org_scope}
                        onChange={(e) => setAgentEdit({ ...agentEdit, org_scope: e.target.value })}
                        className="w-full bg-white border border-stone-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 outline-none"
                      />
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleSaveAgent(agent.id)}
                        disabled={savingAgent}
                        className="flex items-center gap-1 bg-indigo-600 hover:bg-indigo-500 text-white disabled:opacity-50 px-3 py-1.5 rounded-md text-xs font-medium transition-colors"
                      >
                        <Save size={12} /> {savingAgent ? "Saving..." : "Save"}
                      </button>
                      <button
                        onClick={() => setEditingAgent(null)}
                        className="flex items-center gap-1 bg-stone-200 hover:bg-stone-300 px-3 py-1.5 rounded-md text-xs font-medium transition-colors"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  /* View mode */
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="flex flex-wrap gap-2">
                        {agent.domains && agent.domains.map((d) => (
                          <Badge key={d} color="indigo">{d}</Badge>
                        ))}
                        {agent.deployed_by && (
                          <span className="text-xs text-stone-400">deployed by {agent.deployed_by}</span>
                        )}
                      </div>
                      <button
                        onClick={() => startEditAgent(agent)}
                        className="flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-500 transition-colors"
                      >
                        <Pencil size={12} /> Edit Profile
                      </button>
                    </div>
                    {/* Granted sources */}
                    {(agent.source_ids || []).length > 0 && (
                      <div>
                        <p className="text-xs font-medium text-stone-400 mb-1">Granted Sources ({agent.source_ids.length})</p>
                        <div className="space-y-1">
                          {agent.source_ids.map((sid) => {
                            const source = sources.find((s) => s.id === sid);
                            if (!source) return null;
                            return (
                              <div key={sid} className="flex items-center justify-between bg-stone-50 rounded px-2 py-1.5 group">
                                <div className="flex items-center gap-2">
                                  <span className="text-xs">📄</span>
                                  <span className="text-xs text-stone-700">{source.name}</span>
                                  <Badge color={classificationColor(source.classification)}>{source.classification}</Badge>
                                </div>
                                <button
                                  onClick={async () => { await api.revokeAccess(agent.id, sid); await refresh(); }}
                                  className="hidden group-hover:flex items-center gap-1 text-[10px] text-red-500 hover:text-red-600"
                                >
                                  <X size={10} /> Revoke
                                </button>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}

            {agents.length === 0 && (
              <div className="text-center py-16 text-stone-400">
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
