"""Core data models for PrivacyLens."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol, TypedDict, runtime_checkable


@dataclass
class EntitySpan:
    """Represents a detected sensitive entity in text.

    Attributes:
        start: Start character offset (inclusive).
        end: End character offset (exclusive).
        entity_type: The type of entity detected (e.g., "EMAIL", "PHONE").
        value: The original text value of the detected entity.
    """

    start: int
    end: int
    entity_type: str
    value: str

    def __post_init__(self) -> None:
        if self.start > self.end:
            raise ValueError(
                f"EntitySpan.start ({self.start}) must be <= end ({self.end})"
            )


class DetectorConfig(TypedDict, total=False):
    """Configuration for an individual detector."""

    enabled: bool
    patterns: list[dict[str, str]]  # [{"entity_type": str, "pattern": str}]


class Config(TypedDict, total=False):
    """Top-level PrivacyLens configuration."""

    version: str
    detectors: dict[str, DetectorConfig]
    vault: str  # "memory" | "redis" | "sqlite"
    on_detection: Callable[[str], None] | None


@runtime_checkable
class Detector(Protocol):
    """Protocol that all detectors must implement."""

    def detect(self, text: str) -> list[EntitySpan]:
        """Scan text and return a list of detected entity spans.

        Args:
            text: The input text to scan.

        Returns:
            A list of EntitySpan objects for each detected entity.
        """
        ...
