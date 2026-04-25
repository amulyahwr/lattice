import { useMutation } from '@tanstack/react-query'
import { getMockContextResult } from '../lib/mock-data'
import type { ContextResult } from '../lib/types'

export function useContextQuery() {
  return useMutation({
    mutationFn: async ({ query, agentIds }: { query: string; agentIds: string[] }): Promise<ContextResult[]> => {
      // Simulate network delay
      await new Promise(r => setTimeout(r, 300 + Math.random() * 700))
      return agentIds.map(id => getMockContextResult(id, query))
    },
  })
}
