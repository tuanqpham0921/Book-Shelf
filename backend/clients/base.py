"""The provider-neutral interfaces: `BaseLLMRequest` and `BaseLLMClient`."""

from abc import ABC, abstractmethod
from typing import Any, Optional

import asyncio
from pydantic import BaseModel, ConfigDict, Field
from clients.messages import APIMessage, AssistantMessage
from app.common.sse_stream import SSEStream

import logging

logger = logging.getLogger(__name__)


class BaseLLMRequest(BaseModel, ABC):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    prompt: str = Field(..., exclude=True)
    # Where the prompt came from, relative to the prompts directory — what a
    # trace shows in its place
    prompt_path: str
    messages: list[APIMessage]
    model: str

    # NOTE: the one app import left in clients/ (see docs/backlog.md).
    sse_stream: Optional[SSEStream] = Field(default=None, exclude=True)

    @abstractmethod
    def to_payload(self) -> dict[str, Any]: ...


class BaseLLMClient(ABC):
    """Abstract base interface for all LLM providers.

    **Tracing-free by design.** No `@task` anywhere in clients/: a client
    method does its I/O and returns its payload, raising on failure like any
    plain function. The step envelope, the failure capture and the token-usage
    promotion all happen one layer up, on `AppWorkflow`'s thin wrappers
    (`llm_execute`, `get_embeddings`) — the app decides what is a step, the
    client doesn't know envelopes exist.
    """

    client: Any
    max_input_tokens: int
    semaphore: asyncio.Semaphore

    @abstractmethod
    async def execute(
        self, req: BaseLLMRequest, save_payload: bool = False
    ) -> AssistantMessage:
        """Execute a request (stream or not) and return the message itself.
        Failures raise; the app's wrapper task is what turns one into a
        recorded step failure."""
        ...

    @abstractmethod
    async def close(self):
        """Close any resources used by the client."""
        ...

    @abstractmethod
    def token_count(self, text: str) -> int:
        """Count the number of tokens in the text."""
        ...

    def over_max_tokens(self, token_count: int) -> bool:
        return token_count > self.max_input_tokens
