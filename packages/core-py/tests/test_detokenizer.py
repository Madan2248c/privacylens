"""Tests for the De-tokenizer module (Property 13 and unit tests)."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from privacylens.core.detokenizer import detokenize
from privacylens.core.models import EntitySpan
from privacylens.core.tokenizer import tokenize
from privacylens.core.vault import MemoryVault

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_session_id = st.text(min_size=1, max_size=40)
_entity_type = st.from_regex(r"[A-Z][A-Z0-9_]{0,19}", fullmatch=True)
_value = st.text(min_size=1, max_size=50).filter(
    # Exclude strings that look like tokens themselves to keep round-trip clean
    lambda v: not (v.startswith("[") and v.endswith("]"))
)
_plain_text = st.text(min_size=0, max_size=200).filter(
    lambda t: "[" not in t and "]" not in t
)


# ---------------------------------------------------------------------------
# Property 13: tokenize → detokenize round-trip
# ---------------------------------------------------------------------------


@given(
    session_id=_session_id,
    entity_type=_entity_type,
    value=_value,
    prefix=_plain_text,
    suffix=_plain_text,
)
@settings(max_examples=300)
def test_tokenize_detokenize_roundtrip(
    session_id: str,
    entity_type: str,
    value: str,
    prefix: str,
    suffix: str,
) -> None:
    """Property 13: tokenize then detokenize produces the original text.

    For any text and list of EntitySpans, tokenizing the text and then
    de-tokenizing the result using the same session vault SHALL produce
    the original text.

    **Validates: Requirements 6.1, 8.1, 8.5**
    """
    vault = MemoryVault()
    text = prefix + value + suffix
    span = EntitySpan(
        start=len(prefix),
        end=len(prefix) + len(value),
        entity_type=entity_type,
        value=value,
    )

    tokenized, _ = tokenize(text, [span], vault, session_id)
    restored = detokenize(tokenized, vault, session_id)

    assert restored == text, (
        f"Round-trip failed: original={text!r}, tokenized={tokenized!r}, restored={restored!r}"
    )


@given(
    session_id=_session_id,
    entries=st.lists(
        st.tuples(
            st.from_regex(r"[A-Z][A-Z0-9_]{0,19}", fullmatch=True),
            _value,
        ),
        min_size=1,
        max_size=5,
        unique_by=lambda pair: pair[1],  # unique values
    ),
)
@settings(max_examples=200)
def test_tokenize_detokenize_roundtrip_multiple_spans(
    session_id: str,
    entries: list[tuple[str, str]],
) -> None:
    """Property 13 (multi-span): round-trip holds for multiple distinct entities."""
    vault = MemoryVault()

    # Build text by joining values with a fixed separator.
    separator = "---"
    values = [v for _, v in entries]
    entity_types = [et for et, _ in entries]
    text = separator.join(values)

    spans: list[EntitySpan] = []
    cursor = 0
    for entity_type, value in zip(entity_types, values):
        spans.append(EntitySpan(
            start=cursor,
            end=cursor + len(value),
            entity_type=entity_type,
            value=value,
        ))
        cursor += len(value) + len(separator)

    tokenized, _ = tokenize(text, spans, vault, session_id)
    restored = detokenize(tokenized, vault, session_id)

    assert restored == text


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


class TestNoTokenPassthrough:
    def test_text_without_tokens_returned_unchanged(self) -> None:
        """Requirement 8.3: no tokens → return text unchanged."""
        vault = MemoryVault()
        text = "Hello, world! No PII here."
        assert detokenize(text, vault, "s1") == text

    def test_empty_string_returned_unchanged(self) -> None:
        vault = MemoryVault()
        assert detokenize("", vault, "s1") == ""


class TestUnknownTokenPassthrough:
    def test_unknown_token_left_unchanged(self) -> None:
        """Requirement 8.2: token not in vault → leave token string unchanged."""
        vault = MemoryVault()
        text = "Contact [EMAIL_1] for details."
        result = detokenize(text, vault, "s1")
        assert result == text

    def test_mix_of_known_and_unknown_tokens(self) -> None:
        vault = MemoryVault()
        vault.store("s1", "[EMAIL_1]", "alice@example.com")
        text = "Email: [EMAIL_1], phone: [PHONE_1]"
        result = detokenize(text, vault, "s1")
        assert result == "Email: alice@example.com, phone: [PHONE_1]"

    def test_unknown_token_in_different_session(self) -> None:
        vault = MemoryVault()
        vault.store("s1", "[EMAIL_1]", "alice@example.com")
        # Same token but different session — should be left unchanged.
        result = detokenize("[EMAIL_1]", vault, "s2")
        assert result == "[EMAIL_1]"


class TestBasicDetokenization:
    def test_single_token_replaced(self) -> None:
        vault = MemoryVault()
        vault.store("s1", "[EMAIL_1]", "alice@example.com")
        result = detokenize("Email: [EMAIL_1]", vault, "s1")
        assert result == "Email: alice@example.com"

    def test_multiple_tokens_replaced(self) -> None:
        vault = MemoryVault()
        vault.store("s1", "[EMAIL_1]", "alice@example.com")
        vault.store("s1", "[PHONE_1]", "555-1234")
        result = detokenize("[EMAIL_1] / [PHONE_1]", vault, "s1")
        assert result == "alice@example.com / 555-1234"

    def test_repeated_token_replaced_everywhere(self) -> None:
        """Requirement 8.4: single-pass replaces all occurrences."""
        vault = MemoryVault()
        vault.store("s1", "[EMAIL_1]", "alice@example.com")
        result = detokenize("[EMAIL_1] and [EMAIL_1]", vault, "s1")
        assert result == "alice@example.com and alice@example.com"

    def test_surrounding_text_preserved(self) -> None:
        vault = MemoryVault()
        vault.store("s1", "[SSN_1]", "123-45-6789")
        result = detokenize("SSN is [SSN_1] on file.", vault, "s1")
        assert result == "SSN is 123-45-6789 on file."

    def test_token_with_high_counter(self) -> None:
        vault = MemoryVault()
        vault.store("s1", "[EMAIL_42]", "user@example.com")
        result = detokenize("Contact [EMAIL_42].", vault, "s1")
        assert result == "Contact user@example.com."


class TestRoundTripWithTokenizer:
    def test_full_roundtrip_single_entity(self) -> None:
        vault = MemoryVault()
        text = "Please email alice@example.com today."
        span = EntitySpan(start=13, end=30, entity_type="EMAIL", value="alice@example.com")
        tokenized, _ = tokenize(text, [span], vault, "s1")
        assert detokenize(tokenized, vault, "s1") == text

    def test_full_roundtrip_no_spans(self) -> None:
        vault = MemoryVault()
        text = "No PII in this message."
        tokenized, _ = tokenize(text, [], vault, "s1")
        assert detokenize(tokenized, vault, "s1") == text
