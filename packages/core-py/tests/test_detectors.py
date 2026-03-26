"""Tests for the RegexDetector.

Covers Properties 10 and 11 from the design document, plus unit tests for
specific format examples and edge cases.
"""

from __future__ import annotations

import re

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from privacylens.detectors.regex import RegexDetector
from privacylens.core.models import EntitySpan


# ---------------------------------------------------------------------------
# Strategies for generating valid PII strings
# ---------------------------------------------------------------------------

# EMAIL: local@domain.tld
_local_part = st.from_regex(r"[a-zA-Z0-9._%+\-]{1,20}", fullmatch=True)
_domain_label = st.from_regex(r"[a-zA-Z0-9][a-zA-Z0-9\-]{0,10}[a-zA-Z0-9]", fullmatch=True)
_tld = st.from_regex(r"[a-zA-Z]{2,6}", fullmatch=True)

_email = st.builds(
    lambda local, domain, tld: f"{local}@{domain}.{tld}",
    local=_local_part,
    domain=_domain_label,
    tld=_tld,
)

# PHONE: three formats — use explicit ASCII digit ranges to avoid Unicode digits
_three_digits = st.from_regex(r"[2-9][0-9]{2}", fullmatch=True)  # area code can't start with 0/1
_four_digits = st.from_regex(r"[0-9]{4}", fullmatch=True)

_phone_paren = st.builds(
    lambda area, mid, last: f"({area}) {mid}-{last}",
    area=_three_digits,
    mid=_three_digits,
    last=_four_digits,
)
_phone_dash = st.builds(
    lambda area, mid, last: f"{area}-{mid}-{last}",
    area=_three_digits,
    mid=_three_digits,
    last=_four_digits,
)
_phone_plus1 = st.builds(
    lambda area, mid, last: f"+1{area}{mid}{last}",
    area=_three_digits,
    mid=_three_digits,
    last=_four_digits,
)
_phone = st.one_of(_phone_paren, _phone_dash, _phone_plus1)

# SSN: NNN-NN-NNNN (use integer ranges — format strings produce ASCII digits only)
_ssn = st.builds(
    lambda a, b, c: f"{a:03d}-{b:02d}-{c:04d}",
    a=st.integers(min_value=100, max_value=999),
    b=st.integers(min_value=10, max_value=99),
    c=st.integers(min_value=1000, max_value=9999),
)

# Surrounding noise text (no @, -, digits that could form PII on their own)
_noise = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll"), whitelist_characters=" "),
    min_size=0,
    max_size=30,
)


def _embed(pii: str, prefix: str, suffix: str) -> str:
    """Embed a PII value between prefix and suffix noise."""
    return f"{prefix} {pii} {suffix}"


# ---------------------------------------------------------------------------
# Property 10: RegexDetector detects built-in PII patterns
# ---------------------------------------------------------------------------


@given(email=_email, prefix=_noise, suffix=_noise)
@settings(max_examples=300)
def test_property10_detects_email(email: str, prefix: str, suffix: str) -> None:
    """Property 10: For any syntactically valid email, RegexDetector returns at least one span.

    **Validates: Requirements 5.1**
    """
    text = _embed(email, prefix, suffix)
    detector = RegexDetector()
    spans = detector.detect(text)
    email_spans = [s for s in spans if s.entity_type == "EMAIL"]
    assert any(s.value == email for s in email_spans), (
        f"Email '{email}' not detected in text: {text!r}\nSpans: {spans}"
    )


@given(phone=_phone, prefix=_noise, suffix=_noise)
@settings(max_examples=300)
def test_property10_detects_phone(phone: str, prefix: str, suffix: str) -> None:
    """Property 10: For any syntactically valid US phone, RegexDetector returns at least one span.

    **Validates: Requirements 5.1**
    """
    text = _embed(phone, prefix, suffix)
    detector = RegexDetector()
    spans = detector.detect(text)
    phone_spans = [s for s in spans if s.entity_type == "PHONE"]
    assert any(s.value == phone for s in phone_spans), (
        f"Phone '{phone}' not detected in text: {text!r}\nSpans: {spans}"
    )


@given(ssn=_ssn, prefix=_noise, suffix=_noise)
@settings(max_examples=300)
def test_property10_detects_ssn(ssn: str, prefix: str, suffix: str) -> None:
    """Property 10: For any syntactically valid SSN, RegexDetector returns at least one span.

    **Validates: Requirements 5.1**
    """
    text = _embed(ssn, prefix, suffix)
    detector = RegexDetector()
    spans = detector.detect(text)
    ssn_spans = [s for s in spans if s.entity_type == "SSN"]
    assert any(s.value == ssn for s in ssn_spans), (
        f"SSN '{ssn}' not detected in text: {text!r}\nSpans: {spans}"
    )


# ---------------------------------------------------------------------------
# Property 11: Custom patterns are additive
# ---------------------------------------------------------------------------

_custom_entity_type = st.from_regex(r"[A-Z][A-Z0-9_]{1,19}", fullmatch=True)
# A simple word-like custom pattern value
_custom_value = st.from_regex(r"CUSTOM[A-Z]{3,8}", fullmatch=True)


@given(
    entity_type=_custom_entity_type,
    custom_value=_custom_value,
    email=_email,
    prefix=_noise,
    suffix=_noise,
)
@settings(max_examples=200)
def test_property11_custom_patterns_additive(
    entity_type: str,
    custom_value: str,
    email: str,
    prefix: str,
    suffix: str,
) -> None:
    """Property 11: Custom patterns are additive — built-in patterns still fire.

    For any custom pattern entry added to RegexDetector config, the detector
    SHALL return spans for text matching that pattern IN ADDITION TO all
    built-in pattern matches.

    **Validates: Requirements 5.2**
    """
    # Build a text that contains both the custom value and a built-in email.
    text = f"{prefix} {custom_value} {email} {suffix}"

    # Escape the custom value to use as a literal regex pattern.
    custom_pattern = re.escape(custom_value)

    detector = RegexDetector(
        config={"patterns": [{"entity_type": entity_type, "pattern": custom_pattern}]}
    )
    spans = detector.detect(text)

    # Custom entity must be detected.
    custom_spans = [s for s in spans if s.entity_type == entity_type and s.value == custom_value]
    assert len(custom_spans) >= 1, (
        f"Custom pattern '{custom_pattern}' not detected in text: {text!r}\nSpans: {spans}"
    )

    # Built-in EMAIL must also be detected.
    email_spans = [s for s in spans if s.entity_type == "EMAIL" and s.value == email]
    assert len(email_spans) >= 1, (
        f"Built-in EMAIL '{email}' not detected when custom pattern present.\nSpans: {spans}"
    )


# ---------------------------------------------------------------------------
# Unit tests: specific format examples
# ---------------------------------------------------------------------------


class TestEmailFormats:
    def test_simple_email(self) -> None:
        spans = RegexDetector().detect("Contact user@example.com for info.")
        emails = [s for s in spans if s.entity_type == "EMAIL"]
        assert len(emails) == 1
        assert emails[0].value == "user@example.com"

    def test_email_span_offsets_match_text(self) -> None:
        text = "Email: user@example.com end"
        spans = RegexDetector().detect(text)
        emails = [s for s in spans if s.entity_type == "EMAIL"]
        assert len(emails) == 1
        span = emails[0]
        assert text[span.start:span.end] == span.value


class TestPhoneFormats:
    def test_paren_format(self) -> None:
        spans = RegexDetector().detect("Call (555) 555-5555 now.")
        phones = [s for s in spans if s.entity_type == "PHONE"]
        assert any(s.value == "(555) 555-5555" for s in phones)

    def test_dash_format(self) -> None:
        spans = RegexDetector().detect("Call 555-555-5555 now.")
        phones = [s for s in spans if s.entity_type == "PHONE"]
        assert any(s.value == "555-555-5555" for s in phones)

    def test_plus1_format(self) -> None:
        spans = RegexDetector().detect("Call +15555555555 now.")
        phones = [s for s in spans if s.entity_type == "PHONE"]
        assert any(s.value == "+15555555555" for s in phones)

    def test_phone_span_offsets_match_text(self) -> None:
        text = "Phone: 555-555-5555 end"
        spans = RegexDetector().detect(text)
        phones = [s for s in spans if s.entity_type == "PHONE"]
        assert len(phones) == 1
        span = phones[0]
        assert text[span.start:span.end] == span.value


class TestSSNFormats:
    def test_ssn_format(self) -> None:
        spans = RegexDetector().detect("SSN: 123-45-6789")
        ssns = [s for s in spans if s.entity_type == "SSN"]
        assert any(s.value == "123-45-6789" for s in ssns)

    def test_ssn_span_offsets_match_text(self) -> None:
        text = "SSN: 123-45-6789 end"
        spans = RegexDetector().detect(text)
        ssns = [s for s in spans if s.entity_type == "SSN"]
        assert len(ssns) == 1
        span = ssns[0]
        assert text[span.start:span.end] == span.value


class TestEmptyResult:
    def test_no_pii_returns_empty_list(self) -> None:
        spans = RegexDetector().detect("Hello, world! No sensitive data here.")
        assert spans == []

    def test_empty_string_returns_empty_list(self) -> None:
        spans = RegexDetector().detect("")
        assert spans == []


class TestCustomPatterns:
    def test_custom_pattern_detected(self) -> None:
        detector = RegexDetector(
            config={"patterns": [{"entity_type": "ACCOUNT", "pattern": r"ACC-\d{6}"}]}
        )
        spans = detector.detect("Account: ACC-123456 is active.")
        accounts = [s for s in spans if s.entity_type == "ACCOUNT"]
        assert len(accounts) == 1
        assert accounts[0].value == "ACC-123456"

    def test_custom_pattern_additive_with_builtins(self) -> None:
        detector = RegexDetector(
            config={"patterns": [{"entity_type": "ACCOUNT", "pattern": r"ACC-\d{6}"}]}
        )
        spans = detector.detect("Email user@example.com, account ACC-123456.")
        entity_types = {s.entity_type for s in spans}
        assert "EMAIL" in entity_types
        assert "ACCOUNT" in entity_types

    def test_no_custom_patterns_key_uses_builtins_only(self) -> None:
        detector = RegexDetector(config={})
        spans = detector.detect("user@example.com")
        assert any(s.entity_type == "EMAIL" for s in spans)

    def test_span_values_match_text_at_offsets(self) -> None:
        text = "user@example.com and 555-555-5555 and 123-45-6789"
        spans = RegexDetector().detect(text)
        for span in spans:
            assert text[span.start:span.end] == span.value, (
                f"Span value mismatch: expected {text[span.start:span.end]!r}, got {span.value!r}"
            )


# ===========================================================================
# PiiDetector tests (Tasks 10.2 and 10.3)
# ===========================================================================

import sys
import types
from unittest.mock import MagicMock, patch

from privacylens.core.models import Detector


# ---------------------------------------------------------------------------
# Helpers: build a fake presidio_analyzer module so we can import PiiDetector
# without the real package installed.
# ---------------------------------------------------------------------------

def _make_fake_presidio(results: list[MagicMock]) -> types.ModuleType:
    """Return a fake ``presidio_analyzer`` module whose AnalyzerEngine returns *results*."""
    fake_engine = MagicMock()
    fake_engine.analyze.return_value = results

    fake_engine_cls = MagicMock(return_value=fake_engine)

    fake_module = types.ModuleType("presidio_analyzer")
    fake_module.AnalyzerEngine = fake_engine_cls  # type: ignore[attr-defined]
    return fake_module


def _make_result(start: int, end: int, entity_type: str) -> MagicMock:
    r = MagicMock()
    r.start = start
    r.end = end
    r.entity_type = entity_type
    return r


# ---------------------------------------------------------------------------
# Property 21: PiiDetector preserves Presidio entity types unchanged
# ---------------------------------------------------------------------------

# hypothesis already imported above (given, settings, st)


_entity_type_st = st.text(
    alphabet=st.characters(whitelist_categories=("Lu",), whitelist_characters="_"),
    min_size=1,
    max_size=30,
)

_presidio_result_st = st.builds(
    lambda entity_type, start: _make_result(start, start + 5, entity_type),
    entity_type=_entity_type_st,
    start=st.integers(min_value=0, max_value=50),
)


@given(results=st.lists(_presidio_result_st, min_size=0, max_size=10))
@settings(max_examples=200)
def test_property21_pii_detector_preserves_entity_types(results: list[MagicMock]) -> None:
    """Property 21: PiiDetector passes Presidio entity_type strings through unchanged.

    **Validates: Requirements 18.3**
    """
    # Build text long enough to cover all result spans
    text = "x" * 100

    fake_presidio = _make_fake_presidio(results)
    with patch.dict(sys.modules, {"presidio_analyzer": fake_presidio}):
        # Re-import to pick up the patched module
        if "privacylens.detectors.pii" in sys.modules:
            del sys.modules["privacylens.detectors.pii"]
        from privacylens.detectors.pii import PiiDetector

        detector = PiiDetector()
        spans = detector.detect(text)

    assert len(spans) == len(results)
    for span, result in zip(spans, results):
        assert span.entity_type == result.entity_type, (
            f"entity_type mismatch: expected {result.entity_type!r}, got {span.entity_type!r}"
        )


# ---------------------------------------------------------------------------
# Unit tests: ImportError and Detector protocol conformance (Task 10.3)
# ---------------------------------------------------------------------------


import builtins as _builtins
_real_import = _builtins.__import__


def _import_blocking_presidio(name: str, *args, **kwargs):
    """Custom __import__ that raises ImportError for presidio_analyzer."""
    if name == "presidio_analyzer":
        raise ImportError("No module named 'presidio_analyzer'")
    return _real_import(name, *args, **kwargs)


class TestPiiDetectorImportError:
    def test_raises_import_error_when_presidio_missing(self) -> None:
        """ImportError with correct message when presidio_analyzer is not installed."""
        # The lazy import lives inside __init__, so we just patch __import__
        # while constructing — no module reload needed.
        from privacylens.detectors.pii import PiiDetector

        with patch("builtins.__import__", side_effect=_import_blocking_presidio):
            with pytest.raises(ImportError, match="Install Presidio: pip install privacylens\\[pii\\]"):
                PiiDetector()

    def test_import_error_message_exact(self) -> None:
        """The ImportError message must be exactly as specified."""
        from privacylens.detectors.pii import PiiDetector

        with patch("builtins.__import__", side_effect=_import_blocking_presidio):
            try:
                PiiDetector()
                pytest.fail("Expected ImportError was not raised")
            except ImportError as exc:
                assert str(exc) == "Install Presidio: pip install privacylens[pii]"


class TestPiiDetectorProtocol:
    def test_conforms_to_detector_protocol(self) -> None:
        """PiiDetector instance satisfies the runtime-checkable Detector protocol."""
        fake_presidio = _make_fake_presidio([])
        sys.modules.pop("privacylens.detectors.pii", None)

        with patch.dict(sys.modules, {"presidio_analyzer": fake_presidio}):
            if "privacylens.detectors.pii" in sys.modules:
                del sys.modules["privacylens.detectors.pii"]
            from privacylens.detectors.pii import PiiDetector

            detector = PiiDetector()
            assert isinstance(detector, Detector)

    def test_detect_returns_list(self) -> None:
        """detect() returns a list (possibly empty)."""
        fake_presidio = _make_fake_presidio([])
        sys.modules.pop("privacylens.detectors.pii", None)

        with patch.dict(sys.modules, {"presidio_analyzer": fake_presidio}):
            if "privacylens.detectors.pii" in sys.modules:
                del sys.modules["privacylens.detectors.pii"]
            from privacylens.detectors.pii import PiiDetector

            detector = PiiDetector()
            result = detector.detect("some text")
            assert isinstance(result, list)

    def test_detect_maps_spans_correctly(self) -> None:
        """detect() maps Presidio results to EntitySpan with correct fields."""
        text = "Hello world test!"
        results = [_make_result(0, 5, "PERSON"), _make_result(6, 11, "LOCATION")]
        fake_presidio = _make_fake_presidio(results)
        sys.modules.pop("privacylens.detectors.pii", None)

        with patch.dict(sys.modules, {"presidio_analyzer": fake_presidio}):
            if "privacylens.detectors.pii" in sys.modules:
                del sys.modules["privacylens.detectors.pii"]
            from privacylens.detectors.pii import PiiDetector

            detector = PiiDetector()
            spans = detector.detect(text)

        assert len(spans) == 2
        assert spans[0].entity_type == "PERSON"
        assert spans[0].value == text[0:5]
        assert spans[1].entity_type == "LOCATION"
        assert spans[1].value == text[6:11]


# ===========================================================================
# SemanticDetector tests (Tasks 11.2)
# ===========================================================================


def _import_blocking_gliner(name: str, *args, **kwargs):
    """Custom __import__ that raises ImportError for gliner."""
    if name == "gliner":
        raise ImportError("No module named 'gliner'")
    return _real_import(name, *args, **kwargs)


def _make_fake_gliner_module() -> types.ModuleType:
    """Return a fake ``gliner`` module with a GLiNER class stub."""
    fake_gliner_cls = MagicMock()
    fake_gliner_cls.from_pretrained = MagicMock(return_value=MagicMock())

    fake_module = types.ModuleType("gliner")
    fake_module.GLiNER = fake_gliner_cls  # type: ignore[attr-defined]
    return fake_module


class TestSemanticDetectorImportError:
    def test_raises_import_error_when_gliner_missing(self) -> None:
        """ImportError with correct message when gliner is not installed."""
        # Remove any cached module so the lazy import fires fresh
        sys.modules.pop("privacylens.detectors.semantic", None)
        sys.modules.pop("gliner", None)

        with patch("builtins.__import__", side_effect=_import_blocking_gliner):
            with pytest.raises(ImportError, match="pip install privacylens\\[semantic\\]"):
                from privacylens.detectors.semantic import SemanticDetector
                SemanticDetector()

    def test_import_error_message_exact(self) -> None:
        """The ImportError message must be exactly as specified."""
        sys.modules.pop("privacylens.detectors.semantic", None)
        sys.modules.pop("gliner", None)

        with patch("builtins.__import__", side_effect=_import_blocking_gliner):
            try:
                from privacylens.detectors.semantic import SemanticDetector
                SemanticDetector()
                pytest.fail("Expected ImportError was not raised")
            except ImportError as exc:
                assert str(exc) == "Install GLiNER: pip install privacylens[semantic]"


class TestSemanticDetectorLazyModelLoading:
    def test_model_is_none_after_init(self) -> None:
        """_model must be None immediately after construction (not loaded at init)."""
        fake_gliner = _make_fake_gliner_module()
        sys.modules.pop("privacylens.detectors.semantic", None)

        with patch.dict(sys.modules, {"gliner": fake_gliner}):
            from privacylens.detectors.semantic import SemanticDetector
            # Reset class-level model in case a previous test loaded it
            SemanticDetector._model = None

            detector = SemanticDetector()
            assert detector._model is None, "_model should not be loaded at __init__ time"

    def test_model_loaded_on_first_detect(self) -> None:
        """_model is populated after the first call to detect()."""
        fake_gliner = _make_fake_gliner_module()
        fake_model_instance = MagicMock()
        fake_model_instance.predict_entities.return_value = []
        fake_gliner.GLiNER.from_pretrained.return_value = fake_model_instance

        sys.modules.pop("privacylens.detectors.semantic", None)

        with patch.dict(sys.modules, {"gliner": fake_gliner}):
            from privacylens.detectors.semantic import SemanticDetector
            SemanticDetector._model = None

            detector = SemanticDetector()
            assert detector._model is None

            detector.detect("Hello, my name is Alice.")

            fake_gliner.GLiNER.from_pretrained.assert_called_once_with("urchade/gliner_medium-v2.1")
            assert SemanticDetector._model is not None


class TestSemanticDetectorProtocol:
    def test_conforms_to_detector_protocol(self) -> None:
        """SemanticDetector instance satisfies the runtime-checkable Detector protocol."""
        fake_gliner = _make_fake_gliner_module()
        sys.modules.pop("privacylens.detectors.semantic", None)

        with patch.dict(sys.modules, {"gliner": fake_gliner}):
            from privacylens.detectors.semantic import SemanticDetector
            SemanticDetector._model = None

            detector = SemanticDetector()
            assert isinstance(detector, Detector)
