import type { Edge, Node } from "@xyflow/react";
import type { DependencyEdge, Graph, GraphNode } from "../api/client";

export type NodeKind =
  "Brief" | "Requirement" | "Evidence" | "Task" | "AssetVersion";

export interface ExplorerNodeData extends Record<string, unknown> {
  readonly source: GraphNode;
  readonly kind: NodeKind;
  readonly title: string;
  readonly subtitle: string;
  readonly action?: string | null;
  readonly proposedChange?: boolean;
}

function hasField<K extends string>(
  value: GraphNode,
  key: K,
): value is GraphNode & Record<K, unknown> {
  return key in value;
}

export function nodeKind(node: GraphNode): NodeKind {
  if (hasField(node, "asset_id")) return "AssetVersion";
  if (hasField(node, "task_type")) return "Task";
  if (hasField(node, "status")) return "Requirement";
  if (hasField(node, "extracted_span")) return "Evidence";
  return "Brief";
}

export function nodeTitle(node: GraphNode): string {
  if (hasField(node, "task_type") && typeof node.task_type === "string")
    return node.task_type;
  if (hasField(node, "filename") && typeof node.filename === "string")
    return node.filename;
  if (hasField(node, "content") && typeof node.content === "string") {
    const content = node.content.trim().replace(/\s+/g, " ");
    return content.length > 56
      ? `${content.slice(0, 53)}…`
      : content || node.id;
  }
  return node.id;
}

export function nodeSubtitle(node: GraphNode, kind: NodeKind): string {
  if (kind === "Requirement" && hasField(node, "status"))
    return String(node.status);
  if (kind === "Evidence" && hasField(node, "confirmed_by")) {
    return node.confirmed_by
      ? `Confirmed by ${String(node.confirmed_by)}`
      : "Unconfirmed evidence";
  }
  if (kind === "AssetVersion" && hasField(node, "provider"))
    return String(node.provider);
  return `Version ${node.version}`;
}

function layers(graph: Graph): Map<string, number> {
  const incoming = new Map(graph.nodes.map((node) => [node.id, 0]));
  const outgoing = new Map(
    graph.nodes.map((node) => [node.id, [] as string[]]),
  );
  for (const edge of graph.edges) {
    if (edge.valid_to === null) {
      incoming.set(
        edge.dependent_id,
        (incoming.get(edge.dependent_id) ?? 0) + 1,
      );
      outgoing.get(edge.upstream_id)?.push(edge.dependent_id);
    }
  }
  const queue = graph.nodes
    .filter((node) => incoming.get(node.id) === 0)
    .map((node) => node.id)
    .sort();
  const depth = new Map<string, number>(queue.map((id) => [id, 0]));
  while (queue.length) {
    const id = queue.shift();
    if (!id) continue;
    for (const child of [...(outgoing.get(id) ?? [])].sort()) {
      depth.set(
        child,
        Math.max(depth.get(child) ?? 0, (depth.get(id) ?? 0) + 1),
      );
      incoming.set(child, (incoming.get(child) ?? 1) - 1);
      if (incoming.get(child) === 0) queue.push(child);
    }
  }
  return depth;
}

export function toFlowGraph(graph: Graph): {
  readonly nodes: Node<ExplorerNodeData>[];
  readonly edges: Edge[];
} {
  const depth = layers(graph);
  const grouped = new Map<number, GraphNode[]>();
  const outgoingCount = new Map<string, number>();
  for (const edge of graph.edges.filter((edge) => edge.valid_to === null)) {
    outgoingCount.set(
      edge.upstream_id,
      (outgoingCount.get(edge.upstream_id) ?? 0) + 1,
    );
  }
  for (const node of graph.nodes) {
    const layer = depth.get(node.id) ?? 0;
    grouped.set(layer, [...(grouped.get(layer) ?? []), node]);
  }
  const position = new Map<string, { x: number; y: number }>();
  for (const [layer, nodes] of grouped) {
    for (const [index, node] of [...nodes]
      .sort(
        (a, b) =>
          (outgoingCount.get(b.id) ?? 0) - (outgoingCount.get(a.id) ?? 0) ||
          a.id.localeCompare(b.id),
      )
      .entries()) {
      position.set(node.id, { x: layer * 292, y: index * 150 });
    }
  }
  return {
    nodes: graph.nodes.map((source) => {
      const kind = nodeKind(source);
      return {
        id: source.id,
        type: "orcify",
        position: position.get(source.id) ?? { x: 0, y: 0 },
        data: {
          source,
          kind,
          title: nodeTitle(source),
          subtitle: nodeSubtitle(source, kind),
        },
        draggable: false,
        selectable: true,
      };
    }),
    edges: graph.edges.filter((edge) => edge.valid_to === null).map(toFlowEdge),
  };
}

function toFlowEdge(edge: DependencyEdge): Edge {
  const colors: Record<string, string> = {
    HARD: "#7c5cff",
    SOFT: "#32a5a0",
    INFORMATIONAL: "#a8b0bf",
  };
  const color = colors[edge.strength] ?? "#a8b0bf";
  return {
    id: edge.id,
    source: edge.upstream_id,
    target: edge.dependent_id,
    label: edge.strength,
    type: "smoothstep",
    animated: false,
    selectable: false,
    focusable: false,
    style: { stroke: color, strokeWidth: 1.8 },
    labelStyle: { fill: "#667085", fontWeight: 650, fontSize: 10 },
    labelBgStyle: { fill: "#ffffff", fillOpacity: 0.92 },
    markerEnd: { type: "arrowclosed", color },
  };
}

export function displayedVersion(node: GraphNode): string {
  return `v${node.version}`;
}
