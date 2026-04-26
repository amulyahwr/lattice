import { useMutation } from '@tanstack/react-query'
import { api } from '../api/client'
import type { ContextResult } from '../lib/types'

export function useContextQuery() {
  return useMutation({
    mutationFn: ({
      query,
      agentIds,
    }: {
      query: string
      agentIds: string[]
    }): Promise<ContextResult[]> => api.compareContext(query, agentIds),
  })
}
