import { CONGESTION_RATIO } from "./toFlow";

function Line({ className, dashed }: { className: string; dashed?: boolean }) {
  return (
    <svg width="22" height="8" aria-hidden="true" className="shrink-0">
      <line
        x1="1"
        y1="4"
        x2="21"
        y2="4"
        className={className}
        strokeDasharray={dashed ? "5 4" : undefined}
      />
    </svg>
  );
}

export function Legend({ synthetic }: { synthetic: boolean }) {
  return (
    <details
      open
      aria-label="Map legend"
      className="bg-card/95 text-muted-foreground absolute top-2 right-2 z-10 rounded-md border px-3 py-1.5 text-xs"
    >
      <summary className="text-foreground cursor-pointer py-0.5 font-medium">Legend</summary>
      <ul className="mt-1 grid gap-1">
        <li className="flex items-center gap-2">
          <Line className="road-edge" /> Road (arrow = direction)
        </li>
        <li className="flex items-center gap-2">
          <Line className="road-edge on-route" /> Route (selected solution)
        </li>
        <li className="flex items-center gap-2">
          <Line className="road-edge alt-route" dashed /> Comparison run route (dotted)
        </li>
        <li className="flex items-center gap-2">
          <Line className="road-edge congested" /> Congested (≥{CONGESTION_RATIO}× base time)
        </li>
        <li className="flex items-center gap-2">
          <Line className="road-edge closed" dashed /> Closed / incident
        </li>
        <li className="flex items-center gap-2">
          <Line className="road-edge selected" /> Selected road
        </li>
        <li className="flex items-center gap-2">
          <span className="road-node depot ml-1 !h-3 !w-3" aria-hidden="true" /> Depot
        </li>
        <li className="flex items-center gap-2">
          <span className="road-node customer ml-1 !h-2.5 !w-2.5" aria-hidden="true" /> Customer
        </li>
      </ul>
      {synthetic && (
        <p className="text-text-muted mt-2 border-t pt-1">Synthetic network: not geography</p>
      )}
    </details>
  );
}
