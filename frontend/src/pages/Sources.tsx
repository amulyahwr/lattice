import { useState } from 'react'
import { Upload, FileText, ChevronDown, ChevronUp } from 'lucide-react'
import { useSources } from '../hooks/useSources'
import { timeAgo, cn } from '../lib/utils'
import { ATOM_BADGE_CLASSES } from '../lib/constants'
import PipelineStatus from '../components/compiler/PipelineStatus'
import type { AtomKind } from '../lib/types'

export default function Sources() {
  const { data: sources } = useSources()
  const [expandedId, setExpandedId] = useState<string | null>(null)

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h2 className="text-2xl font-bold text-white">Sources</h2>
        <button className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-blue-500">
          <Upload className="h-4 w-4" />
          Upload Source
        </button>
      </div>

      <div className="space-y-4">
        {sources?.map(source => {
          const expanded = expandedId === source.id
          return (
            <div
              key={source.id}
              className="rounded-xl border border-zinc-800 bg-zinc-900/50 transition-colors hover:border-zinc-700"
            >
              <button
                onClick={() => setExpandedId(expanded ? null : source.id)}
                className="flex w-full items-start justify-between p-5 text-left"
              >
                <div className="flex items-start gap-3">
                  <FileText className="mt-0.5 h-5 w-5 text-zinc-400" />
                  <div>
                    <h3 className="text-sm font-semibold text-white">{source.name}</h3>
                    <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-zinc-500">
                      <span>Uploaded: {timeAgo(source.compiled_at)}</span>
                      <span>•</span>
                      <span>{source.atom_count} atoms</span>
                      <span>•</span>
                      <span>{source.frame_count} frames</span>
                    </div>
                    <div className="mt-2 flex items-center gap-2">
                      {source.domains.map(d => (
                        <span key={d} className="rounded-md bg-zinc-800 px-2 py-0.5 text-[10px] text-zinc-400">{d}</span>
                      ))}
                      <span className={cn(
                        'rounded-md px-2 py-0.5 text-[10px]',
                        source.classification === 'confidential'
                          ? 'bg-amber-500/15 text-amber-400'
                          : 'bg-zinc-800 text-zinc-400',
                      )}>
                        {source.classification}
                      </span>
                    </div>
                  </div>
                </div>
                {expanded ? <ChevronUp className="h-4 w-4 text-zinc-500" /> : <ChevronDown className="h-4 w-4 text-zinc-500" />}
              </button>

              {expanded && source.compilation_stats && (
                <div className="border-t border-zinc-800 p-5">
                  <div className="mb-4">
                    <p className="mb-2 text-xs font-medium uppercase tracking-wider text-zinc-500">Compilation Pipeline</p>
                    <PipelineStatus stats={source.compilation_stats} />
                  </div>
                  <div>
                    <p className="mb-2 text-xs font-medium uppercase tracking-wider text-zinc-500">Atoms Extracted</p>
                    <div className="flex flex-wrap gap-2">
                      {Object.entries(source.compilation_stats.atoms_by_kind).map(([kind, count]) => (
                        <span key={kind} className={cn('rounded-md px-2.5 py-1 text-xs font-medium', ATOM_BADGE_CLASSES[kind as AtomKind])}>
                          {kind} ({count})
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
