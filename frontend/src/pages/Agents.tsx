import { useState } from 'react'
import { Plus, X, Loader2 } from 'lucide-react'
import { useAgents, useCreateAgent } from '../hooks/useAgents'
import { formatNumber, formatLatency, formatPercent, cn } from '../lib/utils'
import { ROLES } from '../lib/types'
import { ROLE_COLORS } from '../lib/constants'

// All departments an agent can belong to (excludes 'public' which is a data tag, not a dept)
const DEPARTMENTS = ROLES.filter(r => r !== 'public')

function deptFromMask(roleMask: number): string | null {
  for (let i = 0; i < ROLES.length; i++) {
    if ((roleMask >> i) & 1) return ROLES[i]
  }
  return null
}

function maskFromDept(dept: string): number {
  const bit = ROLES.indexOf(dept as typeof ROLES[number])
  return bit >= 0 ? 1 << bit : 0
}

export default function Agents() {
  const { data: agents } = useAgents()
  const [showCreate, setShowCreate] = useState(false)

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h2 className="text-2xl font-bold text-[#3D2817]">Agents</h2>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-medium text-[#3D2817] transition-colors hover:bg-blue-500"
        >
          <Plus className="h-4 w-4" />
          Create Agent
        </button>
      </div>

      <div className="grid grid-cols-2 gap-4">
        {agents?.map(agent => {
          const dept = deptFromMask(agent.role_mask)
          const color = dept ? ROLE_COLORS[dept as keyof typeof ROLE_COLORS] : undefined
          return (
            <div key={agent.id} className="rounded-xl border border-[#D4BFA8] bg-[#FFF5E6]/50 p-5 transition-colors hover:border-[#C4A888]">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-lg">🤖</span>
                  <h3 className="text-sm font-semibold text-[#3D2817]">{agent.name}</h3>
                </div>
                {dept && (
                  <span
                    className="rounded-md px-2 py-0.5 text-[10px] font-medium capitalize"
                    style={{ background: `${color}20`, color }}
                  >
                    {dept}
                  </span>
                )}
              </div>

              <p className="mt-2 text-xs leading-relaxed text-[#6B5744]">{agent.purpose}</p>

              <div className="mt-4 grid grid-cols-3 gap-3 border-t border-[#D4BFA8] pt-4">
                <div>
                  <p className="text-[10px] text-[#9B8365]">Queries</p>
                  <p className="text-sm font-semibold text-[#3D2817]">{formatNumber(agent.query_count ?? 0)}</p>
                </div>
                <div>
                  <p className="text-[10px] text-[#9B8365]">Avg Latency</p>
                  <p className="text-sm font-semibold text-[#3D2817]">{formatLatency(agent.avg_latency ?? 0)}</p>
                </div>
                <div>
                  <p className="text-[10px] text-[#9B8365]">Cache Hit</p>
                  <p className="text-sm font-semibold text-[#3D2817]">{formatPercent(agent.cache_hit_rate ?? 0)}</p>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {showCreate && <CreateAgentModal onClose={() => setShowCreate(false)} />}
    </div>
  )
}

function CreateAgentModal({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState('')
  const [purpose, setPurpose] = useState('')
  const [department, setDepartment] = useState<string>('')
  const [maxTokens, setMaxTokens] = useState(4000)
  const createAgent = useCreateAgent()

  const handleCreate = () => {
    if (!name.trim() || !department) return
    createAgent.mutate(
      {
        name: name.trim(),
        purpose: purpose.trim(),
        domains: [department],
        role_mask: maskFromDept(department),
        max_tokens: maxTokens,
      },
      { onSuccess: onClose },
    )
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-xl border border-[#D4BFA8] bg-[#FFF5E6] p-6 shadow-2xl">
        <div className="mb-5 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-[#3D2817]">Create Agent</h3>
          <button onClick={onClose} className="text-[#8B7355] hover:text-[#5A4530]">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="mb-1.5 block text-xs font-medium text-[#6B5744]">Name</label>
            <input
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="e.g. Sales Assistant"
              className="w-full rounded-lg border border-[#C4A888] bg-[#E8D4BC] px-3 py-2 text-sm text-[#3D2817] placeholder-zinc-500 outline-none focus:border-blue-500/50"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-xs font-medium text-[#6B5744]">Purpose</label>
            <textarea
              value={purpose}
              onChange={e => setPurpose(e.target.value)}
              placeholder="What does this agent do?"
              rows={2}
              className="w-full rounded-lg border border-[#C4A888] bg-[#E8D4BC] px-3 py-2 text-sm text-[#3D2817] placeholder-zinc-500 outline-none focus:border-blue-500/50"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-xs font-medium text-[#6B5744]">Department</label>
            <p className="mb-2 text-[11px] leading-relaxed text-[#9B8365]">
              The department this agent belongs to. Lattice uses this to route context — the agent only receives atoms from its department and nothing else.
            </p>
            <div className="grid grid-cols-4 gap-2">
              {DEPARTMENTS.map(dept => {
                const color = ROLE_COLORS[dept as keyof typeof ROLE_COLORS]
                const active = department === dept
                return (
                  <button
                    key={dept}
                    onClick={() => setDepartment(dept)}
                    className={cn(
                      'rounded-lg border px-3 py-2 text-xs font-medium capitalize transition-colors',
                      active ? 'text-[#3D2817]' : 'border-[#C4A888] bg-[#E8D4BC] text-[#6B5744] hover:border-zinc-600',
                    )}
                    style={active ? {
                      backgroundColor: `${color}20`,
                      borderColor: `${color}50`,
                      color,
                    } : undefined}
                  >
                    {dept}
                  </button>
                )
              })}
            </div>
            {!department && (
              <p className="mt-1.5 text-[11px] text-amber-500/80">Select a department to continue.</p>
            )}
          </div>

          <div>
            <label className="mb-1.5 block text-xs font-medium text-[#6B5744]">
              Max Context Tokens
              <span className="ml-1.5 font-normal text-[#9B8365]">— token ceiling per response</span>
            </label>
            <input
              type="number"
              value={maxTokens}
              onChange={e => setMaxTokens(Number(e.target.value))}
              className="w-32 rounded-lg border border-[#C4A888] bg-[#E8D4BC] px-3 py-2 text-sm text-[#3D2817] outline-none focus:border-blue-500/50"
            />
          </div>
        </div>

        <div className="mt-6 flex justify-end gap-3">
          <button
            onClick={onClose}
            className="rounded-lg border border-[#C4A888] bg-[#E8D4BC] px-4 py-2 text-sm text-[#5A4530] transition-colors hover:bg-[#D4BFA8]"
          >
            Cancel
          </button>
          <button
            onClick={handleCreate}
            disabled={!name.trim() || !department || createAgent.isPending}
            className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-[#3D2817] transition-colors hover:bg-blue-500 disabled:opacity-60"
          >
            {createAgent.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            Create Agent
          </button>
        </div>
      </div>
    </div>
  )
}
