import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'
import { ROLES, type Role } from './types'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return n.toLocaleString()
}

export function formatLatency(ms: number): string {
  if (ms < 1) return '<1ms'
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`
  return `${ms.toFixed(0)}ms`
}

export function formatPercent(n: number): string {
  return `${(n * 100).toFixed(1)}%`
}

export function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime()
  const minutes = Math.floor(diff / 60000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

export function roleMaskToRoles(mask: number): Role[] {
  return ROLES.filter((_, i) => (mask >> i) & 1) as Role[]
}

export function rolesToMask(roles: Role[]): number {
  let mask = 0
  roles.forEach(r => {
    const idx = ROLES.indexOf(r)
    if (idx >= 0) mask |= (1 << idx)
  })
  return mask
}
