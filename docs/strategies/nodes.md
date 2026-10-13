# Node strategy

BookShelf grows by adding nodes: each capability is one slice the planner can pick, and the planner's prompt stays generic. The step-by-step recipe is in [the domains README](../../backend/app/domains/README.md#adding-a-node); this page says when a new node is the right move and how to keep the catalog honest.

## When to add a node

- **A new capability, not a new flag.** If the ask is something an existing node does with one more argument, it is still a new slice ([decision 002](../decisions/002-capability-nodes.md)), so a model or prompt can change for one node alone.
- **Compose before you add.** A cross-dimension ask is existing retrievals joined by `Combine_Intersect`, not a node that searches two columns ([decision 003](../decisions/003-one-dimension-nodes.md)).
- **Only what a `books` row can answer.** The catalog holds author, year, pages, rating, shelf, genre and a marketing blurb. "Who wrote Dune" is answerable; "who is the main character" is not. A node over the blurb will match words and answer confidently anyway, so a node needs a column that actually holds its answer.
- **Pick the output shape on purpose.** Books the user named are anchors; books matching a description are candidates ([decision 004](../decisions/004-anchors-and-candidates.md)). The shape decides which nodes can depend on it.

## Keeping the catalog honest

- **The request docstring is prompt text.** It is all the planner reads. Write `Do not use:` and `Example queries:`, the sections that prevent misroutes.
- **Every tool costs tokens on every request.** The catalog is sent whole to the planner each turn. Check `make tools-catalog` after adding or editing a node.
- **Add eval cases with the node,** so the golden test knows what the new plan looks like ([eval strategy](evals.md)).
- **Park, don't delete, to test.** Removing a spec from the domain's `guide.py` hides the node from the planner and leaves the code.

## Designed, not built

| Node | What it would do |
|---|---|
| `Retrieve_by_ISBN13` | exact ISBN lookup; an anchor |
| `Retrieve_by_CoAuthors` | joint works only: two or more authors on the same book; the one multi-value node |
| `Retrieve_Random` | one arbitrary pick with an optional filter, for the bare "recommend me a book"; never feeds a combine node |
| `Combine_Union` | an explicit OR, for when a pooled set is itself a step; has a precondition in [decision 005](../decisions/005-counts-first-retrieval.md) |
| `Analyze_Compare` | compare books on metadata; needs a single-book analyze node first |

**Compare comes in two kinds.** Comparing for information ("which is longer, Dune or IT?") is the answer itself. Comparing to pick a winner ("books like whichever is shorter") feeds a later goal, and only that kind needs a dependency contract. The winner need not travel as a book: a title is enough for the next goal to anchor on.
