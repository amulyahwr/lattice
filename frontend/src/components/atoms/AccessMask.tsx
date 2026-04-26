import { ROLES } from '../../lib/types'
import { ROLE_COLORS } from '../../lib/constants'
import { cn } from '../../lib/utils'

interface AccessMaskProps {
  mask: number
  compact?: boolean
}

export default function AccessMask({ mask, compact }: AccessMaskProps) {
  return (
    <div className={cn('flex items-center gap-1', compact ? 'gap-0.5' : 'gap-1')}>
      {ROLES.map((role, i) => {
        const active = (mask >> i) & 1
        return (
          <div key={role} className="group relative">
            <div
              className={cn(
                'rounded-sm transition-colors',
                compact ? 'h-3 w-3' : 'h-4 w-5',
                active
                  ? 'opacity-90'
                  : 'bg-[#E8D4BC] opacity-40',
              )}
              style={active ? { backgroundColor: ROLE_COLORS[role] } : undefined}
            />
            <div className="pointer-events-none absolute -top-8 left-1/2 -translate-x-1/2 whitespace-nowrap rounded bg-[#E8D4BC] px-2 py-1 text-[10px] text-[#5A4530] opacity-0 shadow-lg transition-opacity group-hover:opacity-100">
              {role}
            </div>
          </div>
        )
      })}
    </div>
  )
}
