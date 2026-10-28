import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";

import { algorithms } from "@/test/fake-api";
import {
  changedOnly,
  defaultValues,
  formErrors,
  ParamForm,
  paramError,
  type ParamValues,
} from "./ParamForm";

const sa = algorithms.find((a) => a.id === "simulated_annealing")!.params;
const qpso = algorithms.find((a) => a.id === "qpso_hybrid")!.params;

function Harness({ params, onValues }: { params: typeof sa; onValues: (v: ParamValues) => void }) {
  const [values, setValues] = useState(defaultValues(params));
  return (
    <ParamForm
      params={params}
      values={values}
      onChange={(v) => {
        setValues(v);
        onValues(v);
      }}
    />
  );
}

describe("ParamForm logic", () => {
  it("checks values against the published spec", () => {
    const iters = sa[0];
    expect(paramError(iters, 100)).toBeNull();
    expect(paramError(iters, 0)).toMatch(/≥ 1/);
    expect(paramError(iters, 3_000_000)).toMatch(/≤ 2000000/);
    expect(paramError(iters, 1.5)).toMatch(/whole/);
    expect(paramError(iters, NaN)).toMatch(/number/);
    expect(paramError(iters, null)).toBe("required");
    expect(paramError(sa[1], null)).toBeNull(); // nullable cooling_rate
    expect(paramError(sa[2], [])).toMatch(/at least one/);
  });

  it("sends only values changed from the defaults", () => {
    const values = { ...defaultValues(qpso), iterations: 40 };
    expect(changedOnly(qpso, values)).toEqual({ iterations: 40 });
    expect(changedOnly(qpso, defaultValues(qpso))).toEqual({});
    expect(formErrors(qpso, { ...values, swarm_size: 1 })).toEqual({ swarm_size: "must be ≥ 2" });
  });
});

describe("ParamForm rendering", () => {
  afterEach(cleanup);

  it("renders only published settings, with descriptions and ranges, advanced collapsed", () => {
    render(<Harness params={sa} onValues={() => {}} />);
    expect(screen.getByLabelText("max_iterations")).toBeTruthy();
    expect(screen.getByText(/max_iterations description/).textContent).toContain(
      "Range: 1 – 2000000",
    );
    expect(screen.getByText("Advanced parameters (1)")).toBeTruthy();
    expect(screen.queryByLabelText("inertia")).toBeNull();
  });

  it("edits numbers, nullable switches, enum lists and shows inline errors", () => {
    let last: ParamValues = {};
    render(<Harness params={sa} onValues={(v) => (last = v)} />);
    fireEvent.change(screen.getByLabelText("max_iterations"), { target: { value: "0" } });
    expect(last.max_iterations).toBe(0);
    expect(screen.getByRole("alert").textContent).toMatch(/max_iterations: must be ≥ 1/);
    fireEvent.click(screen.getByLabelText(/auto: final_temperature_ratio/));
    expect(last.cooling_rate).toBe(1e-6); // leaving "auto" starts at the minimum
    fireEvent.click(screen.getByLabelText("swap"));
    expect(last.moves).toEqual(["relocate", "reverse"]);
  });

  it("booleans and enums", () => {
    let last: ParamValues = {};
    render(<Harness params={qpso} onValues={(v) => (last = v)} />);
    fireEvent.click(screen.getByLabelText("lamarckian"));
    expect(last.lamarckian).toBe(false);
    fireEvent.change(screen.getByLabelText("update_rule"), {
      target: { value: "uniform_resample" },
    });
    expect(last.update_rule).toBe("uniform_resample");
  });
});
