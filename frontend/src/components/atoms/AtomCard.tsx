import type { Atom } from '../../lib/types'
import { ATOM_BADGE_CLASSES, ATOM_ICONS } from '../../lib/constants'
import { cn } from '../../lib/utils'

interface AtomCardProps {
  atom: Atom
  compact?: boolean
}

export default function AtomCard({ atom, compact }: AtomCardProps) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 transition-colors hover:border-zinc-700">
      <div className="mb-2 flex items-center gap-2">
        <span className={cn('inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium', ATOM_BADGE_CLASSES[atom.kind])}>
          <span>{ATOM_ICONS[atom.kind]}</span>
          {atom.kind}
        </span>
        {atom.domain.map(d => (
          <span key={d} className="rounded-md bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-400">
            {d}
          </span>
        ))}
      </div>
      <p className={cn('text-sm leading-relaxed text-zinc-300', compact && 'line-clamp-2')}>
        {atom.content}
      </p>
      <div className="mt-3 flex items-center gap-4 text-[11px] text-zinc-500">
        <span>confidence: {(atom.confidence * 100).toFixed(0)}%</span>
        {atom.source_name && <span>source: {atom.source_name}</span>}
        <span>v{atom.version}</span>
      </div>
    </div>
  )
}
