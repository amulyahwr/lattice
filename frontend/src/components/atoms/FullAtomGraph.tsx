import { useCallback, useEffect } from "react";
import {
  ReactFlow,
  Node,
  Edge,
  Background,
  Controls,
  useNodesState,
  useEdgesState,
  useReactFlow,
  MarkerType,
  Position,
  Handle,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { ATOM_COLORS, ATOM_ICONS } from "../../lib/constants";
import type { AtomKind } from "../../lib/types";

interface FullAtomGraphProps {
  nodes: Array<{
    id: string;
    content: string;
    kind: string;
    domain: string[];
    confidence: number;
  }>;
  edges: Array<{ source: string; target: string; relation: string }>;
  onNodeClick?: (atomId: string) => void;
  fitViewTrigger?: number;
}

function AtomNode({ data }: { data: any }) {
  const kind = data.kind as AtomKind;
  const color = ATOM_COLORS[kind] ?? "#8B5CF6";
  const shortId = (data.id as string)?.slice(0, 8) ?? "?";

  return (
    <div
      style={{
        width: 80,
        height: 80,
        borderColor: color,
        backgroundColor: `${color}22`,
      }}
      className="rounded-full border-2 flex flex-col items-center justify-center cursor-pointer shadow-md hover:shadow-xl hover:scale-105 transition-all"
    >
      <Handle type="target" position={Position.Left} style={{ opacity: 0 }} />
      <Handle type="source" position={Position.Right} style={{ opacity: 0 }} />
      <span className="text-xl leading-none select-none">
        {ATOM_ICONS[kind]}
      </span>
      <span
        className="mt-1 font-mono text-[9px] font-bold leading-none"
        style={{ color }}
      >
        {shortId}
      </span>
    </div>
  );
}

// Rendered inside <ReactFlow> so it has access to the flow context.
// Calls fitView whenever the trigger value changes (e.g. panel open/close).
function FitViewController({ trigger }: { trigger?: number }) {
  const { fitView } = useReactFlow();

  useEffect(() => {
    if (trigger === undefined) return;
    // Small delay so the CSS grid column resize finishes painting first.
    const id = setTimeout(() => fitView({ padding: 0.15, duration: 300 }), 100);
    return () => clearTimeout(id);
  }, [trigger, fitView]);

  return null;
}

const nodeTypes = { atomNode: AtomNode };

export default function FullAtomGraph({
  nodes: graphNodes,
  edges: graphEdges,
  onNodeClick,
  fitViewTrigger,
}: FullAtomGraphProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  useEffect(() => {
    if (!graphNodes.length) return;

    const cols = Math.ceil(Math.sqrt(graphNodes.length));
    const spacing = 180;

    const flowNodes: Node[] = graphNodes.map((node, idx) => ({
      id: node.id,
      type: "atomNode",
      position: {
        x: (idx % cols) * spacing,
        y: Math.floor(idx / cols) * spacing,
      },
      data: node,
    }));

    const flowEdges: Edge[] = graphEdges.map((edge, idx) => ({
      id: `${edge.source}-${edge.target}-${idx}`,
      source: edge.source,
      target: edge.target,
      label: edge.relation,
      type: "smoothstep",
      animated: true,
      style: { stroke: "#8B5CF6", strokeWidth: 2 },
      labelStyle: { fill: "#3D2817", fontSize: 10, fontWeight: 700 },
      labelBgStyle: { fill: "#FFF5E6", fillOpacity: 1 },
      labelBgPadding: [6, 3] as [number, number],
      labelBgBorderRadius: 4,
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: "#8B5CF6",
        width: 16,
        height: 16,
      },
    }));

    setNodes(flowNodes);
    setEdges(flowEdges);
  }, [graphNodes, graphEdges, setNodes, setEdges]);

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => onNodeClick?.(node.id),
    [onNodeClick],
  );

  return (
    <div className="h-full w-full overflow-hidden rounded-xl border border-[#D4BFA8] bg-[#FFF5E6]">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        nodeTypes={nodeTypes}
        fitView
        minZoom={0.1}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
      >
        <FitViewController trigger={fitViewTrigger} />
        <Background color="#E8D4BC" gap={20} />
        <Controls />
      </ReactFlow>
    </div>
  );
}
