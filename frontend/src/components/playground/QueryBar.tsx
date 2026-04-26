import { Search, Plus, X } from 'lucide-react'
import type { AgentProfile } from '../../lib/types'
import { cn } from '../../lib/utils'

interface QueryBarProps {
  query: string
  onQueryChange: (q: string) => void
  agents: AgentProfile[]
  selectedAgentIds: string[]
  onToggleAgent: (id: string) => void
  onRun: () => void
  isLoading: boolean
}

export default function QueryBar({
  query,
  onQueryChange,
  agents,
  selectedAgentIds,
  onToggleAgent,
  onRun,
  isLoading,
}: QueryBarProps) {
  const unselected = agents.filter(a => !selectedAgentIds.includes(a.id))

  return (
    <div className="rounded-xl border border-[#D4BFA8] bg-[#FFF5E6]/80 p-5">
      <div className="flex gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#8B7355]" />
          <input
            type="text"
            value={query}
            onChange={e => onQueryChange(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && query.trim() && onRun()}
            placeholder="Ask a question... e.g. 'What's our Q2 outlook?'"
            className="w-full rounded-lg border border-[#C4A888] bg-[#E8D4BC] py-2.5 pl-10 pr-4 text-sm text-[#3D2817] placeholder-zinc-500 outline-none transition-colors focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/25"
          />
        </div>
        <button
          onClick={onRun}
          disabled={!query.trim() || selectedAgentIds.length === 0 || isLoading}
          className={cn(
            'rounded-lg px-5 py-2.5 text-sm font-medium transition-all',
            query.trim() && selectedAgentIds.length > 0 && !isLoading
              ? 'bg-blue-600 text-[#3D2817] hover:bg-blue-500'
              : 'cursor-not-allowed bg-[#E8D4BC] text-[#8B7355]',
          )}
        >
          {isLoading ? 'Running...' : 'Run Query'}
        </button>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <span className="text-xs text-[#8B7355]">Run as:</span>
        {selectedAgentIds.map(id => {
          const agent = agents.find(a => a.id === id)
          if (!agent) return null
          return (
            <button
              key={id}
              onClick={() => onToggleAgent(id)}
              className="flex items-center gap-1.5 rounded-lg border border-blue-500/30 bg-blue-500/10 px-3 py-1.5 text-xs font-medium text-blue-400 transition-colors hover:bg-blue-500/20"
            >
              <span>🤖</span>
              {agent.name}
              <X className="h-3 w-3 opacity-60" />
            </button>
          )
        })}
        {unselected.length > 0 && (
          <div className="relative group">
            <button className="flex items-center gap-1 rounded-lg border border-[#C4A888] bg-[#E8D4BC] px-3 py-1.5 text-xs text-[#6B5744] transition-colors hover:border-zinc-600 hover:text-[#5A4530]">
              <Plus className="h-3 w-3" />
              Add Agent
            </button>
            <div className="invisible absolute left-0 top-full z-10 mt-1 w-48 rounded-lg border border-[#C4A888] bg-[#E8D4BC] py-1 shadow-xl group-hover:visible">
              {unselected.map(agent => (
                <button
                  key={agent.id}
                  onClick={() => onToggleAgent(agent.id)}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-[#5A4530] transition-colors hover:bg-[#D4BFA8]"
                >
                  <span>🤖</span>
                  {agent.name}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
