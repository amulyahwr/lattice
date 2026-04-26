import type { Atom } from '../../lib/types'
import { ATOM_BADGE_CLASSES, ATOM_ICONS } from '../../lib/constants'
import { cn } from '../../lib/utils'

interface AtomCardProps {
  atom: Atom
  compact?: boolean
}

export default function AtomCard({ atom, compact }: AtomCardProps) {
  return (
    <div className="rounded-lg border border-[#D4BFA8] bg-[#FFF5E6]/50 p-4 transition-colors hover:border-[#C4A888]">
      <div className="mb-2 flex items-center gap-2">
        <span className={cn('inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium', ATOM_BADGE_CLASSES[atom.kind])}>
          <span>{ATOM_ICONS[atom.kind]}</span>
          {atom.kind}
        </span>
        {atom.domain.map(d => (
          <span key={d} className="rounded-md bg-[#E8D4BC] px-1.5 py-0.5 text-[10px] text-[#6B5744]">
            {d}
          </span>
        ))}
      </div>
      <p className={cn('text-sm leading-relaxed text-[#5A4530]', compact && 'line-clamp-2')}>
        {atom.content}
      </p>
      <div className="mt-3 flex items-center gap-4 text-[11px] text-[#8B7355]">
        <span>confidence: {(atom.confidence * 100).toFixed(0)}%</span>
        {atom.source_name && <span>source: {atom.source_name}</span>}
        <span>v{atom.version}</span>
      </div>
    </div>
  )
}
