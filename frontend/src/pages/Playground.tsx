import { useState } from 'react'
import { Sparkles } from 'lucide-react'
import { useAgents } from '../hooks/useAgents'
import { useContextQuery } from '../hooks/useContextQuery'
import QueryBar from '../components/playground/QueryBar'
import ResultColumn from '../components/playground/ResultColumn'
import PerfComparison from '../components/playground/PerfComparison'

const SUGGESTED_QUERIES = [
  "What's our Q2 outlook?",
  "How is the EMEA pipeline performing?",
  "What were the major incidents this quarter?",
  "What's the hiring plan for Q3?",
]

export default function Playground() {
  const { data: agents = [] } = useAgents()
  const [query, setQuery] = useState('')
  const [selectedAgentIds, setSelectedAgentIds] = useState<string[]>(['agent-1', 'agent-2'])
  const contextQuery = useContextQuery()

  const handleToggleAgent = (id: string) => {
    setSelectedAgentIds(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id],
    )
  }

  const handleRun = () => {
    if (!query.trim() || selectedAgentIds.length === 0) return
    contextQuery.mutate({ query, agentIds: selectedAgentIds })
  }

  return (
    <div>
      <div className="mb-6 flex items-center gap-3">
        <h2 className="text-2xl font-bold text-white">Context Playground</h2>
        <span className="rounded-md bg-blue-500/15 px-2 py-0.5 text-xs font-medium text-blue-400 border border-blue-500/25">
          ⭐ Hero Page
        </span>
      </div>

      <QueryBar
        query={query}
        onQueryChange={setQuery}
        agents={agents}
        selectedAgentIds={selectedAgentIds}
        onToggleAgent={handleToggleAgent}
        onRun={handleRun}
        isLoading={contextQuery.isPending}
      />

      {/* Suggested Queries */}
      {!contextQuery.data && (
        <div className="mt-6">
          <p className="mb-3 flex items-center gap-2 text-xs text-zinc-500">
            <Sparkles className="h-3 w-3" />
            Try a query:
          </p>
          <div className="flex flex-wrap gap-2">
            {SUGGESTED_QUERIES.map(q => (
              <button
                key={q}
                onClick={() => { setQuery(q); }}
                className="rounded-lg border border-zinc-800 bg-zinc-900/50 px-3 py-2 text-xs text-zinc-400 transition-colors hover:border-zinc-700 hover:text-zinc-300"
              >
                "{q}"
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Results */}
      {contextQuery.data && (
        <div className="mt-6 space-y-6">
          <div className={`grid gap-4 ${
            contextQuery.data.length === 1 ? 'grid-cols-1' :
            contextQuery.data.length === 2 ? 'grid-cols-2' :
            contextQuery.data.length === 3 ? 'grid-cols-3' :
            'grid-cols-2'
          }`}>
            {contextQuery.data.map((result, i) => (
              <ResultColumn key={i} result={result} />
            ))}
          </div>

          <PerfComparison results={contextQuery.data} />
        </div>
      )}

      {/* Loading State */}
      {contextQuery.isPending && (
        <div className="mt-12 flex flex-col items-center justify-center text-center">
          <div className="mb-4 h-8 w-8 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
          <p className="text-sm text-zinc-400">Querying context for {selectedAgentIds.length} agent{selectedAgentIds.length > 1 ? 's' : ''}...</p>
        </div>
      )}
    </div>
  )
}
