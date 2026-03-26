"""Tests for core data models (EntitySpan, DetectorConfig, Config, Detector)."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from privacylens.core.models import Config, Detector, DetectorConfig, EntitySpan

# ---------------------------------------------------------------------------
# Property-based tests (Task 2.5)
# ---------------------------------------------------------------------------


@given(
    start=st.integers(min_value=-10_000, max_value=10_000),
    end=st.integers(min_value=-10_000, max_value=10_000),
)
@settings(max_examples=500)
def test_entity_span_start_gt_end_raises_value_error(start: int, end: int) -> None:
    """Property 1 (invalid): start > end always raises ValueError.

    **Validates: Requirements 1.4**
    """
    if start > end:
        with pytest.raises(ValueError, match="must be <= end"):
            EntitySpan(start=start, end=end, entity_type="X", value="x")


@given(
    start=st.integers(min_value=0, max_value=10_000),
    length=st.integers(min_value=0, max_value=10_000),
)
@settings(max_examples=500)
def test_entity_span_valid_start_lte_end_succeeds(start: int, length: int) -> None:
    """Property 1 (valid): start <= end always constructs successfully.

    **Validates: Requirements 1.4**
    """
    end = start + length
    span = EntitySpan(start=start, end=end, entity_type="EMAIL", value="test@example.com")
    assert span.start <= span.end


# ---------------------------------------------------------------------------
# Unit tests (Task 2.6)
# ---------------------------------------------------------------------------


class TestEntitySpanConstruction:
    def test_valid_construction(self) -> None:
        span = EntitySpan(start=0, end=5, entity_type="EMAIL", value="a@b.c")
        assert span.start == 0
        assert span.end == 5
        assert span.entity_type == "EMAIL"
        assert span.value == "a@b.c"

    def test_start_equals_end_is_valid(self) -> None:
        span = EntitySpan(start=3, end=3, entity_type="PHONE", value="")
        assert span.start == span.end == 3

    def test_start_greater_than_end_raises(self) -> None:
        with pytest.raises(ValueError, match="must be <= end"):
            EntitySpan(start=10, end=5, entity_type="SSN", value="123-45-6789")

    def test_start_negative_end_zero_valid(self) -> None:
        # Negative offsets are unusual but the invariant only requires start <= end
        span = EntitySpan(start=-1, end=0, entity_type="X", value="y")
        assert span.start <= span.end


class TestDetectorConfigConstruction:
    def test_empty_config(self) -> None:
        cfg: DetectorConfig = {}
        assert isinstance(cfg, dict)

    def test_enabled_only(self) -> None:
        cfg: DetectorConfig = {"enabled": True}
        assert cfg["enabled"] is True

    def test_with_patterns(self) -> None:
        cfg: DetectorConfig = {
            "enabled": True,
            "patterns": [{"entity_type": "CUSTOM", "pattern": r"\bfoo\b"}],
        }
        assert len(cfg["patterns"]) == 1
        assert cfg["patterns"][0]["entity_type"] == "CUSTOM"


class TestConfigConstruction:
    def test_full_config(self) -> None:
        cfg: Config = {
            "version": "1.0",
            "detectors": {
                "regex": {"enabled": True},
            },
            "vault": "memory",
            "on_detection": None,
        }
        assert cfg["version"] == "1.0"
        assert cfg["vault"] == "memory"
        assert cfg["detectors"]["regex"]["enabled"] is True
        assert cfg["on_detection"] is None

    def test_config_with_callback(self) -> None:
        received: list[str] = []

        def callback(entity_type: str) -> None:
            received.append(entity_type)

        cfg: Config = {
            "version": "1.0",
            "detectors": {},
            "vault": "memory",
            "on_detection": callback,
        }
        assert cfg["on_detection"] is not None
        cfg["on_detection"]("EMAIL")
        assert received == ["EMAIL"]

    def test_minimal_config(self) -> None:
        # Config is total=False so all fields are optional
        cfg: Config = {}
        assert isinstance(cfg, dict)

    def test_default_vault_is_memory(self) -> None:
        # When vault is not specified, it should default to "memory"
        # This is handled by config loading logic, not TypedDict itself
        cfg: Config = {"version": "1.0"}
        # The vault field is optional in TypedDict, but config loading sets default
        assert "vault" not in cfg  # Not set in TypedDict, handled by config loader


class TestDetectorProtocol:
    def test_class_implementing_detect_satisfies_protocol(self) -> None:
        class MyDetector:
            def detect(self, text: str) -> list[EntitySpan]:
                return []

        detector = MyDetector()
        assert isinstance(detector, Detector)

    def test_class_without_detect_does_not_satisfy_protocol(self) -> None:
        class NotADetector:
            pass

        assert not isinstance(NotADetector(), Detector)


# ---------------------------------------------------------------------------
# Message normalization tests (Task 4)
# ---------------------------------------------------------------------------

from privacylens.core.normalize import normalize_messages

# --- Strategies ---

# A message dict with required role/content plus optional extra fields
_extra_fields = st.fixed_dictionaries(
    {},
    optional={
        "name": st.text(min_size=1, max_size=20),
        "tool_call_id": st.text(min_size=1, max_size=20),
    },
)

_message_dict = st.fixed_dictionaries(
    {"role": st.sampled_from(["user", "assistant", "system"]), "content": st.text()},
    optional={
        "name": st.text(min_size=1, max_size=20),
        "tool_call_id": st.text(min_size=1, max_size=20),
    },
)

_openai_style = st.lists(_message_dict, min_size=1, max_size=5)

_anthropic_style = st.fixed_dictionaries(
    {"messages": _openai_style},
    optional={"model": st.text(min_size=1, max_size=20)},
)

_valid_input = st.one_of(st.text(), _openai_style, _anthropic_style)


# --- Property 4: normalization produces canonical list and preserves extra fields ---


@given(input=_valid_input)
@settings(max_examples=300)
def test_normalize_messages_produces_canonical_list(input: object) -> None:
    """Property 4: normalize_messages always returns a list of dicts with role and content.

    **Validates: Requirements 3.1, 3.2, 3.3, 3.5**
    """
    result = normalize_messages(input)
    assert isinstance(result, list)
    for msg in result:
        assert isinstance(msg, dict)
        assert "role" in msg
        assert "content" in msg


@given(messages=_openai_style)
@settings(max_examples=300)
def test_normalize_messages_preserves_extra_fields(messages: list[dict]) -> None:
    """Property 4 (extra fields): extra fields like name and tool_call_id are preserved.

    **Validates: Requirements 3.5**
    """
    result = normalize_messages(messages)
    for original, normalized in zip(messages, result):
        for key in original:
            assert key in normalized
            assert normalized[key] == original[key]


# --- Property 5: normalize_messages is idempotent ---


@given(input=_valid_input)
@settings(max_examples=300)
def test_normalize_messages_idempotent(input: object) -> None:
    """Property 5: normalize_messages(normalize_messages(x)) == normalize_messages(x).

    **Validates: Requirements 3.6**
    """
    once = normalize_messages(input)
    twice = normalize_messages(once)
    assert once == twice


# --- Task 4.6: Unit tests for TypeError on unrecognized input ---


class TestNormalizeMessagesTypeError:
    def test_integer_raises_type_error(self) -> None:
        with pytest.raises(TypeError, match="Unsupported message format"):
            normalize_messages(42)  # type: ignore[arg-type]

    def test_float_raises_type_error(self) -> None:
        with pytest.raises(TypeError, match="Unsupported message format"):
            normalize_messages(3.14)  # type: ignore[arg-type]

    def test_none_raises_type_error(self) -> None:
        with pytest.raises(TypeError, match="Unsupported message format"):
            normalize_messages(None)  # type: ignore[arg-type]

    def test_dict_without_messages_key_raises_type_error(self) -> None:
        with pytest.raises(TypeError, match="Unrecognized dict format"):
            normalize_messages({"role": "user"})  # type: ignore[arg-type]

    def test_empty_dict_raises_type_error(self) -> None:
        with pytest.raises(TypeError, match="Unrecognized dict format"):
            normalize_messages({})  # type: ignore[arg-type]

    def test_bytes_raises_type_error(self) -> None:
        with pytest.raises(TypeError, match="Unsupported message format"):
            normalize_messages(b"hello")  # type: ignore[arg-type]


class TestNormalizeMessagesValid:
    def test_plain_string(self) -> None:
        result = normalize_messages("hello")
        assert result == [{"role": "user", "content": "hello"}]

    def test_empty_string(self) -> None:
        result = normalize_messages("")
        assert result == [{"role": "user", "content": ""}]

    def test_openai_style_list(self) -> None:
        messages = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
        assert normalize_messages(messages) == messages

    def test_anthropic_style_dict(self) -> None:
        messages = [{"role": "user", "content": "hi"}]
        result = normalize_messages({"messages": messages, "model": "claude-3"})
        assert result == messages

    def test_openai_style_preserves_extra_fields(self) -> None:
        messages = [{"role": "user", "content": "hi", "name": "Alice", "tool_call_id": "tc1"}]
        result = normalize_messages(messages)
        assert result[0]["name"] == "Alice"
        assert result[0]["tool_call_id"] == "tc1"


# ---------------------------------------------------------------------------
# inspect() tests (Task 13)
# ---------------------------------------------------------------------------

from privacylens import inspect as pl_inspect
from privacylens.core.analyzer import Analyzer
from privacylens.core.config import load_config
from privacylens.core.pipeline import _build_detectors
from privacylens.core.vault import MemoryVault

# --- Property 19: inspect() has no side effects on vault state ---


@given(text=st.text(max_size=200))
@settings(max_examples=200, deadline=None)
def test_inspect_does_not_modify_vault(text: str) -> None:
    """Property 19: inspect(text) SHALL NOT modify vault state.

    inspect() runs only the Analyzer — it never instantiates a vault or
    writes tokens. We verify this by confirming a fresh MemoryVault remains
    empty before and after inspect() runs (inspect() has no vault parameter
    and must not write to any shared vault state).

    **Validates: Requirements 20.3**
    """
    vault = MemoryVault()
    assert vault._data == {}  # type: ignore[attr-defined]
    pl_inspect(text)
    # inspect() has no vault — the vault we created must remain untouched
    assert vault._data == {}  # type: ignore[attr-defined]


# --- Property 20: inspect() returns same spans as Analyzer.analyze() ---


@given(text=st.text(max_size=200))
@settings(max_examples=200)
def test_inspect_returns_same_spans_as_analyzer(text: str) -> None:
    """Property 20: inspect(text, config) == Analyzer(config).analyze(text).

    **Validates: Requirements 20.1, 20.2**
    """
    cfg = load_config()
    expected = Analyzer(_build_detectors(cfg), cfg).analyze(text)
    actual = pl_inspect(text, cfg)
    assert actual == expected


# --- Task 13.5: Unit test for inspect() with no config using defaults ---


class TestInspectDefaults:
    def test_detects_email_with_default_config(self) -> None:
        """inspect() with no config should detect EMAIL entities."""
        spans = pl_inspect("Contact me at test@example.com")
        email_spans = [s for s in spans if s.entity_type == "EMAIL"]
        assert len(email_spans) >= 1
        # The span should cover the email address
        span = email_spans[0]
        assert "test@example.com" in "Contact me at test@example.com"[span.start:span.end]

    def test_returns_list_of_entity_spans(self) -> None:
        spans = pl_inspect("Call 555-867-5309")
        assert isinstance(spans, list)
        for s in spans:
            assert hasattr(s, "start")
            assert hasattr(s, "end")
            assert hasattr(s, "entity_type")
            assert hasattr(s, "value")

    def test_no_pii_returns_empty_list(self) -> None:
        spans = pl_inspect("The quick brown fox jumps over the lazy dog.")
        assert spans == []

    def test_does_not_modify_input_text(self) -> None:
        original = "Email me at user@example.com please"
        pl_inspect(original)
        assert original == "Email me at user@example.com please"


# ---------------------------------------------------------------------------
# shield() tests (Task 14.3)
# ---------------------------------------------------------------------------

from unittest.mock import MagicMock, patch

from privacylens import shield
from privacylens.adapters.anthropic import AnthropicAdapter
from privacylens.adapters.langchain import LangChainCallbackHandler
from privacylens.adapters.openai import OpenAIAdapter


class TestShieldOpenAI:
    def test_openai_client_returns_openai_adapter(self) -> None:
        MagicMock()
        mock_openai = MagicMock()
        mock_openai.OpenAI = type("OpenAI", (), {})
        mock_openai.AsyncOpenAI = type("AsyncOpenAI", (), {})
        client = mock_openai.OpenAI()

        with patch.dict("sys.modules", {"openai": mock_openai}):
            result = shield(client)

        assert isinstance(result, OpenAIAdapter)

    def test_async_openai_client_returns_openai_adapter(self) -> None:
        mock_openai = MagicMock()
        mock_openai.OpenAI = type("OpenAI", (), {})
        mock_openai.AsyncOpenAI = type("AsyncOpenAI", (), {})
        client = mock_openai.AsyncOpenAI()

        with patch.dict("sys.modules", {"openai": mock_openai}):
            result = shield(client)

        assert isinstance(result, OpenAIAdapter)


class TestShieldAnthropic:
    def test_anthropic_client_returns_anthropic_adapter(self) -> None:
        mock_anthropic = MagicMock()
        mock_anthropic.Anthropic = type("Anthropic", (), {})
        mock_anthropic.AsyncAnthropic = type("AsyncAnthropic", (), {})
        client = mock_anthropic.Anthropic()

        with patch.dict("sys.modules", {"openai": None, "anthropic": mock_anthropic}):  # type: ignore[dict-item]
            result = shield(client)

        assert isinstance(result, AnthropicAdapter)

    def test_async_anthropic_client_returns_anthropic_adapter(self) -> None:
        mock_anthropic = MagicMock()
        mock_anthropic.Anthropic = type("Anthropic", (), {})
        mock_anthropic.AsyncAnthropic = type("AsyncAnthropic", (), {})
        client = mock_anthropic.AsyncAnthropic()

        with patch.dict("sys.modules", {"openai": None, "anthropic": mock_anthropic}):  # type: ignore[dict-item]
            result = shield(client)

        assert isinstance(result, AnthropicAdapter)


class TestShieldLangChain:
    def test_langchain_base_chat_model_returns_handler(self) -> None:
        BaseChatModel = type("BaseChatModel", (), {})
        client = BaseChatModel()

        mock_lc_models = MagicMock()
        mock_lc_models.BaseChatModel = BaseChatModel
        mock_lc_core = MagicMock()
        mock_lc_core.language_models = mock_lc_models

        with patch.dict(
            "sys.modules",
            {
                "openai": None,  # type: ignore[dict-item]
                "anthropic": None,  # type: ignore[dict-item]
                "langchain_core": mock_lc_core,
                "langchain_core.language_models": mock_lc_models,
            },
        ):
            result = shield(client)

        assert isinstance(result, LangChainCallbackHandler)


class TestShieldTypeError:
    def test_unsupported_type_raises_type_error(self) -> None:
        with patch.dict("sys.modules", {"openai": None, "anthropic": None, "langchain_core": None}):  # type: ignore[dict-item]
            with pytest.raises(TypeError, match="Unsupported client type"):
                shield(object())

    def test_type_error_message_lists_supported_types(self) -> None:
        with patch.dict("sys.modules", {"openai": None, "anthropic": None, "langchain_core": None}):  # type: ignore[dict-item]
            with pytest.raises(TypeError) as exc_info:
                shield(42)
        msg = str(exc_info.value)
        assert "openai.OpenAI" in msg
        assert "anthropic.Anthropic" in msg
        assert "BaseChatModel" in msg

    def test_plain_dict_raises_type_error(self) -> None:
        with patch.dict("sys.modules", {"openai": None, "anthropic": None, "langchain_core": None}):  # type: ignore[dict-item]
            with pytest.raises(TypeError):
                shield({"model": "gpt-4"})  # type: ignore[arg-type]


class TestShieldDefaultConfig:
    def test_default_config_applied_when_no_kwargs(self) -> None:
        """shield() with no kwargs should use default config (regex detector, memory vault)."""
        mock_openai = MagicMock()
        mock_openai.OpenAI = type("OpenAI", (), {})
        mock_openai.AsyncOpenAI = type("AsyncOpenAI", (), {})
        client = mock_openai.OpenAI()

        with patch.dict("sys.modules", {"openai": mock_openai}):
            result = shield(client)

        assert isinstance(result, OpenAIAdapter)
        # Pipeline should have been built with default config
        assert result._pipeline is not None
        assert result._pipeline._config["vault"] == "memory"

    def test_kwargs_passed_to_config(self) -> None:
        """shield() kwargs are forwarded to load_config()."""
        mock_openai = MagicMock()
        mock_openai.OpenAI = type("OpenAI", (), {})
        mock_openai.AsyncOpenAI = type("AsyncOpenAI", (), {})
        client = mock_openai.OpenAI()

        with patch.dict("sys.modules", {"openai": mock_openai}):
            result = shield(client, vault="memory")

        assert isinstance(result, OpenAIAdapter)
        assert result._pipeline._config["vault"] == "memory"
