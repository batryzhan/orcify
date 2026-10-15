import {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  type NodeProps,
} from "@xyflow/react";
import {
  Check,
  FileText,
  Image,
  Layers3,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { memo, useMemo } from "react";
import type { GraphNode } from "../api/client";
import { Badge } from "../components/ui";
import { displayedVersion, toFlowGraph, type ExplorerNodeData } from "./model";

const nodeIcons = {
  Brief: FileText,
  Requirement: ShieldCheck,
  Evidence: Check,
  Task: Sparkles,
  AssetVersion: Image,
} as const;

function OrcifyNode({
  data,
  selected,
}: NodeProps & { data: ExplorerNodeData }) {
  const Icon = nodeIcons[data.kind];
  const source = data.source as GraphNode;
  const state =
    data.kind === "Requirement" && "status" in source
      ? String(source.status)
      : data.subtitle;
  return (
    <div
      className={`graph-node kind-${data.kind.toLowerCase()} ${selected ? "selected" : ""} ${data.action ? `impact-${data.action.toLowerCase()}` : ""} ${data.proposedChange ? "proposed-source" : ""}`}
    >
      <div className="node-topline">
        <span className="node-icon">
          <Icon size={14} strokeWidth={2} />
        </span>
        <span className="node-kind">
          {data.kind === "AssetVersion" ? "Asset" : data.kind}
        </span>
        <span className="node-version">{displayedVersion(source)}</span>
      </div>
      <div className="node-title" title={data.title}>
        {data.title}
      </div>
      <div className="node-bottomline">
        <span className="node-state">
          {data.proposedChange ? "PROPOSED CHANGE" : (data.action ?? state)}
        </span>
        <span className="node-open">Details</span>
      </div>
      <Handle type="target" position={Position.Left} className="node-handle" />
      <Handle type="source" position={Position.Right} className="node-handle" />
    </div>
  );
}

const nodeTypes = { orcify: memo(OrcifyNode) };

export function GraphCanvas({
  graph,
  selectedId,
  onSelect,
  actions,
  caption = "Authoritative snapshot",
  labels,
  changedId,
}: {
  graph: import("../api/client").Graph;
  selectedId: string | null;
  onSelect: (node: GraphNode) => void;
  actions?: Record<string, string>;
  caption?: string;
  labels?: Record<string, string>;
  changedId?: string;
}) {
  const flow = useMemo(() => toFlowGraph(graph), [graph]);
  const nodes = useMemo(
    () =>
      flow.nodes.map((node) => ({
        ...node,
        selected: node.id === selectedId,
        data: {
          ...node.data,
          title: labels?.[node.id] ?? node.data.title,
          action: actions?.[node.id] ?? null,
          proposedChange: node.id === changedId,
        },
      })),
    [flow.nodes, selectedId, actions, labels, changedId],
  );
  const minimapColor = (node: { id: string }) =>
    node.id === selectedId ? "#7b61ff" : "#b8c0cf";

  return (
    <div
      className="canvas-wrap"
      aria-label="Read-only project dependency graph"
    >
      <div className="canvas-caption">
        <Layers3 size={14} /> {caption}
      </div>
      {nodes.length === 0 ? (
        <div className="empty-graph">
          <div className="empty-icon">
            <Layers3 />
          </div>
          <h3>No graph nodes yet</h3>
          <p>This project has no authoritative nodes to explore.</p>
        </div>
      ) : (
        <ReactFlow
          nodes={nodes}
          edges={flow.edges}
          nodeTypes={nodeTypes}
          onNodeClick={(_, node) => onSelect(node.data.source)}
          fitView
          fitViewOptions={{ padding: 0.28, minZoom: 0.45, maxZoom: 1.35 }}
          minZoom={0.2}
          maxZoom={1.8}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable
          edgesFocusable={false}
          proOptions={{ hideAttribution: true }}
          className="orcify-flow"
        >
          <Background color="#d9dee7" gap={24} size={1.15} />
          <Controls showInteractive={false} position="bottom-left" />
          <MiniMap
            nodeColor={minimapColor}
            maskColor="rgba(247,248,250,.72)"
            position="bottom-right"
          />
        </ReactFlow>
      )}
      <div className="edge-legend" aria-label="Dependency edge types">
        <Badge>
          <i className="legend-dot hard" />
          Hard
        </Badge>
        <Badge>
          <i className="legend-dot soft" />
          Soft
        </Badge>
        <Badge>
          <i className="legend-dot info" />
          Informational
        </Badge>
      </div>
    </div>
  );
}
