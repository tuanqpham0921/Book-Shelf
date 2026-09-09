# Planner shape: capability nodes vs. entity + intent (decision record)

**Date:** 2026-07-24 · **Status:** accepted for V1 — revisit as a V2 cost optimization

Graduated from `backend/TODO.md` (the "book entity" experiment notes, 2026-07-21/24).
The node set this decision produces is recorded in
[node-taxonomy-v1.md](node-taxonomy-v1.md); the phases that build on it are in
[../roadmap.md](../roadmap.md).

## The question

The planner's first stage has to turn a sentence into something structured. Two shapes
were on the table, and the repo has now tried both:

- **Capability nodes (current).** One request schema per thing the system can do —
  `Retrieve_by_Title`, `Retrieve_by_Author`, `Retrieve_by_Lexical_Traits`, `Analyze_Recommend`, …
  The LLM picks a node type and fills that node's small argument set.
- **Entity + intent.** One generic `BookEntity` extraction (title, authors, genre, page
  range, year, rating …) plus a separate intent identifier (compare / recommend /
  look up), linked afterwards.

## Evidence for the entity shape

Real, and the reason it kept coming back:

- Noticeably faster, and it works acceptably on a **smaller model** — less decision-making
  asked of the LLM per call.
- Fewer tokens: one database request schema instead of N node docstrings in the catalog.
- Multiple identifiers could be extracted **concurrently**.

## Why V1 keeps capability nodes anyway

1. **The catalog is the capability contract.** Because each node is a separate registered
   schema, the tool catalog literally states what the system can and cannot do. There is
   no `published_year` node, so nothing offers to filter on publication year. With one
   big entity, every field is implicitly on offer, and removing a capability means editing
   a system prompt and re-running a whole-entity eval instead of deleting a registry line.
2. **One big field is hard to constrain case by case.** "Get books with 100–200 pages,
   fiction" has no author in it, but a wide entity schema invites the model to fill
   `authors` anyway. Preventing that means prompt examples per field — book-specific
   wording back in a prompt that [roadmap Phase 2](../roadmap.md) deliberately made
   generic.
3. **The entity still has to be linked, and linking is the expensive part.** The whole
   entity blob would have to be passed into a linker/intent step. That is worse for prompt
   caching (the blob varies every request, unlike the byte-identical catalog) and it
   re-introduces the second call the entity shape was supposed to save.
4. **The analyze nodes are already intents.** Going entity-first would still require an
   intent identifier plus a linkage step — `compare_books(entity[book1, book2])` is the
   same graph the current planner already produces. The rewrite would arrive back at the
   present design, one abstraction later.
5. **Adding a field is cheap and local.** New capability → new schema + registry line +
   eval cases (`backend/app/domains/README.md`). The system prompt stays generic, which is
   the property that makes this planner reusable outside the book domain.

**Accepted tradeoff:** V1 pays more tokens and one extra LLM call for determinism, a
generic prompt, and a catalog that cannot over-promise. Cost reduction is a V2 project,
and the entity shape is the leading candidate there — possibly as a *split* entity
(retrieval-task goals + intent goals, then link), which is close to what exists now.

**Supporting measurement:** verbose docstrings are worth their tokens; shipping each
node's full pydantic model instead would cost roughly **1k more tokens per node**. Run
`make tools-catalog` to see the current per-tool cost and the per-request catalog price,
cached and uncached.

## The instruction (settled 2026-09-07)

`SystemGoal.description` was renamed to **`instruction`** — with `NodeInput.query` →
`instruction` and `NodeWorkflowOutput.goal_description` → `goal_instruction`, so one word
means one thing along the whole path.

The rename records what was already true rather than changing behaviour. The field was
never a label: it is the *only* thing a node is told about the ask, because no node reads
`ctx.user_message`, and every slice already shipped it to its argument parser as an
`AssistantMessage` under the comment "the goal text is the planner's own work, not
something the user typed". The open-experiment bullet above had noticed the same thing
from the other side.

What the name buys is a contract the planner prompt can state and the docstring can hold:

- **Self-contained.** Carry every literal the node needs — titles, author names, numbers,
  bounds — as the user wrote them.
- **Scoped.** Carry no work belonging to another goal; drop the parts of the message this
  node is not for.
- **Resolvable.** No pronoun or back-reference the node cannot resolve alone. "books like
  it" is unusable; "books like Dune" is not.

Two consequences worth keeping:

- **The bound is its own constant.** `MAX_INSTRUCTION_LENGTH` is 300, not `reasoning`'s
  `MAX_STRING_LENGTH` of 100, because `bounded_string` truncates *silently*. Losing the
  tail of a label costs nothing; "…and published before 20" still parses, into the wrong
  filter.
- **The node that writes prose reads it.** `Generate_Recommendations` did, for the one day
  it existed; with that node deleted (2026-09-08) it is `Analyze_Similar_Books`, which
  renders the instruction as the `asked for:` line of the summary its reply is written
  from. Either way the point stands: the argument for planning generation at all ("the
  instruction can say *what to write*") is only true if something reads the line. See
  [execution-pipeline-v1.md](execution-pipeline-v1.md).

**Not covered by the golden test.** `evals/report_system_goals.py` diffs
`target_node_type` only, so instruction *text* has no automated check — the suite catches
a planner that picks the wrong node, not one that writes a thin instruction. That is the
standing gap this contract is enforced against by prompt and review.

## The generation instruction (planner half 2026-09-08, delivered 2026-09-09)

A goal now carries a **second, optional brief**: `SystemGoal.generation_instruction`,
what this step is to *say* back, as against `instruction`, what it is to *do*. It is
`None` on almost every goal.

The case that motivated it is a message with two halves of different kinds: *"do you have
Dune, and can you recommend something like it?"* The plan is the same two goals as the
plain recommendation ask — the "do you have it" adds no node, because the lookup is
already running. What it adds is a demand to hear the answer in words rather than in book
cards, and that demand belongs to the goal that answers it. So it is a field on the goal
and not a goal of its own, which is the same conclusion the generation-node reversal
reached from the other end (a stage whose only job is to talk about someone else's work
has to go looking for that work; see [execution-pipeline-v1.md](execution-pipeline-v1.md)).

The rules the prompt states:

- **Null is the default, and null is not silence.** An analyze node writes a reply either
  way. Null there means "no special ask", so a bare "recommend me something like Dune"
  leaves the field empty and still gets prose. On a retrieval or combine goal, a non-null
  value is asking for prose that step would not otherwise write.
- **It is the ask, never the answer.** The goal has not run, so the planner cannot know
  what it found. "Confirm whether Dune is in the catalogue", not "Yes, we have Dune".
- **Same self-containment as `instruction`,** and the same bound — 300 characters via
  `OptionalInstructionStr`, not `reasoning`'s 100 — for the same reason: it is a direction,
  and `bounded_string` truncates silently. The one difference is the fallback: blank stays
  `None` rather than becoming a placeholder string, because an empty ask has to read as no
  ask at all downstream.
- **One goal's ask never lands on another goal.** The goal that finds the books is the goal
  that talks about them.

Strict tool calling puts every property in `required`, so the model emits the field on
every goal and writes `null` where there is no ask — "leave it null", not "omit it", is
what the prompt has to say. And when the field does reach a node it arrives in the same
position as `instruction`: planner prose paraphrasing an untrusted message, trusted as a
description of the ask and not as an instruction to the writer. The shared reply prompt
(`app/domains/prompts/reply.txt`) states that rule once, for both lines — use them to know
what the step was set to do and what to cover, never quote either back — so no slice
restates it and no slice can forget to.

### Delivery (2026-09-09)

Three decisions, and each one was forced by something already in the code.

**How it reaches the node: by name, alongside `instruction`.** `build_input` gained a
keyword-only `generation_instruction` and now fills *both* of the goal's briefs by name,
leaving everything else by type. The rule that replaced "by type, never by name" is
sharper than the old one: **a field is filled by name when it comes from the goal, and by
type when it comes from an artifact.** There are exactly two of the former. Passing the
whole `SystemGoal` instead was the obvious alternative and is not available —
`node_input.py` importing `planjane.external` closes a cycle (`planjane/external` →
registry → specs → `node_input`).

**Where it is declared: on the slice, not on `NodeInput`.** The symmetric-looking choice
is wrong here. `node_input.py` opens by saying a declared field a node never reads "would
make the field a lie", and `Combine_Intersect` makes no LLM call at all, so it cannot
speak under any plan. Declaring the field is therefore the *claim* — this node can be
asked to answer in words — which is exactly what an input class is for. Two declare it:
`FindByTitleInput` and `SimilarBooksInput`. The cost this seemed to avoid was imaginary:
`build_input` iterates `model_fields`, so the by-name branch simply never fires on a class
that does not declare it.

**What a node does with it: writes, through one shared call.** `AppWorkflow.run_llm_reply`
is the reply's counterpart to `run_llm_args_parse` — the base owns delivery and voice (the
streaming request, and `domains/prompts/reply.txt`: role, trust boundary, tone, and what
`asked for` and `asked to say` mean), the slice owns content (its rendered `facts`, its own
`guidance`, its own model and budget). `asked_to_say` is appended to the *facts*, not the
prompt, which is what puts it in the trust position the paragraph above describes. The two
callers differ exactly where the null rule says they should: `find_by_title` gates on the
field and stays silent without it; `find_similar_books` writes either way and lets it
steer.

One consequence worth stating because it is not obvious: the runner reads the brief off
the **assembled input** (not off the goal) to decide whether a goal's UI section is
folded. A node that cannot speak never gets an expanded, prose-less section, and an answer
never arrives hidden behind a disclosure triangle.

What this does **not** fix: a title lookup that matches nothing *succeeds*, so the
similarity goal after it still dispatches and dies in `check_anchors` with nothing said
about why. See [execution-pipeline-v1.md](execution-pipeline-v1.md).

**Not covered by the golden test either,** for the same reason as the instruction:
`expected_nodes` is a list of node types, and this field changes no node type. A planner
that never fills it and one that fills it on every goal produce identical suite reports.

## Open experiments (not decided)

### 1. System goals as the dependency linker

Today: `parse_intent` produces goals, `strategy_classification` fills arguments *and*
resolves `depends_on`. The experiment is to have the goal stage emit dependencies too
(`goal_1`, `goal_2` …), validated against `NodeTypeEnum`, and measure completion cost.

- **For:** goals and tasks are already 1-1, so if goals carry the dependencies, every
  argument parser could run **independently and in parallel**. The dependency field is
  cheap — it is just goal ids, not prose. The goal's text already doubles as a
  rewrite of the user's query for the parser, which is useful on its own — **settled
  2026-09-07**, see "The instruction" below.
- **Against:** the goal stage becomes the planner *and* the source of truth. If even a
  frontier model misclassifies often, there is no second opinion; keeping the parser and
  linkage separate leaves room for best-effort injection, and the parser doubles as a
  mistake catcher. Completion cost may rise, and it may need reasoning fields or better
  query normalization to hold quality.
- **Related:** `depends_on` may be droppable from the parser entirely, since each goal
  already carries exactly one `node_type`.
- **Retrieval intent:** retrieval nodes may want a `purpose` field (for reference, for
  verification, for information). Worked example — *"Did Jane Austen write Dune?"* becomes
  `Retrieve_by_Title` with the goal *"Find Dune by Jane Austen to verify authorship"*;
  the intent is currently only implied by the instruction. Still open, and now cheaper to
  decline: a 300-character instruction has room to *say* "to verify authorship", so the
  question is whether a node can act on a typed field that it cannot act on as prose.

### 2. Vector embeddings for routing and retrieval

`book_store.search_by_embedding` already exists. Unmeasured questions:

- Single-word embeddings for **genre** and **author names** — how closely related do near
  misses actually score?
- Embedding a composed record ("title, page count, description …") and querying it
  semantically — would *"find books with 100 pages"* be caught by similarity alone, or
  does it need the structured filter path?

### 3. Planner semantics still unanswered

- Should the model be allowed to **infer contradictory constraints**, or must it refuse?
  (Adversarial suite territory — the clarification node in
  [roadmap Phase 1](../roadmap.md) is the mechanism either way.)
- Do system goals need explicit **numbering**, or is multi-step ordering enough?
- Should small talk and gibberish be filtered **before** the goal stage rather than
  becoming goals? (See [backlog.md](../backlog.md).)
- Was the planner's edge-linking separation optimized away too early? Recorded here so
  the question survives; the answer likely comes from executor work, not more planner
  tinkering.
- **Duplicate goals.** The split planner occasionally emits two goals for one ask. Rare
  enough that nothing has been built for it; noted so it is not mistaken for a new
  regression when it shows up in a run. (Graduated from `backend/TODO.md` 2026-09-07.)
- **Domain pre-filtering as a catalog shrink.** The goal stage has to link across the
  whole catalog, where the old two-stage planner had already narrowed it. Filtering by
  domain first (book / project / user), then by tier, would cut the choices the linker
  weighs. Recorded with the owner's own verdict attached — *"I don't think it's the main
  issue tho; linkage and goal setting seem okay"* — so it stays a cheap idea rather than
  a planned change. `make tools-catalog` prints the per-request cost of shipping the
  catalog, which is what would say whether this is worth anything.

### 4. Routing inside a node vs. routing in the planner

Graduated from `backend/TODO.md` 2026-09-07, where it ran to ~90 lines. The question:
should a node like `Analyze_Similar_Books` do its **own** runtime routing — branch on what
it was given, retrieve what it lacks, then search — instead of the planner deciding the
whole shape up front?

The sketch was a recommend node that owns the branches:

```
run(instruction, artifacts):
    if the ask compares two books and then recommends → compare first, take the winner
    if it names an author + a genre + a bound      → author, then narrow, then check
                                                      enough books survive to embed
    if it names reference books                    → retrieve them, check what came back
    if it names none                               → metadata lookup only, no embedding
    ── common tail ──
    build the ideal-book description → embed → search → re-rank → show and tell
```

- **For:** those branches are decisions that want **runtime** facts — how many books came
  back, whether the anchors resolved, whether anything survives a bound — and the planner
  decides before any of that is known. Everything above the "common tail" is exactly what
  the planner does today, so this is a relocation, not new behavior.
- **Against, and why V1 does not do it:** *"if you don't [keep it flat], then you'll make
  the recommend node the planner."* One node absorbing routing becomes a second planner
  with no catalog, no diagram and no eval. The flat plan is legible — one query shows the
  whole picture — and it is what `make suite-goals` scores; a nested node hides its
  branches from the golden test entirely. Testing gets harder in kind, not just in degree:
  a flat plan mocks one layer, a nested one mocks a tree (`b1 → b11, b12`).
- **The middle options are already in play.** "Several versions of the recommend node,
  each with a primary task" and "cache deterministic plans for common shapes" are both the
  same idea as the if-branches, moved somewhere legible — the second is the *pre-made
  graphs* item in [../backlog.md](../backlog.md) (`find title → recommend`, `recommend me
  something`).
- **Deferred for a stated reason:** *"this can be for later, since you don't have eval for
  it"* — there is no measurement that would say the nested version routes better, so
  building it would be a preference, not a finding. Revisit when a suite can score a
  branch that only exists at runtime.

Note the tension with experiment 1: that one moves *more* work into a single planner
stage, this one moves work *out* of the planner into nodes. They are the two directions
out of today's shape, and the evidence that would settle either is the same — eval cases
whose correct plan depends on a count nobody has yet.

## Standing note

From the owner's 2026-07-24 entry, and the reason this record exists: *"I think I can
tinker with the planner and system goals forever. It works well enough for now. I need to
get the executors in, because then I know what they need first and I can go back to the
planner."* The 2026-07-24 eval baseline (157/164, see [../eval-strategy.md](../eval-strategy.md))
is the evidence that the planner is good enough to build on — every remaining red traces
to the one node that was never built, not to routing quality.
