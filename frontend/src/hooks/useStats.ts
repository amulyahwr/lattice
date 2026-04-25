import { useQuery } from '@tanstack/react-query'
import { mockStats, mockActivity, mockQueryTimeline } from '../lib/mock-data'

export function useStats() {
  return useQuery({
    queryKey: ['stats'],
    queryFn: async () => mockStats,
  })
}

export function useActivity() {
  return useQuery({
    queryKey: ['activity'],
    queryFn: async () => mockActivity,
  })
}

export function useQueryTimeline() {
  return useQuery({
    queryKey: ['query-timeline'],
    queryFn: async () => mockQueryTimeline,
  })
}
