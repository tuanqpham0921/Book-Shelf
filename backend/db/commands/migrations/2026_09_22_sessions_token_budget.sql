-- Session token budget (2026-09-22).
-- A new sessions table: one row per session that has sent a message, carrying
-- the tokens it has left. The row is created on the first message and debited
-- once per turn by Orchestrator._finalize with the turn's whole spend (planner,
-- tasks and reply together); the chat route refuses a message once the balance
-- reaches zero. Existing chat_runs.session_id values are left alone — this adds
-- no foreign key, so rows for sessions that predate the table simply never exist
-- and those sessions get a fresh budget on their next message.
--
-- Apply with: make postgres-query FILE=db/commands/migrations/2026_09_22_sessions_token_budget.sql
-- On Neon:    make neon-cli ARGS='-f db/commands/migrations/2026_09_22_sessions_token_budget.sql'
BEGIN;

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_updated TIMESTAMPTZ NOT NULL DEFAULT now(),
    remaining_tokens INTEGER NOT NULL
);

COMMIT;
