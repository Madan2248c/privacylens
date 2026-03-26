"""De-tokenizer for PrivacyLens.

Restores original PII values in text by replacing ``[ENTITY_TYPE_N]`` tokens
with the values stored in the session vault.  Also handles cases where the LLM
strips the square brackets (e.g. ``EMAIL_1`` instead of ``[EMAIL_1]``).
"""

from __future__ import annotations

import logging
import re

from privacylens.core.vault import SessionVault

_log = logging.getLogger("privacylens")

# Matches tokens with brackets: [EMAIL_1], [PHONE_2]
_TOKEN_RE = re.compile(r"\[([A-Z][A-Z0-9_]*_\d+)\]")

# Matches tokens without brackets: EMAIL_1, PHONE_2 (word boundary)
_TOKEN_BARE_RE = re.compile(r"\b([A-Z][A-Z0-9_]*_\d+)\b")


def detokenize(text: str, vault: SessionVault, session_id: str) -> str:
    """Replace ``[ENTITY_TYPE_N]`` tokens in *text* with their original values.

    Performs two passes:
    1. Bracketed tokens like ``[EMAIL_1]``
    2. Bare tokens like ``EMAIL_1`` (for when LLMs strip brackets)

    Tokens not present in the vault are left unchanged.

    Args:
        text: The tokenized text to restore.
        vault: Session vault holding token→value mappings.
        session_id: Identifier for the current session.

    Returns:
        The de-tokenized text with original values restored.
    """
    restored_count = 0
    missed_count = 0

    def _replace_bracketed(match: re.Match[str]) -> str:
        nonlocal restored_count
        token = match.group(0)  # [EMAIL_1]
        try:
            value = vault.retrieve(session_id, token)
            restored_count += 1
            return value
        except KeyError:
            return token

    # Pass 1: bracketed tokens
    result = _TOKEN_RE.sub(_replace_bracketed, text)

    # Pass 2: bare tokens (LLM stripped brackets)
    def _replace_bare(match: re.Match[str]) -> str:
        nonlocal restored_count, missed_count
        bare = match.group(1)  # EMAIL_1
        token = f"[{bare}]"  # reconstruct [EMAIL_1]
        try:
            value = vault.retrieve(session_id, token)
            restored_count += 1
            _log.debug("Restored bare token %s (LLM stripped brackets)", bare)
            return value
        except KeyError:
            missed_count += 1
            return match.group(0)

    result = _TOKEN_BARE_RE.sub(_replace_bare, result)

    if missed_count > 0:
        _log.warning(
            "Detokenization: %d token(s) could not be restored (not found in vault)",
            missed_count,
        )

    return result
