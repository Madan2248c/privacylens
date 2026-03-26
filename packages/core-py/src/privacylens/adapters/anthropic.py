"""Anthropic adapter for PrivacyLens.

Wraps anthropic.Anthropic / anthropic.AsyncAnthropic to transparently mask
PII in messages.create calls, including streaming variants.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from privacylens.core.pipeline import Pipeline

# Regex that matches a complete [ENTITY_TYPE_N] token.
_TOKEN_RE = re.compile(r"\[[A-Z_]+_\d+\]")
# Regex that matches the *start* of a token (partial prefix).
_TOKEN_PREFIX_RE = re.compile(r"\[[A-Z_]*(?:_\d*)?$")


def _new_session_id() -> str:
    return str(uuid.uuid4())


class _StreamBuffer:
    """Accumulates partial [TOKEN] strings across streaming chunks."""

    def __init__(self) -> None:
        self._buf = ""

    def feed(self, chunk: str) -> str:
        self._buf += chunk
        match = _TOKEN_PREFIX_RE.search(self._buf)
        if match:
            safe = self._buf[: match.start()]
            self._buf = self._buf[match.start() :]
        else:
            safe = self._buf
            self._buf = ""
        return safe

    def flush(self) -> str:
        remaining = self._buf
        self._buf = ""
        return remaining


class _MessagesProxy:
    """Intercepts messages.create for both sync and async Anthropic clients."""

    def __init__(self, real_messages: Any, pipeline: Pipeline, is_async: bool) -> None:
        self._real = real_messages
        self._pipeline = pipeline
        self._is_async = is_async

    # ------------------------------------------------------------------
    # Sync path
    # ------------------------------------------------------------------

    def create(self, *, messages: Any, **kwargs: Any) -> Any:
        session_id = _new_session_id()
        tokenized = self._pipeline.tokenize_messages(messages, session_id)
        stream: bool = kwargs.get("stream", False)

        if stream:
            raw = self._real.create(messages=tokenized, **kwargs)
            return self._wrap_sync_stream(raw, session_id)

        response = self._real.create(messages=tokenized, **kwargs)
        for block in response.content:
            if hasattr(block, "text"):
                block.text = self._pipeline.detokenize(block.text, session_id)
        return response

    def _wrap_sync_stream(self, raw: Any, session_id: str) -> Iterator[Any]:
        buf = _StreamBuffer()
        with raw as stream:
            for event in stream:
                delta_text = _get_text_delta(event)
                if delta_text is not None:
                    safe = buf.feed(delta_text)
                    if safe:
                        safe = self._pipeline.detokenize(safe, session_id)
                    _set_text_delta(event, safe)
                yield event
        remaining = buf.flush()
        if remaining:
            self._pipeline.detokenize(remaining, session_id)

    # ------------------------------------------------------------------
    # Async path
    # ------------------------------------------------------------------

    async def acreate(self, *, messages: Any, **kwargs: Any) -> Any:
        session_id = _new_session_id()
        tokenized = self._pipeline.tokenize_messages(messages, session_id)
        stream: bool = kwargs.get("stream", False)

        if stream:
            raw = await self._real.create(messages=tokenized, **kwargs)
            return self._wrap_async_stream(raw, session_id)

        response = await self._real.create(messages=tokenized, **kwargs)
        for block in response.content:
            if hasattr(block, "text"):
                block.text = self._pipeline.detokenize(block.text, session_id)
        return response

    async def _wrap_async_stream(
        self, raw: Any, session_id: str
    ) -> AsyncIterator[Any]:
        buf = _StreamBuffer()
        async with raw as stream:
            async for event in stream:
                delta_text = _get_text_delta(event)
                if delta_text is not None:
                    safe = buf.feed(delta_text)
                    if safe:
                        safe = self._pipeline.detokenize(safe, session_id)
                    _set_text_delta(event, safe)
                yield event
        remaining = buf.flush()
        if remaining:
            self._pipeline.detokenize(remaining, session_id)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


class AnthropicAdapter:
    """Proxy wrapper around an anthropic.Anthropic or anthropic.AsyncAnthropic client.

    Intercepts ``messages.create``, tokenizes PII in messages, and
    de-tokenizes the response content blocks.  All other attributes are
    proxied transparently to the underlying client.

    Args:
        client: An ``anthropic.Anthropic`` or ``anthropic.AsyncAnthropic`` instance.
        pipeline: The PrivacyLens pipeline to use for tokenization.
    """

    def __init__(self, client: Any, pipeline: Pipeline) -> None:
        self._client = client
        self._pipeline = pipeline
        is_async = type(client).__name__ == "AsyncAnthropic"
        self.messages = _MessagesProxy(client.messages, pipeline, is_async)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)

    def __repr__(self) -> str:
        return f"AnthropicAdapter(client={self._client!r})"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_text_delta(event: Any) -> str | None:
    """Extract text delta from an Anthropic MessageStreamEvent, or None."""
    try:
        if event.type == "content_block_delta":
            delta = event.delta
            if getattr(delta, "type", None) == "text_delta":
                return delta.text
    except AttributeError:
        pass
    return None


def _set_text_delta(event: Any, value: str | None) -> None:
    """Set text delta on an Anthropic MessageStreamEvent."""
    try:
        if event.type == "content_block_delta":
            delta = event.delta
            if getattr(delta, "type", None) == "text_delta":
                delta.text = value
    except AttributeError:
        pass
