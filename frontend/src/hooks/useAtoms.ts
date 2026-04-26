import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

export function useAtomSearch(
  params: {
    search?: string;
    kind?: string;
    domain?: string;
    limit?: number;
  } = {},
) {
  return useQuery({
    queryKey: ["atoms", params],
    queryFn: () => api.getAtoms(params),
    staleTime: 30_000,
  });
}

export function useAtom(id: string | null) {
  return useQuery({
    queryKey: ["atom", id],
    queryFn: () => api.getAtom(id!),
    enabled: !!id,
    staleTime: 30_000,
  });
}

export function useAtomNeighborhood(id: string | null) {
  return useQuery({
    queryKey: ["atom-neighborhood", id],
    queryFn: () => api.getAtomNeighborhood(id!),
    enabled: !!id,
    staleTime: 30_000,
  });
}

export function useFullGraph(limit = 100) {
  return useQuery({
    queryKey: ["full-graph", limit],
    queryFn: () => api.getFullGraph(limit),
    staleTime: 60_000,
  });
}
