// Verifies the centralized tokens in globals.css against SPEC_FULL 13.2/13.3 and checks contrast.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(join(__dirname, "..", "app", "globals.css"), "utf8");

function block(selector: string): Record<string, string> {
  const start = css.indexOf(`${selector} {`);
  expect(start, `block ${selector}`).toBeGreaterThan(-1);
  const body = css.slice(start, css.indexOf("}", start));
  return Object.fromEntries(
    [...body.matchAll(/(--tq-[\w-]+):\s*(#[0-9a-f]{6})/gi)].map((m) => [m[1], m[2].toLowerCase()]),
  );
}

const dark = block('[data-theme="dark"]');
const light = block('[data-theme="light"]');

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

describe("design tokens", () => {
  it("dark theme uses the exact spec values (13.2)", () => {
    expect(dark).toMatchObject({
      "--tq-bg": "#111210",
      "--tq-surface": "#191b17",
      "--tq-surface-2": "#20221e",
      "--tq-elevated": "#292b25",
      "--tq-text": "#e9e5da",
      "--tq-text-secondary": "#a5a397",
      "--tq-text-muted": "#77786f",
      "--tq-border": "#363830",
      "--tq-signal": "#ff6b35",
      "--tq-vermilion": "#d94f35",
      "--tq-ochre": "#b78b48",
      "--tq-sage": "#727c67",
      "--tq-traffic-normal": "#78a083",
      "--tq-traffic-congested": "#d9b45b",
      "--tq-incident": "#d94f35",
      "--tq-route": "#ff6b35",
      "--tq-disabled": "#77786f",
    });
  });

  it("light theme uses the exact spec values (13.3)", () => {
    expect(light).toMatchObject({
      "--tq-bg": "#f3f0e8",
      "--tq-surface": "#faf8f2",
      "--tq-surface-2": "#e9e4d8",
      "--tq-text": "#252722",
      "--tq-text-secondary": "#65665d",
      "--tq-border": "#d5d0c3",
      "--tq-signal": "#d94f35",
      "--tq-sage": "#727c67",
    });
  });

  it("both themes define the same token set", () => {
    expect(Object.keys(light).sort()).toEqual(Object.keys(dark).sort());
  });

  it.each([
    ["dark", dark],
    ["light", light],
  ])("%s theme text contrast meets WCAG AA", (_name, t) => {
    for (const surface of ["--tq-bg", "--tq-surface", "--tq-surface-2"]) {
      expect(contrast(t["--tq-text"], t[surface])).toBeGreaterThanOrEqual(7);
    }
    for (const surface of ["--tq-bg", "--tq-surface", "--tq-surface-2"]) {
      expect(contrast(t["--tq-text-secondary"], t[surface])).toBeGreaterThanOrEqual(4.5);
    }
    expect(contrast(t["--tq-text-muted"], t["--tq-bg"])).toBeGreaterThanOrEqual(4.0);
    expect(contrast(t["--tq-on-signal"], t["--tq-signal-fill"])).toBeGreaterThanOrEqual(4.5);
  });

  it.each([
    ["dark", dark],
    ["light", light],
  ])("%s status text tokens reach AA on every surface", (_name, t) => {
    for (const text of [
      "--tq-signal-text",
      "--tq-incident-text",
      "--tq-traffic-normal",
      "--tq-traffic-congested",
    ]) {
      for (const surface of ["--tq-bg", "--tq-surface", "--tq-surface-2", "--tq-elevated"]) {
        expect(contrast(t[text], t[surface]), `${text} on ${surface}`).toBeGreaterThanOrEqual(4.5);
      }
    }
  });

  it("documents that the spec muted token is not used for small text on surfaces", () => {
    // Spec 13.2 muted (#77786f) on the dark surface is below AA (4.5:1) for small text, so the UI
    // uses the secondary text token for small informational text (axe audit, STATUS D31).
    expect(contrast(dark["--tq-text-muted"], dark["--tq-surface"])).toBeLessThan(4.5);
    expect(contrast(dark["--tq-text-secondary"], dark["--tq-surface"])).toBeGreaterThanOrEqual(4.5);
  });

  it("uses a derived fill where the spec light accent cannot carry small text", () => {
    expect(contrast("#ffffff", light["--tq-signal"])).toBeLessThan(4.5);
    expect(light["--tq-signal"]).toBe("#d94f35"); // strokes keep the spec accent
    expect(dark["--tq-signal-fill"]).toBe(dark["--tq-signal"]);
  });

  it("series palette is disjoint from traffic semantics", () => {
    for (const t of [dark, light]) {
      const series = [1, 2, 3, 4].map((i) => t[`--tq-series-${i}`]);
      const semantic = [
        "--tq-signal",
        "--tq-incident",
        "--tq-ochre",
        "--tq-sage",
        "--tq-route",
        "--tq-traffic-normal",
        "--tq-traffic-congested",
      ].map((k) => t[k]);
      expect(new Set(series).size).toBe(4);
      expect(series.filter((s) => semantic.includes(s))).toEqual([]);
    }
  });
});
