import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { mockQueryTimeline } from '../lib/mock-data'

export function useStats() {
  return useQuery({
    queryKey: ['stats'],
    queryFn: () => api.getStats(),
    refetchInterval: 10_000,
  })
}

export function useActivity() {
  return useQuery({
    queryKey: ['activity'],
    queryFn: () => api.getActivity(),
    refetchInterval: 5_000,
  })
}

// No time-series endpoint yet — keep mock chart data
export function useQueryTimeline() {
  return useQuery({
    queryKey: ['query-timeline'],
    queryFn: async () => mockQueryTimeline,
  })
}
