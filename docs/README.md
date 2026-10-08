# docs/

The durable planning layer for this repo. The `TODO.md` files in `backend/` and
`frontend/` are short-lived scratchpads; anything worth keeping graduates into a file
here. Eval campaign outputs stay under `backend/evals/` (see
[eval-strategy.md](eval-strategy.md)).

## Doc map

| Doc | Purpose |
|---|---|
| [roadmap.md](roadmap.md) | Where V1 stands, what's next, the release checklist, deferred features |
| [backlog.md](backlog.md) | Open work items (P1/P2/P3) with code references, plus settled decisions |
| [eval-strategy.md](eval-strategy.md) | The golden test, the single-call evals, what nothing grades yet, suite inventory |
| [deployment.md](deployment.md) | Runbook: Cloud Run and Firebase — live config, deploying, the image, security and spend controls |
| [deployment-neon.md](deployment-neon.md) | Runbook: the Neon database — connecting, bootstrap order, migrations, pool sizing |
| [design/node-taxonomy-v1.md](design/node-taxonomy-v1.md) | Decision record: the node set, the rules every node follows, per-node notes, the conversation contract |
| [design/execution-pipeline-v1.md](design/execution-pipeline-v1.md) | Design record (built): counts-first retrieval, composition, the task runner and the reply stage |
| [design/planner-shape.md](design/planner-shape.md) | Decision record: capability nodes vs. entity + intent, the instruction contract, open planner experiments |
| [design/human-in-the-loop.md](design/human-in-the-loop.md) | Design record (proposed): pause / persist / resume — pause points, blockers, recommendation |
| [design/node-refusal-v1.md](design/node-refusal-v1.md) | Design record (proposed): a node that can say "wrong node for this", and empty results reaching consumers |

## Conventions

- **Read the nearest README first.** Most backend and frontend folders have a `README.md`
  with the local context; read it before changing that folder.
- **Docs update with the code.** A change to routes, the node registry, enums, or the
  request flow updates the nearest README, `CLAUDE.md`'s architecture section, and the
  relevant doc here, in the same change.
- **Docs describe the present.** When a decision is reversed, rewrite the section; don't
  append a dated amendment. Git keeps the history.
- **Decision records** go in `design/`, one file per decision, with the evidence that
  drove it.
