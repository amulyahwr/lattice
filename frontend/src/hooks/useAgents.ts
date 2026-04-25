import { useQuery } from '@tanstack/react-query'
import { mockAgents } from '../lib/mock-data'

export function useAgents() {
  return useQuery({
    queryKey: ['agents'],
    queryFn: async () => mockAgents,
  })
}
