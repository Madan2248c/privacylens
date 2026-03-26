"""Tokenizer for PrivacyLens.

Replaces detected EntitySpan ranges in text with stable placeholder tokens
of the form ``[ENTITY_TYPE_N]``, storing the original values in the vault.
"""

from __future__ import annotations

from privacylens.core.models import EntitySpan
from privacylens.core.vault import SessionVault


def tokenize(
    text: str,
    spans: list[EntitySpan],
    vault: SessionVault,
    session_id: str,
) -> tuple[str, list[tuple[str, str]]]:
    """Replace entity spans in *text* with stable ``[ENTITY_TYPE_N]`` tokens.

    Algorithm:
    1. Sort spans by ``start`` ascending (Analyzer already does this, but we
       sort defensively).
    2. Walk spans left-to-right, skipping any span fully contained within an
       already-processed span.
    3. For each span, look up whether the same *value* already has a token in
       this session; if not, assign the next counter token and store it.
    4. Build the output string by copying verbatim text between spans and
       inserting tokens in place of spans.

    Args:
        text: The original input text.
        spans: Detected entity spans (need not be pre-sorted).
        vault: Session vault for storing token↔value mappings.
        session_id: Identifier for the current session.

    Returns:
        A tuple of:
        - The tokenized text string.
        - A list of ``(token, original_value)`` pairs produced during this call.
    """
    if not spans:
        return text, []

    # Sort by start; ties broken by longer span first (matches Analyzer order).
    sorted_spans = sorted(spans, key=lambda s: (s.start, -(s.end - s.start)))

    # Per-entity-type counters for *new* token assignment within this call.
    # We first check the vault for existing value→token mappings so that the
    # same value always gets the same token across multiple tokenize() calls
    # within the same session.
    type_counters: dict[str, int] = {}

    # value → token cache (populated from vault lookups + new assignments).
    value_to_token: dict[str, str] = {}

    # Helper: find or create a token for a given (entity_type, value) pair.
    def _get_or_create_token(entity_type: str, value: str) -> str:
        if value in value_to_token:
            return value_to_token[value]

        # Try to find an existing token in the vault by scanning known tokens.
        # We use a naming convention: [ENTITY_TYPE_1], [ENTITY_TYPE_2], …
        # Scan upward until we find a match or a gap.
        n = 1
        while True:
            candidate = f"[{entity_type}_{n}]"
            try:
                stored_value = vault.retrieve(session_id, candidate)
                if stored_value == value:
                    value_to_token[value] = candidate
                    return candidate
                n += 1
            except KeyError:
                # No more tokens of this type in the vault — assign a new one.
                break

        # Assign the next counter for this entity type.
        # n is already pointing at the first unused slot.
        counter = max(n, type_counters.get(entity_type, 0) + 1)
        type_counters[entity_type] = counter
        token = f"[{entity_type}_{counter}]"
        vault.store(session_id, token, value)
        value_to_token[value] = token
        return token

    parts: list[str] = []
    pairs: list[tuple[str, str]] = []
    cursor = 0
    last_end = -1  # tracks the end of the last processed span

    for span in sorted_spans:
        # Skip spans fully contained within an already-processed span.
        if span.start < last_end and span.end <= last_end:
            continue

        # Copy verbatim text between the previous span and this one.
        parts.append(text[cursor : span.start])

        token = _get_or_create_token(span.entity_type, span.value)
        parts.append(token)
        pairs.append((token, span.value))

        cursor = span.end
        last_end = span.end

    # Append any remaining text after the last span.
    parts.append(text[cursor:])

    return "".join(parts), pairs
