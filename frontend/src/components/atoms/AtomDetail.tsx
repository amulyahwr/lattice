import { useState } from 'react'
import { ArrowRight, ExternalLink, ChevronDown, ChevronRight } from 'lucide-react'
import type { AtomDetail } from '../../lib/types'
import { ATOM_BADGE_CLASSES, ATOM_ICONS, ROLE_COLORS, DOMAIN_COLORS } from '../../lib/constants'
import { cn, timeAgo } from '../../lib/utils'
import { ROLES } from '../../lib/types'
import AccessMask from './AccessMask'

interface AtomDetailProps {
  atom: AtomDetail
  onNavigate?: (atomId: string) => void
}

const RELATION_COLORS: Record<string, string> = {
  causal:       'text-amber-400 bg-amber-500/10 border-amber-500/20',
  temporal:     'text-blue-400 bg-blue-500/10 border-blue-500/20',
  hierarchical: 'text-purple-400 bg-purple-500/10 border-purple-500/20',
  topical:      'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
  contradicts:  'text-rose-400 bg-rose-500/10 border-rose-500/20',
}

export default function AtomDetail({ atom, onNavigate }: AtomDetailProps) {
  const [canonicalOpen, setCanonicalOpen] = useState(false)

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-2">
        <span className={cn('inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium', ATOM_BADGE_CLASSES[atom.kind])}>
          <span>{ATOM_ICONS[atom.kind]}</span>
          {atom.kind}
        </span>
        {atom.domain.map(d => {
          const c = DOMAIN_COLORS[d];
          return (
            <span
              key={d}
              style={c ? { background: `${c}18`, color: c, border: `1px solid ${c}40` } : undefined}
              className={`rounded-md px-2 py-0.5 text-[11px] font-medium${!c ? ' bg-[#E8D4BC] text-[#6B5744]' : ''}`}
            >
              {d}
            </span>
          );
        })}
        <span className="ml-auto font-mono text-[10px] text-[#9B8365]">
          {atom.id.slice(0, 8)}…
        </span>
      </div>

      {/* Content */}
      <div className="rounded-lg border border-[#D4BFA8] bg-[#FFF5E6]/50 p-4">
        <p className="text-sm leading-relaxed text-[#4A3520]">{atom.content}</p>
        {atom.raw_content && atom.raw_content !== atom.content && (
          <p className="mt-3 border-t border-[#D4BFA8] pt-3 text-xs leading-relaxed text-[#8B7355]">
            <span className="text-[#9B8365]">Raw: </span>{atom.raw_content}
          </p>
        )}
      </div>

      {/* Metadata grid */}
      <div className="grid grid-cols-2 gap-3 text-xs">
        <div className="rounded-lg border border-[#D4BFA8] bg-[#FFF5E6]/30 p-3">
          <p className="mb-1 text-[#8B7355]">Confidence</p>
          <p className="font-mono text-[#4A3520]">{(atom.confidence * 100).toFixed(0)}%</p>
        </div>
        <div className="rounded-lg border border-[#D4BFA8] bg-[#FFF5E6]/30 p-3">
          <p className="mb-1 text-[#8B7355]">Version</p>
          <p className="font-mono text-[#4A3520]">v{atom.version}</p>
        </div>
        <div className="rounded-lg border border-[#D4BFA8] bg-[#FFF5E6]/30 p-3">
          <p className="mb-1 text-[#8B7355]">Freshness</p>
          <p className="text-[#4A3520]">{atom.freshness ? timeAgo(atom.freshness) : '—'}</p>
        </div>
        <div className="rounded-lg border border-[#D4BFA8] bg-[#FFF5E6]/30 p-3">
          <p className="mb-1 text-[#8B7355]">Compiled</p>
          <p className="text-[#4A3520]">{atom.compiled_at ? timeAgo(atom.compiled_at) : '—'}</p>
        </div>
      </div>

      {/* Access mask */}
      <div className="rounded-lg border border-[#D4BFA8] bg-[#FFF5E6]/30 p-4">
        <p className="mb-2 text-xs text-[#8B7355]">Access Mask</p>
        <AccessMask mask={atom.access_mask} />
        <div className="mt-2 flex flex-wrap gap-1.5">
          {ROLES.map((role, i) => {
            const active = (atom.access_mask >> i) & 1
            if (!active) return null
            return (
              <span
                key={role}
                className="rounded px-1.5 py-0.5 text-[10px] font-medium"
                style={{ background: `${ROLE_COLORS[role]}20`, color: ROLE_COLORS[role] }}
              >
                {role}
              </span>
            )
          })}
        </div>
      </div>

      {/* Sources */}
      {atom.sources && atom.sources.length > 0 && (
        <div className="rounded-lg border border-[#D4BFA8] bg-[#FFF5E6]/30 p-4">
          <p className="mb-2 text-xs text-[#8B7355]">Source Lineage</p>
          <div className="space-y-2">
            {atom.sources.map(s => (
              <div key={s.source_id} className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-2">
                  <ExternalLink className="h-3 w-3 text-[#9B8365]" />
                  <span className="text-[#5A4530]">{s.source_name}</span>
                  <span className="text-[#9B8365]">{s.source_type}</span>
                </div>
                {s.is_primary && (
                  <span className="rounded bg-blue-500/10 px-1.5 py-0.5 text-[10px] text-blue-400 border border-blue-500/20">primary</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Canonical */}
      {atom.canonical && Object.keys(atom.canonical).length > 0 && (
        <div className="rounded-lg border border-[#D4BFA8] bg-[#FFF5E6]/30 p-4">
          <button
            onClick={() => setCanonicalOpen(o => !o)}
            className="flex w-full items-center gap-2 text-xs text-[#8B7355] hover:text-[#6B5744]"
          >
            {canonicalOpen
              ? <ChevronDown className="h-3.5 w-3.5 shrink-0" />
              : <ChevronRight className="h-3.5 w-3.5 shrink-0" />}
            Canonical Form
          </button>
          {canonicalOpen && (
            <pre className="mt-3 overflow-x-auto rounded border border-[#D4BFA8] bg-[#FFF5E6] p-3 font-mono text-[10px] leading-relaxed text-[#4A3520]">
              {JSON.stringify(atom.canonical, null, 2)}
            </pre>
          )}
        </div>
      )}

      {/* Links */}
      {atom.links && atom.links.length > 0 && (
        <div className="rounded-lg border border-[#D4BFA8] bg-[#FFF5E6]/30 p-4">
          <p className="mb-2 text-xs text-[#8B7355]">Links ({atom.links.length})</p>
          <div className="space-y-2">
            {atom.links.map((link, i) => (
              <button
                key={i}
                onClick={() => onNavigate?.(link.target_id)}
                className="flex w-full items-center justify-between rounded-lg border border-[#D4BFA8] bg-[#FFF5E6] px-3 py-2 text-left text-xs transition-colors hover:border-[#C4A888]"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <ArrowRight className="h-3 w-3 shrink-0 text-[#9B8365]" />
                  <span className="truncate font-mono text-[#6B5744]">{link.target_id.slice(0, 8)}…</span>
                </div>
                <span className={cn('shrink-0 rounded border px-1.5 py-0.5 text-[10px]', RELATION_COLORS[link.relation] ?? 'text-[#6B5744] bg-[#E8D4BC] border-[#C4A888]')}>
                  {link.relation}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
