import { useCallback, useEffect } from "react";
import {
  ReactFlow,
  Node,
  Edge,
  Background,
  useNodesState,
  useEdgesState,
  MarkerType,
  Position,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { cn } from "../../lib/utils";
import { ATOM_BADGE_CLASSES, ATOM_ICONS } from "../../lib/constants";
import type { Atom, AtomKind } from "../../lib/types";

interface AtomGraphProps {
  centerAtom: Atom;
  neighbors: Array<{ atom: Atom; relation: string }>;
  onNodeClick?: (atomId: string) => void;
}

// Custom node component for atoms
function AtomNode({ data }: { data: any }) {
  const kind = data.kind as AtomKind;

  return (
    <div
      className={cn(
        "rounded-lg border-2 bg-[#FFF5E6] p-3 shadow-lg transition-all hover:shadow-xl",
        data.isCenter ? "border-blue-500 w-64" : "border-[#C4A888] w-56",
      )}
    >
      <div className="mb-2 flex items-center gap-2">
        <span
          className={cn(
            "rounded px-2 py-0.5 text-[10px] font-medium",
            ATOM_BADGE_CLASSES[kind],
          )}
        >
          {ATOM_ICONS[kind]} {kind}
        </span>
        {data.isCenter && (
          <span className="ml-auto rounded bg-blue-500/20 px-2 py-0.5 text-[9px] font-medium text-blue-400">
            CENTER
          </span>
        )}
      </div>
      <p className="line-clamp-3 text-xs leading-relaxed text-[#5A4530]">
        {data.content}
      </p>
      {data.domain && data.domain.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {data.domain.slice(0, 3).map((d: string) => (
            <span
              key={d}
              className="rounded bg-[#E8D4BC] px-1.5 py-0.5 text-[9px] text-[#8B7355]"
            >
              {d}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

const nodeTypes = {
  atomNode: AtomNode,
};

export default function AtomGraph({
  centerAtom,
  neighbors,
  onNodeClick,
}: AtomGraphProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  // Build graph layout
  useEffect(() => {
    const centerNode: Node = {
      id: centerAtom.id,
      type: "atomNode",
      position: { x: 400, y: 300 },
      data: {
        ...centerAtom,
        isCenter: true,
      },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
    };

    // Arrange neighbors in a circle around the center
    const radius = 250;
    const angleStep = (2 * Math.PI) / Math.max(neighbors.length, 1);

    const neighborNodes: Node[] = neighbors.map((neighbor, idx) => {
      const angle = idx * angleStep - Math.PI / 2; // Start from top
      const x = 400 + radius * Math.cos(angle);
      const y = 300 + radius * Math.sin(angle);

      return {
        id: neighbor.atom.id,
        type: "atomNode",
        position: { x, y },
        data: {
          ...neighbor.atom,
          isCenter: false,
        },
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
      };
    });

    const newEdges: Edge[] = neighbors.map((neighbor, idx) => ({
      id: `${centerAtom.id}-${neighbor.atom.id}`,
      source: centerAtom.id,
      target: neighbor.atom.id,
      label: neighbor.relation || "related",
      type: "straight",
      animated: true,
      style: {
        stroke: "#8B5CF6",
        strokeWidth: 3,
      },
      labelStyle: {
        fill: "#3D2817",
        fontSize: 12,
        fontWeight: 700,
      },
      labelBgStyle: {
        fill: "#FFF5E6",
        fillOpacity: 1,
        rx: 6,
        ry: 6,
      },
      labelBgPadding: [10, 6] as [number, number],
      labelBgBorderRadius: 6,
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: "#8B5CF6",
        width: 25,
        height: 25,
      },
    }));

    setNodes([centerNode, ...neighborNodes]);
    setEdges(newEdges);
  }, [centerAtom, neighbors, setNodes, setEdges]);

  const onNodeClickHandler = useCallback(
    (_event: React.MouseEvent, node: Node) => {
      if (onNodeClick) {
        onNodeClick(node.id);
      }
    },
    [onNodeClick],
  );

  return (
    <div className="h-full w-full rounded-xl border border-[#D4BFA8] bg-[#FFF5E6]">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={onNodeClickHandler}
        nodeTypes={nodeTypes}
        fitView
        minZoom={0.2}
        maxZoom={1.5}
        defaultViewport={{ x: 0, y: 0, zoom: 0.8 }}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#E8D4BC" gap={16} />
      </ReactFlow>
    </div>
  );
}
