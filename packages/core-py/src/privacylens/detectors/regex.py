"""Built-in regex-based detector for common PII patterns.

Zero runtime dependencies beyond the standard library (``re`` only).
"""

from __future__ import annotations

import re

from privacylens.core.models import DetectorConfig, EntitySpan

# ---------------------------------------------------------------------------
# Built-in compiled patterns
# ---------------------------------------------------------------------------

# EMAIL: RFC 5321 local-part + @ + domain
_EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    re.ASCII,
)

# PHONE: (NNN) NNN-NNNN | NNN-NNN-NNNN | +1NNNNNNNNNN
_PHONE_RE = re.compile(
    r"(?:\(\d{3}\)\s?\d{3}-\d{4}|\d{3}-\d{3}-\d{4}|\+1\d{10})",
    re.ASCII,
)

# SSN: NNN-NN-NNNN
_SSN_RE = re.compile(
    r"\b\d{3}-\d{2}-\d{4}\b",
    re.ASCII,
)

_BUILTIN_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", _EMAIL_RE),
    ("PHONE", _PHONE_RE),
    ("SSN", _SSN_RE),
]


class RegexDetector:
    """Detects PII using regular expressions.

    Built-in patterns cover EMAIL, PHONE, and SSN.  Custom patterns supplied
    via ``config["patterns"]`` are compiled once at construction time and
    appended to the built-in set.

    Args:
        config: Optional :class:`~privacylens.core.models.DetectorConfig`
            dict.  The ``patterns`` key, if present, must be a list of
            ``{"entity_type": str, "pattern": str}`` dicts.
    """

    def __init__(self, config: DetectorConfig | None = None) -> None:
        self._patterns: list[tuple[str, re.Pattern[str]]] = list(_BUILTIN_PATTERNS)

        if config:
            for entry in config.get("patterns", []):
                entity_type: str = entry["entity_type"]
                pattern: str = entry["pattern"]
                self._patterns.append((entity_type, re.compile(pattern)))

    def detect(self, text: str) -> list[EntitySpan]:
        """Scan *text* and return a list of :class:`~privacylens.core.models.EntitySpan`.

        Returns an empty list when no matches are found.
        """
        spans: list[EntitySpan] = []
        for entity_type, regex in self._patterns:
            for match in regex.finditer(text):
                spans.append(
                    EntitySpan(
                        start=match.start(),
                        end=match.end(),
                        entity_type=entity_type,
                        value=match.group(),
                    )
                )
        return spans
