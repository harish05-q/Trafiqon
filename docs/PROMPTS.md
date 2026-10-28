# Paste-ready prompts

Start Claude Code in the repo root (where `CLAUDE.md` lives). Run one prompt per session. Every milestone prompt below also ends with the verification step. Review the result and commit before the next. Use `/clear` between milestones; `STATUS.md` carries the state.

## M0 (use Plan mode, Shift+Tab twice)
```
Read CLAUDE.md, STATUS.md and docs/SPEC.md sections 1-4. Do Milestone 0 only.
Inspect the repo and environment (runtimes, uv, node, docker, postgres, redis availability).
Report: inventory, proposed directory structure, conflicts, dependency/infra findings, milestone plan with acceptance criteria, top risks, and the smallest vertical slice. Write no application code. Update STATUS.md.
```

## M1 (first vertical slice)
```
Read CLAUDE.md, STATUS.md, docs/SPEC.md section 1. Do Milestone 1 only.
Build: domain models, closure-aware Dijkstra, A*, route reconstruction, shared evaluator, the Urban Grid fixture, and a minimal API endpoint that returns a real route. Then render that route in React Flow.
Write tests alongside. Run them and report actual output. Before stopping, re-read the matching milestone and requirement sections in docs/SPEC_FULL.md and list any requirement not yet met. Update STATUS.md and stop.
```

## M2
```
Read CLAUDE.md, STATUS.md, docs/SPEC.md sections 2-3 (not 3.4). Do Milestone 2 only.
Implement the common optimizer contract, OR-Tools CVRP baseline, and Simulated Annealing on the shared evaluator. Add a deterministic baseline experiment script. Run tests. Before stopping, re-read the matching milestone and requirement sections in docs/SPEC_FULL.md and list any requirement not yet met. Update STATUS.md, stop.
```

## M3 (the risky one)
```
Read CLAUDE.md, STATUS.md, docs/SPEC.md section 3.4. Do Milestone 3 only.
First write docs/algorithms.md with the encoding, decoding, repair, and update rule in math. Show it to me and wait for approval before coding.
After approval: implement, test determinism, feasibility, and cancellation against the shared evaluator. Document limitations. Before stopping, re-read the matching milestone and requirement sections in docs/SPEC_FULL.md and list any requirement not yet met. Update STATUS.md, stop.
```

## M4
```
Read CLAUDE.md, STATUS.md, docs/SPEC.md sections 5-6. Do Milestone 4 only.
Models, Alembic migrations, scenario versioning, run lifecycle, a Postgres-backed `JobQueue` (SELECT ... FOR UPDATE SKIP LOCKED) consumed by a separate worker process (not API threads), heartbeats and stale-job recovery, bounded retry, SSE from run_events, DB-flag cooperative cancellation, and a guard so terminal states are never overwritten. Do NOT add Celery or Redis (deferred, see STATUS.md D1); keep the `JobQueue` interface clean so they can be added later. Include the race and failure integration tests (two workers claiming, cancel vs complete race, worker crash, worker exception, late event after terminal). If Postgres cannot run here, say so and mark those tests not run. Before stopping, re-read the matching milestone and requirement sections in docs/SPEC_FULL.md and list any requirement not yet met. Update STATUS.md, stop.
```

## M5
```
Read CLAUDE.md, STATUS.md, docs/DESIGN.md, docs/SPEC.md section 8. Do Milestone 5 only.
Tokens, both themes, workspace shell, reusable components, React Flow road renderers, real API wiring. Add component tests and check keyboard focus and reduced motion. Before stopping, re-read the matching milestone and requirement sections in docs/SPEC_FULL.md and list any requirement not yet met. Update STATUS.md, stop.
```

## M6
```
Read CLAUDE.md, STATUS.md, docs/DESIGN.md, docs/SPEC.md section 8. Do Milestone 6 only.
Build Command Center, Algorithm Lab, Scenario Studio, Experiment Explorer against the real API. Every control must do something real, with loading/empty/error/cancelled states. Add Playwright flows 1-4. Before stopping, re-read the matching milestone and requirement sections in docs/SPEC_FULL.md and list any requirement not yet met. Update STATUS.md, stop.
```

## M7
```
Read CLAUDE.md, STATUS.md, docs/SPEC.md section 4. Do Milestone 7 only.
Simulation engine, session API, vehicle edge traversal, incidents, replanning of remaining journey only. Unit tests first for traversal and replanning invariants. Then Playwright flow 5. Before stopping, re-read the matching milestone and requirement sections in docs/SPEC_FULL.md and list any requirement not yet met. Update STATUS.md, stop.
```

## M8
```
Read CLAUDE.md, STATUS.md, docs/SPEC.md sections 7, 9, 10. Do Milestone 8 only.
Benchmarks and exports, remaining charts, a11y and performance pass, full test/lint/build run, write all docs in docs/, verify docs against behavior, Playwright flow 6. Then go through the Definition of Done item by item and mark each verified or not, with evidence. Update STATUS.md.
```

## Recovery prompts
- After a context reset: `Read CLAUDE.md and STATUS.md, then continue the current milestone.`
- A test fails: `Do not weaken the test. Find the root cause, fix the code, rerun, report output.`
- It claims done too early: `Check each acceptance criterion for this milestone against the code and test output. List any that are unmet.`
