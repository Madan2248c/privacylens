"""Task 22.1 — Zero-dependency validation for the Python core package.

Validates: Requirement 22.1
"""

from __future__ import annotations

import subprocess
import sys


_FORBIDDEN_MODULES = ["spacy", "transformers", "torch", "redis"]

_CHECK_SCRIPT = """
import sys
import privacylens  # noqa: F401 — trigger all top-level imports

# Also import every core and adapter module explicitly
import privacylens.core.models
import privacylens.core.config
import privacylens.core.normalize
import privacylens.core.analyzer
import privacylens.core.tokenizer
import privacylens.core.detokenizer
import privacylens.core.vault
import privacylens.adapters.openai
import privacylens.adapters.anthropic
import privacylens.adapters.langchain
import privacylens.adapters.crewai
import privacylens.adapters.strands

forbidden = {name for name in sys.modules if name in {forbidden_set}}
if forbidden:
    print("FORBIDDEN MODULES LOADED:", forbidden, file=sys.stderr)
    sys.exit(1)
sys.exit(0)
"""


def test_core_import_does_not_load_ml_libraries() -> None:
    """Importing privacylens core must not pull in spacy, transformers, torch, or redis.

    Runs in a fresh subprocess to avoid contamination from the test runner.
    """
    script = _CHECK_SCRIPT.replace("{forbidden_set}", repr(set(_FORBIDDEN_MODULES)))

    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, (
        f"Forbidden ML modules were loaded when importing privacylens core.\n"
        f"stderr: {result.stderr}\n"
        f"stdout: {result.stdout}"
    )
