"""De-tokenizer for PrivacyLens.

Restores original PII values in text by replacing ``[ENTITY_TYPE_N]`` tokens
with the values stored in the session vault.  Uses a single-pass ``re.sub``
with a callable replacement so every token is visited exactly once.
"""

from __future__ import annotations

import re

from privacylens.core.vault import SessionVault

# Matches tokens of the form [ENTITY_TYPE_N], e.g. [EMAIL_1], [PHONE_2].
_TOKEN_RE = re.compile(r"\[([A-Z][A-Z0-9_]*)_(\d+)\]")


def detokenize(text: str, vault: SessionVault, session_id: str) -> str:
    """Replace ``[ENTITY_TYPE_N]`` tokens in *text* with their original values.

    Performs a single pass over *text* using ``re.sub`` with a callable
    replacement.  Tokens not present in the vault for the given session are
    left unchanged in the output.

    Args:
        text: The tokenized text to restore.
        vault: Session vault holding token→value mappings.
        session_id: Identifier for the current session.

    Returns:
        The de-tokenized text with original values restored.
    """
    def _replace(match: re.Match[str]) -> str:
        token = match.group(0)
        try:
            return vault.retrieve(session_id, token)
        except KeyError:
            return token  # leave unknown tokens unchanged

    return _TOKEN_RE.sub(_replace, text)
