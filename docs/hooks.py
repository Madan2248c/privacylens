"""MkDocs hook: regenerate llms-full.txt before each build."""

import os
from pathlib import Path


def on_pre_build(config, **kwargs):  # type: ignore[no-untyped-def]
    docs_dir = Path(config["docs_dir"])
    pages = [
        "getting-started.md",
        "configuration.md",
        "detectors.md",
        "adapters.md",
        "writing-a-custom-detector.md",
    ]
    lines = [
        "# PrivacyLens — Full Documentation",
        "",
        "Source: https://madan2248c.github.io/privacylens/",
        "GitHub: https://github.com/Madan2248c/privacylens",
        "",
        "---",
        "",
    ]
    for page in pages:
        path = docs_dir / page
        if path.exists():
            lines.append(path.read_text())
            lines.append("\n---\n")

    (docs_dir / "llms-full.txt").write_text("\n".join(lines))
