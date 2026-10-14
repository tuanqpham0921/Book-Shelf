"""`SSEStream`, the turn's outbound event queue: workflows `send` typed events
into it, and the chat route drains it as server-sent events. The events and
their payloads are listed in frontend/src/README.md.
"""

import asyncio
import json
import logging
from typing import Any

from sse_starlette import ServerSentEvent

logger = logging.getLogger(__name__)

SSE_TIMEOUT = 120  # seconds the consumer waits for the next event


class SSEStream:
    """One turn's event queue. Sends after `close()` are dropped, and the
    consumer stops only once it has drained everything queued before it."""

    def __init__(self) -> None:
        self._queue = asyncio.Queue()
        self._stream_end = object()
        # _closed: producer is done sending (guards re-entrant close()/put()).
        # _finished: consumer has actually drained the end sentinel — only
        # this should stop __anext__, otherwise items still sitting in the
        # queue when close() fires get silently dropped.
        self._closed = False
        self._finished = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._finished:
            raise StopAsyncIteration

        # NOTE: no early return on self._closed here — close() enqueues the
        # _stream_end sentinel rather than stopping iteration directly, so a
        # closed-but-not-finished stream must still drain the queue (which
        # may hold real events queued before close(), then the sentinel).
        # Returning early on _closed orphans that sentinel: _finished never
        # flips, and the caller's `async for` spins on None forever.
        try:
            data = await asyncio.wait_for(self._queue.get(), timeout=SSE_TIMEOUT)
            if data is self._stream_end:
                self._finished = True
                raise StopAsyncIteration
            return ServerSentEvent(data=data)
        except asyncio.CancelledError:
            self._finished = True
            raise
        except asyncio.TimeoutError:
            logger.error("⏰ SSE stream timeout")
            self._finished = True
            raise StopAsyncIteration
        except StopAsyncIteration:
            raise
        except Exception as e:
            logger.exception(f"❌ SSE stream error: {e}")
            self._finished = True
            raise StopAsyncIteration

    async def put(self, data: str | dict):
        """Queue one raw payload; a dict is JSON-encoded. Prefer `send`."""
        if self._closed or self._finished:
            return

        if isinstance(data, dict):
            data = json.dumps(data)

        try:
            await self._queue.put(data)
        except Exception as e:
            logger.exception(f"❌ Error putting data into the queue: {data} with type: {type(data)}", exc_info=e)
    
    async def send(self, event_type: str, data: dict[str, Any] | str):
        """Queue a `{type, data}` event. An empty type or data is dropped."""
        if self._closed or self._finished:
            return
        if not event_type or not data:
            return

        payload = {"type": event_type, "data": data}
        await self.put(json.dumps(payload))

    async def send_book_card(self, position: int, data: dict):
        """Send one book card, at `position` among its section's cards."""
        # TODO: nest under data, as {position, data}, like every other event
        if self._closed or self._finished or not data:
            return
        payload = {"type": "book_card", "position": position, "data": data}
        await self.put(json.dumps(payload))

    async def send_chars(self, data: str, delay: float = 0.01):
        """Stream text one `content.delta` per character, for a typing effect."""
        for ch in data:
            await self.send(event_type="content.delta", data=str(ch))
            await asyncio.sleep(delay)

    async def send_ui_loading(self, text: str):
        """Set the loading line under the chat."""
        await self.send(event_type="ui.loading", data=text)

    async def send_chat_id(self, chat_id: str):
        """Send the chat_id as soon as it's known, so the client can attach
        feedback to this run even if the turn later errors, times out, or
        is stopped before the final 'complete' event is reached."""
        await self.send(event_type="chat.id", data={"chat_id": chat_id})

    async def send_error(self, text: str):
        """Send an error message for the chat to show."""
        await self.send(event_type="error", data=text)

    async def send_divider(self, data: str = "\n\n---\n\n"):
        """Send a horizontal rule between parts of the reply."""
        # TODO: its own event type, so the UI can skip it after a section
        await self.send(event_type="content.delta", data=data)

    async def send_mermaid(self, data: str):
        """Send the plan's Mermaid diagram."""
        await self.send(event_type="mermaid.diagram", data=data)

    async def send_sources(self, sources: list[str]):
        """Send the docs a project answer rests on, shown under the reply."""
        await self.send(event_type="sources", data={"sources": sources})

    async def send_task_start(
        self, task_id: str, title: str, collapsible: bool = True
    ):
        """Open a task section. Everything streamed until the matching
        `send_task_end` nests inside it in the UI, so these must be paired —
        `TaskRunnerWorkflow` owns both ends and closes in a `finally`."""
        await self.send(
            event_type="task.start",
            data={"task_id": task_id, "title": title, "collapsible": collapsible},
        )

    async def send_task_end(
        self,
        task_id: str,
        count: int | None = None,
        ok: bool = True,
        details: dict[str, Any] | None = None,
    ):
        """Close a task section. `count` stamps the header and `details`
        fills the block above the cards, both after the fact — the section
        opens before the node has parsed, counted or spent anything."""
        await self.send(
            event_type="task.end",
            data={
                "task_id": task_id,
                "count": count,
                "ok": ok,
                "details": details or {},
            },
        )

    async def close(self):
        """End the stream after whatever is already queued."""
        if self._closed or self._finished:
            return

        self._closed = True
        await self._queue.put(self._stream_end)
        logger.info("🔚 Endpoint cleanup: closing SSE stream")