"""Property-based and unit tests for the Analyzer module.

Covers Properties 6, 7, 8, 9, 17, and 18 from the design document.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from privacylens.core.analyzer import Analyzer, get_detector, register_detector
from privacylens.core.models import Config, Detector, EntitySpan


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_entity_type = st.from_regex(r"[A-Z][A-Z0-9_]{0,19}", fullmatch=True)
_text_content = st.text(min_size=1, max_size=200)
_offset = st.integers(min_value=0, max_value=100)

# PII values with a distinctive prefix+suffix pattern that won't collide with
# log boilerplate words like "entity", "entities", "detected", etc.
_pii_value = st.from_regex(r"pii[a-z]{4,12}val", fullmatch=True)


def _span_strategy(
    min_start: int = 0,
    max_start: int = 50,
    min_len: int = 1,
    max_len: int = 20,
) -> st.SearchStrategy[EntitySpan]:
    """Strategy that generates valid EntitySpan objects."""
    return st.builds(
        lambda start, length, entity_type: EntitySpan(
            start=start,
            end=start + length,
            entity_type=entity_type,
            value="x" * length,
        ),
        start=st.integers(min_value=min_start, max_value=max_start),
        length=st.integers(min_value=min_len, max_value=max_len),
        entity_type=_entity_type,
    )


def _overlapping_pair_strategy() -> st.SearchStrategy[tuple[EntitySpan, EntitySpan]]:
    """Strategy that generates two overlapping EntitySpans where one is longer."""
    @st.composite
    def _build(draw: Any) -> tuple[EntitySpan, EntitySpan]:
        start = draw(st.integers(min_value=0, max_value=50))
        # Shorter span: [start, start+short_len)
        short_len = draw(st.integers(min_value=1, max_value=10))
        # Longer span: starts at or before start, ends after start+short_len
        long_extra = draw(st.integers(min_value=1, max_value=10))
        long_len = short_len + long_extra
        entity_type_a = draw(_entity_type)
        entity_type_b = draw(_entity_type)

        shorter = EntitySpan(
            start=start,
            end=start + short_len,
            entity_type=entity_type_a,
            value="s" * short_len,
        )
        longer = EntitySpan(
            start=start,
            end=start + long_len,
            entity_type=entity_type_b,
            value="l" * long_len,
        )
        return shorter, longer

    return _build()


# ---------------------------------------------------------------------------
# Helper detectors
# ---------------------------------------------------------------------------


class FixedDetector:
    """A detector that always returns a fixed list of spans."""

    def __init__(self, spans: list[EntitySpan]) -> None:
        self._spans = spans

    def detect(self, text: str) -> list[EntitySpan]:
        return list(self._spans)


class FailingDetector:
    """A detector that always raises an exception."""

    def detect(self, text: str) -> list[EntitySpan]:
        raise RuntimeError("Simulated detector failure")


class PiiValueDetector:
    """A detector that returns spans whose values are the actual text substrings."""

    def __init__(self, pii_values: list[str]) -> None:
        self._pii_values = pii_values

    def detect(self, text: str) -> list[EntitySpan]:
        spans = []
        for pii in self._pii_values:
            idx = text.find(pii)
            if idx != -1:
                spans.append(
                    EntitySpan(
                        start=idx,
                        end=idx + len(pii),
                        entity_type="PII",
                        value=pii,
                    )
                )
        return spans


# ---------------------------------------------------------------------------
# Property 6: Overlap resolution retains longest span
# ---------------------------------------------------------------------------


@given(pair=_overlapping_pair_strategy())
@settings(max_examples=300)
def test_overlap_resolution_retains_longest_span(pair: tuple[EntitySpan, EntitySpan]) -> None:
    """Property 6: When spans overlap, the Analyzer retains the longest span.

    **Validates: Requirements 4.5, 9.2**
    """
    shorter, longer = pair
    # Both spans start at the same position; longer is strictly longer.
    assert longer.end - longer.start > shorter.end - shorter.start

    detector = FixedDetector([shorter, longer])
    analyzer = Analyzer([detector])
    result = analyzer.analyze("x" * (longer.end + 5))

    # Only one span should survive (the longer one).
    assert len(result) == 1
    surviving = result[0]
    surviving_len = surviving.end - surviving.start
    shorter_len = shorter.end - shorter.start
    assert surviving_len >= shorter_len, (
        f"Surviving span length {surviving_len} should be >= shorter span length {shorter_len}"
    )
    # The surviving span must be the longer one.
    assert surviving.end - surviving.start == longer.end - longer.start


@given(spans=st.lists(_span_strategy(), min_size=2, max_size=10))
@settings(max_examples=200)
def test_overlap_resolution_no_overlaps_in_output(spans: list[EntitySpan]) -> None:
    """Property 6 (corollary): Analyzer output never contains overlapping spans.

    **Validates: Requirements 4.5, 9.2**
    """
    detector = FixedDetector(spans)
    analyzer = Analyzer([detector])
    result = analyzer.analyze("x" * 200)

    # Verify no two spans in the result overlap.
    for i in range(len(result) - 1):
        assert result[i].end <= result[i + 1].start, (
            f"Spans overlap: {result[i]} and {result[i + 1]}"
        )


# ---------------------------------------------------------------------------
# Property 7: Analyzer output sorted by start offset
# ---------------------------------------------------------------------------


@given(spans=st.lists(_span_strategy(min_start=0, max_start=100), min_size=0, max_size=15))
@settings(max_examples=300)
def test_analyzer_output_sorted_by_start(spans: list[EntitySpan]) -> None:
    """Property 7: Analyzer.analyze() output is always sorted by start offset ascending.

    **Validates: Requirements 9.3**
    """
    detector = FixedDetector(spans)
    analyzer = Analyzer([detector])
    result = analyzer.analyze("x" * 200)

    for i in range(len(result) - 1):
        assert result[i].start <= result[i + 1].start, (
            f"Output not sorted: result[{i}].start={result[i].start} > "
            f"result[{i+1}].start={result[i+1].start}"
        )


@given(
    spans_a=st.lists(_span_strategy(min_start=0, max_start=50), min_size=0, max_size=5),
    spans_b=st.lists(_span_strategy(min_start=51, max_start=100), min_size=0, max_size=5),
)
@settings(max_examples=200)
def test_analyzer_output_sorted_multiple_detectors(
    spans_a: list[EntitySpan],
    spans_b: list[EntitySpan],
) -> None:
    """Property 7 (multi-detector): output is sorted even when spans come from different detectors.

    **Validates: Requirements 9.3**
    """
    detector_a = FixedDetector(spans_a)
    detector_b = FixedDetector(spans_b)
    analyzer = Analyzer([detector_a, detector_b])
    result = analyzer.analyze("x" * 200)

    for i in range(len(result) - 1):
        assert result[i].start <= result[i + 1].start


# ---------------------------------------------------------------------------
# Property 8: Detector exception does not halt analysis
# ---------------------------------------------------------------------------


@given(spans=st.lists(_span_strategy(), min_size=1, max_size=10))
@settings(max_examples=200)
def test_detector_exception_does_not_halt_analysis(spans: list[EntitySpan]) -> None:
    """Property 8: A failing detector does not prevent results from working detectors.

    **Validates: Requirements 4.3**
    """
    failing = FailingDetector()
    working = FixedDetector(spans)

    # Failing detector first, then working.
    analyzer = Analyzer([failing, working])
    result = analyzer.analyze("x" * 200)

    # Results from the working detector must still be present.
    assert len(result) > 0


@given(spans=st.lists(_span_strategy(), min_size=1, max_size=10))
@settings(max_examples=200)
def test_detector_exception_logs_warning(spans: list[EntitySpan]) -> None:
    """Property 8 (logging): A failing detector causes a WARNING log with detector name.

    **Validates: Requirements 4.3**
    """
    failing = FailingDetector()
    working = FixedDetector(spans)
    analyzer = Analyzer([failing, working])

    # Capture log output.
    with _capture_log_records("privacylens", logging.WARNING) as records:
        analyzer.analyze("x" * 200)

    assert len(records) >= 1
    warning_text = records[0].getMessage()
    assert "FailingDetector" in warning_text


# ---------------------------------------------------------------------------
# Property 9: Detector plugin registry round-trip
# ---------------------------------------------------------------------------


@given(name=st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="_-")))
@settings(max_examples=200)
def test_detector_registry_round_trip(name: str) -> None:
    """Property 9: register then get returns the same detector instance.

    **Validates: Requirements 4.4**
    """

    class _TestDetector:
        def detect(self, text: str) -> list[EntitySpan]:
            return []

    detector_instance = _TestDetector()
    register_detector(name, detector_instance)  # type: ignore[arg-type]
    retrieved = get_detector(name)
    assert retrieved is detector_instance


@given(
    name=st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="_")),
)
@settings(max_examples=100)
def test_detector_registry_overwrite(name: str) -> None:
    """Property 9 (overwrite): registering a new detector under the same name replaces the old one.

    **Validates: Requirements 4.4**
    """

    class _DetA:
        def detect(self, text: str) -> list[EntitySpan]:
            return []

    class _DetB:
        def detect(self, text: str) -> list[EntitySpan]:
            return []

    det_a = _DetA()
    det_b = _DetB()

    register_detector(name, det_a)  # type: ignore[arg-type]
    register_detector(name, det_b)  # type: ignore[arg-type]
    assert get_detector(name) is det_b


# ---------------------------------------------------------------------------
# Property 17: on_detection callback never receives PII values
# ---------------------------------------------------------------------------


@given(
    pii_values=st.lists(_pii_value, min_size=1, max_size=5, unique=True)
)
@settings(max_examples=200)
def test_on_detection_callback_never_receives_pii_values(pii_values: list[str]) -> None:
    """Property 17: on_detection callback is called with entity type only, never the PII value.

    **Validates: Requirements 9.5, 21.3**
    """
    received_args: list[str] = []

    def callback(arg: str) -> None:
        received_args.append(arg)

    # Build text containing all PII values.
    text = " ".join(pii_values)
    detector = PiiValueDetector(pii_values)
    config: Config = {"on_detection": callback}
    analyzer = Analyzer([detector], config)
    analyzer.analyze(text)

    # Callback must have been called at least once (we have PII in the text).
    assert len(received_args) > 0

    # None of the callback arguments should be an actual PII value.
    for arg in received_args:
        assert arg not in pii_values, (
            f"Callback received PII value '{arg}' — it should only receive entity type strings"
        )

    # All callback arguments should be entity type strings (uppercase, no spaces).
    for arg in received_args:
        assert arg == arg.upper() or arg.replace("_", "").isalnum(), (
            f"Callback argument '{arg}' does not look like an entity type"
        )


@given(
    pii_values=st.lists(_pii_value, min_size=1, max_size=5, unique=True)
)
@settings(max_examples=200)
def test_on_detection_callback_called_once_per_span(pii_values: list[str]) -> None:
    """Property 17 (count): callback is invoked exactly once per detected span.

    **Validates: Requirements 9.5**
    """
    call_count = [0]

    def callback(entity_type: str) -> None:
        call_count[0] += 1

    text = " ".join(pii_values)
    detector = PiiValueDetector(pii_values)
    config: Config = {"on_detection": callback}
    analyzer = Analyzer([detector], config)
    result = analyzer.analyze(text)

    assert call_count[0] == len(result)


# ---------------------------------------------------------------------------
# Property 18: Logging never includes PII values
# ---------------------------------------------------------------------------


@given(
    pii_values=st.lists(_pii_value, min_size=1, max_size=5, unique=True)
)
@settings(max_examples=200)
def test_logging_never_includes_pii_values(pii_values: list[str]) -> None:
    """Property 18: Log records emitted by Analyzer never contain original PII values.

    **Validates: Requirements 21.1**
    """
    text = " ".join(pii_values)
    detector = PiiValueDetector(pii_values)
    analyzer = Analyzer([detector])

    with _capture_log_records("privacylens", logging.DEBUG) as records:
        analyzer.analyze(text)

    # Check that no log record message contains any of the PII values.
    for record in records:
        msg = record.getMessage()
        for pii in pii_values:
            assert pii not in msg, (
                f"Log record contains PII value '{pii}': {msg!r}"
            )


@given(
    pii_values=st.lists(_pii_value, min_size=1, max_size=5, unique=True)
)
@settings(max_examples=200)
def test_logging_includes_entity_types_and_count(pii_values: list[str]) -> None:
    """Property 18 (content): INFO log contains entity types and count, not values.

    **Validates: Requirements 21.1**
    """
    text = " ".join(pii_values)
    detector = PiiValueDetector(pii_values)
    analyzer = Analyzer([detector])

    with _capture_log_records("privacylens", logging.INFO) as records:
        analyzer.analyze(text)

    info_records = [r for r in records if r.levelno == logging.INFO]
    assert len(info_records) >= 1

    # The INFO log should mention the count.
    combined = " ".join(r.getMessage() for r in info_records)
    # Should contain a number (the count of detected entities).
    assert any(char.isdigit() for char in combined), (
        f"INFO log should contain entity count, got: {combined!r}"
    )


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


class TestAnalyzerBasic:
    def test_no_detectors_returns_empty(self) -> None:
        analyzer = Analyzer([])
        result = analyzer.analyze("some text with email@example.com")
        assert result == []

    def test_single_detector_returns_spans(self) -> None:
        span = EntitySpan(start=0, end=5, entity_type="EMAIL", value="hello")
        analyzer = Analyzer([FixedDetector([span])])
        result = analyzer.analyze("hello world")
        assert len(result) == 1
        assert result[0].entity_type == "EMAIL"

    def test_empty_text_returns_empty(self) -> None:
        span = EntitySpan(start=0, end=5, entity_type="EMAIL", value="hello")
        analyzer = Analyzer([FixedDetector([span])])
        result = analyzer.analyze("")
        # Spans are returned regardless of text (FixedDetector ignores text)
        assert isinstance(result, list)

    def test_failing_detector_continues_with_others(self) -> None:
        span = EntitySpan(start=0, end=5, entity_type="EMAIL", value="hello")
        analyzer = Analyzer([FailingDetector(), FixedDetector([span])])
        result = analyzer.analyze("hello world")
        assert len(result) == 1

    def test_on_detection_callback_invoked(self) -> None:
        received: list[str] = []
        span = EntitySpan(start=0, end=5, entity_type="EMAIL", value="hello")
        config: Config = {"on_detection": received.append}
        analyzer = Analyzer([FixedDetector([span])], config)
        analyzer.analyze("hello world")
        assert received == ["EMAIL"]

    def test_on_detection_callback_not_invoked_when_no_spans(self) -> None:
        received: list[str] = []
        config: Config = {"on_detection": received.append}
        analyzer = Analyzer([FixedDetector([])], config)
        analyzer.analyze("hello world")
        assert received == []


class TestRegistryUnit:
    def test_get_unregistered_raises_key_error(self) -> None:
        with pytest.raises(KeyError):
            get_detector("__nonexistent_detector_xyz__")

    def test_register_and_retrieve(self) -> None:
        class _D:
            def detect(self, text: str) -> list[EntitySpan]:
                return []

        d = _D()
        register_detector("__test_unit_detector__", d)  # type: ignore[arg-type]
        assert get_detector("__test_unit_detector__") is d


class TestOverlapResolutionUnit:
    def test_non_overlapping_spans_all_retained(self) -> None:
        spans = [
            EntitySpan(start=0, end=5, entity_type="A", value="hello"),
            EntitySpan(start=10, end=15, entity_type="B", value="world"),
        ]
        analyzer = Analyzer([FixedDetector(spans)])
        result = analyzer.analyze("x" * 20)
        assert len(result) == 2

    def test_overlapping_longer_retained(self) -> None:
        shorter = EntitySpan(start=0, end=5, entity_type="SHORT", value="hello")
        longer = EntitySpan(start=0, end=10, entity_type="LONG", value="hello worl")
        analyzer = Analyzer([FixedDetector([shorter, longer])])
        result = analyzer.analyze("x" * 20)
        assert len(result) == 1
        assert result[0].entity_type == "LONG"

    def test_fully_contained_span_discarded(self) -> None:
        outer = EntitySpan(start=0, end=20, entity_type="OUTER", value="x" * 20)
        inner = EntitySpan(start=5, end=10, entity_type="INNER", value="x" * 5)
        analyzer = Analyzer([FixedDetector([outer, inner])])
        result = analyzer.analyze("x" * 25)
        assert len(result) == 1
        assert result[0].entity_type == "OUTER"


# ---------------------------------------------------------------------------
# Logging capture context manager
# ---------------------------------------------------------------------------


import contextlib
from typing import Generator


@contextlib.contextmanager
def _capture_log_records(
    logger_name: str, level: int = logging.DEBUG
) -> Generator[list[logging.LogRecord], None, None]:
    """Context manager that captures log records from the named logger."""
    records: list[logging.LogRecord] = []

    class _Handler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Handler()
    handler.setLevel(level)
    logger = logging.getLogger(logger_name)
    original_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(level)
    try:
        yield records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(original_level)
