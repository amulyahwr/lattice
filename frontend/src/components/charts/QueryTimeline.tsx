import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

interface QueryTimelineProps {
  data: { hour: string; l3: number }[];
}

export default function QueryTimeline({ data }: QueryTimelineProps) {
  return (
    <div className="rounded-xl border border-[#D4BFA8] bg-[#FFF5E6]/50 p-5">
      <h3 className="mb-4 text-sm font-semibold text-[#3D2817]">
        Queries (last 24h)
      </h3>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data} margin={{ left: -10 }}>
          <XAxis
            dataKey="hour"
            tick={{ fill: "#71717a", fontSize: 10 }}
            axisLine={{ stroke: "#27272a" }}
            tickLine={false}
            interval={3}
          />
          <YAxis
            tick={{ fill: "#71717a", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#18181b",
              border: "1px solid #3f3f46",
              borderRadius: "8px",
              fontSize: 12,
            }}
          />
          <Line
            type="monotone"
            dataKey="l3"
            name="🔍 Vector Search"
            stroke="#3B82F6"
            strokeWidth={2}
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
