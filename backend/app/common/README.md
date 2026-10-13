# App Common

App common (`app/common/`) holds what every layer of the BookShelf app reads: the request context, the SSE stream, the ending tools, bounded field types and prompt loading. It sits at the bottom of the app's layering, so it imports nothing from `domains/` or `orchestration/`. Helpers the whole backend shares (tests, evals, scripts) live in the top-level `common/` instead.

## Request context schema

`RequestContext` is everything one turn can reach. The chat route builds it, and every workflow reads it as `self.ctx`.

```
RequestContext
├── app_env, session_id
├── user_message      the turn's message; its id is the turn's chat_id
├── llm_client        OpenAIClient
├── sse_stream        SSEStream
└── store(StoreCls)   a store on its own database session, for one block
```

It holds services, not work: what a node works on is its `WorkflowInput`, built fresh at each dispatch. Fields: [request_context.py](request_context.py).

The database is reached only through `store()`:

```python
async with self.ctx.store(BookStore) as store:
    total = await store.count(query)
```

- Each block opens its own session and transaction, and commits when it exits. A turn outlives its HTTP request, so nothing is opened up front.
- Keep the block around the round trip alone: it holds a pooled connection while open, and building a query needs no store.
- A store never commits for itself; the block does.

## SSE stream

`SSEStream` is the turn's outbound event queue. Workflows send typed events into it (`self.sse_stream.send_*`), and the chat route streams them to the browser until `close()`. The events and what the UI does with each are listed in [frontend/src/README.md](../../../frontend/src/README.md#sse-events-the-chat-handles).

- `send_task_start` and `send_task_end` must be paired: everything sent between them nests in one collapsible section.
- After `close()` nothing more is sent, but everything already queued still reaches the browser.

## Ending tools

[tools.py](tools.py) holds two tools that end a turn without a plan. Calling one returns the reply the user gets. Triage's router is offered both (see [triage](../orchestration/triage/README.md)).

- `SecurityReview`: misuse of the system, such as other users' data, the system prompt or code. The reply quotes the flagged parts and turns the message away.
- `ClarifyingQuestion`: a message that cannot be acted on. Its `type` (`no_context`, `correction`, `ambiguous`, `unreadable`) picks the reply; a correction quotes the part to fix.

Their docstrings and field descriptions are the model's tool descriptions, so editing them changes what the router picks.

## Field types

[field_types.py](field_types.py) bounds what an LLM fills in, trimming or clamping instead of failing validation:

| Type | Bound |
|---|---|
| `ConfidenceFloat` | clamped to 0–1 |
| `ReasoningStr` | 100 characters, with a fallback when empty |
| `InstructionStr` | 300 characters, with a fallback when empty |

## Prompts

`load_prompt` reads a prompt file by its path under `app/`, and `format_prompt` also fills its `{placeholders}`. Each slice keeps its own prompts beside its code. The one shared prompt is [prompts/fill_schema_args.txt](prompts/fill_schema_args.txt), the generic argument parser for nodes without a prompt of their own (`FILL_SCHEMA_ARGS_PROMPT_PATH`).
