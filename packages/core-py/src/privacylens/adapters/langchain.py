"""LangChain callback handler for PrivacyLens.

Integrates with LangChain's callback system to transparently mask PII in
prompts before they reach any LLM backend, then restore original values in
the generated response.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from privacylens.core.pipeline import Pipeline


def _new_session_id() -> str:
    return str(uuid.uuid4())


class LangChainCallbackHandler:
    """LangChain ``BaseCallbackHandler`` that tokenizes prompts and de-tokenizes responses.

    Pass an instance of this handler as an element of the ``callbacks`` list in
    any LangChain ``invoke()`` or ``run()`` call::

        handler = LangChainCallbackHandler(pipeline)
        chain.invoke({"input": "..."}, config={"callbacks": [handler]})

    The handler uses ``run_id``-scoped sessions so that concurrent LLM runs
    remain isolated from each other.

    Args:
        pipeline: The PrivacyLens pipeline to use for tokenization.
    """

    def __init__(self, pipeline: Pipeline) -> None:
        # Lazy import so that langchain_core is not a hard dependency of core.
        try:
            from langchain_core.callbacks import BaseCallbackHandler  # noqa: F401
        except ImportError:
            pass  # Allow instantiation without langchain installed (tests mock it)

        self._pipeline = pipeline
        # Maps str(run_id) → session_id for in-flight LLM runs.
        self._sessions: dict[str, str] = {}

    # ------------------------------------------------------------------
    # BaseCallbackHandler interface
    # ------------------------------------------------------------------

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: Any,
        **kwargs: Any,
    ) -> None:
        """Tokenize PII in each prompt string in-place before the LLM call.

        LangChain passes a mutable list, so mutating ``prompts[i]`` is the
        correct way to intercept the content.

        Args:
            serialized: Serialized LLM metadata (unused).
            prompts: Mutable list of prompt strings to tokenize in-place.
            run_id: Unique identifier for this LLM run.
        """
        session_id = _new_session_id()
        self._sessions[str(run_id)] = session_id
        for i, prompt in enumerate(prompts):
            prompts[i] = self._pipeline.tokenize_text(prompt, session_id)

    def on_llm_end(
        self,
        response: Any,
        *,
        run_id: Any,
        **kwargs: Any,
    ) -> None:
        """De-tokenize all text generations in the LLM response.

        Args:
            response: An ``LLMResult`` object whose ``generations`` are
                de-tokenized in-place.
            run_id: Unique identifier for this LLM run (matches ``on_llm_start``).
        """
        session_id = self._sessions.pop(str(run_id), None)
        if session_id is None:
            return

        for generation_list in response.generations:
            for gen in generation_list:
                if hasattr(gen, "text") and isinstance(gen.text, str):
                    gen.text = self._pipeline.detokenize(gen.text, session_id)

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: Any,
        **kwargs: Any,
    ) -> None:
        """Clean up session state when an LLM run fails.

        Args:
            error: The exception raised by the LLM.
            run_id: Unique identifier for the failed run.
        """
        self._sessions.pop(str(run_id), None)

    def __repr__(self) -> str:
        return f"LangChainCallbackHandler(pipeline={self._pipeline!r})"
