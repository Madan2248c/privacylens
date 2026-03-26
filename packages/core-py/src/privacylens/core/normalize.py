"""Message normalization for PrivacyLens.

Converts any supported message format into a canonical list of message dicts.
"""

from __future__ import annotations

from typing import Any


def normalize_messages(input: Any) -> list[dict[str, Any]]:
    """Normalize any supported message format to a canonical list of message dicts.

    Supported input formats:
    - Plain string → ``[{"role": "user", "content": input}]``
    - OpenAI-style list of dicts (each with ``role`` and ``content``) → returned unchanged
    - Anthropic-style dict with a ``"messages"`` key → ``input["messages"]``

    Args:
        input: The message input in any supported format.

    Returns:
        A list of message dicts, each containing at least ``role`` and ``content`` keys.

    Raises:
        TypeError: If the input is not a string, list, or recognized dict structure.
    """
    if isinstance(input, str):
        return [{"role": "user", "content": input}]

    if isinstance(input, list):
        return input

    if isinstance(input, dict):
        if "messages" in input:
            return input["messages"]
        raise TypeError(
            f"Unrecognized dict format: expected a dict with a 'messages' key "
            f"(Anthropic-style), but got keys: {list(input.keys())!r}"
        )

    raise TypeError(
        f"Unsupported message format: expected a str, list, or dict with a 'messages' key, "
        f"but got {type(input).__name__!r}"
    )
