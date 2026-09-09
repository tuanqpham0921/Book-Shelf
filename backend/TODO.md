# TODO (scratchpad)

Durable planning lives in [/docs](../docs/README.md) — roadmap, backlog, eval strategy,
and design decisions. This file is only for in-flight scribbles that die within a
session; anything worth keeping graduates into a `docs/` file.

## Migration log

**2026-07-17** — V1 scoping → `docs/design/node-taxonomy-v1.md` + `docs/roadmap.md`;
code-review/security findings, test gaps, workflow-framework notes → `docs/backlog.md`;
golden-test/suite notes → `docs/eval-strategy.md`.

**2026-08-19** — "make the node args parse choose the tool → `ok=False` message back to
the planner", the `num_books == 0` propagation bug, and "add more nodes before over
debugging" → `docs/design/node-refusal-v1.md` (+ two backlog bullets under "Node contracts
& refusal").

**2026-09-07 (a)** — the sink-vs-slice sketch ("if a node failed then you have to go and
find it") → `docs/design/execution-pipeline-v1.md`, under the second generation-node
attempt. Answered by the failure artifacts: a failed goal leaves a `FailedGoalOutput` and
the runner composes the reason naming the upstream cause, so the generation node is handed
the failure instead of having to go looking for it.

**2026-09-07 (b) — full sweep against the code.** ~700 lines went out. Where they went:

| What it was | Where it is now |
|---|---|
| Retries design; `@task` idempotency question | `docs/backlog.md` → Workflow framework, items 6–7 |
| HITL scope limits; the intersect/CTE pause point; "you can't go back" | `docs/design/human-in-the-loop.md` → "Status update — 2026-09-07" |
| Nested routing inside the recommend node vs. a flat planner (~90 lines) | `docs/design/planner-shape.md` → open experiment 4 |
| Duplicate goals; domain pre-filtering as a catalog shrink | `docs/design/planner-shape.md` → open experiment 3 |
| "Can't answer what isn't a column" (main characters, plot) | `docs/design/node-taxonomy-v1.md` → V1 conversation contract |
| Two kinds of compare; the winner-as-filter insight; edge pruning | `docs/design/node-taxonomy-v1.md` → Future considerations |
| SQLAlchemy pooled-connection GC warning (was a raw log paste) | `docs/backlog.md` → Reliability |
| Rate-limit capacity arithmetic (15 requests/plan, 500 RPM) | `docs/backlog.md` → Reliability |
| `confidence` 0.0; analyze→analyze prompt examples; first-person reasoning | `docs/backlog.md` → Planner quality |
| Compact tracer; `add_details(log=True)`; finish the Responses API migration | `docs/backlog.md` → Tracing, clients & tooling |
| Batching several counts into one round trip | `docs/backlog.md` → Performance |
| "Why?" button; nodes calling the planner; bounded multi-turn loop; narration field; pre-made plans; unified artifact renderer | `docs/backlog.md` → Ideas pool |
| Session factories on stores; per-node parsing; bounds-after-search; the 0.7 floor; generation as a sink | `docs/backlog.md` → Settled (all decided the other way) |

Also restored: **`docs/design/human-in-the-loop.md`**, which five docs link to and which
was lost in the `5df0d80` revert.

Deleted as already built — the code is the record: the architecture "Guidelines" block and
the re-architecture plan (that *is* the current architecture), `OperationResult.input`,
`parse_intent`'s removal, the genre node (now `Retrieve_by_Lexical_Traits`), the
collect/filter node (now `Combine_Intersect`), SSE section events (`task.start`/`task.end`),
tasks returning typed outputs, the `Analyze_Recommend` → `Analyze_Similar_Books` rename, the
`published after 2015` docstring gap, and the generation-node deliberation.

Two items were already tracked and were **not** duplicated: the "Brave New World" title
match is `docs/backlog.md` → Planner quality ("`Retrieve_by_Title` should prefer exact
matches"), and retry/backoff is the same decision as the rate-limit item under Reliability.

Historical cleanup logs live in git history (`git log -p -- backend/TODO.md`).

---

## In flight

- ~~**What the generation node feeds its writer.**~~ **Decided 2026-09-08, and the node
  it was about is gone.** `write_recommendations/` was deleted and writing the reply went
  back inside `find_similar_books/`, in the old `analyze_recommend` shape: counts and
  ranges only (authors, shelves, page span), with the books reaching the user as cards and
  never reaching the LLM. So the tradeoff resolved toward "a reply that cannot invent a
  plot" over per-book "why this fits" — the blurbs the alternative needed are exactly what
  let a writer describe a book it was only shown the metadata of. The slice's renderer,
  which sent full entries up to 12k chars, is recoverable from git history.

- **Nothing narrates a *failed* chain.** Narrowed 2026-09-09 but not closed. The
  `FailedGoalOutput` artifacts and `_upstream_context` still compose the reason, and no
  input declares a slot for one — `write_recommendations` was the only one that did.
  `Retrieve_by_Title` can now say "I don't have Dune" when the plan asks it to, which
  covers the common shape; what it does not cover is the goal *after* it. A title lookup
  that matched nothing **succeeds** (zero matches is a real answer), so `anchors` is
  filled, the similarity goal dispatches and dies in `check_anchors`, and "so I couldn't
  line anything up against it" is still said by nobody. A goal that fails in `_prepare`
  opens no UI section at all, so it stays silent whatever brief it carried. Open: a
  failure-narrating path on the similarity node, or a stage that owns the reply. See
  `docs/design/execution-pipeline-v1.md`.

- ~~**The generation instruction is planned but not delivered.**~~ **Delivered
  2026-09-09.** `build_input` fills both of the goal's briefs by name and leaves
  everything else by type; the field is declared per-slice (`FindByTitleInput`,
  `SimilarBooksInput`) rather than on `NodeInput`, so declaring it *is* a node's claim
  that it can be asked to speak. `AppWorkflow.run_llm_reply` is what turns one into
  prose, over `domains/prompts/reply.txt`. The two open questions in this item both
  resolved toward the node: the reply is a writing step of the node's own, and the runner
  reads the brief off the assembled input to decide whether the section folds.

- **The other three retrieval nodes cannot speak yet.** `find_by_author`,
  `find_by_lexical_traits` and `find_by_numeric_traits` have no `generation_instruction`
  field, so "anything by Sanderson?" still answers in cards alone. Deliberately left:
  their facts blocks will look near-identical to `render_title_facts`, and whether that
  becomes a third method on `BookWorkflow` is a call worth making after seeing it twice
  rather than by writing it four times.

- **Nothing records what the user was actually shown.** Every node that writes prose
  renders its own facts block beside the SSE calls, because `send_chars`,
  `send_book_card` and `send_divider` write to the queue and retain nothing, and
  `self.messages` is a *model* trace (completions, tool results, one `AssistantMessage`
  per goal brief), not a transcript. That reconstruction is where the wording hazards
  come from — `render_title_facts` has to say `3 of them on screen` by hand, and a writer
  handed only the rows would describe forty editions as three. A `ui_messages`
  accumulator — the prose and the preview rows exactly as sent, separate from pipeline
  context — would let a reply be written from the screen instead. `run_llm_reply` takes
  `facts` as one opaque string partly so that when this exists the base can render it
  without every slice changing shape.

- **A chain that continues past the similarity search writes its note too early.** The
  node writes about its 250-book pool; a `Combine_Intersect` after it then shows a
  narrower set of cards with no prose about them. The one plan shape where the deleted
  generation goal was strictly better.
