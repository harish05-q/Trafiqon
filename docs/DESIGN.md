# TRAFIQON Design System

Industrial-cartography: a transport command center crossed with scientific research software. Technical, purposeful, data-dense. Every visual element serves a function. Avoid generic SaaS dashboards, neon, blue-purple gradients, glassmorphism, glowing oversized type, needless cards, and decorative animation. Implement all values as centralized tokens (CSS variables + Tailwind theme), never scattered hex codes.

## Dark theme (default; Command Center always starts dark)
| Token | Value |
|---|---|
| background | `#111210` |
| surface | `#191B17` |
| surface-2 | `#20221E` |
| surface-elevated | `#292B25` |
| text | `#E9E5DA` |
| text-secondary | `#A5A397` |
| text-muted | `#77786F` |
| border | `#363830` |
| accent (Signal Orange) | `#FF6B35` |
| accent-2 (Vermilion) | `#D94F35` |
| highlight (Ochre) | `#B78B48` |
| data-2 (Sage) | `#727C67` |
| traffic-normal | `#78A083` |
| traffic-congested | `#D9B45B` |
| incident / closure | `#D94F35` |
| selected route | `#FF6B35` |
| disabled | `#77786F` |

## Light analytical theme (reports, experiment analysis, docs, exports)
| Token | Value |
|---|---|
| background | `#F3F0E8` |
| surface | `#FAF8F2` |
| surface-2 | `#E9E4D8` |
| text | `#252722` |
| text-secondary | `#65665D` |
| border | `#D5D0C3` |
| accent | `#D94F35` |
| accent-2 | `#727C67` |

Do not mix light and dark surfaces within one workspace. Theme switching goes through tokens only.

## Color meaning
Orange = interaction and selected/best route. Vermilion = critical/incident/closed. Ochre = congestion and analytical emphasis. Sage = healthy/secondary data. Pair status colors with labels, icons, or dash patterns (never color alone). Check contrast. Disabled must still be legible. Use a separate restrained palette for algorithm series in charts so traffic colors are never confused with series colors; always show a legend.

## Typography
Inter for UI. JetBrains Mono for numbers, params, times, objectives, iterations, run IDs, metadata. Tabular numerals for comparable figures. Compact; hierarchy via size, weight, spacing, contrast. No universal all-caps.

## Layout
Persistent shell. Top bar: identity, workspace nav, scenario, service status, sim state, global controls. Left: scenario/traffic/fleet/algorithm/incident controls. Center: network (dominant). Right: inspector for the selected node/edge/vehicle/route/run. Bottom: playback, progress, logs, convergence, run details. Panels collapse/resize. Responsive with touch targets; the inspector must not permanently cover the network.

## Network rendering
Ordinary roads neutral graphite. Selected/best route orange. Alternatives restrained and distinct. Congestion ochre. Closed/incident vermilion with dashes plus icon. Healthy sage only where defined. Distinct markers for depot, customer, intersection, vehicle. States: selected, hovered, active, inactive, disabled. Use weight, dashes, arrows, and labels to separate overlapping routes. Minimal glow. Legend and tooltips. Edge details: direction, time, distance, traffic status, closure, route membership. Label synthetic scenarios as synthetic; never imply geographic accuracy.

## Charts
Convergence, evaluations, feasibility, runtime, route costs/changes, benchmark comparison, seed variance, replanning latency. Label axes, units, sample counts. Mark measured vs derived vs estimated vs simulated. Never animate convergence independently of real execution.

## Motion and accessibility
Restrained transitions for selection, route highlight, incident create/resolve, vehicle movement, best-solution updates, panel expansion. Vehicles follow authoritative sim time. No particles or looping decoration. Keyboard navigation, visible focus, contrast, `prefers-reduced-motion`. Fully usable with animation off.
