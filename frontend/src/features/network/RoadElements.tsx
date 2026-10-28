"use client";

import { Handle, Position, type EdgeProps, type NodeProps } from "@xyflow/react";
import { memo } from "react";

import { offsetSegment, type RoadEdge, type RoadNode } from "./toFlow";

const hidden = { left: "50%", top: "50%", opacity: 0, pointerEvents: "none" } as const;

export const RoadNodeView = memo(function RoadNodeView({ id, data }: NodeProps<RoadNode>) {
  const cls = ["road-node", data.kind, data.onRoute && "on-route", data.selected && "selected"]
    .filter(Boolean)
    .join(" ");
  const title =
    data.kind === "customer"
      ? `Customer ${data.refId} at ${id}, demand ${data.demand}`
      : data.kind === "depot"
        ? `Depot ${data.refId} at ${id}`
        : `Intersection ${id}`;
  return (
    <div className={cls} title={title} data-node-id={id} aria-label={title}>
      <Handle type="target" position={Position.Top} style={hidden} isConnectable={false} />
      <Handle type="source" position={Position.Top} style={hidden} isConnectable={false} />
      {data.kind !== "intersection" && <span className="road-node-label">{data.refId}</span>}
    </div>
  );
});

const OFFSET_PX = 3;

export const RoadEdgeView = memo(function RoadEdgeView({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  data,
  markerEnd,
}: EdgeProps<RoadEdge>) {
  if (!data) return null;
  const { x1, y1, x2, y2 } = offsetSegment(
    sourceX,
    sourceY,
    targetX,
    targetY,
    data.hasReverse ? OFFSET_PX : 0,
  );
  const d = `M ${x1},${y1} L ${x2},${y2}`;
  const e = data.edge;
  const cls = [
    "road-edge",
    data.traffic !== "normal" && data.traffic,
    data.onRoute && "on-route",
    data.dimmed && "dimmed",
    data.selected && "selected",
  ]
    .filter(Boolean)
    .join(" ");
  const status = data.traffic === "closed" ? "closed" : data.traffic;
  const routeInfo = data.vehicles.length ? ` · route ${data.vehicles.join(", ")}` : "";
  return (
    <g className="road-edge-group" data-edge-id={id} data-traffic={data.traffic}>
      <title>{`${e.source} → ${e.target} · ${e.current_time.toFixed(2)} min · ${e.distance.toFixed(2)} km · ${status}${routeInfo}`}</title>
      <path d={d} className="road-edge-hit" />
      <path d={d} className={cls} markerEnd={markerEnd} />
    </g>
  );
});
