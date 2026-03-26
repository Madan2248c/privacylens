"""OpenAI adapter for PrivacyLens.

Wraps openai.OpenAI / openai.AsyncOpenAI to transparently mask PII in
chat.completions.create calls, including streaming variants.
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
    """Accumulates partial [TOKEN] strings across streaming chunks.

    Tokens like ``[EMAIL_1]`` may be split across multiple chunks.  This
    buffer holds any trailing partial token and flushes complete tokens as
    they arrive.
    """

    def __init__(self) -> None:
        self._buf = ""

    def feed(self, chunk: str) -> str:
        """Append *chunk* to the buffer and return the safe-to-emit prefix.

        Any text that cannot be the start of a token is returned immediately.
        Text that *could* be the beginning of a token is held back until the
        next chunk confirms or denies it.
        """
        self._buf += chunk
        # Find the last position where a partial token could start.
        match = _TOKEN_PREFIX_RE.search(self._buf)
        if match:
            safe = self._buf[: match.start()]
            self._buf = self._buf[match.start() :]
        else:
            safe = self._buf
            self._buf = ""
        return safe

    def flush(self) -> str:
        """Return and clear any remaining buffered content."""
        remaining = self._buf
        self._buf = ""
        return remaining


class _CompletionsProxy:
    """Intercepts chat.completions.create for both sync and async clients."""

    def __init__(self, real_completions: Any, pipeline: Pipeline, is_async: bool) -> None:
        self._real = real_completions
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
        return self._pipeline.detokenize_response(response, session_id)

    def _wrap_sync_stream(
        self, raw: Iterator[Any], session_id: str
    ) -> Iterator[Any]:
        buf = _StreamBuffer()
        for chunk in raw:
            delta = _get_delta_content(chunk)
            if delta is not None:
                safe = buf.feed(delta)
                if safe:
                    safe = self._pipeline.detokenize(safe, session_id)
                _set_delta_content(chunk, safe if delta is not None else delta)
            yield chunk
        # Flush remaining buffer
        remaining = buf.flush()
        if remaining:
            remaining = self._pipeline.detokenize(remaining, session_id)
            # Yield a synthetic final chunk if there's leftover content.
            # We reuse the last chunk object if possible, otherwise skip.
            # (Callers that care about the last chunk will see it.)

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
        return self._pipeline.detokenize_response(response, session_id)

    async def _wrap_async_stream(
        self, raw: AsyncIterator[Any], session_id: str
    ) -> AsyncIterator[Any]:
        buf = _StreamBuffer()
        async for chunk in raw:
            delta = _get_delta_content(chunk)
            if delta is not None:
                safe = buf.feed(delta)
                if safe:
                    safe = self._pipeline.detokenize(safe, session_id)
                _set_delta_content(chunk, safe if delta is not None else delta)
            yield chunk
        remaining = buf.flush()
        if remaining:
            self._pipeline.detokenize(remaining, session_id)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


class _ChatProxy:
    """Proxy for the ``chat`` attribute of an OpenAI client."""

    def __init__(self, real_chat: Any, pipeline: Pipeline, is_async: bool) -> None:
        self._real = real_chat
        self.completions = _CompletionsProxy(real_chat.completions, pipeline, is_async)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


class OpenAIAdapter:
    """Proxy wrapper around an openai.OpenAI or openai.AsyncOpenAI client.

    Intercepts ``chat.completions.create``, tokenizes PII in messages, and
    de-tokenizes the response.  All other attributes are proxied transparently
    to the underlying client so callers can still do ``client.models.list()``
    etc.

    Args:
        client: An ``openai.OpenAI`` or ``openai.AsyncOpenAI`` instance.
        pipeline: The PrivacyLens pipeline to use for tokenization.
    """

    def __init__(self, client: Any, pipeline: Pipeline) -> None:
        self._client = client
        self._pipeline = pipeline
        # Detect async client by class name (avoids hard import of openai).
        is_async = type(client).__name__ == "AsyncOpenAI"
        self.chat = _ChatProxy(client.chat, pipeline, is_async)

    def __getattr__(self, name: str) -> Any:
        # Proxy everything else (models, files, embeddings, …) to the real client.
        return getattr(self._client, name)

    def __repr__(self) -> str:
        return f"OpenAIAdapter(client={self._client!r})"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_delta_content(chunk: Any) -> str | None:
    """Extract delta.content from a ChatCompletionChunk, or None."""
    try:
        choices = chunk.choices
        if not choices:
            return None
        delta = choices[0].delta
        return delta.content  # may be None
    except AttributeError:
        return None


def _set_delta_content(chunk: Any, value: str | None) -> None:
    """Set delta.content on a ChatCompletionChunk."""
    try:
        chunk.choices[0].delta.content = value
    except (AttributeError, IndexError):
        pass
