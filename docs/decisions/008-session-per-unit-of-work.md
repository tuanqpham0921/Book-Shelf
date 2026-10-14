# 008: a database session per unit of work

**Status:** accepted · 2026-09-23

## Context

A chat turn runs *after* its HTTP handler returns. FastAPI closes yield-dependencies at that point, which for the SSE route is before the first event is sent, so a session opened per request was already closed when the turn used it. Machinery had grown to work around that (`NodeSpec.context`, `RequestContext.stores`, `require_store()`), resolving one store per domain at dispatch only because the store had to be built before it was used.

## Decision

`RequestContext` carries only the session factory. `ctx.store(SomeStore)` is an async context manager over `session_factory.begin()`: it yields the store, then commits and closes.

- **Keep the block around the round trip and nothing else.** It holds a pooled connection and an open transaction while entered. Building a query needs no store.
- **No store commits for itself.** The block owns the transaction.
- Plain HTTP routes keep a request-scoped session, because there the request *is* the unit of work.

## Consequences

- A connection is held only around a round trip, not for a whole SSE stream, which is what lets three instances share a small pool ([database strategy](../strategies/database.md#pool-sizing)).
- The shielded end-of-turn write (the token debit, the recorded run) can outlive the request.
- Several sessions per turn instead of one, so two writes in a turn are not one transaction.
