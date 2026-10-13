# 004: anchor and candidate outputs

**Status:** accepted · 2026-08-22

## Context

`Analyze_Similar_Books` folds the books it is given into one description. That works for a book the user named and fails for a 358-book subject search, but both arrived as the same `BookRetrievalOutput`, so the only guard was a runtime check inside the node. One similarity search could also seed the next.

## Decision

`BookRetrievalOutput` splits by **whether the user named the books**, not by how many there are:

- **`BookAnchorOutput`:** the user named these (`Retrieve_by_Title`).
- **`BookCandidateOutput`:** these match a description (author, lexical and numeric searches, and the similarity pool, whose description the system wrote).

Neither adds a field. The task runner fills inputs by `isinstance`, so the type *is* the payload: a node declaring `list[BookAnchorOutput]` cannot be handed a subject search, and the runner skips the goal naming the field instead.

The base stays concrete and means "either, not anchorable". `CombineIntersectOutput` lands on it, because an intersection of two titles is anchor-shaped and one of two subject searches is not, and the class can't know which. A node that wants both writes `list[BookAnchorOutput | BookCandidateOutput]`.

## Consequences

- **"Named", not "small":** a title search can still match several editions, so a node that folds anchors still needs a cap (`MAX_ANCHOR_BOOKS`).
- An author's bibliography is a candidate, because the node can't tell twelve books from eight hundred. "Books like Frank Herbert's" cannot anchor on it.
- "Books like Harry Potter by Rowling" anchors on the title retrieval, not on the intersect.
- No pydantic discriminated union: `isinstance` against a subscripted generic raises, and the class already is the discriminator.
- When a plan sends an anchor and a candidate to a `list[BookAnchorOutput]` field, the candidate is dropped with only a debug log line.
