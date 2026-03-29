# Writing a Custom Detector

A detector is any class with a single `detect(text)` method. You can add one to PrivacyLens without touching the core library.

## The Detector protocol

### Python

```python
from privacylens.core.models import EntitySpan

class MyDetector:
    def detect(self, text: str) -> list[EntitySpan]:
        ...
```

That's the entire interface. No base class to inherit, no registration decorator.

### TypeScript

```typescript
import type { EntitySpan } from "privacylens";

interface Detector {
  detect(text: string): EntitySpan[];
}
```

---

## Step-by-step example: detecting UK National Insurance numbers

### Python

```python
import re
from privacylens.core.models import EntitySpan

class NINODetector:
    """Detects UK National Insurance numbers (e.g. AB 12 34 56 C)."""

    _RE = re.compile(
        r"\b[A-CEGHJ-PR-TW-Z]{2}\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]\b",
        re.IGNORECASE,
    )

    def detect(self, text: str) -> list[EntitySpan]:
        return [
            EntitySpan(
                start=m.start(),
                end=m.end(),
                entity_type="NINO",
                value=m.group(),
            )
            for m in self._RE.finditer(text)
        ]
```

### TypeScript

```typescript
import { createEntitySpan, type EntitySpan } from "privacylens";

export class NINODetector {
  private readonly re = /\b[A-CEGHJ-PR-TW-Z]{2}\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]\b/gi;

  detect(text: string): EntitySpan[] {
    const spans: EntitySpan[] = [];
    this.re.lastIndex = 0;
    let match: RegExpExecArray | null;
    while ((match = this.re.exec(text)) !== null) {
      spans.push(createEntitySpan(match.index, match.index + match[0].length, "NINO", match[0]));
    }
    return spans;
  }
}
```

---

## Registering your detector

### Python — pass via the Analyzer

```python
from privacylens.core.analyzer import Analyzer
from privacylens.core.pipeline import Pipeline
from privacylens.core.config import load_config

analyzer = Analyzer([NINODetector()], load_config())
```

Or register it on an existing analyzer:

```python
analyzer.register_detector("nino", NINODetector())
```

To use it with `shield()`, build a custom pipeline and pass it to the adapter directly:

```python
from privacylens.adapters.openai import OpenAIAdapter
from privacylens.core.pipeline import Pipeline
from privacylens.core.config import load_config
import openai

pipeline = Pipeline(load_config(), extra_detectors=[NINODetector()])
client = OpenAIAdapter(openai.OpenAI(), pipeline)
```

> **Note:** A cleaner `shield(client, detectors=[...])` API is planned — see [issue #8](https://github.com/Madan2248c/privacylens/issues).

### TypeScript

```typescript
import { Pipeline, loadConfig } from "privacylens";
import { shieldOpenAI } from "privacylens"; // internal export
import OpenAI from "openai";

// Build a pipeline with your custom detector registered
const pipeline = new Pipeline(loadConfig());
pipeline.analyzer.registerDetector("nino", new NINODetector());

const client = shieldOpenAI(new OpenAI(), pipeline);
```

---

## Tips

**Keep `detect()` pure** — no side effects, no I/O. It may be called many times per request.

**Return non-overlapping spans** — if your detector can produce overlapping matches, PrivacyLens will resolve them by keeping the longest span, but it's cleaner to avoid them.

**Use `entity_type` in SCREAMING_SNAKE_CASE** — e.g. `NINO`, `EMPLOYEE_ID`, `PASSPORT_NUMBER`. This is what appears in the token: `[NINO_1]`.

**Lazy-load heavy dependencies** — if your detector uses an ML model, load it in `__init__` or on first call to `detect()`, not at import time.

```python
class MyMLDetector:
    def __init__(self) -> None:
        try:
            import my_ml_lib
        except ImportError:
            raise ImportError("Install my_ml_lib: pip install my-ml-lib")
        self._model = my_ml_lib.load()

    def detect(self, text: str) -> list[EntitySpan]:
        ...
```

---

## Testing your detector

```python
def test_nino_detected():
    detector = NINODetector()
    spans = detector.detect("My NI number is AB 12 34 56 C.")
    assert len(spans) == 1
    assert spans[0].entity_type == "NINO"
    assert spans[0].value == "AB 12 34 56 C"
```
