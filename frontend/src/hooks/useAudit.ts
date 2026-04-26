import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'

export function useAuditLog() {
  return useQuery({
    queryKey: ['audit-log'],
    queryFn: () => api.getAuditLog(),
    refetchInterval: 10_000,
  })
}
