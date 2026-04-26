import type { ContextResult } from "../../lib/types";
import { CACHE_TIER_CONFIG } from "../../lib/constants";
import { formatLatency, formatNumber } from "../../lib/utils";

interface PerfComparisonProps {
  results: ContextResult[];
}

export default function PerfComparison({ results }: PerfComparisonProps) {
  if (results.length < 2) return null;

  const withAtoms = results.filter((r) => r.atoms_served > 0);
  const noAccess = results.filter((r) => r.atoms_served === 0);

  const slowest = withAtoms.length
    ? Math.max(...withAtoms.map((r) => r.latency_ms))
    : 0;
  const fastest = withAtoms.length
    ? Math.min(...withAtoms.map((r) => r.latency_ms))
    : 0;
  const speedup = fastest > 0 ? slowest / fastest : 0;

  return (
    <div className="rounded-xl border border-[#D4BFA8] bg-[#FFF5E6]/50 p-5">
      <h3 className="mb-4 text-sm font-semibold text-[#3D2817]">
        Performance Comparison
      </h3>
      <div className="space-y-3">
        {withAtoms.map((result, i) => {
          const tier =
            result.cache_tier === "L3"
              ? CACHE_TIER_CONFIG.L3
              : CACHE_TIER_CONFIG.L3;
          const width =
            slowest > 0 ? Math.max(8, (result.latency_ms / slowest) * 100) : 8;
          return (
            <div key={i} className="flex items-center gap-4">
              <span className="w-36 shrink-0 truncate text-xs font-medium text-[#5A4530]">
                {result.agent}
              </span>
              <div className="flex-1">
                <div className="flex items-center gap-3">
                  <div
                    className="h-6 rounded-md transition-all duration-500"
                    style={{
                      width: `${width}%`,
                      backgroundColor:
                        result.cache_tier === "L2" ? "#22C55E" : "#EAB308",
                      opacity: 0.7,
                    }}
                  />
                  <div className="flex items-center gap-3 text-xs text-[#6B5744]">
                    <span className={tier.color}>{result.cache_tier}</span>
                    <span className="font-mono">
                      {formatLatency(result.latency_ms)}
                    </span>
                    <span>{result.atoms_served} atoms</span>
                    <span>{formatNumber(result.total_tokens)} tok</span>
                  </div>
                </div>
              </div>
            </div>
          );
        })}

        {noAccess.map((result, i) => (
          <div key={`na-${i}`} className="flex items-center gap-4">
            <span className="w-36 shrink-0 truncate text-xs font-medium text-[#8B7355]">
              {result.agent}
            </span>
            <div className="flex items-center gap-2 text-xs">
              <span className="rounded border border-[#C4A888] bg-[#E8D4BC] px-2 py-0.5 text-[#8B7355]">
                No accessible atoms — role mask excluded all content
              </span>
            </div>
          </div>
        ))}
      </div>

      {speedup > 1.5 && withAtoms.length >= 2 && (
        <div className="mt-4 rounded-lg border border-green-500/20 bg-green-500/10 px-4 py-2.5 text-xs text-green-400">
          ⚡ Speedup: {speedup.toFixed(1)}x (fastest vs slowest)
        </div>
      )}
    </div>
  );
}
