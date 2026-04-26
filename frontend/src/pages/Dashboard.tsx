import { Atom, Layers, Bot, Gauge } from "lucide-react";
import { useStats, useActivity, useQueryTimeline } from "../hooks/useStats";
import { formatNumber, formatPercent, timeAgo, cn } from "../lib/utils";
import { CACHE_TIER_CONFIG } from "../lib/constants";
import AtomsByKind from "../components/charts/AtomsByKind";
import QueryTimeline from "../components/charts/QueryTimeline";

const statCards = [
  {
    key: "total_atoms",
    label: "Total Atoms",
    icon: Atom,
    format: formatNumber,
  },
  {
    key: "total_agents",
    label: "Active Agents",
    icon: Bot,
    format: formatNumber,
  },
] as const;

export default function Dashboard() {
  const { data: stats } = useStats();
  const { data: activity } = useActivity();
  const { data: timeline } = useQueryTimeline();

  return (
    <div>
      <h2 className="mb-6 text-2xl font-bold text-[#3D2817]">Dashboard</h2>

      {/* Stat Cards */}
      <div className="mb-6 grid grid-cols-4 gap-4">
        {statCards.map(({ key, label, icon: Icon, format }) => (
          <div
            key={key}
            className="rounded-xl border border-[#D4BFA8] bg-[#FFF5E6]/50 p-5"
          >
            <div className="flex items-center justify-between">
              <p className="text-xs font-medium uppercase tracking-wider text-[#8B7355]">
                {label}
              </p>
              <Icon className="h-4 w-4 text-[#9B8365]" />
            </div>
            <p className="mt-2 text-3xl font-bold text-[#3D2817]">
              {stats ? format(stats[key] as number) : "—"}
            </p>
          </div>
        ))}
      </div>

      {/* Charts */}
      <div className="mb-6 grid grid-cols-2 gap-4">
        {stats && <AtomsByKind data={stats.atoms_by_kind} />}
        {timeline && <QueryTimeline data={timeline} />}
      </div>

      {/* Recent Activity */}
      <div className="rounded-xl border border-[#D4BFA8] bg-[#FFF5E6]/50 p-5">
        <h3 className="mb-4 text-sm font-semibold text-[#3D2817]">
          Recent Activity
        </h3>
        <div className="space-y-2">
          {activity?.map((event) => (
            <div
              key={event.id}
              className="flex items-center justify-between rounded-lg border border-[#D4BFA8]/50 px-4 py-3 text-sm"
            >
              <div className="flex items-center gap-3">
                <span
                  className={cn(
                    "h-2 w-2 rounded-full",
                    event.type === "query"
                      ? "bg-blue-500"
                      : event.type === "compile"
                        ? "bg-emerald-500"
                        : "bg-rose-500",
                  )}
                />
                <span className="text-[#5A4530]">{event.description}</span>
              </div>
              <div className="flex items-center gap-4 text-xs text-[#8B7355]">
                {event.cache_tier && event.cache_tier === "L3" && (
                  <span className={CACHE_TIER_CONFIG.L3.color}>
                    {event.cache_tier}
                  </span>
                )}
                {event.latency_ms != null && (
                  <span className="font-mono">{event.latency_ms}ms</span>
                )}
                <span>{timeAgo(event.timestamp)}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
