"""Optional PII detector backed by Microsoft Presidio Analyzer.

Install the extra to use this detector:
    pip install privacylens[pii]
"""

from __future__ import annotations

from privacylens.core.models import EntitySpan


class PiiDetector:
    """Detects PII entities using Microsoft Presidio Analyzer.

    Presidio is loaded lazily at construction time. If it is not installed,
    an :class:`ImportError` is raised with installation instructions.

    Entity type strings returned by Presidio are passed through to
    :class:`~privacylens.core.models.EntitySpan` without modification.
    """

    def __init__(self) -> None:
        try:
            from presidio_analyzer import (
                AnalyzerEngine,  # type: ignore[import-not-found]
            )
        except ImportError:
            raise ImportError("Install Presidio: pip install privacylens[pii]")
        self._engine = AnalyzerEngine()

    def detect(self, text: str) -> list[EntitySpan]:
        """Scan *text* and return a list of :class:`~privacylens.core.models.EntitySpan`.

        Entity types are taken directly from Presidio results without any
        mapping or transformation.
        """
        results = self._engine.analyze(text=text, language="en")
        return [
            EntitySpan(
                start=r.start,
                end=r.end,
                entity_type=r.entity_type,
                value=text[r.start : r.end],
            )
            for r in results
        ]
