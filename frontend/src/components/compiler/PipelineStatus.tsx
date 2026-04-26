import { Check, Loader2 } from 'lucide-react'
import { cn } from '../../lib/utils'

interface PipelineStatusProps {
  stats?: {
    atomize_ms?: number
    distill_ms?: number
    embed_ms?: number
    link_ms?: number
    tag_ms?: number
    index_ms?: number
  }
}

const stages = [
  { key: 'atomize_ms', label: 'Atomize' },
  { key: 'distill_ms', label: 'Distill' },
  { key: 'embed_ms', label: 'Embed' },
  { key: 'link_ms', label: 'Link' },
  { key: 'tag_ms', label: 'Tag' },
  { key: 'index_ms', label: 'Index' },
] as const

export default function PipelineStatus({ stats }: PipelineStatusProps) {
  return (
    <div className="flex items-center gap-1">
      {stages.map((stage, i) => {
        const ms = stats?.[stage.key]
        const done = ms != null
        return (
          <div key={stage.key} className="flex items-center">
            <div className={cn(
              'flex flex-col items-center rounded-md border px-2.5 py-1.5',
              done
                ? 'border-emerald-500/30 bg-emerald-500/10'
                : 'border-[#C4A888] bg-[#E8D4BC]/50',
            )}>
              <div className="mb-0.5">
                {done ? (
                  <Check className="h-3 w-3 text-emerald-400" />
                ) : (
                  <Loader2 className="h-3 w-3 animate-spin text-[#8B7355]" />
                )}
              </div>
              <span className="text-[10px] font-medium text-[#6B5744]">{stage.label}</span>
              {done && (
                <span className="text-[9px] text-[#8B7355]">{(ms / 1000).toFixed(1)}s</span>
              )}
            </div>
            {i < stages.length - 1 && (
              <div className={cn('mx-0.5 h-px w-2', done ? 'bg-emerald-500/40' : 'bg-[#D4BFA8]')} />
            )}
          </div>
        )
      })}
    </div>
  )
}
