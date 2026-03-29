# Configuration

PrivacyLens is zero-config by default. Drop a `privacylens.yaml` in your project root to customize it.

## Config file

```yaml
# privacylens.yaml
version: "1"

detectors:
  regex:
    enabled: true
    patterns:
      - entity_type: EMPLOYEE_ID
        pattern: 'EMP-\d{4,}'
      - entity_type: PROJECT_CODE
        pattern: 'PROJ-[A-Z]{2,4}-\d{3,}'

vault: memory  # "memory" | "sqlite" | "redis"
```

PrivacyLens looks for `privacylens.yaml` in the **current working directory** when your app starts.

## Priority order

Settings are merged from lowest to highest priority:

| Priority | Source |
|----------|--------|
| 4 (lowest) | Built-in defaults |
| 3 | `privacylens.yaml` in cwd |
| 2 | Explicit file path passed to `shield()` |
| 1 (highest) | Keyword arguments passed directly |

## All options

### `version`

Schema version. Currently always `"1"`.

```yaml
version: "1"
```

---

### `detectors`

Controls which detectors are active and their settings.

```yaml
detectors:
  regex:
    enabled: true          # set false to disable built-in regex
    patterns:              # additional custom patterns (additive)
      - entity_type: MY_ID
        pattern: 'ID-\d{6}'
  pii:
    enabled: true          # requires: pip install privacylens[pii]
  semantic:
    enabled: true          # requires: pip install privacylens[semantic]
```

Custom `patterns` are **additive** — they extend the built-in EMAIL, PHONE, SSN patterns rather than replacing them.

---

### `vault`

Where token↔value mappings are stored within a session.

| Value | Description |
|-------|-------------|
| `memory` | In-process dict. Default. Lost when process exits. |
| `sqlite` | Persisted to a local SQLite file. |
| `redis` | Stored in Redis. Requires `pip install privacylens[redis]`. |

```yaml
vault: sqlite
sqlite_path: /tmp/privacylens.db   # optional, default: privacylens.db

# or
vault: redis
redis_url: redis://localhost:6379  # optional, default shown
```

---

## Passing config in code

### Python

```python
from privacylens import shield
import openai

# Pass a file path
client = shield(openai.OpenAI(), config="path/to/privacylens.yaml")

# Pass options directly (highest priority)
client = shield(openai.OpenAI(), vault="sqlite", detectors={"regex": {"enabled": True}})
```

### TypeScript

```typescript
import { shield, loadConfig } from "privacylens";
import OpenAI from "openai";

// Pass a config file path
const client = shield(new OpenAI(), loadConfig({ configPath: "privacylens.yaml" }));

// Pass overrides directly
const client = shield(new OpenAI(), loadConfig({
  overrides: { vault: "memory" }
}));
```

---

## on_detection callback (Python only)

Get notified when PII is detected — useful for logging entity types (never log values).

```python
def on_detection(entity_type: str) -> None:
    print(f"Masked: {entity_type}")  # e.g. "Masked: EMAIL"

client = shield(openai.OpenAI(), on_detection=on_detection)
```

> **Never log the actual PII value** — only the entity type is passed to the callback.

---

## JSON Schema

The config file is validated against [`privacylens.schema.json`](../privacylens.schema.json) at load time. Invalid configs raise a `ValueError` with a descriptive message.
