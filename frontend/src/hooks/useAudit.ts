import { useQuery } from '@tanstack/react-query'
import { mockAuditLog } from '../lib/mock-data'

export function useAuditLog() {
  return useQuery({
    queryKey: ['audit-log'],
    queryFn: async () => mockAuditLog,
  })
}
