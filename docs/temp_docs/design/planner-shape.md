# Planner shape: capability nodes vs. entity + intent (decision record)

**Updated:** 2026-10-08 · **Status:** accepted for V1 — revisit as a V2 cost optimization.

The node set this produces is in [node-taxonomy-v1.md](node-taxonomy-v1.md).

## The question

The planner has to turn a sentence into something structured. Two shapes were tried:

- **Capability nodes (current).** One request schema per thing the system can do
  (`Retrieve_by_Title`, `Analyze_Similar_Books`, …). PlanJane picks node types and writes
  each goal's instruction; each node then parses its own small argument set.
- **Entity + intent.** One generic `BookEntity` extraction (title, authors, genre, page
  range, year, rating …) plus a separate intent (compare / recommend / look up), linked
  afterwards.

## Evidence for the entity shape

- Noticeably faster, and acceptable on a **smaller model**.
- Fewer tokens: one schema instead of a catalog of node docstrings.
- Identifiers could be extracted **concurrently**.

## Why V1 keeps capability nodes

1. **The catalog is the capability contract.** Each node is a registered schema, so the
   catalog states exactly what the system can and cannot do. With one big entity, every
   field is implicitly on offer, and removing a capability means editing a prompt and
   re-running a whole-entity eval instead of deleting one registry line.
2. **One big schema is hard to constrain.** "Books with 100–200 pages, fiction" has no
   author, but a wide entity invites the model to fill `authors` anyway. Preventing that
   needs per-field prompt examples — book-specific wording in a prompt that is otherwise
   generic.
3. **The entity still has to be linked, and linking is the expensive part.** The blob
   would go to a linker step, which is worse for prompt caching (it varies per request,
   unlike the byte-identical catalog) and brings back the call it was meant to save.
4. **The analyze nodes already are intents.** Entity-first would still need an intent
   identifier and a linker, arriving back at the present design one abstraction later.
5. **Adding a capability is cheap and local:** a slice, a `SPEC` line, eval cases
   (`backend/app/domains/README.md`). The system prompt stays generic, which is what makes
   the planner reusable outside books.

**Accepted tradeoff:** more tokens and an extra call per node for determinism, a generic
prompt, and a catalog that cannot over-promise. The entity shape is the leading V2
candidate, possibly as a split entity (retrieval goals + intent goals, then link).

Verbose docstrings are worth their tokens: shipping each node's full pydantic model
instead would cost roughly 1k more tokens per node. `make tools-catalog` prints the
current per-tool and per-request cost.

## The instruction contract

`SystemGoal.instruction` is the **only** thing a node is told about the ask — no node
reads `ctx.user_message` — and each slice ships it to its parser as an
`AssistantMessage`, because it is planner work, not something the user typed. So it is a
contract on the planner, stated in its prompt and the field docstring:

- **Self-contained.** Carry every literal the node needs — titles, names, numbers,
  bounds — as the user wrote them.
- **Scoped.** Carry no other goal's work.
- **Resolvable.** No pronoun the node cannot resolve alone: "books like it" is unusable,
  "books like Dune" is not.

Its bound is `MAX_INSTRUCTION_LENGTH` (300), not `MAX_STRING_LENGTH` (100), because
`bounded_string` truncates *silently*: a clipped label costs nothing, a clipped
instruction ("…published before 20") parses into the wrong filter.

**Not covered by the golden test.** `report_system_goals.py` diffs `target_node_type`
only, so instruction quality has no automated check.

## Settled

- **Goals carry their own dependencies.** PlanJane emits goals with ids and `depends_on`
  in one call, and every node parses its own arguments in its own call. That lets
  parsers use per-node prompts and models, and an upstream failure means a downstream
  parse never runs.
- **Small talk, misuse and unclear messages are filtered before the planner,** by the
  message check and triage's router.

## Open experiments

### 1. Retrieval purpose

Retrieval goals might want a `purpose` (for reference, for verification, for
information). Example: "Did Jane Austen write Dune?" is `Retrieve_by_Title` with the
instruction "Find Dune by Jane Austen to verify authorship". A 300-character instruction
can already say "to verify authorship", so the question is whether a node can act on a
typed field it cannot act on as prose.

### 2. Embeddings for routing and retrieval

Unmeasured: how closely do single-word genre or author embeddings score against near
misses? Would a composed record embedding ("title, page count, description …") answer
"books with 100 pages" by similarity alone?

### 3. Planner semantics

- May the model **infer through contradictory constraints**, or must it refuse?
- **Duplicate goals:** the planner occasionally emits two goals for one ask. Rare; noted
  so it isn't mistaken for a new regression.
- **Domain pre-filtering** (book / project, then tier) to shrink the catalog. The owner's
  verdict: "I don't think it's the main issue". `make tools-catalog` says what it would
  save.

### 4. Routing inside a node vs. in the planner

Should a node like `Analyze_Similar_Books` branch on what it was given and retrieve what
it lacks, instead of the planner deciding the whole shape up front?

- **For:** those branches want runtime facts — how many books came back, whether anchors
  resolved — that the planner cannot know.
- **Against, and why V1 doesn't:** one node absorbing routing becomes a second planner
  with no catalog, no diagram and no eval. The flat plan is legible and is what
  `make suite-goals` scores; a nested node hides its branches from the golden test.
- **Middle options:** several narrower versions of a node, or cached plans for common
  shapes (see the Ideas pool in [../backlog.md](../backlog.md)).
- **Deferred** until a suite can score a branch that only exists at runtime.
