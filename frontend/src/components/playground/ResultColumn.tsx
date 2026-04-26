import type { ContextResult } from "../../lib/types";
import { CACHE_TIER_CONFIG } from "../../lib/constants";
import { formatLatency, formatNumber } from "../../lib/utils";
import AtomCard from "../atoms/AtomCard";
import { ShieldAlert, Zap } from "lucide-react";

interface ResultColumnProps {
  result: ContextResult;
}

export default function ResultColumn({ result }: ResultColumnProps) {
  const tier =
    result.cache_tier === "L3" ? CACHE_TIER_CONFIG.L3 : CACHE_TIER_CONFIG.L3;

  return (
    <div className="flex flex-col rounded-xl border border-[#D4BFA8] bg-[#FFF5E6]/50">
      {/* Header */}
      <div className="border-b border-[#D4BFA8] p-4">
        <div className="flex items-center justify-between">
          <h3 className="flex items-center gap-2 text-sm font-semibold text-[#3D2817]">
            <span>🤖</span>
            {result.agent}
          </h3>
          <span
            className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium ${tier.bg}`}
          >
            <span className={tier.color}>{tier.label}</span>
          </span>
        </div>

        {/* Stats row */}
        <div className="mt-3 flex items-center gap-4 text-xs text-[#6B5744]">
          <span className="flex items-center gap-1">
            <Zap className="h-3 w-3 text-yellow-500" />
            {formatLatency(result.latency_ms)}
          </span>
          <span>{result.atoms_served} atoms</span>
          <span>{formatNumber(result.total_tokens)} tokens</span>
          {result.atoms_filtered > 0 && (
            <span className="flex items-center gap-1 text-rose-400">
              <ShieldAlert className="h-3 w-3" />
              {result.atoms_filtered} filtered
            </span>
          )}
        </div>
      </div>

      {/* Atoms */}
      <div
        className="flex-1 space-y-3 overflow-y-auto p-4"
        style={{ maxHeight: "600px" }}
      >
        {result.atoms.map((atom) => (
          <AtomCard key={atom.id} atom={atom} />
        ))}
      </div>
    </div>
  );
}
