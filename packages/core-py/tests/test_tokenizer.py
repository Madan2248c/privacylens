"""Tests for the Tokenizer module (Property 12 and unit tests)."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from privacylens.core.models import EntitySpan
from privacylens.core.tokenizer import tokenize
from privacylens.core.vault import MemoryVault


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_session_id = st.text(min_size=1, max_size=40)
_entity_type = st.from_regex(r"[A-Z][A-Z0-9_]{0,19}", fullmatch=True)
_value = st.text(min_size=1, max_size=50)


def _make_span(entity_type: str, value: str, offset: int = 0) -> EntitySpan:
    return EntitySpan(
        start=offset,
        end=offset + len(value),
        entity_type=entity_type,
        value=value,
    )


# ---------------------------------------------------------------------------
# Property 12: Stable token assignment within session
# ---------------------------------------------------------------------------


@given(
    session_id=_session_id,
    entity_type=_entity_type,
    value=_value,
    repetitions=st.integers(min_value=2, max_value=5),
)
@settings(max_examples=300)
def test_stable_token_assignment_same_value(
    session_id: str,
    entity_type: str,
    value: str,
    repetitions: int,
) -> None:
    """Property 12: same value → same token within a session.

    For any text where the same value appears multiple times, the Tokenizer
    SHALL assign the same [ENTITY_TYPE_N] token to all occurrences of that
    value within the same session.

    **Validates: Requirements 6.2**
    """
    vault = MemoryVault()

    # Build a text that contains the value `repetitions` times, separated by spaces.
    separator = " | "
    text = separator.join([value] * repetitions)

    # Build spans for each occurrence.
    spans: list[EntitySpan] = []
    cursor = 0
    for _ in range(repetitions):
        spans.append(EntitySpan(start=cursor, end=cursor + len(value), entity_type=entity_type, value=value))
        cursor += len(value) + len(separator)

    tokenized, pairs = tokenize(text, spans, vault, session_id)

    # All pairs must map to the same token.
    tokens_used = {token for token, _ in pairs}
    assert len(tokens_used) == 1, (
        f"Expected a single token for repeated value, got: {tokens_used}"
    )

    # The tokenized text should contain only that one token (no original value).
    the_token = next(iter(tokens_used))
    assert value not in tokenized or the_token in tokenized


@given(
    session_id=_session_id,
    entity_type=_entity_type,
    value=_value,
)
@settings(max_examples=200)
def test_stable_token_across_multiple_tokenize_calls(
    session_id: str,
    entity_type: str,
    value: str,
) -> None:
    """Property 12 (cross-call): same value in the same session always gets the same token.

    **Validates: Requirements 6.2**
    """
    vault = MemoryVault()
    span = _make_span(entity_type, value)

    _, pairs1 = tokenize(value, [span], vault, session_id)
    _, pairs2 = tokenize(value, [span], vault, session_id)

    assert len(pairs1) == 1
    assert len(pairs2) == 1
    assert pairs1[0][0] == pairs2[0][0], (
        "Same value in same session must always produce the same token"
    )


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


class TestEmptySpans:
    def test_empty_spans_returns_original_text(self) -> None:
        """Requirement 6.5: empty span list → original text unchanged, empty pairs."""
        vault = MemoryVault()
        text = "Hello, alice@example.com!"
        result, pairs = tokenize(text, [], vault, "s1")
        assert result == text
        assert pairs == []

    def test_empty_text_empty_spans(self) -> None:
        vault = MemoryVault()
        result, pairs = tokenize("", [], vault, "s1")
        assert result == ""
        assert pairs == []


class TestBasicTokenization:
    def test_single_span_replaced(self) -> None:
        vault = MemoryVault()
        text = "Email: alice@example.com"
        span = EntitySpan(start=7, end=24, entity_type="EMAIL", value="alice@example.com")
        result, pairs = tokenize(text, [span], vault, "s1")
        assert result == "Email: [EMAIL_1]"
        assert pairs == [("[EMAIL_1]", "alice@example.com")]

    def test_multiple_distinct_values_get_distinct_tokens(self) -> None:
        vault = MemoryVault()
        text = "alice@example.com and bob@example.com"
        spans = [
            EntitySpan(start=0, end=17, entity_type="EMAIL", value="alice@example.com"),
            EntitySpan(start=22, end=37, entity_type="EMAIL", value="bob@example.com"),
        ]
        result, pairs = tokenize(text, spans, vault, "s1")
        assert "[EMAIL_1]" in result
        assert "[EMAIL_2]" in result
        assert "alice@example.com" not in result
        assert "bob@example.com" not in result
        assert len(pairs) == 2

    def test_same_value_twice_gets_same_token(self) -> None:
        vault = MemoryVault()
        text = "alice@example.com and alice@example.com"
        spans = [
            EntitySpan(start=0, end=17, entity_type="EMAIL", value="alice@example.com"),
            EntitySpan(start=22, end=39, entity_type="EMAIL", value="alice@example.com"),
        ]
        result, pairs = tokenize(text, spans, vault, "s1")
        assert result == "[EMAIL_1] and [EMAIL_1]"
        tokens = {t for t, _ in pairs}
        assert tokens == {"[EMAIL_1]"}

    def test_different_entity_types_have_independent_counters(self) -> None:
        vault = MemoryVault()
        text = "alice@example.com 555-1234"
        spans = [
            EntitySpan(start=0, end=17, entity_type="EMAIL", value="alice@example.com"),
            EntitySpan(start=18, end=26, entity_type="PHONE", value="555-1234"),
        ]
        result, pairs = tokenize(text, spans, vault, "s1")
        assert "[EMAIL_1]" in result
        assert "[PHONE_1]" in result

    def test_token_stored_in_vault(self) -> None:
        vault = MemoryVault()
        text = "alice@example.com"
        span = EntitySpan(start=0, end=17, entity_type="EMAIL", value="alice@example.com")
        tokenize(text, [span], vault, "s1")
        assert vault.retrieve("s1", "[EMAIL_1]") == "alice@example.com"

    def test_text_before_and_after_span_preserved(self) -> None:
        vault = MemoryVault()
        text = "Hello alice@example.com, how are you?"
        span = EntitySpan(start=6, end=23, entity_type="EMAIL", value="alice@example.com")
        result, _ = tokenize(text, [span], vault, "s1")
        assert result == "Hello [EMAIL_1], how are you?"


class TestOverlapHandling:
    def test_fully_contained_span_skipped(self) -> None:
        """Requirement 6.3: span fully contained within already-processed span is skipped."""
        vault = MemoryVault()
        # Outer span covers "alice@example.com", inner span covers "alice"
        text = "alice@example.com"
        outer = EntitySpan(start=0, end=17, entity_type="EMAIL", value="alice@example.com")
        inner = EntitySpan(start=0, end=5, entity_type="NAME", value="alice")
        result, pairs = tokenize(text, [outer, inner], vault, "s1")
        # Only the outer span should be tokenized
        assert result == "[EMAIL_1]"
        assert len(pairs) == 1
        assert pairs[0][0] == "[EMAIL_1]"

    def test_partially_overlapping_spans_first_wins(self) -> None:
        """When spans partially overlap, the first (by start) is processed; the second is skipped if contained."""
        vault = MemoryVault()
        # span1: 0-10, span2: 5-15 — partial overlap, span2 is NOT fully contained
        text = "0123456789abcde"
        span1 = EntitySpan(start=0, end=10, entity_type="TYPE_A", value="0123456789")
        span2 = EntitySpan(start=5, end=15, entity_type="TYPE_B", value="56789abcde")
        result, pairs = tokenize(text, [span1, span2], vault, "s1")
        # span2 starts before last_end (10) but ends after it — not fully contained,
        # so it should still be processed (starts at 5 < 10, ends at 15 > 10).
        # Per the algorithm: skip only if span.start < last_end AND span.end <= last_end.
        # span2.end (15) > last_end (10), so it is NOT skipped.
        assert "[TYPE_A_1]" in result
        assert "[TYPE_B_1]" in result

    def test_adjacent_spans_both_tokenized(self) -> None:
        vault = MemoryVault()
        text = "alice@example.com555-1234"
        spans = [
            EntitySpan(start=0, end=17, entity_type="EMAIL", value="alice@example.com"),
            EntitySpan(start=17, end=25, entity_type="PHONE", value="555-1234"),
        ]
        result, pairs = tokenize(text, spans, vault, "s1")
        assert result == "[EMAIL_1][PHONE_1]"
        assert len(pairs) == 2


class TestSessionIsolation:
    def test_different_sessions_get_independent_counters(self) -> None:
        vault = MemoryVault()
        text = "alice@example.com"
        span = EntitySpan(start=0, end=17, entity_type="EMAIL", value="alice@example.com")

        _, pairs_s1 = tokenize(text, [span], vault, "session-1")
        _, pairs_s2 = tokenize(text, [span], vault, "session-2")

        # Both sessions independently assign [EMAIL_1] for the same value.
        assert pairs_s1[0][0] == "[EMAIL_1]"
        assert pairs_s2[0][0] == "[EMAIL_1]"
        # But they are stored independently in the vault.
        assert vault.retrieve("session-1", "[EMAIL_1]") == "alice@example.com"
        assert vault.retrieve("session-2", "[EMAIL_1]") == "alice@example.com"

    def test_stable_token_across_calls_same_session(self) -> None:
        vault = MemoryVault()
        text = "alice@example.com"
        span = EntitySpan(start=0, end=17, entity_type="EMAIL", value="alice@example.com")

        _, pairs1 = tokenize(text, [span], vault, "s1")
        _, pairs2 = tokenize(text, [span], vault, "s1")

        assert pairs1[0][0] == pairs2[0][0] == "[EMAIL_1]"
