"""CrewAI adapter for PrivacyLens.

Wraps any CrewAI-compatible LLM callable to transparently mask PII in
messages before the call and restore original values in the response.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from privacylens.core.pipeline import Pipeline


def _new_session_id() -> str:
    return str(uuid.uuid4())


class CrewAIAdapter:
    """Wraps a CrewAI-compatible LLM callable.

    Intercepts calls to the underlying LLM, tokenizing PII in the messages
    before the call and de-tokenizing the response after.  The adapter is
    a callable itself, so it can be passed directly as the ``llm`` argument
    to a CrewAI ``Agent`` or ``Crew`` without modifying CrewAI internals.

    Args:
        llm: Any callable that accepts ``(messages: list[dict], **kwargs) -> str``.
        pipeline: The PrivacyLens pipeline to use for tokenization.
    """

    def __init__(self, llm: Any, pipeline: Pipeline) -> None:
        self._llm = llm
        self._pipeline = pipeline

    def __call__(self, messages: list[dict[str, Any]], **kwargs: Any) -> str:
        session_id = _new_session_id()
        tokenized = self._pipeline.tokenize_messages(messages, session_id)
        response = self._llm(tokenized, **kwargs)
        return self._pipeline.detokenize(response, session_id)

    def __repr__(self) -> str:
        return f"CrewAIAdapter(llm={self._llm!r})"
