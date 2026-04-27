import { useState } from "react";
import { Network, Info, X } from "lucide-react";
import { useFullGraph, useAtom } from "../hooks/useAtoms";
import FullAtomGraph from "../components/atoms/FullAtomGraph";
import AtomDetail from "../components/atoms/AtomDetail";
import { DOMAIN_COLORS } from "../lib/constants";

export default function AtomExplorer() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [fitViewTrigger, setFitViewTrigger] = useState(0);
  const { data: graphData, isLoading } = useFullGraph(100);
  const { data: selectedAtom } = useAtom(selectedId);

  function selectAtom(id: string | null) {
    setSelectedId(id);
    setFitViewTrigger((n) => n + 1);
  }

  return (
    <div
      className="h-[calc(100vh-3rem)] gap-3 overflow-hidden"
      style={{
        display: "grid",
        gridTemplateColumns: selectedAtom ? "1fr 400px" : "1fr",
      }}
    >
      {/* Graph column — grid enforces it stays within 1fr */}
      <div className="flex min-h-0 min-w-0 flex-col gap-3 overflow-hidden">
        <div className="flex shrink-0 items-center justify-between">
          <div className="flex items-center gap-3">
            <Network className="h-6 w-6 text-[#8B5CF6]" />
            <h2 className="text-2xl font-bold text-[#3D2817]">
              Knowledge Graph
            </h2>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            {graphData && (
              <div className="flex items-center gap-4 text-sm text-[#6B5744]">
                <span>{graphData.nodes.length} atom{graphData.nodes.length !== 1 ? "s" : ""}</span>
                <span>{graphData.edges.length} connection{graphData.edges.length !== 1 ? "s" : ""}</span>
              </div>
            )}
            <div className="flex items-center gap-2 flex-wrap">
              {Object.entries(DOMAIN_COLORS).map(([domain, color]) => (
                <span
                  key={domain}
                  style={{ background: `${color}18`, color, border: `1px solid ${color}40` }}
                  className="rounded-md px-2 py-0.5 text-[10px] font-medium"
                >
                  {domain}
                </span>
              ))}
            </div>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-hidden">
          {isLoading ? (
            <div className="flex h-full items-center justify-center rounded-xl border border-[#D4BFA8] bg-[#FFF5E6]">
              <div className="text-center">
                <Network className="mx-auto h-12 w-12 animate-pulse text-[#8B5CF6]" />
                <p className="mt-3 text-sm text-[#6B5744]">
                  Loading knowledge graph...
                </p>
              </div>
            </div>
          ) : graphData && graphData.nodes.length > 0 ? (
            <FullAtomGraph
              nodes={graphData.nodes}
              edges={graphData.edges}
              onNodeClick={selectAtom}
              fitViewTrigger={fitViewTrigger}
            />
          ) : (
            <div className="flex h-full items-center justify-center rounded-xl border border-[#D4BFA8] bg-[#FFF5E6]">
              <div className="text-center">
                <Network className="mx-auto h-12 w-12 text-[#C4A888]" />
                <p className="mt-3 text-sm text-[#6B5744]">
                  No atoms found. Ingest some documents to build the knowledge
                  graph.
                </p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Detail panel — grid allocates exactly 400px for this column */}
      {selectedAtom && (
        <div className="flex min-h-0 flex-col gap-3 overflow-hidden">
          <div className="flex shrink-0 items-center justify-between rounded-xl border border-[#D4BFA8] bg-[#FFF5E6] px-4 py-3">
            <div className="flex items-center gap-2">
              <Info className="h-5 w-5 text-[#8B5CF6]" />
              <h3 className="font-semibold text-[#3D2817]">Atom Details</h3>
            </div>
            <button
              onClick={() => selectAtom(null)}
              className="rounded-lg p-1.5 text-[#6B5744] transition-colors hover:bg-[#E8D4BC]"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto rounded-xl border border-[#D4BFA8] bg-[#FFF5E6] p-5 shadow-lg">
            <AtomDetail
              atom={selectedAtom}
              onNavigate={selectAtom}
            />
          </div>
        </div>
      )}
    </div>
  );
}
