"""Strands adapter for PrivacyLens.

Wraps a Strands ``Model`` instance to transparently mask PII in input
messages and restore original values in the response content blocks.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, AsyncIterable
from typing import (
    TYPE_CHECKING,
    Any,
)

if TYPE_CHECKING:
    from privacylens.core.pipeline import Pipeline

# Try to import the Strands Model base class for isinstance checks and
# subclassing.  If strands-agents is not installed we fall back to a plain
# object base so the wrapper can still be imported without error.
try:
    from strands.models import Model as _StrandsModel

    _STRANDS_AVAILABLE = True
except ImportError:  # pragma: no cover
    _StrandsModel = object  # type: ignore[assignment,misc]
    _STRANDS_AVAILABLE = False


def _new_session_id() -> str:
    return str(uuid.uuid4())


class StrandsModelWrapper(_StrandsModel):
    """Wraps a Strands ``Model`` with PII masking.

    Tokenizes PII in input messages before delegating to the underlying
    model, then de-tokenizes the response content blocks before returning
    them to the caller.

    The response structure expected from the underlying model is::

        {
            "output": {
                "message": {
                    "content": [
                        {"text": "..."},
                        ...
                    ]
                }
            }
        }

    Non-text content blocks (e.g. ``{"image": ...}``) are passed through
    unchanged.

    Args:
        model: A Strands-compatible ``Model`` instance.
        pipeline: The PrivacyLens pipeline to use for tokenization.
    """

    def __init__(self, model: Any, pipeline: Pipeline) -> None:
        self._model = model
        self._pipeline = pipeline

    # ------------------------------------------------------------------
    # Primary method — PII masking + de-tokenization
    # ------------------------------------------------------------------

    def invoke(self, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        """Invoke the underlying model with PII-masked messages.

        Args:
            messages: List of message dicts in Strands format.
            **kwargs: Additional keyword arguments forwarded to the model.

        Returns:
            The model response dict with PII tokens replaced by original values.
        """
        session_id = _new_session_id()
        tokenized = self._pipeline.tokenize_messages(messages, session_id)
        response: dict[str, Any] = self._model.invoke(tokenized, **kwargs)

        # De-tokenize text blocks in the nested response structure:
        # response["output"]["message"]["content"] is a list of content blocks.
        for block in (
            response.get("output", {})
            .get("message", {})
            .get("content", [])
        ):
            if "text" in block:
                block["text"] = self._pipeline.detokenize(block["text"], session_id)

        return response

    # ------------------------------------------------------------------
    # Strands Model ABC — delegate to wrapped model
    # ------------------------------------------------------------------

    def update_config(self, **model_config: Any) -> None:
        """Delegate config update to the wrapped model."""
        self._model.update_config(**model_config)

    def get_config(self) -> Any:
        """Delegate config retrieval to the wrapped model."""
        return self._model.get_config()

    def structured_output(
        self,
        output_model: type[Any],
        prompt: Any,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> "AsyncGenerator[dict[str, Any], None]":
        """Delegate structured output to the wrapped model."""
        return self._model.structured_output(  # type: ignore[no-any-return]
            output_model, prompt, system_prompt, **kwargs
        )

    def stream(
        self,
        messages: Any,
        tool_specs: list[Any] | None = None,
        system_prompt: str | None = None,
        *,
        tool_choice: Any = None,
        system_prompt_content: list[Any] | None = None,
        **kwargs: Any,
    ) -> "AsyncIterable[Any]":
        """Delegate streaming to the wrapped model."""
        return self._model.stream(  # type: ignore[no-any-return]
            messages,
            tool_specs=tool_specs,
            system_prompt=system_prompt,
            tool_choice=tool_choice,
            system_prompt_content=system_prompt_content,
            **kwargs,
        )

    def __repr__(self) -> str:
        return f"StrandsModelWrapper(model={self._model!r})"
