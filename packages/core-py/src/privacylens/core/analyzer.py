"""Analyzer for PrivacyLens.

Orchestrates all enabled detectors, resolves overlapping EntitySpans, and
emits structured logs and on_detection callbacks — never including original
PII values.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from privacylens.core.models import Config, Detector, EntitySpan

if TYPE_CHECKING:
    pass

logger = logging.getLogger("privacylens")

# ---------------------------------------------------------------------------
# Module-level detector plugin registry
# ---------------------------------------------------------------------------

_registry: dict[str, Detector] = {}


def register_detector(name: str, detector: Detector) -> None:
    """Register a detector under the given name.

    Args:
        name: The name to register the detector under.
        detector: Any object implementing the Detector protocol.
    """
    _registry[name] = detector


def get_detector(name: str) -> Detector:
    """Retrieve a previously registered detector by name.

    Args:
        name: The name the detector was registered under.

    Returns:
        The registered Detector instance.

    Raises:
        KeyError: If no detector is registered under *name*.
    """
    return _registry[name]


# ---------------------------------------------------------------------------
# Overlap resolution helper
# ---------------------------------------------------------------------------

def _resolve_overlaps(spans: list[EntitySpan]) -> list[EntitySpan]:
    """Resolve overlapping spans, retaining the longest character range.

    Algorithm (O(n log n)):
      1. Sort spans by start asc, then by length desc.
      2. Walk through; if a span starts at or after the current end, append it.
         If it starts before the current end but extends further, replace the
         last appended span (it is longer).

    Args:
        spans: Unsorted list of EntitySpan objects (may contain overlaps).

    Returns:
        A new list with overlaps resolved, sorted by start ascending.
    """
    if not spans:
        return []

    sorted_spans = sorted(spans, key=lambda s: (s.start, -(s.end - s.start)))

    result: list[EntitySpan] = []
    last_end = -1

    for span in sorted_spans:
        if span.start >= last_end:
            result.append(span)
            last_end = span.end
        elif span.end > last_end:
            # This span starts before last_end but extends further — it is
            # longer than the previously appended span, so replace it.
            result[-1] = span
            last_end = span.end
        # else: span is fully contained within the last span — discard it.

    return result


# ---------------------------------------------------------------------------
# Analyzer class
# ---------------------------------------------------------------------------

class Analyzer:
    """Orchestrates detectors and produces a unified, deduplicated EntitySpan list.

    Args:
        detectors: List of Detector instances to run against input text.
        config: Active PrivacyLens configuration.
    """

    def __init__(self, detectors: list[Detector], config: Config | None = None) -> None:
        self._detectors = detectors
        self._config: Config = config if config is not None else {}

    def analyze(self, text: str) -> list[EntitySpan]:
        """Run all detectors against *text* and return a resolved EntitySpan list.

        Steps:
        1. Invoke each detector's ``detect()`` method; catch and log any exception.
        2. Merge all returned spans.
        3. Resolve overlaps (retain longest span).
        4. Sort by ``start`` ascending.
        5. Invoke ``on_detection`` callback with entity type only (never value).
        6. Emit a structured INFO log with entity types and count (never values).

        Args:
            text: The input text to analyze.

        Returns:
            A list of EntitySpan objects sorted by start offset, with overlaps
            resolved.
        """
        all_spans: list[EntitySpan] = []

        for detector in self._detectors:
            try:
                spans = detector.detect(text)
                all_spans.extend(spans)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Detector %s raised an exception: %s",
                    type(detector).__name__,
                    exc,
                )

        resolved = _resolve_overlaps(all_spans)

        # Invoke on_detection callback with entity type only.
        on_detection = self._config.get("on_detection")
        if on_detection is not None:
            for span in resolved:
                on_detection(span.entity_type)

        # Emit structured INFO log — entity types and count, never values.
        if resolved:
            entity_types = [s.entity_type for s in resolved]
            logger.info(
                "Detected %d entit%s: %s",
                len(resolved),
                "y" if len(resolved) == 1 else "ies",
                ", ".join(entity_types),
            )

        return resolved
