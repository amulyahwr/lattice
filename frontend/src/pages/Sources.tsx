import { useRef, useState } from 'react'
import { Upload, FileText, ChevronDown, ChevronUp, Loader2 } from 'lucide-react'
import { useSources, useIngestSource } from '../hooks/useSources'
import { timeAgo, cn } from '../lib/utils'
import { ATOM_BADGE_CLASSES } from '../lib/constants'
import PipelineStatus from '../components/compiler/PipelineStatus'
import type { AtomKind } from '../lib/types'

export default function Sources() {
  const { data: sources } = useSources()
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const ingest = useIngestSource()

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    ingest.mutate(file)
    e.target.value = ''
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h2 className="text-2xl font-bold text-[#3D2817]">Sources</h2>
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.txt,.md"
          className="hidden"
          onChange={handleFileChange}
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={ingest.isPending}
          className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-medium text-[#3D2817] transition-colors hover:bg-blue-500 disabled:opacity-60"
        >
          {ingest.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
          {ingest.isPending ? 'Processing…' : 'Upload Source'}
        </button>
      </div>

      {/* Processing overlay */}
      {ingest.isPending && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="flex flex-col items-center gap-4 rounded-xl border border-[#D4BFA8] bg-[#FFF5E6] px-10 py-8">
            <Loader2 className="h-8 w-8 animate-spin text-blue-400" />
            <div className="text-center">
              <p className="text-sm font-medium text-[#3D2817]">Compiling source…</p>
              <p className="mt-1 text-xs text-[#8B7355]">LLM is atomizing, distilling, and linking</p>
            </div>
          </div>
        </div>
      )}

      <div className="space-y-4">
        {sources?.map(source => {
          const expanded = expandedId === source.id
          return (
            <div
              key={source.id}
              className="rounded-xl border border-[#D4BFA8] bg-[#FFF5E6]/50 transition-colors hover:border-[#C4A888]"
            >
              <button
                onClick={() => setExpandedId(expanded ? null : source.id)}
                className="flex w-full items-start justify-between p-5 text-left"
              >
                <div className="flex items-start gap-3">
                  <FileText className="mt-0.5 h-5 w-5 text-[#6B5744]" />
                  <div>
                    <h3 className="text-sm font-semibold text-[#3D2817]">{source.name}</h3>
                    <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-[#8B7355]">
                      <span>Uploaded: {source.created_at ? timeAgo(source.created_at) : '—'}</span>
                      <span>•</span>
                      <span>{source.atom_count} atoms</span>
                    </div>
                    {source.domains.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {source.domains.map(d => (
                          <span key={d} className="rounded-md bg-[#E8D4BC] px-2 py-0.5 text-[10px] text-[#6B5744]">{d}</span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
                {expanded ? <ChevronUp className="h-4 w-4 text-[#8B7355]" /> : <ChevronDown className="h-4 w-4 text-[#8B7355]" />}
              </button>

              {expanded && source.compilation_stats && (
                <div className="border-t border-[#D4BFA8] p-5">
                  <div className="mb-4">
                    <p className="mb-2 text-xs font-medium uppercase tracking-wider text-[#8B7355]">Compilation Pipeline</p>
                    <PipelineStatus stats={source.compilation_stats} />
                  </div>
                  <div>
                    <p className="mb-2 text-xs font-medium uppercase tracking-wider text-[#8B7355]">Atoms Extracted</p>
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
