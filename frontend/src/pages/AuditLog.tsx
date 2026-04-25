import { useState } from 'react'
import { Shield, Filter } from 'lucide-react'
import { useAuditLog } from '../hooks/useAudit'
import { formatLatency, cn } from '../lib/utils'
import { CACHE_TIER_CONFIG } from '../lib/constants'

export default function AuditLog() {
  const { data: logs } = useAuditLog()
  const [agentFilter, setAgentFilter] = useState<string>('all')

  const agents = [...new Set(logs?.map(l => l.agent_name) ?? [])]
  const filtered = agentFilter === 'all' ? logs : logs?.filter(l => l.agent_name === agentFilter)

  // Summary stats
  const totalServed = logs?.reduce((s, l) => s + l.atoms_served, 0) ?? 0
  const totalFiltered = logs?.reduce((s, l) => s + l.atoms_filtered, 0) ?? 0
  const l2Count = logs?.filter(l => l.cache_tier === 'L2').length ?? 0
  const l3Count = logs?.filter(l => l.cache_tier === 'L3').length ?? 0

  return (
    <div>
      <div className="mb-6 flex items-center gap-3">
        <Shield className="h-6 w-6 text-zinc-400" />
        <h2 className="text-2xl font-bold text-white">Audit Trail</h2>
      </div>

      {/* Summary */}
      <div className="mb-6 grid grid-cols-4 gap-4">
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4">
          <p className="text-xs text-zinc-500">Total Queries</p>
          <p className="mt-1 text-2xl font-bold text-white">{logs?.length ?? 0}</p>
        </div>
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4">
          <p className="text-xs text-zinc-500">Atoms Served</p>
          <p className="mt-1 text-2xl font-bold text-white">{totalServed}</p>
        </div>
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4">
          <p className="text-xs text-zinc-500">Atoms Filtered (ACL)</p>
          <p className="mt-1 text-2xl font-bold text-rose-400">{totalFiltered}</p>
        </div>
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4">
          <p className="text-xs text-zinc-500">Cache Split</p>
          <p className="mt-1 text-sm">
            <span className="text-green-400 font-semibold">{l2Count} L2</span>
            <span className="text-zinc-600 mx-2">/</span>
            <span className="text-yellow-400 font-semibold">{l3Count} L3</span>
          </p>
        </div>
      </div>

      {/* Filter */}
      <div className="mb-4 flex items-center gap-3">
        <Filter className="h-4 w-4 text-zinc-500" />
        <select
          value={agentFilter}
          onChange={e => setAgentFilter(e.target.value)}
          className="rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-xs text-zinc-300 outline-none"
        >
          <option value="all">All Agents</option>
          {agents.map(a => <option key={a} value={a}>{a}</option>)}
        </select>
      </div>

      {/* Table */}
      <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-800 text-left text-xs font-medium uppercase tracking-wider text-zinc-500">
              <th className="px-4 py-3">Time</th>
              <th className="px-4 py-3">Agent</th>
              <th className="px-4 py-3">Query</th>
              <th className="px-4 py-3 text-right">Served</th>
              <th className="px-4 py-3 text-right">Filtered</th>
              <th className="px-4 py-3 text-center">Tier</th>
              <th className="px-4 py-3 text-right">Latency</th>
            </tr>
          </thead>
          <tbody>
            {filtered?.map(log => {
              const tier = CACHE_TIER_CONFIG[log.cache_tier]
              return (
                <tr key={log.id} className="border-b border-zinc-800/50 transition-colors hover:bg-zinc-800/30">
                  <td className="px-4 py-3 text-xs text-zinc-500 font-mono">
                    {new Date(log.timestamp).toLocaleTimeString()}
                  </td>
                  <td className="px-4 py-3 text-xs text-zinc-300">{log.agent_name}</td>
                  <td className="px-4 py-3 text-xs text-zinc-300 max-w-xs truncate">"{log.query}"</td>
                  <td className="px-4 py-3 text-xs text-right text-zinc-300">{log.atoms_served}</td>
                  <td className={cn('px-4 py-3 text-xs text-right', log.atoms_filtered > 0 ? 'text-rose-400' : 'text-zinc-500')}>
                    {log.atoms_filtered}
                  </td>
                  <td className="px-4 py-3 text-center">
                    <span className={cn('rounded-md px-2 py-0.5 text-[10px] font-medium', tier.bg, tier.color)}>
                      {log.cache_tier}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs text-right font-mono text-zinc-400">
                    {formatLatency(log.latency_ms)}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* Access Denied Breakdown */}
      <div className="mt-6 rounded-xl border border-zinc-800 bg-zinc-900/50 p-5">
        <h3 className="mb-4 text-sm font-semibold text-white">Access Denied Breakdown (last 24h)</h3>
        <div className="space-y-3">
          {[
            { reason: 'Role mismatch', pct: 67, color: 'bg-rose-500' },
            { reason: 'Classification level', pct: 28, color: 'bg-amber-500' },
            { reason: 'Domain irrelevant', pct: 5, color: 'bg-zinc-500' },
          ].map(item => (
            <div key={item.reason} className="flex items-center gap-3">
              <span className="w-36 text-xs text-zinc-400">{item.reason}</span>
              <div className="flex-1">
                <div className="h-4 rounded-full bg-zinc-800">
                  <div
                    className={cn('h-4 rounded-full transition-all', item.color)}
                    style={{ width: `${item.pct}%`, opacity: 0.6 }}
                  />
                </div>
              </div>
              <span className="w-10 text-right text-xs font-medium text-zinc-300">{item.pct}%</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
