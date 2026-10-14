# 003: one dimension per node, composed by intersect

**Status:** accepted · 2026-08-24, when `Combine_Intersect` replaced `Filter_Retrieval`

## Context

"Horror by Stephen King over 500 pages" crosses three columns. The first node set handled that with `Filter_Retrieval`, a node that searched for a subject and parsed a second set of bounds on top. That gave two ways to express a bound, and put a filter object back on a planner-facing schema.

## Decision

1. **Each retrieval node searches one dimension, for one value:** one title, one author. Several authors' separate bibliographies are several `Retrieve_by_Author` goals.
2. **Cross-dimension asks are composition.** One retrieval per dimension, joined by `Combine_Intersect`, which searches for nothing itself and only narrows what earlier goals found. It takes two or more inputs of any book shape, so one intersect serves three conditions. The combine tier is the only place a plan says "and".
3. **Pooling is implicit.** Several ids in one `depends_on` mean OR. `Combine_Union` is for when a pooled set is itself a step something consumes.
4. **Two exceptions, both because their subject has no single dimension:**
   - `Retrieve_by_Numeric_Traits` carries a whole bounds filter. A bound is always the *subject* of its search ("books under 200 pages"); a bound beside another subject is this node plus an intersect.
   - `Retrieve_by_Lexical_Traits` carries keywords, fiction-ness and audience, ANDed, because "non-fiction about history" is one question.
5. **The request schema the planner sees is fieldless:** a docstring and a node-type literal. Arguments live on the slice's own `*Args` model, which only the node's parse call sees.
6. **`unknown` is a node type,** so the planner can decline a goal rather than pick a wrong one.
7. **There is no generate tier.** A plan finds things; the reply is written after it ([006](006-one-reply-stage.md)).

## Consequences

- **The dropped-intersect trap.** A plan that emits a subject and a bound but forgets the intersect pools them and answers with *more* books, not fewer. Both node docstrings warn about it, and the golden test can't catch it: a node-type diff can't tell "meant to pool" from "forgot to intersect".
- **A failed input widens the answer.** With three retrievals and one failed, the intersect still has two inputs and runs. The trace shows it ("12 ∩ 340"); nothing refuses it.
- Plans get longer: a three-condition ask is four goals.
- A future `Retrieve_Random` must never feed a combine node (intersecting a one-book pick almost always empties it); bounds on a surprise go in its own filter.
