import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'

export function useSources() {
  return useQuery({
    queryKey: ['sources'],
    queryFn: () => api.getSources(),
  })
}

export function useIngestSource() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => api.ingestSource(file),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sources'] }),
  })
}
