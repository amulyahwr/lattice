import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { ATOM_COLORS } from '../../lib/constants'
import type { AtomKind } from '../../lib/types'

interface AtomsByKindProps {
  data: Record<string, number>
}

export default function AtomsByKind({ data }: AtomsByKindProps) {
  const chartData = Object.entries(data).map(([kind, count]) => ({ kind, count }))

  return (
    <div className="rounded-xl border border-[#D4BFA8] bg-[#FFF5E6]/50 p-5">
      <h3 className="mb-4 text-sm font-semibold text-[#3D2817]">Atoms by Kind</h3>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={chartData} margin={{ left: -10 }}>
          <XAxis
            dataKey="kind"
            tick={{ fill: '#71717a', fontSize: 11 }}
            axisLine={{ stroke: '#27272a' }}
            tickLine={false}
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
            labelStyle={{ color: '#e4e4e7' }}
          />
          <Bar dataKey="count" radius={[4, 4, 0, 0]}>
            {chartData.map((entry) => (
              <Cell key={entry.kind} fill={ATOM_COLORS[entry.kind as AtomKind] || '#64748B'} fillOpacity={0.8} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
