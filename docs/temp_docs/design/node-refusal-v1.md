# When a node can't do the work: refusal and empty results (design record)

**Updated:** 2026-10-08 · **Status:** proposed, not built.

Two problems share one root: **a node handed work it cannot do has no way to say so.** It
can finalize `ok=True` (claiming it did the job) or raise (claiming the code broke). The
honest third answer — "I ran fine, and this was the wrong node for this" — does not exist.

## Problem 1 — the args parser cannot decline

**Now.** When a request offers one tool model, `OpenAIParserRequest.to_payload`
(`clients/openai_requests.py`) pins `tool_choice` to it, so the parse is mandatory. "Give
me a book about war" mis-routed to `Retrieve_by_Title` must produce a `FindByTitleArgs`, so
it produces `title="war"`, counts the matches and finalizes `ok=True`. Downstream, that is
indistinguishable from a real title search.

`Retrieve_by_Lexical_Traits` now gives that ask a correct plan, so a mis-route like this is
evidence about routing quality, not a gap in the catalog.

**Proposed.** Let the parser *choose* the tool. When it declines, its text is the refusal
("this node needs a book title"), and the node finalizes **`ok=False` with no runtime
error**, carrying the message so the reply can say it plainly.

**This amends a written rule.** Executor rule 2 in `backend/app/domains/README.md` says
"raise when the node cannot proceed; never hand-set `ok=False` and return". The reason to
amend it: a business dead-end that raises and a genuine crash both land in
`runtime_error`, so the record cannot tell them apart (the review page has the same
problem — see [backlog.md](../backlog.md)). A mis-routed goal is a third thing, and
raising is the worst way to report it.

**Touch points:**

| | |
|---|---|
| `clients/openai_requests.py` | `tool_choice` pinned for a single tool model; needs to become optional per request |
| `app/domains/base_workflow.py` | `run_llm_tool_calls` raises on "no tool calls"; that path becomes the refusal |
| each slice's `finalize_result` | a declined parse leaves `args` None, which already reads as not-ok; the missing half is the message |
| `app/orchestration/task_runner.py` | a not-ok goal becomes a `FailedGoalOutput`; its `reason` is where a refusal message would travel to the reply |

**Open:** whether the refusal rides on a new output field or on `details`, and whether the
planner is re-invoked in the same turn (there is no re-plan loop; the turn is single-pass).

## Problem 2 — `num_books == 0` is right for the producer, wrong for the consumer

**The contract.** `BookRetrievalOutput` says `num_books == 0` is a real answer — nothing
matched, not a failure — so the reply has an answer to write from rather than a stack
trace. That holds and should stay.

**Where it breaks.** One step later, in a node that consumes the output. A 0-count query
composed into an anchor is an OR branch that scans and contributes nothing, while making
the anchor look populated.

**What already handles it.** `ParsedDependents.from_anchors`
(`books/find_similar_books/dependents.py`) sorts 0-count anchors into an `empty` pile
instead of pooling them, and the similarity node raises when nothing is left. That raise is
Problem 1 in another form: with refusal, it would be `ok=False` with a reason.

**The remaining options:**

1. **Answer in the producing node.** Rejected in effect: the reply stage now explains
   empties from the failure artifacts, and a node answering for itself would duplicate it
   ("I found no books" in one section, "so I can't continue" in the next).
2. **Don't pass it on.** Withhold 0-count outputs from dependents in the runner, or drop
   them in each consumer (done for the similarity node).
3. **Skip the consumer** when every dependency is empty. The reply stage already gives
   this somewhere to put its explanation, through the `FailedGoalOutput` reason.

Option 3 is the one to build when this is picked up.

## When to build it

The original triggers have been met: the catalog covers thematic asks, and a reply stage
exists to carry a refusal to the user. What is still missing is evidence that it matters:

- `make suite-goals` showing mis-routes that a declining parser would have caught, or
- traces where a forced parse produced a confident wrong answer.

It also touches the V1.1 conversation seams: a refusal that travels back to the planner
is a re-plan loop, which is the same machinery as clarification across turns.
