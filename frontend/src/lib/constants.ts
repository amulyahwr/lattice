import type { AtomKind } from "./types";

export const ATOM_COLORS: Record<AtomKind, string> = {
  fact: "#3B82F6",
  metric: "#10B981",
  decision: "#F59E0B",
  relationship: "#8B5CF6",
  event: "#F43F5E",
  procedure: "#64748B",
};

export const ATOM_BG_CLASSES: Record<AtomKind, string> = {
  fact: "bg-blue-500/15 border-blue-500/30 text-blue-400",
  metric: "bg-emerald-500/15 border-emerald-500/30 text-emerald-400",
  decision: "bg-amber-500/15 border-amber-500/30 text-amber-400",
  relationship: "bg-purple-500/15 border-purple-500/30 text-purple-400",
  event: "bg-rose-500/15 border-rose-500/30 text-rose-400",
  procedure: "bg-slate-500/15 border-slate-500/30 text-slate-400",
};

export const ATOM_BADGE_CLASSES: Record<AtomKind, string> = {
  fact: "bg-blue-500/20 text-blue-400 border border-blue-500/30",
  metric: "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30",
  decision: "bg-amber-500/20 text-amber-400 border border-amber-500/30",
  relationship: "bg-purple-500/20 text-purple-400 border border-purple-500/30",
  event: "bg-rose-500/20 text-rose-400 border border-rose-500/30",
  procedure: "bg-slate-500/20 text-slate-400 border border-slate-500/30",
};

export const ATOM_ICONS: Record<AtomKind, string> = {
  fact: "📋",
  metric: "📊",
  decision: "⚖️",
  relationship: "🔗",
  event: "📅",
  procedure: "📝",
};

export const CACHE_TIER_CONFIG = {
  L3: {
    label: "🔍 Vector search",
    color: "text-blue-400",
    bg: "bg-blue-500/15 border-blue-500/30",
  },
} as const;

export const ROLE_COLORS: Record<string, string> = {
  sales: "#3B82F6",
  finance: "#10B981",
  engineering: "#F59E0B",
  hr: "#F43F5E",
  legal: "#8B5CF6",
  product: "#06B6D4",
};
