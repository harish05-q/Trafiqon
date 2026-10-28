"use client";

// Configuration form generated from the server's published parameter specs, so it can only
// show settings that the algorithm really supports, within the server's limits.
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import type { ParamOut } from "@/lib/api/types";

export type ParamValues = Record<string, unknown>;

export function defaultValues(params: ParamOut[]): ParamValues {
  return Object.fromEntries(params.map((p) => [p.key, p.default]));
}

/** Client-side check against the published spec. The server remains the authority. */
export function paramError(p: ParamOut, value: unknown): string | null {
  if (value === null) return p.nullable ? null : "required";
  if (p.kind === "int" || p.kind === "float") {
    if (typeof value !== "number" || !Number.isFinite(value)) return "enter a number";
    if (p.kind === "int" && !Number.isInteger(value)) return "must be a whole number";
    if (p.minimum !== null && value < p.minimum) return `must be ≥ ${p.minimum}`;
    if (p.maximum !== null && value > p.maximum) return `must be ≤ ${p.maximum}`;
  }
  if (p.kind === "enum" && !p.choices.includes(String(value))) return "unknown option";
  if (p.kind === "enum_list" && (!Array.isArray(value) || value.length === 0))
    return "choose at least one";
  return null;
}

export function formErrors(params: ParamOut[], values: ParamValues): Record<string, string> {
  const out: Record<string, string> = {};
  for (const p of params) {
    const e = paramError(p, values[p.key]);
    if (e) out[p.key] = e;
  }
  return out;
}

/** Only keys that differ from the defaults are sent; the server records the resolved config. */
export function changedOnly(params: ParamOut[], values: ParamValues): ParamValues {
  return Object.fromEntries(
    params
      .filter((p) => JSON.stringify(values[p.key]) !== JSON.stringify(p.default))
      .map((p) => [p.key, values[p.key]]),
  );
}

function range(p: ParamOut): string {
  const lo = p.minimum ?? "−∞";
  const hi = p.maximum ?? "∞";
  return `${lo} – ${hi}${p.unit ? ` ${p.unit}` : ""}`;
}

function Field({
  p,
  value,
  error,
  onChange,
}: {
  p: ParamOut;
  value: unknown;
  error?: string;
  onChange: (v: unknown) => void;
}) {
  const id = `param-${p.key}`;
  const helpId = `${id}-help`;
  const isNull = value === null;
  let control: React.ReactNode;
  if (p.kind === "bool") {
    control = (
      <input
        id={id}
        type="checkbox"
        className="accent-[var(--tq-signal)] size-4"
        checked={Boolean(value)}
        onChange={(e) => onChange(e.target.checked)}
        aria-describedby={helpId}
      />
    );
  } else if (p.kind === "enum") {
    control = (
      <NativeSelect
        id={id}
        value={String(value)}
        onChange={(e) => onChange(e.target.value)}
        aria-describedby={helpId}
      >
        {p.choices.map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
      </NativeSelect>
    );
  } else if (p.kind === "enum_list") {
    const list = Array.isArray(value) ? (value as string[]) : [];
    control = (
      <fieldset className="flex flex-wrap gap-3" aria-describedby={helpId} id={id}>
        <legend className="sr-only">{p.key}</legend>
        {p.choices.map((c) => (
          <label key={c} className="flex items-center gap-1 text-xs">
            <input
              type="checkbox"
              className="accent-[var(--tq-signal)]"
              checked={list.includes(c)}
              onChange={(e) =>
                onChange(e.target.checked ? [...list, c] : list.filter((x) => x !== c))
              }
            />
            {c}
          </label>
        ))}
      </fieldset>
    );
  } else {
    control = (
      <Input
        id={id}
        type="number"
        className="num h-8"
        disabled={isNull}
        min={p.minimum ?? undefined}
        max={p.maximum ?? undefined}
        step={p.kind === "int" ? 1 : "any"}
        value={isNull || value === undefined ? "" : String(value)}
        onChange={(e) => onChange(e.target.value === "" ? NaN : Number(e.target.value))}
        aria-invalid={!!error}
        aria-describedby={helpId}
      />
    );
  }
  return (
    <div className="grid gap-1">
      <div className="flex items-center justify-between gap-2">
        <Label htmlFor={id} className="num text-xs">
          {p.key}
        </Label>
        {p.nullable && (
          <label className="text-muted-foreground flex items-center gap-1 text-[11px]">
            <input
              type="checkbox"
              className="accent-[var(--tq-signal)]"
              checked={isNull}
              onChange={(e) =>
                onChange(e.target.checked ? null : (p.minimum ?? (p.kind === "int" ? 1 : 0.1)))
              }
            />
            {p.null_meaning}
          </label>
        )}
      </div>
      {control}
      <p id={helpId} className="text-muted-foreground text-[11px]">
        {p.description}
        {(p.kind === "int" || p.kind === "float") && <> Range: {range(p)}.</>}
      </p>
      {error && (
        <p role="alert" className="text-incident-text text-[11px]">
          {p.key}: {error}
        </p>
      )}
    </div>
  );
}

export function ParamForm({
  params,
  values,
  onChange,
}: {
  params: ParamOut[];
  values: ParamValues;
  onChange: (values: ParamValues) => void;
}) {
  const errors = formErrors(params, values);
  const set = (key: string) => (v: unknown) => onChange({ ...values, [key]: v });
  const basic = params.filter((p) => !p.advanced);
  const advanced = params.filter((p) => p.advanced);
  return (
    <div className="grid gap-3">
      {basic.map((p) => (
        <Field
          key={p.key}
          p={p}
          value={values[p.key]}
          error={errors[p.key]}
          onChange={set(p.key)}
        />
      ))}
      {advanced.length > 0 && (
        <details className="grid gap-3">
          <summary className="text-muted-foreground cursor-pointer text-xs">
            Advanced parameters ({advanced.length})
          </summary>
          <div className="mt-2 grid gap-3">
            {advanced.map((p) => (
              <Field
                key={p.key}
                p={p}
                value={values[p.key]}
                error={errors[p.key]}
                onChange={set(p.key)}
              />
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
