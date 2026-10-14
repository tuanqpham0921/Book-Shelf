# 002: the planner picks capability nodes

**Status:** accepted for V1; the entity shape is the leading V2 candidate

## Context

The planner has to turn a sentence into something structured. Two shapes were tried:

- **Capability nodes.** One request schema per thing the system can do (`Retrieve_by_Title`, `Analyze_Similar_Books`, …). PlanJane picks node types and writes each goal's instruction, and each node parses its own small argument set.
- **Entity + intent.** One generic `BookEntity` extraction (title, authors, genre, page range, year, rating …) plus a separate intent (compare, recommend, look up), linked afterwards.

The entity shape was faster, worked on a smaller model, used fewer tokens (one schema instead of a catalog of docstrings) and could extract identifiers concurrently.

## Decision

1. **Capability nodes.** Each node is a registered schema, so the catalog states exactly what the system can and cannot do. Removing a capability is deleting one registry line, not editing a prompt and re-running a whole-entity eval.
2. **Goals carry their own dependencies.** PlanJane emits goals with ids and `depends_on` in one call.
3. **Each node parses its own arguments in its own call,** with its own prompt and model. A parse never runs when an upstream goal failed.
4. **The instruction is the node's whole brief.** No node reads the user's message. The planner's instruction is sent to the node's parser as an assistant message, because it is planner work, not something the user typed. So the instruction must be:
   - **self-contained:** every title, name, number and bound the node needs, as the user wrote it;
   - **scoped:** no other goal's work;
   - **resolvable:** no pronoun the node can't resolve alone ("books like Dune", not "books like it").

   It is bounded at 300 characters, not 100 like a label, because the bound truncates silently: a clipped label costs nothing, but a clipped "…published before 20" parses into the wrong filter.

The entity shape lost on four points:

- A wide entity invites the model to fill fields the message never mentioned (`authors` on "fiction, 100 to 200 pages"), and stopping that needs book-specific examples in a prompt that is otherwise generic.
- The entity still has to be linked, which brings back the call it was meant to save, and a per-request linker prompt caches worse than a byte-identical catalog.
- The analyze nodes already are intents, so entity-first arrives back at this design one abstraction later.
- Adding a capability here is cheap and local: a slice, a spec line, eval cases.

## Consequences

- More tokens, and one extra LLM call per node, in exchange for determinism, a generic planner prompt and a catalog that can't over-promise. `make tools-catalog` prints the current cost; full docstrings cost about 1k fewer tokens per node than shipping each pydantic model.
- Instruction quality has no automated check: the golden test diffs node types only.
- **Routing stays in the planner, not inside nodes.** A node that branches on runtime facts (how many books came back) becomes a second planner with no catalog, no diagram and no eval, and its branches are hidden from the golden test. Revisit when a suite can score a branch that exists only at runtime.
