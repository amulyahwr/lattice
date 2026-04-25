import { useQuery } from '@tanstack/react-query'
import { mockSources } from '../lib/mock-data'

export function useSources() {
  return useQuery({
    queryKey: ['sources'],
    queryFn: async () => mockSources,
  })
}
