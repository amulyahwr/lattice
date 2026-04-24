import { useState, useEffect } from "react";
import { Upload, Search, Shield, Database, Trash2, Plus, Key } from "lucide-react";
import * as api from "./api";

function App() {
  const [tab, setTab] = useState("search");
  const [sources, setSources] = useState([]);
  const [agents, setAgents] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState(null);
  const [selectedAgent, setSelectedAgent] = useState(null);
  const [searching, setSearching] = useState(false);
  const [newAgentName, setNewAgentName] = useState("");
  const [error, setError] = useState(null);

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
      await api.uploadPDF(file);
      await refresh();
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
    if (!newAgentName.trim()) return;
    setError(null);
    try {
      const agent = await api.createAgent(newAgentName);
      setNewAgentName("");
      await refresh();
      setSelectedAgent(agent);
    } catch (e) {
      setError(e.message);
    }
  };

  const handleGrant = async (agentId, sourceId) => {
    try {
      await api.grantAccess(agentId, sourceId);
      setError(null);
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
            <div className="w-8 h-8 bg-indigo-600 rounded-lg flex items-center justify-center font-bold text-sm">
              L
            </div>
            <h1 className="text-xl font-semibold tracking-tight">Lattice</h1>
            <span className="text-xs text-gray-500 bg-gray-800 px-2 py-0.5 rounded-full">MVP</span>
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

        {/* Search Tab */}
        {tab === "search" && (
          <div className="space-y-6">
            <div className="flex gap-3">
              <select
                value={selectedAgent?.id || ""}
                onChange={(e) => setSelectedAgent(agents.find((a) => a.id === e.target.value))}
                className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none"
              >
                {agents.map((a) => (
                  <option key={a.id} value={a.id}>{a.name}</option>
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

            {searchResults && (
              <div className="space-y-3">
                <p className="text-sm text-gray-400">
                  {searchResults.total} results for "<span className="text-gray-200">{searchResults.query}</span>"
                  as <span className="text-indigo-400">{searchResults.agent}</span>
                </p>
                {searchResults.results.map((r, i) => (
                  <div key={r.chunk_id} className="bg-gray-900 border border-gray-800 rounded-lg p-4">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-mono text-gray-500">#{i + 1}</span>
                        <span className="text-sm font-medium text-indigo-400">{r.source_name}</span>
                        <span className="text-xs bg-gray-800 text-gray-400 px-2 py-0.5 rounded">{r.source_type}</span>
                      </div>
                      <span className="text-xs text-gray-500">
                        relevance: <span className="text-green-400">{(r.relevance_score * 100).toFixed(1)}%</span>
                      </span>
                    </div>
                    <p className="text-sm text-gray-300 leading-relaxed">{r.content}</p>
                  </div>
                ))}
              </div>
            )}

            {!searchResults && (
              <div className="text-center py-16 text-gray-500">
                <Search size={48} className="mx-auto mb-4 opacity-30" />
                <p>Search across your connected data sources</p>
                <p className="text-sm mt-1">Select an agent, type a query, and hit search</p>
              </div>
            )}
          </div>
        )}

        {/* Sources Tab */}
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
                <p className="text-sm mt-1">Upload a PDF to get started</p>
              </div>
            ) : (
              <div className="space-y-2">
                {sources.map((s) => (
                  <div key={s.id} className="flex items-center justify-between bg-gray-900 border border-gray-800 rounded-lg p-4">
                    <div>
                      <p className="font-medium">{s.name}</p>
                      <p className="text-sm text-gray-400">{s.source_type} · {s.chunk_count} chunks</p>
                    </div>
                    <button
                      onClick={() => handleDelete(s.id)}
                      className="text-gray-500 hover:text-red-400 transition-colors"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Agents Tab */}
        {tab === "agents" && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-medium">Agents & Access Control</h2>
            </div>

            <div className="flex gap-3">
              <input
                type="text"
                placeholder="New agent name..."
                value={newAgentName}
                onChange={(e) => setNewAgentName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleCreateAgent()}
                className="flex-1 bg-gray-900 border border-gray-700 rounded-lg px-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none"
              />
              <button
                onClick={handleCreateAgent}
                className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 px-4 py-2.5 rounded-lg text-sm font-medium transition-colors"
              >
                <Plus size={16} /> Create Agent
              </button>
            </div>

            {agents.map((agent) => (
              <div key={agent.id} className="bg-gray-900 border border-gray-800 rounded-lg p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="font-medium">{agent.name}</h3>
                  <div className="flex items-center gap-2 text-xs text-gray-500">
                    <Key size={12} />
                    <code className="bg-gray-800 px-2 py-0.5 rounded">{agent.api_key.slice(0, 12)}...</code>
                  </div>
                </div>
                {sources.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {sources.map((s) => (
                      <button
                        key={s.id}
                        onClick={() => handleGrant(agent.id, s.id)}
                        className="text-xs bg-gray-800 hover:bg-indigo-600 px-3 py-1.5 rounded-md transition-colors"
                      >
                        + Grant: {s.name}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))}

            {agents.length === 0 && (
              <div className="text-center py-16 text-gray-500">
                <Shield size={48} className="mx-auto mb-4 opacity-30" />
                <p>No agents yet</p>
                <p className="text-sm mt-1">Create an agent to start managing access</p>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
