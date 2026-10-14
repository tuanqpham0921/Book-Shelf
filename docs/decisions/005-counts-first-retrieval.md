# 005: counts-first retrieval

**Status:** accepted

## Context

Retrieval nodes used to fetch rows and hand them on. A later step then filtered a list someone else had fetched, and intersecting two capped lists was simply wrong: two 4-book previews almost never overlap, even when the full results do.

## Decision

**A retrieval node does not materialize its result.** It runs a `COUNT`, fetches a 4-book preview for its cards, and hands on a `DeferredBookQuery`. A later node composes against that query in SQL.

- **No LIMIT and no ORDER BY on a deferred query.** That is what makes it composable. Ordering and the cap are added only when rows are fetched.
- **One exception: the vector search.** It doesn't select a subset; it orders the whole table by cosine distance and truncates, so the cap (250 books, about 5% of the catalog) *is* the pool. Nothing on the class marks the exception: a flag and a compose guard were built and removed the same day, as machinery for a caller that didn't exist.
- **AND carries one score through.** An intersection is a subset of every input, so when exactly one input is scored, the score is defined on every row. That keeps "books like Dune under 300 pages" in similarity order. Two scores (say a trigram score and a text rank) can't be compared, so both are dropped.
- **OR drops every score,** because a union holds rows the scored input never matched.

## Consequences

- The count is known at every step before anything large is built. That is the natural pause point for human-in-the-loop ([010](010-human-in-the-loop.md)).
- More round trips: a count and a preview per retrieval. Fine when the LLM calls take seconds.
- An intersect over a similarity pool counts "of the 250 nearest, N also match". Accepted and not shown in the UI.
- **Before `Combine_Union` is registered,** either tune the similarity floor (`MIN_SIMILARITY`, untuned at 0.35) until the vector search needs no LIMIT, or restore a guard on scored inputs under OR. A tuned floor would also remove the exception outright.
