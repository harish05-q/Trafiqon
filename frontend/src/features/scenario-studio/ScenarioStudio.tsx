"use client";

import { MousePointer2, Plus, Spline, Trash2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useReducer, useState } from "react";

import { WorkspaceLayout } from "@/components/shell/WorkspaceLayout";
import { EmptyState, ErrorState, Section, Stat } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { trafficState } from "@/features/network/toFlow";
import { api } from "@/lib/api/client";
import {
  useBuiltinScenarios,
  useSaveScenario,
  useSavedScenarios,
  useValidateDraft,
} from "@/lib/api/hooks";
import type { ScenarioData, ScenarioValidation } from "@/lib/api/types";
import { cn } from "@/lib/utils";
import { useWorkspace } from "@/stores/workspace";
import {
  draftReducer,
  emptyScenario,
  initialDraft,
  toScenarioData,
  type DraftAction,
} from "./draft";
import { StudioCanvas, type Tool } from "./StudioCanvas";

type Source =
  | { kind: "empty" }
  | { kind: "builtin"; id: string }
  | { kind: "saved"; scenarioId: string; versionNumber: number };

type NumberFieldProps = {
  id: string;
  label: string;
  value: number;
  onCommit: (v: number) => void;
  step?: number | "any";
  min?: number;
};

/** Text is local while typing; a new committed value remounts the input (via key). */
function NumberField(props: NumberFieldProps) {
  return <NumberFieldInner key={`${props.id}:${props.value}`} {...props} />;
}

function NumberFieldInner({ id, label, value, onCommit, step = "any", min = 0 }: NumberFieldProps) {
  const [text, setText] = useState(String(value));
  return (
    <div className="grid gap-1">
      <Label htmlFor={id} className="text-xs">
        {label}
      </Label>
      <Input
        id={id}
        type="number"
        className="num h-8"
        step={step}
        min={min}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onBlur={() => onCommit(text === "" ? NaN : Number(text))}
        onKeyDown={(e) => {
          if (e.key === "Enter") onCommit(text === "" ? NaN : Number(text));
        }}
      />
    </div>
  );
}

function ValidationReport({ v }: { v: ScenarioValidation }) {
  const tone = {
    error: "text-incident-text",
    infeasible: "text-traffic-congested",
    warning: "text-muted-foreground",
  };
  return (
    <div className="grid gap-2 text-xs">
      <p
        className={cn(
          v.valid
            ? v.feasible_so_far
              ? "text-traffic-normal"
              : "text-traffic-congested"
            : "text-incident-text",
        )}
      >
        {!v.valid
          ? "Invalid: fix the errors below before saving."
          : v.feasible_so_far
            ? "Valid. No infeasibility detected (not a proof that a solution exists)."
            : "Valid but infeasible: it can be saved, but runs will report infeasible_scenario."}
      </p>
      <dl className="grid grid-cols-4 gap-2">
        <Stat label="Demand" value={v.total_demand} digits={0} />
        <Stat label="Capacity" value={v.total_capacity} digits={0} />
        <Stat label="Strong components" value={v.strongly_connected_components} digits={0} />
        <Stat label="Unreachable pairs" value={v.unreachable_location_pairs} digits={0} />
      </dl>
      {v.issues.length > 0 && (
        <ul className="grid gap-0.5" aria-label="Validation issues">
          {v.issues.map((i, k) => (
            <li key={k} className={tone[i.severity]}>
              <span className="num">
                [{i.severity}] {i.code}
              </span>{" "}
              {i.message}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function ScenarioStudio() {
  const [draft, dispatch] = useReducer(draftReducer, undefined, () =>
    initialDraft(emptyScenario()),
  );
  const [source, setSource] = useState<Source>({ kind: "empty" });
  const [name, setName] = useState("New scenario");
  const [note, setNote] = useState("");
  const [tool, setTool] = useState<Tool>("select");
  const [pending, setPending] = useState<string | null>(null);
  const [sel, setSel] = useState<{ kind: "node" | "edge"; id: string } | null>(null);
  const [loadError, setLoadError] = useState<Error | null>(null);
  const [savedVersion, setSavedVersion] = useState<string | null>(null);
  const saved = useSavedScenarios();
  const builtin = useBuiltinScenarios();
  const validate = useValidateDraft();
  const save = useSaveScenario();
  const setVersion = useWorkspace((s) => s.setVersion);
  const d = draft.data;

  const act = (a: DraftAction) => {
    dispatch(a);
    validate.reset();
    setSavedVersion(null);
  };

  async function load(next: Source) {
    if (draft.dirty && !window.confirm("Discard unsaved changes?")) return;
    setLoadError(null);
    try {
      let data: ScenarioData = emptyScenario();
      if (next.kind === "builtin") {
        const s = await api.getBuiltinScenario(next.id);
        data = toScenarioData(s);
        setName(`${s.name} (edited)`);
      } else if (next.kind === "saved") {
        const sc = await api.getScenario(next.scenarioId);
        const v = await api.getVersion(sc.current_version_id!);
        data = toScenarioData(v.data);
        setName(sc.name);
        next = { ...next, versionNumber: v.version_number };
      } else {
        setName("New scenario");
      }
      dispatch({ type: "load", data });
      setSource(next);
      setSel(null);
      setPending(null);
      validate.reset();
      setSavedVersion(null);
    } catch (e) {
      setLoadError(e as Error);
    }
  }

  // Keyboard shortcuts (shown on the tool buttons); ignored while typing in a field.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (["INPUT", "SELECT", "TEXTAREA"].includes(t.tagName) || e.ctrlKey || e.metaKey) return;
      if (e.key === "n") setTool("add-node");
      else if (e.key === "r") setTool("add-road");
      else if (e.key === "Escape") {
        setTool("select");
        setPending(null);
      } else if ((e.key === "Delete" || e.key === "Backspace") && sel) {
        dispatch({ type: sel.kind === "node" ? "deleteNode" : "deleteEdge", id: sel.id });
        setSel(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [sel]);

  useEffect(() => {
    if (!draft.dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [draft.dirty]);

  const selectedNode =
    sel?.kind === "node" ? d.graph.nodes.find((n) => n.id === sel.id) : undefined;
  const selectedEdge =
    sel?.kind === "edge" ? d.graph.edges.find((e) => e.id === sel.id) : undefined;
  const scenarioId = source.kind === "saved" ? source.scenarioId : null;

  const tools: { tool: Tool; label: string; key: string; icon: React.ReactNode }[] = [
    { tool: "select", label: "Select / move", key: "Esc", icon: <MousePointer2 /> },
    { tool: "add-node", label: "Add node", key: "N", icon: <Plus /> },
    { tool: "add-road", label: "Add road", key: "R", icon: <Spline /> },
  ];

  const left = (
    <>
      <Section title="Start from">
        <div className="grid gap-2">
          <NativeSelect
            aria-label="Load a saved scenario"
            value=""
            onChange={(e) =>
              e.target.value &&
              load({ kind: "saved", scenarioId: e.target.value, versionNumber: 0 })
            }
          >
            <option value="">Saved scenario…</option>
            {saved.data?.items.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </NativeSelect>
          <NativeSelect
            aria-label="Copy a built-in scenario"
            value=""
            onChange={(e) => e.target.value && load({ kind: "builtin", id: e.target.value })}
          >
            <option value="">Built-in (synthetic)…</option>
            {builtin.data?.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </NativeSelect>
          <Button variant="outline" size="sm" onClick={() => load({ kind: "empty" })}>
            Empty network
          </Button>
          {loadError && <ErrorState error={loadError} title="Could not load" />}
          <p className="text-muted-foreground text-[11px]">
            Editing:{" "}
            {source.kind === "saved"
              ? `${name} (from v${source.versionNumber}; saving creates a new version)`
              : source.kind === "builtin"
                ? "copy of a built-in (saving creates a new scenario)"
                : "new network (saving creates a new scenario)"}
            {draft.dirty && " · unsaved changes"}
          </p>
        </div>
      </Section>
      <Section title="Tools">
        <div className="grid grid-cols-3 gap-1" role="toolbar" aria-label="Editing tools">
          {tools.map((t) => (
            <Button
              key={t.tool}
              size="sm"
              variant={tool === t.tool ? "default" : "outline"}
              aria-pressed={tool === t.tool}
              title={`${t.label} (${t.key})`}
              onClick={() => {
                setTool(t.tool);
                setPending(null);
              }}
            >
              {t.icon}
              <span className="sr-only">{t.label}</span>
            </Button>
          ))}
        </div>
        <p className="text-muted-foreground mt-2 text-[11px]" aria-live="polite">
          {tool === "add-node" && "Click the canvas to place a node."}
          {tool === "add-road" &&
            (pending
              ? `From ${pending}: click the destination node.`
              : "Click the origin node, then the destination (one direction).")}
          {tool === "select" &&
            "Click to inspect, drag nodes to move. Delete removes the selection."}
        </p>
      </Section>
      <Section
        title={`Fleet (${d.vehicles.length})`}
        actions={
          <Button size="xs" variant="outline" onClick={() => act({ type: "addVehicle" })}>
            <Plus /> Vehicle
          </Button>
        }
      >
        {d.vehicles.length === 0 ? (
          <EmptyState>No vehicles. Mark a node as depot, then add vehicles.</EmptyState>
        ) : (
          <ul className="grid gap-1.5">
            {d.vehicles.map((v) => (
              <li key={v.id} className="grid grid-cols-[2.5rem_1fr_1fr_auto] items-end gap-1">
                <span className="num pb-2 text-xs">{v.id}</span>
                <NumberField
                  id={`cap-${v.id}`}
                  label="Capacity"
                  value={v.capacity}
                  step={1}
                  min={1}
                  onCommit={(c) => act({ type: "updateVehicle", id: v.id, capacity: c })}
                />
                <div className="grid gap-1">
                  <Label htmlFor={`depot-${v.id}`} className="text-xs">
                    Depot
                  </Label>
                  <NativeSelect
                    id={`depot-${v.id}`}
                    value={v.start_depot_id}
                    onChange={(e) =>
                      act({ type: "updateVehicle", id: v.id, startDepotId: e.target.value })
                    }
                  >
                    {d.depots.map((dp) => (
                      <option key={dp.id} value={dp.id}>
                        {dp.id}
                      </option>
                    ))}
                  </NativeSelect>
                </div>
                <Button
                  size="icon-sm"
                  variant="ghost"
                  aria-label={`Delete vehicle ${v.id}`}
                  onClick={() => act({ type: "deleteVehicle", id: v.id })}
                >
                  <Trash2 />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Section>
      <Section title="Validate and save">
        <div className="grid gap-2">
          {source.kind !== "saved" && (
            <div className="grid gap-1">
              <Label htmlFor="scenario-name" className="text-xs">
                Scenario name
              </Label>
              <Input
                id="scenario-name"
                className="h-8"
                value={name}
                maxLength={200}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
          )}
          <div className="grid gap-1">
            <Label htmlFor="version-note" className="text-xs">
              Version note
            </Label>
            <Input
              id="version-note"
              className="h-8"
              value={note}
              maxLength={2000}
              onChange={(e) => setNote(e.target.value)}
              placeholder="What changed?"
            />
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              className="flex-1"
              disabled={validate.isPending}
              onClick={() => validate.mutate(d)}
            >
              Validate
            </Button>
            <Button
              className="flex-1"
              disabled={save.isPending || (source.kind === "saved" && !draft.dirty) || !name.trim()}
              onClick={() =>
                save.mutate(
                  { scenarioId, name: name.trim(), data: d, note },
                  {
                    onSuccess: (versionId) => {
                      dispatch({ type: "markSaved" });
                      setSavedVersion(versionId);
                      setVersion(versionId);
                    },
                  },
                )
              }
            >
              {save.isPending
                ? "Saving…"
                : source.kind === "saved"
                  ? "Save new version"
                  : "Save scenario"}
            </Button>
          </div>
          {save.isError && <ErrorState error={save.error} title="Save rejected by the server" />}
          {savedVersion && (
            <p role="status" className="text-traffic-normal text-xs">
              Saved as an immutable version and loaded in the workspace.{" "}
              <Link className="underline" href="/command-center">
                Run it in the Command Center
              </Link>
            </p>
          )}
        </div>
      </Section>
    </>
  );

  let right: React.ReactNode = <EmptyState>Select a node or road to edit it.</EmptyState>;
  if (selectedNode) {
    const depot = d.depots.find((x) => x.node_id === selectedNode.id);
    const customer = d.customers.find((x) => x.node_id === selectedNode.id);
    right = (
      <div className="grid gap-2">
        <p className="num text-xs">Node {selectedNode.id}</p>
        <div className="grid grid-cols-2 gap-2">
          <NumberField
            id="node-x"
            label="x (synthetic units)"
            value={selectedNode.x ?? 0}
            min={-1e6}
            onCommit={(x) =>
              act({ type: "moveNode", id: selectedNode.id, x, y: selectedNode.y ?? 0 })
            }
          />
          <NumberField
            id="node-y"
            label="y (synthetic units)"
            value={selectedNode.y ?? 0}
            min={-1e6}
            onCommit={(y) =>
              act({ type: "moveNode", id: selectedNode.id, x: selectedNode.x ?? 0, y })
            }
          />
        </div>
        <div className="grid gap-1">
          <Label htmlFor="node-role" className="text-xs">
            Role
          </Label>
          <NativeSelect
            id="node-role"
            value={depot ? "depot" : customer ? "customer" : "intersection"}
            onChange={(e) =>
              act({
                type: "setRole",
                nodeId: selectedNode.id,
                role: e.target.value as "intersection" | "depot" | "customer",
              })
            }
          >
            <option value="intersection">intersection</option>
            <option value="depot">depot</option>
            <option value="customer">customer</option>
          </NativeSelect>
        </div>
        {customer && (
          <NumberField
            id="demand"
            label={`Demand of ${customer.id}`}
            value={customer.demand}
            step={1}
            min={1}
            onCommit={(v) => act({ type: "setDemand", customerId: customer.id, demand: v })}
          />
        )}
        {depot && <p className="text-muted-foreground text-xs">Depot {depot.id}</p>}
        <Button
          variant="destructive"
          size="sm"
          onClick={() => {
            act({ type: "deleteNode", id: selectedNode.id });
            setSel(null);
          }}
        >
          <Trash2 /> Delete node and its roads
        </Button>
      </div>
    );
  } else if (selectedEdge) {
    const e = selectedEdge;
    const reverse = d.graph.edges.some((x) => x.source === e.target && x.target === e.source);
    right = (
      <div className="grid gap-2">
        <p className="num text-xs">
          Road {e.id}: {e.source} → {e.target} ({trafficState(e)})
        </p>
        <NumberField
          id="edge-distance"
          label="Distance (km)"
          value={e.distance}
          onCommit={(v) => act({ type: "updateEdge", id: e.id, patch: { distance: v } })}
        />
        <NumberField
          id="edge-base"
          label="Base time (min, free flow)"
          value={e.base_time}
          onCommit={(v) => act({ type: "updateEdge", id: e.id, patch: { base_time: v } })}
        />
        <NumberField
          id="edge-current"
          label="Current time (min, used for routing)"
          value={e.current_time}
          onCommit={(v) => act({ type: "updateEdge", id: e.id, patch: { current_time: v } })}
        />
        <label className="flex items-center gap-2 text-xs">
          <input
            type="checkbox"
            className="accent-[var(--tq-signal)]"
            checked={e.closed}
            onChange={(ev) =>
              act({ type: "updateEdge", id: e.id, patch: { closed: ev.target.checked } })
            }
          />
          Closed (never used by routing)
        </label>
        {!reverse && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => act({ type: "addEdge", source: e.target, target: e.source })}
          >
            Add reverse direction
          </Button>
        )}
        <Button
          variant="destructive"
          size="sm"
          onClick={() => {
            act({ type: "deleteEdge", id: e.id });
            setSel(null);
          }}
        >
          <Trash2 /> Delete road
        </Button>
      </div>
    );
  }

  return (
    <WorkspaceLayout
      left={left}
      center={
        <StudioCanvas
          data={d}
          name={name}
          tool={tool}
          selectedNodeId={sel?.kind === "node" ? sel.id : null}
          selectedEdgeId={sel?.kind === "edge" ? sel.id : null}
          pendingSource={pending}
          onAddNode={(x, y) => act({ type: "addNode", x, y })}
          onMoveNode={(id, x, y) => act({ type: "moveNode", id, x, y })}
          onNodeClick={(id) => {
            if (tool === "add-road") {
              if (!pending) setPending(id);
              else {
                act({ type: "addEdge", source: pending, target: id });
                setPending(null);
              }
            } else setSel({ kind: "node", id });
          }}
          onEdgeClick={(id) => setSel({ kind: "edge", id })}
          onPaneClick={() => setSel(null)}
        />
      }
      right={
        <Section title="Inspector">
          {draft.error && (
            <div className="mb-2">
              <ErrorState error={new Error(draft.error)} title="Edit rejected" />
            </div>
          )}
          {right}
        </Section>
      }
      bottom={
        <Section title="Validation">
          <p className="num text-muted-foreground mb-2 text-xs">
            {d.graph.nodes.length} nodes · {d.graph.edges.length} roads ·{" "}
            {d.graph.edges.filter((e) => e.closed).length} closed · {d.depots.length} depots ·{" "}
            {d.customers.length} customers · {d.vehicles.length} vehicles
          </p>
          {validate.isError && <ErrorState error={validate.error} />}
          {validate.data ? (
            <ValidationReport v={validate.data} />
          ) : (
            <EmptyState>
              Press Validate to check connectivity and feasibility on the server.
            </EmptyState>
          )}
        </Section>
      }
    />
  );
}
