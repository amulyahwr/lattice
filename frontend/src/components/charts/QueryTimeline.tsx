import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from 'recharts'

interface QueryTimelineProps {
  data: { hour: string; l2: number; l3: number }[]
}

export default function QueryTimeline({ data }: QueryTimelineProps) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-5">
      <h3 className="mb-4 text-sm font-semibold text-white">Queries (last 24h)</h3>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data} margin={{ left: -10 }}>
          <XAxis
            dataKey="hour"
            tick={{ fill: '#71717a', fontSize: 10 }}
            axisLine={{ stroke: '#27272a' }}
            tickLine={false}
            interval={3}
          />
          <YAxis
            tick={{ fill: '#71717a', fontSize: 11 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: '#18181b',
              border: '1px solid #3f3f46',
              borderRadius: '8px',
              fontSize: 12,
            }}
          />
          <Legend
            iconType="circle"
            iconSize={8}
            wrapperStyle={{ fontSize: 11, color: '#a1a1aa' }}
          />
          <Line
            type="monotone"
            dataKey="l2"
            name="⚡ L2 (Cache)"
            stroke="#22C55E"
            strokeWidth={2}
            dot={false}
          />
          <Line
            type="monotone"
            dataKey="l3"
            name="🔍 L3 (Index)"
            stroke="#EAB308"
            strokeWidth={2}
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
