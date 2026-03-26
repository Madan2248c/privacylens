"""Optional semantic detector backed by GLiNER.

Install the extra to use this detector:
    pip install privacylens[semantic]
"""

from __future__ import annotations

from privacylens.core.models import EntitySpan

DEFAULT_LABELS = ["person", "email", "phone", "address", "organization"]


class SemanticDetector:
    """Detects PII entities using GLiNER (Generalist and Lightweight NER).

    GLiNER is loaded lazily on the first call to :meth:`detect`. If it is not
    installed, an :class:`ImportError` is raised at construction time with
    installation instructions.
    """

    _model = None  # lazy-loaded on first use

    def __init__(self, labels: list[str] | None = None) -> None:
        try:
            import gliner  # noqa: F401
        except ImportError:
            raise ImportError("Install GLiNER: pip install privacylens[semantic]")
        self._labels = labels or DEFAULT_LABELS

    def detect(self, text: str) -> list[EntitySpan]:
        """Scan *text* and return a list of :class:`~privacylens.core.models.EntitySpan`.

        The GLiNER model is loaded on the first call to this method.
        """
        if self._model is None:
            from gliner import GLiNER
            SemanticDetector._model = GLiNER.from_pretrained("urchade/gliner_medium-v2.1")

        entities = self._model.predict_entities(text, self._labels)
        return [
            EntitySpan(
                start=e["start"],
                end=e["end"],
                entity_type=e["label"].upper(),
                value=e["text"],
            )
            for e in entities
        ]
