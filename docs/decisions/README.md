# decisions

BookShelf's decision records say why a part of the system is built the way it is: the problem, what was chosen, and what it costs. One decision per file, numbered in the order they were written. The format is in the [documentation strategy](../strategies/documentation.md#decision-records).

| # | Decision | Status |
|---|---|---|
| [001](001-airglider-step-semantics.md) | airglider's step semantics: automatic nesting, one envelope, `ok` means ran to completion | accepted |
| [002](002-capability-nodes.md) | The planner picks capability nodes, not entity + intent; the instruction contract | accepted |
| [003](003-one-dimension-nodes.md) | One dimension per node, composed by `Combine_Intersect` | accepted |
| [004](004-anchors-and-candidates.md) | Anchor and candidate outputs: the type is the payload | accepted |
| [005](005-counts-first-retrieval.md) | Counts-first retrieval over composable deferred queries | accepted |
| [006](006-one-reply-stage.md) | One reply stage per turn, not a reply node | accepted |
| [007](007-neon.md) | Neon for the production database | accepted |
| [008](008-session-per-unit-of-work.md) | A database session per unit of work | accepted |
| [009](009-no-user-auth-in-v1.md) | No user auth in V1: review routes off, App Check, spend caps | accepted |
| [010](010-human-in-the-loop.md) | Human-in-the-loop: pause, persist, resume | proposed |
| [011](011-node-refusal.md) | A node can say "wrong node for this" | proposed |
