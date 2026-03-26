"""Configuration loading for PrivacyLens.

Priority order (highest to lowest):
1. Keyword arguments passed to load_config()
2. File path passed as config= argument (YAML or JSON)
3. privacylens.yaml in current working directory
4. Built-in defaults
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from privacylens.core.models import Config

# Locate schema relative to this file: packages/core-py/src/privacylens/core/config.py
# Go up: core/ -> privacylens/ -> src/ -> core-py/ -> packages/ -> workspace root
_SCHEMA_PATH = Path(__file__).parents[5] / "privacylens.schema.json"

_DEFAULT_CONFIG: dict[str, Any] = {
    "version": "1",
    "detectors": {
        "regex": {"enabled": True},
    },
    "vault": "memory",
    "on_detection": None,
}


def _load_file(path: str | Path) -> dict[str, Any]:
    """Load a YAML or JSON file into a dict."""
    path = Path(path)
    suffix = path.suffix.lower()
    with open(path) as f:
        if suffix in (".yaml", ".yml"):
            import yaml  # type: ignore[import-untyped]

            return yaml.safe_load(f) or {}
        elif suffix == ".json":
            return json.load(f)
        else:
            # Default: try YAML (superset of JSON)
            import yaml  # type: ignore[import-untyped]

            return yaml.safe_load(f) or {}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge *override* into *base*, returning a new dict.

    Nested dicts are merged recursively; all other values are replaced.
    """
    result = copy.deepcopy(base)
    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _validate_schema(config: dict[str, Any]) -> None:
    """Validate *config* against privacylens.schema.json.

    Silently skips validation if jsonschema is not installed.
    Raises ValueError with a descriptive message on schema violations.
    """
    try:
        import jsonschema  # type: ignore[import-untyped]
    except ImportError:
        return  # validation is best-effort when jsonschema is absent

    schema_path = _SCHEMA_PATH
    if not schema_path.exists():
        # Fallback: look in cwd
        schema_path = Path("privacylens.schema.json")

    if not schema_path.exists():
        return  # no schema file found — skip validation

    with open(schema_path) as f:
        schema = json.load(f)

    # Strip non-serialisable fields before validation
    serialisable = {k: v for k, v in config.items() if k != "on_detection"}

    try:
        jsonschema.validate(serialisable, schema)
    except jsonschema.ValidationError as exc:
        raise ValueError(f"Config schema violation: {exc.message}") from exc


def load_config(**kwargs: Any) -> Config:
    """Load and merge configuration from all sources.

    Priority (highest first):
      1. *kwargs* passed directly
      2. File at ``config=`` path (YAML or JSON)
      3. ``privacylens.yaml`` in the current working directory
      4. Built-in defaults

    Raises:
        FileNotFoundError: if a ``config=`` path is given but does not exist.
        ValueError: if the merged config violates the JSON Schema.
    """
    # Start from defaults
    config: dict[str, Any] = copy.deepcopy(_DEFAULT_CONFIG)

    # Layer 3 (lowest after defaults): privacylens.yaml in cwd
    cwd_yaml = Path("privacylens.yaml")
    if cwd_yaml.exists():
        file_data = _load_file(cwd_yaml)
        config = _deep_merge(config, file_data)

    # Layer 2: explicit config= file
    kwargs = dict(kwargs)  # mutable copy
    if "config" in kwargs:
        config_path = kwargs.pop("config")
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        file_data = _load_file(path)
        config = _deep_merge(config, file_data)

    # Layer 1 (highest): remaining kwargs
    # Pull out on_detection separately — it's a callable, not serialisable
    on_detection = kwargs.pop("on_detection", None)
    if kwargs:
        config = _deep_merge(config, kwargs)
    if on_detection is not None:
        config["on_detection"] = on_detection

    _validate_schema(config)
    return config  # type: ignore[return-value]


def dump_config(config: Config) -> str:
    """Serialize *config* to a YAML string.

    Non-serialisable fields (``on_detection``) are excluded.
    """
    import yaml  # type: ignore[import-untyped]

    serialisable = {
        k: v
        for k, v in config.items()
        if k != "on_detection" and v is not None
    }
    return yaml.dump(serialisable, default_flow_style=False, sort_keys=True)
