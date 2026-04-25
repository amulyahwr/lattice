import { useState } from 'react'
import { Plus, X } from 'lucide-react'
import { useAgents } from '../hooks/useAgents'
import { formatNumber, formatLatency, formatPercent, cn } from '../lib/utils'
import { ROLES, type Role } from '../lib/types'
import { ROLE_COLORS } from '../lib/constants'
import AccessMask from '../components/atoms/AccessMask'

export default function Agents() {
  const { data: agents } = useAgents()
  const [showCreate, setShowCreate] = useState(false)

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h2 className="text-2xl font-bold text-white">Agents</h2>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-blue-500"
        >
          <Plus className="h-4 w-4" />
          Create Agent
        </button>
      </div>

      <div className="grid grid-cols-2 gap-4">
        {agents?.map(agent => (
          <div key={agent.id} className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-5 transition-colors hover:border-zinc-700">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-2">
                <span className="text-lg">🤖</span>
                <h3 className="text-sm font-semibold text-white">{agent.name}</h3>
              </div>
              <span className="rounded-md bg-zinc-800 px-2 py-0.5 text-[10px] text-zinc-400">
                {formatNumber(agent.max_tokens)} tokens
              </span>
            </div>

            <p className="mt-2 text-xs text-zinc-400 leading-relaxed">{agent.purpose}</p>

            <div className="mt-3 flex flex-wrap gap-1.5">
              {agent.domains.map(d => (
                <span key={d} className="rounded-md bg-zinc-800 px-2 py-0.5 text-[10px] text-zinc-400">{d}</span>
              ))}
            </div>

            <div className="mt-4">
              <p className="mb-1.5 text-[10px] font-medium uppercase tracking-wider text-zinc-600">Access Mask</p>
              <AccessMask mask={agent.role_mask} />
            </div>

            <div className="mt-4 grid grid-cols-3 gap-3 border-t border-zinc-800 pt-4">
              <div>
                <p className="text-[10px] text-zinc-600">Queries</p>
                <p className="text-sm font-semibold text-white">{formatNumber(agent.query_count ?? 0)}</p>
              </div>
              <div>
                <p className="text-[10px] text-zinc-600">Avg Latency</p>
                <p className="text-sm font-semibold text-white">{formatLatency(agent.avg_latency ?? 0)}</p>
              </div>
              <div>
                <p className="text-[10px] text-zinc-600">Cache Hit</p>
                <p className="text-sm font-semibold text-white">{formatPercent(agent.cache_hit_rate ?? 0)}</p>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Create Agent Modal */}
      {showCreate && <CreateAgentModal onClose={() => setShowCreate(false)} />}
    </div>
  )
}

function CreateAgentModal({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState('')
  const [purpose, setPurpose] = useState('')
  const [selectedDomains, setSelectedDomains] = useState<string[]>([])
  const [selectedRoles, setSelectedRoles] = useState<Role[]>([])
  const [maxTokens, setMaxTokens] = useState(4000)

  const domains = ['sales', 'finance', 'engineering', 'hr', 'legal', 'product', 'marketing', 'operations']

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-xl border border-zinc-800 bg-zinc-900 p-6 shadow-2xl">
        <div className="mb-5 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-white">Create Agent</h3>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="mb-1.5 block text-xs font-medium text-zinc-400">Name</label>
            <input
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="e.g. Sales Assistant"
              className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-white placeholder-zinc-500 outline-none focus:border-blue-500/50"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-xs font-medium text-zinc-400">Purpose</label>
            <textarea
              value={purpose}
              onChange={e => setPurpose(e.target.value)}
              placeholder="What does this agent do?"
              rows={2}
              className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-white placeholder-zinc-500 outline-none focus:border-blue-500/50"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-xs font-medium text-zinc-400">Domains</label>
            <div className="flex flex-wrap gap-2">
              {domains.map(d => (
                <button
                  key={d}
                  onClick={() => setSelectedDomains(prev =>
                    prev.includes(d) ? prev.filter(x => x !== d) : [...prev, d]
                  )}
                  className={cn(
                    'rounded-md border px-2.5 py-1 text-xs font-medium transition-colors',
                    selectedDomains.includes(d)
                      ? 'border-blue-500/30 bg-blue-500/10 text-blue-400'
                      : 'border-zinc-700 bg-zinc-800 text-zinc-400 hover:border-zinc-600',
                  )}
                >
                  {d}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="mb-1.5 block text-xs font-medium text-zinc-400">Role Mask</label>
            <div className="flex flex-wrap gap-2">
              {ROLES.map(role => (
                <button
                  key={role}
                  onClick={() => setSelectedRoles(prev =>
                    prev.includes(role) ? prev.filter(x => x !== role) : [...prev, role]
                  )}
                  className={cn(
                    'rounded-md border px-2.5 py-1 text-xs font-medium transition-colors',
                    selectedRoles.includes(role)
                      ? 'border-opacity-50 text-white'
                      : 'border-zinc-700 bg-zinc-800 text-zinc-400 hover:border-zinc-600',
                  )}
                  style={selectedRoles.includes(role) ? {
                    backgroundColor: ROLE_COLORS[role] + '20',
                    borderColor: ROLE_COLORS[role] + '50',
                    color: ROLE_COLORS[role],
                  } : undefined}
                >
                  {role}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="mb-1.5 block text-xs font-medium text-zinc-400">Token Budget</label>
            <input
              type="number"
              value={maxTokens}
              onChange={e => setMaxTokens(Number(e.target.value))}
              className="w-32 rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-white outline-none focus:border-blue-500/50"
            />
          </div>
        </div>

        <div className="mt-6 flex justify-end gap-3">
          <button
            onClick={onClose}
            className="rounded-lg border border-zinc-700 bg-zinc-800 px-4 py-2 text-sm text-zinc-300 transition-colors hover:bg-zinc-700"
          >
            Cancel
          </button>
          <button
            onClick={onClose}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500"
          >
            Create Agent
          </button>
        </div>
      </div>
    </div>
  )
}
