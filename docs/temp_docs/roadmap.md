# V1 Roadmap

**Updated:** 2026-10-08

## V1 philosophy

A small, polished node set that showcases the **planner and orchestration
architecture**. Books are the demo domain; the planner is the point. Retrieval and
similarity cores, plus what makes the app feel complete: answering unclear or misused
messages instead of failing quietly, feedback, and clean single-turn conversation. No
user accounts, so preferences, saved books and reading history are out of scope. On the
frontend, **reduce** features rather than add them.

## Where V1 stands

**Built and live** at [tuanqpham0921.web.app](https://tuanqpham0921.web.app):

- **The request path end to end:** message check → triage → PlanJane → task runner →
  reply stage, streamed over SSE ([../CLAUDE.md](../CLAUDE.md), Request Flow).
- **Seven registered nodes**, all with real executors: four book retrievals,
  `Analyze_Similar_Books`, `Combine_Intersect`, and `Retrieve_Project_Info`
  ([design/node-taxonomy-v1.md](design/node-taxonomy-v1.md)).
- **Counts-first execution** and a one-per-turn reply written from every goal's result
  ([design/execution-pipeline-v1.md](design/execution-pipeline-v1.md)).
- **Answering what the planner shouldn't plan:** small talk, clarifying questions and
  misuse are answered by triage; harmful or gibberish messages by the message check;
  off-topic portions by the reply stage.
- **Spend controls:** a per-session token budget, a site-wide daily cap and a per-IP
  message limit, all enforced in production.
- **Deployment:** Cloud Run + Neon + Firebase Hosting, App Check, the review routes off
  in production ([deployment.md](deployment.md)).
- **Feedback:** thumbs up/down and comments on a chat, with an ownership check.

## Next

In rough priority order:

1. **Project questions in production.** The lookup searches an OpenAI vector store from
   the app (2026-10-09), and `make deploy` now sets the store id and the production key.
   Confirm one live lookup after the next deploy, then fix the lookup's token issues in
   [backlog.md](backlog.md).
2. **Refused goals get no reply.** A turn whose goals are all refused ends in the
   orchestrator's generic error (TODO in `planjane/executor.py`).
3. **The golden-test gate.** Re-baseline the suites against the current node set, set
   thresholds, and make `make suite-goals` the release gate
   ([eval-strategy.md](eval-strategy.md)).
4. **Human-in-the-loop**, pause point A first
   ([design/human-in-the-loop.md](design/human-in-the-loop.md)). The owner rates it the
   highest-value feature left.
5. **UI polish** from the backlog's UI and accessibility pools.

## Release checklist ("Definition of Done")

- [x] Every registered node plans **and executes** end to end with real data over SSE.
- [~] Ambiguous or unsupported input always gets a clarification or rejection reply —
  done in triage and the message check; refused planner goals are still open.
- [ ] Suites re-baselined and passing their thresholds via `make suite-goals`.
- [~] Security blockers closed — the review surface is off in production; `uuid_8`'s
  32-bit ids and the message-length literal remain ([backlog.md](backlog.md)).
- [ ] README, CLAUDE.md and `docs/` accurate against the code.
- [x] Chat feedback works with an ownership check.

## Deferred (V1.1 and beyond)

| Feature | Notes |
|---|---|
| **Multi-turn conversation** | V1.1 flagship. `chat_runs` already records turns; needs history loading, prompt changes and a summary. Triage turns a follow-up with no earlier turn into a clarification today. **The reply prompt asserts the opposite and must be unwound:** `write_reply/prompts/reply.txt` says the system keeps no memory between messages, and its no-questions rule leans on that |
| More book nodes | `Retrieve_by_ISBN13`, `Retrieve_by_CoAuthors`, `Retrieve_Random`, `Combine_Union` — designed in [design/node-taxonomy-v1.md](design/node-taxonomy-v1.md); `Combine_Union` has a precondition in [design/execution-pipeline-v1.md](design/execution-pipeline-v1.md) |
| `Analyze_Compare` and single-book analysis | Needs an analyze-book node first |
| Node refusal | [design/node-refusal-v1.md](design/node-refusal-v1.md) |
| User accounts and personalization | Preferences, saved books, reading history — all need a user DB |
| Checkpoint/resume and incremental step recording | Workflow-framework work in [backlog.md](backlog.md); blocker 1 for HITL |
| Server-side stop | No stop endpoint exists, client or server |
| Book-clamped recommendations | "Do you have Dune? — yes, and you'll like these" |
| A public review page | Needs real auth (an admin gate), not a bundled token — see [deployment.md](deployment.md) |
