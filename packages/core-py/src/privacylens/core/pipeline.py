"""Pipeline facade for PrivacyLens.

Wires together Normalizer, Analyzer, Tokenizer, Vault, and De-tokenizer into
a single cohesive interface used by all adapters.
"""

from __future__ import annotations

import logging
from typing import Any

from privacylens.core.analyzer import Analyzer, get_detector
from privacylens.core.detokenizer import detokenize
from privacylens.core.models import Config, Detector
from privacylens.core.normalize import normalize_messages
from privacylens.core.tokenizer import tokenize
from privacylens.core.vault import _build_vault

logger = logging.getLogger("privacylens")


def _build_detectors(config: Config) -> list[Detector]:
    """Instantiate and return the list of enabled detectors from *config*.

    Default behaviour (no ``detectors`` key in config): enable
    :class:`~privacylens.detectors.regex.RegexDetector` only.

    Detector modules are lazy-imported so that importing ``pipeline.py``
    itself does not pull in optional dependencies.

    Args:
        config: The active PrivacyLens configuration.

    Returns:
        A list of instantiated :class:`~privacylens.core.models.Detector` objects.
    """
    detectors_cfg: dict[str, Any] = config.get("detectors", {})  # type: ignore[assignment]

    # If no detectors config at all, default to RegexDetector only.
    if not detectors_cfg:
        from privacylens.detectors.regex import RegexDetector  # lazy import

        return [RegexDetector()]

    result: list[Detector] = []

    for name, det_cfg in detectors_cfg.items():
        enabled: bool = (
            det_cfg.get("enabled", True) if isinstance(det_cfg, dict) else True
        )

        if not enabled:
            continue

        if name == "regex":
            from privacylens.detectors.regex import RegexDetector  # lazy import

            result.append(RegexDetector(det_cfg or None))  # type: ignore[arg-type]

        elif name == "pii":
            from privacylens.detectors.pii import PiiDetector  # lazy import

            result.append(PiiDetector())

        elif name == "semantic":
            from privacylens.detectors.semantic import SemanticDetector  # lazy import

            labels = det_cfg.get("labels") if isinstance(det_cfg, dict) else None
            result.append(SemanticDetector(labels=labels))

        else:
            # Try the plugin registry for any other detector names.
            try:
                detector = get_detector(name)
                result.append(detector)
            except KeyError:
                logger.warning("Unknown detector %r — skipping.", name)

    return result


class Pipeline:
    """Internal facade wiring together all core pipeline stages.

    Args:
        config: The active PrivacyLens configuration.
    """

    def __init__(self, config: Config) -> None:
        self._config = config
        self._vault = _build_vault(config)
        self._analyzer = Analyzer(_build_detectors(config), config)

    def tokenize_messages(
        self, messages: Any, session_id: str
    ) -> list[dict[str, Any]]:
        """Normalize *messages*, detect PII, and replace spans with tokens.

        Args:
            messages: Any supported message format (plain string, OpenAI-style
                list, or Anthropic-style dict).
            session_id: Identifier for the current session.

        Returns:
            A list of message dicts with PII replaced by ``[ENTITY_TYPE_N]``
            tokens in the ``content`` field.
        """
        normalized = normalize_messages(messages)
        result: list[dict[str, Any]] = []
        for msg in normalized:
            content = msg.get("content", "")
            if isinstance(content, str):
                spans = self._analyzer.analyze(content)
                tokenized, _ = tokenize(content, spans, self._vault, session_id)
                result.append({**msg, "content": tokenized})
            else:
                result.append(msg)
        return result

    def tokenize_text(self, text: str, session_id: str) -> str:
        """Analyze and tokenize a single string.

        Convenience method used by the LangChain adapter which operates on
        raw prompt strings rather than message lists.

        Args:
            text: The input text to tokenize.
            session_id: Identifier for the current session.

        Returns:
            The tokenized text with PII replaced by tokens.
        """
        spans = self._analyzer.analyze(text)
        tokenized, _ = tokenize(text, spans, self._vault, session_id)
        return tokenized

    def detokenize(self, text: str, session_id: str) -> str:
        """Restore original PII values in *text* using the session vault.

        Args:
            text: The tokenized text to restore.
            session_id: Identifier for the current session.

        Returns:
            The de-tokenized text with original values restored.
        """
        return detokenize(text, self._vault, session_id)

    def detokenize_response(self, response: Any, session_id: str) -> Any:
        """De-tokenize an OpenAI-style response object in-place.

        Handles both the primary ``choices[0].message.content`` field and all
        choices in the response.  Non-OpenAI objects are returned unchanged.

        Args:
            response: An OpenAI ``ChatCompletion`` response object (or any
                object with a ``choices`` attribute).
            session_id: Identifier for the current session.

        Returns:
            The response object with PII tokens restored.
        """
        choices = getattr(response, "choices", None)
        if choices is None:
            return response

        for choice in choices:
            message = getattr(choice, "message", None)
            if message is not None:
                content = getattr(message, "content", None)
                if isinstance(content, str):
                    message.content = detokenize(content, self._vault, session_id)

        return response
