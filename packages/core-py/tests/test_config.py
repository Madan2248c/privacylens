"""Tests for configuration loading (Tasks 3.6 – 3.9).

Property tests:
  - Property 2: config priority merge
  - Property 3: schema validation rejects invalid configs
  - Property 22: config round-trip (parse -> serialize -> parse)

Unit tests:
  - FileNotFoundError for missing config= path
  - Default config when no sources present
  - Schema violation raises ValueError
"""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator

import pytest
import yaml
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from privacylens.core.config import dump_config, load_config
from privacylens.core.models import Config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@contextmanager
def isolated_dir() -> Generator[Path, None, None]:
    """Create a temp dir and chdir into it, restoring cwd on exit."""
    original = os.getcwd()
    with tempfile.TemporaryDirectory() as td:
        os.chdir(td)
        try:
            yield Path(td)
        finally:
            os.chdir(original)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_VAULT_VALUES = st.sampled_from(["memory", "redis", "sqlite"])

_VERSION_ST = st.text(
    alphabet=st.characters(
        whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters=".-_"
    ),
    min_size=1,
    max_size=20,
)

_DETECTOR_NAME_ST = st.text(
    alphabet=st.characters(whitelist_categories=("Ll",), whitelist_characters="_"),
    min_size=1,
    max_size=20,
)


def _detector_config_st() -> st.SearchStrategy[dict[str, Any]]:
    return st.fixed_dictionaries({"enabled": st.booleans()})


def _config_dict_st() -> st.SearchStrategy[dict[str, Any]]:
    return st.fixed_dictionaries(
        {
            "version": _VERSION_ST,
            "vault": _VAULT_VALUES,
            "detectors": st.dictionaries(
                _DETECTOR_NAME_ST,
                _detector_config_st(),
                min_size=0,
                max_size=3,
            ),
        }
    )


# ---------------------------------------------------------------------------
# Property 2: Config priority merge
# **Validates: Requirements 2.1, 2.2**
# ---------------------------------------------------------------------------


@given(
    kwargs_vault=_VAULT_VALUES,
    file_vault=_VAULT_VALUES,
    cwd_vault=_VAULT_VALUES,
)
@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_config_priority_merge_vault(
    kwargs_vault: str,
    file_vault: str,
    cwd_vault: str,
) -> None:
    """Property 2: kwargs override file, which overrides cwd YAML, for vault key.

    **Validates: Requirements 2.1, 2.2**
    """
    with isolated_dir() as tmp:
        (tmp / "privacylens.yaml").write_text(
            yaml.dump({"vault": cwd_vault}), encoding="utf-8"
        )
        config_file = tmp / "explicit.yaml"
        config_file.write_text(yaml.dump({"vault": file_vault}), encoding="utf-8")

        # kwargs beat everything
        result = load_config(config=str(config_file), vault=kwargs_vault)
        assert result["vault"] == kwargs_vault

        # file beats cwd YAML
        result2 = load_config(config=str(config_file))
        assert result2["vault"] == file_vault

        # cwd YAML only
        result3 = load_config()
        assert result3["vault"] == cwd_vault


@given(
    kwargs_version=_VERSION_ST,
    file_version=_VERSION_ST,
)
@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_config_priority_merge_version(
    kwargs_version: str,
    file_version: str,
) -> None:
    """Property 2: kwargs version overrides file version.

    **Validates: Requirements 2.1, 2.2**
    """
    with isolated_dir() as tmp:
        config_file = tmp / "cfg.yaml"
        config_file.write_text(
            yaml.dump({"version": file_version}), encoding="utf-8"
        )

        result = load_config(config=str(config_file), version=kwargs_version)
        assert result["version"] == kwargs_version

        result2 = load_config(config=str(config_file))
        assert result2["version"] == file_version


# ---------------------------------------------------------------------------
# Property 3: Schema validation rejects invalid configs
# **Validates: Requirements 2.5**
# ---------------------------------------------------------------------------


@given(
    bad_vault=st.text(
        alphabet=st.characters(whitelist_categories=("Ll",)),
        min_size=1,
        max_size=20,
    ).filter(lambda v: v not in ("memory", "redis", "sqlite"))
)
@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_schema_rejects_invalid_vault(bad_vault: str) -> None:
    """Property 3: vault values not in enum raise ValueError.

    **Validates: Requirements 2.5**
    """
    with isolated_dir():
        with pytest.raises(ValueError, match="schema violation"):
            load_config(vault=bad_vault)


@given(
    extra_key=st.text(
        alphabet=st.characters(whitelist_categories=("Ll",)),
        min_size=1,
        max_size=20,
    ).filter(
        lambda k: k not in ("version", "detectors", "vault", "on_detection", "config")
    )
)
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_schema_rejects_unknown_fields(extra_key: str) -> None:
    """Property 3: unknown top-level fields raise ValueError (additionalProperties: false).

    **Validates: Requirements 2.5**
    """
    with isolated_dir():
        with pytest.raises(ValueError, match="schema violation"):
            load_config(**{extra_key: "some_value"})


# ---------------------------------------------------------------------------
# Property 22: Config round-trip (parse -> serialize -> parse)
# **Validates: Requirements 23.4**
# ---------------------------------------------------------------------------


@given(cfg_dict=_config_dict_st())
@settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_config_roundtrip(cfg_dict: dict[str, Any]) -> None:
    """Property 22: load_config(**dump_config_as_dict(c)) produces equivalent Config.

    **Validates: Requirements 23.4**
    """
    with isolated_dir() as tmp:
        original: Config = load_config(**cfg_dict)

        yaml_str = dump_config(original)
        config_file = tmp / "roundtrip.yaml"
        config_file.write_text(yaml_str, encoding="utf-8")

        reloaded: Config = load_config(config=str(config_file))

        assert reloaded["version"] == original["version"]
        assert reloaded["vault"] == original["vault"]
        assert reloaded.get("detectors") == original.get("detectors")


# ---------------------------------------------------------------------------
# Unit tests (Task 3.9)
# ---------------------------------------------------------------------------


class TestMissingFileError:
    def test_missing_config_file_raises_file_not_found(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        missing = str(tmp_path / "does_not_exist.yaml")
        with pytest.raises(FileNotFoundError, match="does_not_exist.yaml"):
            load_config(config=missing)

    def test_error_message_contains_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        path_str = str(tmp_path / "missing_config.json")
        with pytest.raises(FileNotFoundError) as exc_info:
            load_config(config=path_str)
        assert "missing_config.json" in str(exc_info.value)


class TestDefaultConfig:
    def test_default_config_no_sources(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        cfg = load_config()
        assert cfg["vault"] == "memory"
        assert cfg["version"] == "1"
        assert "regex" in cfg["detectors"]  # type: ignore[operator]
        assert cfg["detectors"]["regex"]["enabled"] is True  # type: ignore[index]

    def test_default_vault_is_memory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        cfg = load_config()
        assert cfg["vault"] == "memory"

    def test_default_enables_regex_detector(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        cfg = load_config()
        detectors = cfg.get("detectors", {})
        assert "regex" in detectors
        assert detectors["regex"].get("enabled") is True  # type: ignore[union-attr]


class TestSchemaViolation:
    def test_invalid_vault_raises_value_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        with pytest.raises(ValueError, match="schema violation"):
            load_config(vault="invalid_backend")

    def test_unknown_top_level_field_raises_value_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        with pytest.raises(ValueError, match="schema violation"):
            load_config(unknown_field="oops")

    def test_valid_config_does_not_raise(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        cfg = load_config(vault="redis", version="2")
        assert cfg["vault"] == "redis"


class TestYamlAndJsonParsing:
    def test_load_yaml_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        cfg_file = tmp_path / "cfg.yaml"
        cfg_file.write_text(
            yaml.dump({"vault": "sqlite", "version": "2"}), encoding="utf-8"
        )
        cfg = load_config(config=str(cfg_file))
        assert cfg["vault"] == "sqlite"
        assert cfg["version"] == "2"

    def test_load_json_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        cfg_file = tmp_path / "cfg.json"
        cfg_file.write_text(
            json.dumps({"vault": "redis", "version": "3"}), encoding="utf-8"
        )
        cfg = load_config(config=str(cfg_file))
        assert cfg["vault"] == "redis"
        assert cfg["version"] == "3"

    def test_cwd_yaml_is_loaded(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "privacylens.yaml").write_text(
            yaml.dump({"vault": "sqlite"}), encoding="utf-8"
        )
        cfg = load_config()
        assert cfg["vault"] == "sqlite"


class TestDumpConfig:
    def test_dump_produces_valid_yaml(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        cfg = load_config(vault="redis", version="2")
        yaml_str = dump_config(cfg)
        parsed = yaml.safe_load(yaml_str)
        assert parsed["vault"] == "redis"
        assert parsed["version"] == "2"

    def test_dump_excludes_on_detection(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        cfg = load_config(on_detection=lambda t: None)
        yaml_str = dump_config(cfg)
        assert "on_detection" not in yaml_str
