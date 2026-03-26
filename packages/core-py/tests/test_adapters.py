"""Tests for PrivacyLens adapters — OpenAI (sync, async, streaming).

Uses respx to mock the OpenAI HTTP layer so no real API calls are made.
"""

from __future__ import annotations

import json
import time
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
import respx
from openai import AsyncOpenAI, OpenAI

from privacylens.adapters.openai import OpenAIAdapter, _StreamBuffer
from privacylens.core.config import load_config
from privacylens.core.pipeline import Pipeline

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CHAT_URL = "https://api.openai.com/v1/chat/completions"


def _make_pipeline() -> Pipeline:
    """Return a Pipeline with default config (RegexDetector, MemoryVault)."""
    return Pipeline(load_config())


def _chat_response_body(content: str) -> dict[str, Any]:
    """Build a minimal OpenAI chat completion JSON body."""
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "gpt-4o",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def _sse_chunk(content: str | None, finish: bool = False) -> bytes:
    """Build a single SSE data line for a streaming chunk."""
    delta: dict[str, Any] = {"role": "assistant"} if content is None else {"content": content}
    chunk = {
        "id": "chatcmpl-stream",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": "gpt-4o",
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": "stop" if finish else None,
            }
        ],
    }
    return f"data: {json.dumps(chunk)}\n\n".encode()


def _sse_done() -> bytes:
    return b"data: [DONE]\n\n"


# ---------------------------------------------------------------------------
# _StreamBuffer unit tests
# ---------------------------------------------------------------------------


class TestStreamBuffer:
    def test_passthrough_plain_text(self) -> None:
        buf = _StreamBuffer()
        assert buf.feed("Hello world") == "Hello world"

    def test_holds_partial_token_start(self) -> None:
        buf = _StreamBuffer()
        # "[EMAIL" looks like the start of a token — should be held back
        safe = buf.feed("Hello [EMAIL")
        assert "[EMAIL" not in safe
        assert "Hello " in safe

    def test_flushes_complete_token(self) -> None:
        buf = _StreamBuffer()
        buf.feed("Hello [EMAIL")
        # Complete the token in the next chunk
        safe = buf.feed("_1] world")
        assert "[EMAIL_1]" in safe or "world" in safe

    def test_flush_returns_remaining(self) -> None:
        buf = _StreamBuffer()
        # feed() returns the safe prefix "partial " immediately; "[" is held back
        safe = buf.feed("partial [")
        assert safe == "partial "
        remaining = buf.flush()
        assert remaining == "["
        assert buf.flush() == ""

    def test_no_token_no_buffering(self) -> None:
        buf = _StreamBuffer()
        assert buf.feed("no pii here") == "no pii here"
        assert buf.flush() == ""

    def test_split_token_across_three_chunks(self) -> None:
        buf = _StreamBuffer()
        buf.feed("[")
        buf.feed("EMAIL")
        result = buf.feed("_1] done")
        # After completing the token, it should be present in output
        combined = result + buf.flush()
        assert "[EMAIL_1]" in combined or "done" in combined


# ---------------------------------------------------------------------------
# OpenAIAdapter — sync non-streaming
# ---------------------------------------------------------------------------


class TestOpenAIAdapterSync:
    @respx.mock
    def test_pii_masked_in_request(self) -> None:
        """PII in messages must be replaced with a token before hitting the API."""
        captured: list[Any] = []

        def capture_and_respond(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            captured.append(body)
            # Echo back whatever content was sent (tokenized)
            sent_content = body["messages"][0]["content"]
            return httpx.Response(200, json=_chat_response_body(sent_content))

        respx.post(CHAT_URL).mock(side_effect=capture_and_respond)

        client = OpenAI(api_key="test-key")
        adapter = OpenAIAdapter(client, _make_pipeline())

        adapter.chat.completions.create(
            messages=[{"role": "user", "content": "My email is user@example.com"}],
            model="gpt-4o",
        )

        assert len(captured) == 1
        sent_content = captured[0]["messages"][0]["content"]
        # Original email must NOT appear in the request
        assert "user@example.com" not in sent_content
        # A token placeholder must be present
        assert "[EMAIL_" in sent_content

    @respx.mock
    def test_pii_restored_in_response(self) -> None:
        """The original PII value must be restored in the response content."""
        respx.post(CHAT_URL).mock(
            return_value=httpx.Response(
                200,
                json=_chat_response_body(
                    "I received your message about [EMAIL_1], thanks!"
                ),
            )
        )

        client = OpenAI(api_key="test-key")
        adapter = OpenAIAdapter(client, _make_pipeline())

        response = adapter.chat.completions.create(
            messages=[{"role": "user", "content": "My email is user@example.com"}],
            model="gpt-4o",
        )

        content = response.choices[0].message.content
        assert "user@example.com" in content
        assert "[EMAIL_1]" not in content

    @respx.mock
    def test_non_messages_kwargs_preserved(self) -> None:
        """Extra kwargs (model, temperature, max_tokens) must reach the API unchanged."""
        captured: list[Any] = []

        def capture(request: httpx.Request) -> httpx.Response:
            captured.append(json.loads(request.content))
            return httpx.Response(200, json=_chat_response_body("ok"))

        respx.post(CHAT_URL).mock(side_effect=capture)

        client = OpenAI(api_key="test-key")
        adapter = OpenAIAdapter(client, _make_pipeline())

        adapter.chat.completions.create(
            messages=[{"role": "user", "content": "hello"}],
            model="gpt-4o",
            temperature=0.7,
            max_tokens=100,
        )

        body = captured[0]
        assert body["model"] == "gpt-4o"
        assert body["temperature"] == 0.7
        assert body["max_tokens"] == 100

    @respx.mock
    def test_no_pii_passthrough(self) -> None:
        """Messages without PII should pass through unchanged."""
        captured: list[Any] = []

        def capture(request: httpx.Request) -> httpx.Response:
            captured.append(json.loads(request.content))
            return httpx.Response(200, json=_chat_response_body("Sure!"))

        respx.post(CHAT_URL).mock(side_effect=capture)

        client = OpenAI(api_key="test-key")
        adapter = OpenAIAdapter(client, _make_pipeline())

        adapter.chat.completions.create(
            messages=[{"role": "user", "content": "What is the weather today?"}],
            model="gpt-4o",
        )

        assert captured[0]["messages"][0]["content"] == "What is the weather today?"

    @respx.mock
    def test_proxy_passes_through_other_attributes(self) -> None:
        """Non-chat attributes should be proxied to the underlying client."""
        respx.post(CHAT_URL).mock(return_value=httpx.Response(200, json=_chat_response_body("ok")))

        client = OpenAI(api_key="test-key")
        adapter = OpenAIAdapter(client, _make_pipeline())

        # api_key is an attribute on the real client — should be accessible
        assert adapter.api_key == "test-key"

    @respx.mock
    def test_multiple_messages_all_tokenized(self) -> None:
        """PII in multiple messages must all be tokenized."""
        captured: list[Any] = []

        def capture(request: httpx.Request) -> httpx.Response:
            captured.append(json.loads(request.content))
            return httpx.Response(200, json=_chat_response_body("ok"))

        respx.post(CHAT_URL).mock(side_effect=capture)

        client = OpenAI(api_key="test-key")
        adapter = OpenAIAdapter(client, _make_pipeline())

        adapter.chat.completions.create(
            messages=[
                {"role": "user", "content": "Email me at a@example.com"},
                {"role": "assistant", "content": "Sure"},
                {"role": "user", "content": "Also try b@example.com"},
            ],
            model="gpt-4o",
        )

        msgs = captured[0]["messages"]
        assert "a@example.com" not in msgs[0]["content"]
        assert "b@example.com" not in msgs[2]["content"]
        assert "[EMAIL_" in msgs[0]["content"]
        assert "[EMAIL_" in msgs[2]["content"]


# ---------------------------------------------------------------------------
# OpenAIAdapter — async non-streaming
# ---------------------------------------------------------------------------


class TestOpenAIAdapterAsync:
    @pytest.mark.asyncio
    @respx.mock
    async def test_async_pii_masked_in_request(self) -> None:
        captured: list[Any] = []

        def capture(request: httpx.Request) -> httpx.Response:
            captured.append(json.loads(request.content))
            sent = captured[-1]["messages"][0]["content"]
            return httpx.Response(200, json=_chat_response_body(sent))

        respx.post(CHAT_URL).mock(side_effect=capture)

        client = AsyncOpenAI(api_key="test-key")
        adapter = OpenAIAdapter(client, _make_pipeline())

        await adapter.chat.completions.acreate(
            messages=[{"role": "user", "content": "Call me at 555-867-5309"}],
            model="gpt-4o",
        )

        sent = captured[0]["messages"][0]["content"]
        assert "555-867-5309" not in sent
        assert "[PHONE_" in sent

    @pytest.mark.asyncio
    @respx.mock
    async def test_async_pii_restored_in_response(self) -> None:
        respx.post(CHAT_URL).mock(
            return_value=httpx.Response(
                200,
                json=_chat_response_body("Your number [PHONE_1] has been noted."),
            )
        )

        client = AsyncOpenAI(api_key="test-key")
        adapter = OpenAIAdapter(client, _make_pipeline())

        response = await adapter.chat.completions.acreate(
            messages=[{"role": "user", "content": "Call me at 555-867-5309"}],
            model="gpt-4o",
        )

        content = response.choices[0].message.content
        assert "555-867-5309" in content
        assert "[PHONE_1]" not in content

    @pytest.mark.asyncio
    @respx.mock
    async def test_async_kwargs_preserved(self) -> None:
        captured: list[Any] = []

        def capture(request: httpx.Request) -> httpx.Response:
            captured.append(json.loads(request.content))
            return httpx.Response(200, json=_chat_response_body("ok"))

        respx.post(CHAT_URL).mock(side_effect=capture)

        client = AsyncOpenAI(api_key="test-key")
        adapter = OpenAIAdapter(client, _make_pipeline())

        await adapter.chat.completions.acreate(
            messages=[{"role": "user", "content": "hi"}],
            model="gpt-4o-mini",
            temperature=0.2,
        )

        assert captured[0]["model"] == "gpt-4o-mini"
        assert captured[0]["temperature"] == 0.2


# ---------------------------------------------------------------------------
# OpenAIAdapter — sync streaming
# ---------------------------------------------------------------------------


class TestOpenAIAdapterStreaming:
    @respx.mock
    def test_streaming_pii_restored_across_chunks(self) -> None:
        """Tokens split across chunks must be fully restored."""
        # Simulate [EMAIL_1] split as "[EMAIL" + "_1]"
        chunks = (
            _sse_chunk("Your email ")
            + _sse_chunk("[EMAIL")
            + _sse_chunk("_1]")
            + _sse_chunk(" is confirmed.")
            + _sse_chunk(None, finish=True)
            + _sse_done()
        )

        respx.post(CHAT_URL).mock(
            return_value=httpx.Response(
                200,
                content=chunks,
                headers={"content-type": "text/event-stream"},
            )
        )

        client = OpenAI(api_key="test-key")
        pipeline = _make_pipeline()
        # Pre-store the token so detokenize can resolve it
        pipeline._vault.store("__stream_test__", "[EMAIL_1]", "user@example.com")
        adapter = OpenAIAdapter(client, pipeline)

        # Collect all delta content from the stream
        collected = []
        stream = adapter.chat.completions.create(
            messages=[{"role": "user", "content": "My email is user@example.com"}],
            model="gpt-4o",
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                collected.append(delta)

        full_response = "".join(collected)
        # The token should not appear raw in the output
        assert "[EMAIL_1]" not in full_response

    @respx.mock
    def test_streaming_plain_text_passthrough(self) -> None:
        """Streaming responses without tokens pass through unchanged."""
        chunks = (
            _sse_chunk("Hello ")
            + _sse_chunk("world!")
            + _sse_chunk(None, finish=True)
            + _sse_done()
        )

        respx.post(CHAT_URL).mock(
            return_value=httpx.Response(
                200,
                content=chunks,
                headers={"content-type": "text/event-stream"},
            )
        )

        client = OpenAI(api_key="test-key")
        adapter = OpenAIAdapter(client, _make_pipeline())

        collected = []
        for chunk in adapter.chat.completions.create(
            messages=[{"role": "user", "content": "Say hello"}],
            model="gpt-4o",
            stream=True,
        ):
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                collected.append(delta)

        assert "".join(collected) == "Hello world!"

    @pytest.mark.asyncio
    @respx.mock
    async def test_async_streaming_pii_restored(self) -> None:
        """Async streaming must also de-tokenize chunks."""
        chunks = (
            _sse_chunk("SSN: ")
            + _sse_chunk("[SSN_1]")
            + _sse_chunk(" confirmed.")
            + _sse_chunk(None, finish=True)
            + _sse_done()
        )

        respx.post(CHAT_URL).mock(
            return_value=httpx.Response(
                200,
                content=chunks,
                headers={"content-type": "text/event-stream"},
            )
        )

        client = AsyncOpenAI(api_key="test-key")
        pipeline = _make_pipeline()
        pipeline._vault.store("__async_stream__", "[SSN_1]", "123-45-6789")
        adapter = OpenAIAdapter(client, pipeline)

        collected = []
        stream = await adapter.chat.completions.acreate(
            messages=[{"role": "user", "content": "My SSN is 123-45-6789"}],
            model="gpt-4o",
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                collected.append(delta)

        full = "".join(collected)
        assert "[SSN_1]" not in full


# ---------------------------------------------------------------------------
# OpenAIAdapter — repr
# ---------------------------------------------------------------------------


class TestOpenAIAdapterRepr:
    def test_repr_contains_adapter_name(self) -> None:
        client = OpenAI(api_key="test-key")
        adapter = OpenAIAdapter(client, _make_pipeline())
        assert "OpenAIAdapter" in repr(adapter)


# ---------------------------------------------------------------------------
# Anthropic adapter helpers
# ---------------------------------------------------------------------------

from anthropic import Anthropic, AsyncAnthropic

from privacylens.adapters.anthropic import AnthropicAdapter

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"


def _anthropic_response_body(content: str) -> dict[str, Any]:
    """Build a minimal Anthropic messages response JSON body."""
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": content}],
        "model": "claude-3-opus-20240229",
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


# ---------------------------------------------------------------------------
# AnthropicAdapter — sync non-streaming
# ---------------------------------------------------------------------------


class TestAnthropicAdapterSync:
    @respx.mock
    def test_pii_masked_in_request(self) -> None:
        """PII in messages must be replaced with a token before hitting Anthropic."""
        captured: list[Any] = []

        def capture_and_respond(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            captured.append(body)
            sent_content = body["messages"][0]["content"]
            return httpx.Response(200, json=_anthropic_response_body(sent_content))

        respx.post(ANTHROPIC_MESSAGES_URL).mock(side_effect=capture_and_respond)

        client = Anthropic(api_key="test-key")
        adapter = AnthropicAdapter(client, _make_pipeline())

        adapter.messages.create(
            messages=[{"role": "user", "content": "Contact alice@example.com for details"}],
            model="claude-3-opus-20240229",
            max_tokens=100,
        )

        assert len(captured) == 1
        sent_content = captured[0]["messages"][0]["content"]
        assert "alice@example.com" not in sent_content
        assert "[EMAIL_" in sent_content

    @respx.mock
    def test_pii_restored_in_response(self) -> None:
        """The original PII value must be restored in the response TextBlock."""
        respx.post(ANTHROPIC_MESSAGES_URL).mock(
            return_value=httpx.Response(
                200,
                json=_anthropic_response_body(
                    "I'll reach out to [EMAIL_1] on your behalf."
                ),
            )
        )

        client = Anthropic(api_key="test-key")
        adapter = AnthropicAdapter(client, _make_pipeline())

        response = adapter.messages.create(
            messages=[{"role": "user", "content": "Contact alice@example.com for details"}],
            model="claude-3-opus-20240229",
            max_tokens=100,
        )

        text = response.content[0].text
        assert "alice@example.com" in text
        assert "[EMAIL_1]" not in text

    @respx.mock
    def test_non_messages_kwargs_preserved(self) -> None:
        """Extra kwargs (model, max_tokens, system) must reach the API unchanged."""
        captured: list[Any] = []

        def capture(request: httpx.Request) -> httpx.Response:
            captured.append(json.loads(request.content))
            return httpx.Response(200, json=_anthropic_response_body("ok"))

        respx.post(ANTHROPIC_MESSAGES_URL).mock(side_effect=capture)

        client = Anthropic(api_key="test-key")
        adapter = AnthropicAdapter(client, _make_pipeline())

        adapter.messages.create(
            messages=[{"role": "user", "content": "hello"}],
            model="claude-3-opus-20240229",
            max_tokens=100,
            system="You are a helpful assistant.",
        )

        body = captured[0]
        assert body["model"] == "claude-3-opus-20240229"
        assert body["max_tokens"] == 100
        assert body["system"] == "You are a helpful assistant."

    @respx.mock
    def test_no_pii_passthrough(self) -> None:
        """Messages without PII should pass through unchanged."""
        captured: list[Any] = []

        def capture(request: httpx.Request) -> httpx.Response:
            captured.append(json.loads(request.content))
            return httpx.Response(200, json=_anthropic_response_body("Sure!"))

        respx.post(ANTHROPIC_MESSAGES_URL).mock(side_effect=capture)

        client = Anthropic(api_key="test-key")
        adapter = AnthropicAdapter(client, _make_pipeline())

        adapter.messages.create(
            messages=[{"role": "user", "content": "What is the weather today?"}],
            model="claude-3-opus-20240229",
            max_tokens=50,
        )

        assert captured[0]["messages"][0]["content"] == "What is the weather today?"

    @respx.mock
    def test_proxy_passes_through_other_attributes(self) -> None:
        """Non-messages attributes should be proxied to the underlying client."""
        client = Anthropic(api_key="test-key")
        adapter = AnthropicAdapter(client, _make_pipeline())

        assert adapter.api_key == "test-key"

    def test_repr_contains_adapter_name(self) -> None:
        client = Anthropic(api_key="test-key")
        adapter = AnthropicAdapter(client, _make_pipeline())
        assert "AnthropicAdapter" in repr(adapter)


# ---------------------------------------------------------------------------
# AnthropicAdapter — async non-streaming
# ---------------------------------------------------------------------------


class TestAnthropicAdapterAsync:
    @pytest.mark.asyncio
    @respx.mock
    async def test_async_pii_masked_in_request(self) -> None:
        captured: list[Any] = []

        def capture(request: httpx.Request) -> httpx.Response:
            captured.append(json.loads(request.content))
            sent = captured[-1]["messages"][0]["content"]
            return httpx.Response(200, json=_anthropic_response_body(sent))

        respx.post(ANTHROPIC_MESSAGES_URL).mock(side_effect=capture)

        client = AsyncAnthropic(api_key="test-key")
        adapter = AnthropicAdapter(client, _make_pipeline())

        await adapter.messages.acreate(
            messages=[{"role": "user", "content": "Call me at 555-867-5309"}],
            model="claude-3-opus-20240229",
            max_tokens=100,
        )

        sent = captured[0]["messages"][0]["content"]
        assert "555-867-5309" not in sent
        assert "[PHONE_" in sent

    @pytest.mark.asyncio
    @respx.mock
    async def test_async_pii_restored_in_response(self) -> None:
        respx.post(ANTHROPIC_MESSAGES_URL).mock(
            return_value=httpx.Response(
                200,
                json=_anthropic_response_body(
                    "Your number [PHONE_1] has been noted."
                ),
            )
        )

        client = AsyncAnthropic(api_key="test-key")
        adapter = AnthropicAdapter(client, _make_pipeline())

        response = await adapter.messages.acreate(
            messages=[{"role": "user", "content": "Call me at 555-867-5309"}],
            model="claude-3-opus-20240229",
            max_tokens=100,
        )

        text = response.content[0].text
        assert "555-867-5309" in text
        assert "[PHONE_1]" not in text

    @pytest.mark.asyncio
    @respx.mock
    async def test_async_kwargs_preserved(self) -> None:
        captured: list[Any] = []

        def capture(request: httpx.Request) -> httpx.Response:
            captured.append(json.loads(request.content))
            return httpx.Response(200, json=_anthropic_response_body("ok"))

        respx.post(ANTHROPIC_MESSAGES_URL).mock(side_effect=capture)

        client = AsyncAnthropic(api_key="test-key")
        adapter = AnthropicAdapter(client, _make_pipeline())

        await adapter.messages.acreate(
            messages=[{"role": "user", "content": "hi"}],
            model="claude-3-haiku-20240307",
            max_tokens=50,
        )

        assert captured[0]["model"] == "claude-3-haiku-20240307"
        assert captured[0]["max_tokens"] == 50


# ---------------------------------------------------------------------------
# LangChain callback handler tests
# ---------------------------------------------------------------------------


def _make_generation(text: str) -> MagicMock:
    """Build a mock LangChain Generation object with a .text attribute."""
    gen = MagicMock()
    gen.text = text
    return gen


def _make_llm_result(*generation_texts: str) -> MagicMock:
    """Build a mock LLMResult with one generation list per positional arg."""
    result = MagicMock()
    result.generations = [[_make_generation(t)] for t in generation_texts]
    return result


class TestLangChainCallbackHandler:
    """Unit tests for LangChainCallbackHandler."""

    def _make_handler(self) -> Any:
        from privacylens.adapters.langchain import LangChainCallbackHandler

        return LangChainCallbackHandler(_make_pipeline())

    # ------------------------------------------------------------------
    # on_llm_start — tokenization
    # ------------------------------------------------------------------

    def test_on_llm_start_tokenizes_pii_in_place(self) -> None:
        """Prompts containing PII are tokenized in-place."""
        handler = self._make_handler()
        prompts = ["Contact me at user@example.com"]
        handler.on_llm_start({}, prompts, run_id="run-1")
        assert "user@example.com" not in prompts[0]
        assert "[EMAIL_1]" in prompts[0]

    def test_on_llm_start_multiple_prompts(self) -> None:
        """All prompts in the list are tokenized."""
        handler = self._make_handler()
        prompts = ["Email: a@b.com", "SSN: 123-45-6789"]
        handler.on_llm_start({}, prompts, run_id="run-2")
        assert "a@b.com" not in prompts[0]
        assert "123-45-6789" not in prompts[1]

    def test_on_llm_start_no_pii_unchanged(self) -> None:
        """Prompts without PII pass through unchanged."""
        handler = self._make_handler()
        prompts = ["Hello, world!"]
        handler.on_llm_start({}, prompts, run_id="run-3")
        assert prompts[0] == "Hello, world!"

    # ------------------------------------------------------------------
    # on_llm_end — de-tokenization
    # ------------------------------------------------------------------

    def test_on_llm_end_restores_pii_in_response(self) -> None:
        """Tokens in generation text are replaced with original values."""
        handler = self._make_handler()
        prompts = ["Contact me at user@example.com"]
        handler.on_llm_start({}, prompts, run_id="run-4")

        # Simulate LLM echoing the token back
        token = prompts[0].split("Contact me at ")[1]
        result = _make_llm_result(f"Sure, I'll email {token}")
        handler.on_llm_end(result, run_id="run-4")

        assert result.generations[0][0].text == "Sure, I'll email user@example.com"

    def test_on_llm_end_unknown_token_left_unchanged(self) -> None:
        """Tokens not in the vault are left as-is in the output."""
        handler = self._make_handler()
        prompts = ["Hello"]
        handler.on_llm_start({}, prompts, run_id="run-5")

        result = _make_llm_result("Here is [EMAIL_99] for you")
        handler.on_llm_end(result, run_id="run-5")

        assert "[EMAIL_99]" in result.generations[0][0].text

    def test_on_llm_end_no_tokens_passthrough(self) -> None:
        """Responses without tokens are returned unchanged."""
        handler = self._make_handler()
        prompts = ["Hello"]
        handler.on_llm_start({}, prompts, run_id="run-6")

        result = _make_llm_result("Just a plain response.")
        handler.on_llm_end(result, run_id="run-6")

        assert result.generations[0][0].text == "Just a plain response."

    def test_on_llm_end_multiple_generations(self) -> None:
        """All generation lists and their items are de-tokenized."""
        handler = self._make_handler()
        prompts = ["Email: a@b.com"]
        handler.on_llm_start({}, prompts, run_id="run-7")

        token = prompts[0].split("Email: ")[1]
        result = MagicMock()
        gen1 = _make_generation(f"First: {token}")
        gen2 = _make_generation(f"Second: {token}")
        result.generations = [[gen1], [gen2]]
        handler.on_llm_end(result, run_id="run-7")

        assert gen1.text == "First: a@b.com"
        assert gen2.text == "Second: a@b.com"

    # ------------------------------------------------------------------
    # Session isolation
    # ------------------------------------------------------------------

    def test_sessions_are_isolated_by_run_id(self) -> None:
        """Tokens from run A cannot bleed into run B's de-tokenization."""
        handler = self._make_handler()

        prompts_a = ["Email: a@example.com"]
        prompts_b = ["Email: b@example.com"]
        handler.on_llm_start({}, prompts_a, run_id="run-a")
        handler.on_llm_start({}, prompts_b, run_id="run-b")

        token_a = prompts_a[0].split("Email: ")[1]
        token_b = prompts_b[0].split("Email: ")[1]

        # End run-b first — should only restore b's token
        result_b = _make_llm_result(f"Got {token_b}")
        handler.on_llm_end(result_b, run_id="run-b")
        assert result_b.generations[0][0].text == "Got b@example.com"

        # End run-a — should only restore a's token
        result_a = _make_llm_result(f"Got {token_a}")
        handler.on_llm_end(result_a, run_id="run-a")
        assert result_a.generations[0][0].text == "Got a@example.com"

    def test_session_cleaned_up_after_on_llm_end(self) -> None:
        """The session mapping is removed after on_llm_end completes."""
        handler = self._make_handler()
        prompts = ["user@example.com"]
        handler.on_llm_start({}, prompts, run_id="run-cleanup")
        assert "run-cleanup" in handler._sessions

        handler.on_llm_end(_make_llm_result("ok"), run_id="run-cleanup")
        assert "run-cleanup" not in handler._sessions

    def test_session_cleaned_up_after_on_llm_error(self) -> None:
        """The session mapping is removed when the LLM run fails."""
        handler = self._make_handler()
        prompts = ["user@example.com"]
        handler.on_llm_start({}, prompts, run_id="run-err")
        assert "run-err" in handler._sessions

        handler.on_llm_error(RuntimeError("boom"), run_id="run-err")
        assert "run-err" not in handler._sessions

    def test_on_llm_end_without_matching_start_is_noop(self) -> None:
        """on_llm_end with an unknown run_id does not raise."""
        handler = self._make_handler()
        result = _make_llm_result("some text")
        handler.on_llm_end(result, run_id="nonexistent-run")
        # text should be unchanged since there's no session to de-tokenize with
        assert result.generations[0][0].text == "some text"

    # ------------------------------------------------------------------
    # Passable as callbacks list element
    # ------------------------------------------------------------------

    def test_handler_is_passable_as_callbacks_list_element(self) -> None:
        """Handler can be placed in a list (the LangChain callbacks= pattern)."""
        handler = self._make_handler()
        callbacks = [handler]
        assert callbacks[0] is handler

    def test_repr(self) -> None:
        handler = self._make_handler()
        assert "LangChainCallbackHandler" in repr(handler)


# ---------------------------------------------------------------------------
# CrewAI adapter tests
# ---------------------------------------------------------------------------

from privacylens.adapters.crewai import CrewAIAdapter


class TestCrewAIAdapter:
    """Unit tests for CrewAIAdapter."""

    def _make_adapter(self, llm: Any) -> CrewAIAdapter:
        return CrewAIAdapter(llm, _make_pipeline())

    # ------------------------------------------------------------------
    # PII masking
    # ------------------------------------------------------------------

    def test_pii_masked_before_llm_call(self) -> None:
        """PII in messages must be tokenized before reaching the LLM callable."""
        captured: list[Any] = []

        def mock_llm(messages: list[dict], **kwargs: Any) -> str:
            captured.append(messages)
            return "ok"

        adapter = self._make_adapter(mock_llm)
        adapter([{"role": "user", "content": "My email is user@example.com"}])

        assert len(captured) == 1
        sent_content = captured[0][0]["content"]
        assert "user@example.com" not in sent_content
        assert "[EMAIL_" in sent_content

    def test_pii_restored_in_response(self) -> None:
        """Tokens in the LLM response must be replaced with original values."""
        def mock_llm(messages: list[dict], **kwargs: Any) -> str:
            # Echo back the token that was sent
            return "I'll contact [EMAIL_1] shortly."

        pipeline = _make_pipeline()
        adapter = CrewAIAdapter(mock_llm, pipeline)

        result = adapter([{"role": "user", "content": "My email is user@example.com"}])

        assert "user@example.com" in result
        assert "[EMAIL_1]" not in result

    # ------------------------------------------------------------------
    # kwargs passthrough
    # ------------------------------------------------------------------

    def test_extra_kwargs_passed_to_llm(self) -> None:
        """Extra kwargs must be forwarded to the underlying LLM callable."""
        captured_kwargs: list[dict] = []

        def mock_llm(messages: list[dict], **kwargs: Any) -> str:
            captured_kwargs.append(kwargs)
            return "response"

        adapter = self._make_adapter(mock_llm)
        adapter(
            [{"role": "user", "content": "hello"}],
            temperature=0.5,
            max_tokens=200,
        )

        assert captured_kwargs[0]["temperature"] == 0.5
        assert captured_kwargs[0]["max_tokens"] == 200

    # ------------------------------------------------------------------
    # No PII passthrough
    # ------------------------------------------------------------------

    def test_no_pii_messages_pass_through_unchanged(self) -> None:
        """Messages without PII should reach the LLM unchanged."""
        captured: list[Any] = []

        def mock_llm(messages: list[dict], **kwargs: Any) -> str:
            captured.append(messages)
            return "Sure!"

        adapter = self._make_adapter(mock_llm)
        adapter([{"role": "user", "content": "What is the weather today?"}])

        assert captured[0][0]["content"] == "What is the weather today?"

    # ------------------------------------------------------------------
    # repr
    # ------------------------------------------------------------------

    def test_repr_contains_adapter_name(self) -> None:
        adapter = self._make_adapter(lambda m, **kw: "ok")
        assert "CrewAIAdapter" in repr(adapter)


# ---------------------------------------------------------------------------
# StrandsModelWrapper tests
# ---------------------------------------------------------------------------

from privacylens.adapters.strands import StrandsModelWrapper


class TestStrandsModelWrapper:
    """Unit tests for StrandsModelWrapper.

    strands-agents is not required in the test environment.  We mock the
    Strands Model interface with a plain callable class.
    """

    def _make_mock_model(self, response: dict) -> Any:
        """Return a minimal mock that mimics the Strands Model.invoke interface."""

        class _MockModel:
            def __init__(self, resp: dict) -> None:
                self._resp = resp
                self.received: list[Any] = []

            def invoke(self, messages: list[dict], **kwargs: Any) -> dict:
                self.received.append(messages)
                return self._resp

        return _MockModel(response)

    def _make_wrapper(self, mock_model: Any) -> StrandsModelWrapper:
        return StrandsModelWrapper(mock_model, _make_pipeline())

    # ------------------------------------------------------------------
    # Interface
    # ------------------------------------------------------------------

    def test_has_invoke_method(self) -> None:
        """StrandsModelWrapper must expose an invoke() method."""
        mock = self._make_mock_model({"output": {"message": {"content": []}}})
        wrapper = self._make_wrapper(mock)
        assert callable(wrapper.invoke)

    # ------------------------------------------------------------------
    # PII masking in request
    # ------------------------------------------------------------------

    def test_pii_masked_before_model_call(self) -> None:
        """PII in messages must be tokenized before reaching the underlying model."""
        mock = self._make_mock_model({"output": {"message": {"content": []}}})
        wrapper = self._make_wrapper(mock)

        wrapper.invoke([{"role": "user", "content": "My email is user@example.com"}])

        assert len(mock.received) == 1
        sent_content = mock.received[0][0]["content"]
        assert "user@example.com" not in sent_content
        assert "[EMAIL_" in sent_content

    def test_no_pii_messages_pass_through_unchanged(self) -> None:
        """Messages without PII should reach the model unchanged."""
        mock = self._make_mock_model({"output": {"message": {"content": []}}})
        wrapper = self._make_wrapper(mock)

        wrapper.invoke([{"role": "user", "content": "What is the weather today?"}])

        assert mock.received[0][0]["content"] == "What is the weather today?"

    # ------------------------------------------------------------------
    # PII restoration in response
    # ------------------------------------------------------------------

    def test_pii_restored_in_response_text_block(self) -> None:
        """Tokens in response text blocks must be replaced with original values."""
        response = {
            "output": {
                "message": {
                    "content": [{"text": "I'll contact [EMAIL_1] shortly."}]
                }
            }
        }
        mock = self._make_mock_model(response)
        wrapper = self._make_wrapper(mock)

        result = wrapper.invoke(
            [{"role": "user", "content": "My email is user@example.com"}]
        )

        text = result["output"]["message"]["content"][0]["text"]
        assert "user@example.com" in text
        assert "[EMAIL_1]" not in text

    def test_multiple_text_blocks_all_detokenized(self) -> None:
        """All text blocks in the response content list are de-tokenized."""
        response = {
            "output": {
                "message": {
                    "content": [
                        {"text": "First: [EMAIL_1]"},
                        {"text": "Second: [EMAIL_1] again"},
                    ]
                }
            }
        }
        mock = self._make_mock_model(response)
        wrapper = self._make_wrapper(mock)

        result = wrapper.invoke(
            [{"role": "user", "content": "Email: user@example.com"}]
        )

        blocks = result["output"]["message"]["content"]
        assert "user@example.com" in blocks[0]["text"]
        assert "user@example.com" in blocks[1]["text"]
        assert "[EMAIL_1]" not in blocks[0]["text"]
        assert "[EMAIL_1]" not in blocks[1]["text"]

    # ------------------------------------------------------------------
    # Non-text content blocks pass through unchanged
    # ------------------------------------------------------------------

    def test_non_text_blocks_passed_through_unchanged(self) -> None:
        """Content blocks without a 'text' key must not be modified."""
        image_block = {"image": {"format": "png", "source": {"bytes": b"..."}}}
        response = {
            "output": {
                "message": {
                    "content": [
                        image_block,
                        {"text": "Here is the image."},
                    ]
                }
            }
        }
        mock = self._make_mock_model(response)
        wrapper = self._make_wrapper(mock)

        result = wrapper.invoke([{"role": "user", "content": "Show me a picture"}])

        # Image block must be untouched
        assert result["output"]["message"]["content"][0] is image_block

    # ------------------------------------------------------------------
    # Nested response structure edge cases
    # ------------------------------------------------------------------

    def test_empty_content_list(self) -> None:
        """An empty content list should not raise."""
        mock = self._make_mock_model({"output": {"message": {"content": []}}})
        wrapper = self._make_wrapper(mock)
        result = wrapper.invoke([{"role": "user", "content": "hello"}])
        assert result["output"]["message"]["content"] == []

    def test_missing_output_key_does_not_raise(self) -> None:
        """A response without 'output' key should not raise."""
        mock = self._make_mock_model({})
        wrapper = self._make_wrapper(mock)
        result = wrapper.invoke([{"role": "user", "content": "hello"}])
        assert result == {}

    # ------------------------------------------------------------------
    # kwargs forwarding
    # ------------------------------------------------------------------

    def test_extra_kwargs_forwarded_to_model(self) -> None:
        """Extra kwargs must be forwarded to the underlying model's invoke."""
        captured_kwargs: list[dict] = []

        class _KwargCapture:
            def invoke(self, messages: list[dict], **kwargs: Any) -> dict:
                captured_kwargs.append(kwargs)
                return {"output": {"message": {"content": []}}}

        wrapper = StrandsModelWrapper(_KwargCapture(), _make_pipeline())
        wrapper.invoke(
            [{"role": "user", "content": "hello"}],
            temperature=0.7,
            max_tokens=256,
        )

        assert captured_kwargs[0]["temperature"] == 0.7
        assert captured_kwargs[0]["max_tokens"] == 256

    # ------------------------------------------------------------------
    # repr
    # ------------------------------------------------------------------

    def test_repr_contains_wrapper_name(self) -> None:
        mock = self._make_mock_model({})
        wrapper = self._make_wrapper(mock)
        assert "StrandsModelWrapper" in repr(wrapper)
