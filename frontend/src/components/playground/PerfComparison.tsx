import type { ContextResult } from '../../lib/types'
import { CACHE_TIER_CONFIG } from '../../lib/constants'
import { formatLatency, formatNumber } from '../../lib/utils'

interface PerfComparisonProps {
  results: ContextResult[]
}

export default function PerfComparison({ results }: PerfComparisonProps) {
  if (results.length < 2) return null

  const fastest = Math.min(...results.map(r => r.latency_ms))
  const slowest = Math.max(...results.map(r => r.latency_ms))
  const speedup = slowest / fastest

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-5">
      <h3 className="mb-4 text-sm font-semibold text-white">Performance Comparison</h3>
      <div className="space-y-3">
        {results.map((result, i) => {
          const tier = CACHE_TIER_CONFIG[result.cache_tier]
          const width = Math.max(8, (result.latency_ms / slowest) * 100)
          return (
            <div key={i} className="flex items-center gap-4">
              <span className="w-36 text-xs font-medium text-zinc-300 truncate">{result.agent}</span>
              <div className="flex-1">
                <div className="flex items-center gap-3">
                  <div
                    className="h-6 rounded-md transition-all duration-500"
                    style={{
                      width: `${width}%`,
                      backgroundColor: result.cache_tier === 'L2' ? '#22C55E' : '#EAB308',
                      opacity: 0.7,
                    }}
                  />
                  <div className="flex items-center gap-3 text-xs text-zinc-400">
                    <span className={tier.color}>{result.cache_tier}</span>
                    <span className="font-mono">{formatLatency(result.latency_ms)}</span>
                    <span>{result.atoms_served} atoms</span>
                    <span>{formatNumber(result.total_tokens)} tok</span>
                  </div>
                </div>
              </div>
            </div>
          )
        })}
      </div>
      {speedup > 1.5 && (
        <div className="mt-4 rounded-lg bg-green-500/10 border border-green-500/20 px-4 py-2.5 text-xs text-green-400">
          ⚡ Speedup: {speedup.toFixed(1)}x ({CACHE_TIER_CONFIG[results.find(r => r.latency_ms === fastest)!.cache_tier].label} vs {CACHE_TIER_CONFIG[results.find(r => r.latency_ms === slowest)!.cache_tier].label})
        </div>
      )}
    </div>
  )
}
