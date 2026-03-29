# Detectors

Detectors scan text for PII and return a list of `EntitySpan` objects. PrivacyLens ships with three detectors — one built-in and two optional.

## Built-in: Regex detector

Zero dependencies. Always available. Covers the most common PII types.

| Entity | Example input | Token |
|--------|--------------|-------|
| `EMAIL` | `john@example.com` | `[EMAIL_1]` |
| `PHONE` | `555-123-4567`, `(415) 555-0198`, `+14155550198` | `[PHONE_1]` |
| `SSN` | `123-45-6789` | `[SSN_1]` |

The regex detector is enabled by default — no config needed.

### Adding custom patterns

```yaml
# privacylens.yaml
detectors:
  regex:
    patterns:
      - entity_type: EMPLOYEE_ID
        pattern: 'EMP-\d{4,}'
      - entity_type: CREDIT_CARD
        pattern: '\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b'
```

Custom patterns are **additive** — EMAIL, PHONE, and SSN are still detected.

---

## Optional: Presidio (50+ entity types)

[Microsoft Presidio](https://microsoft.github.io/presidio/) provides ML-backed detection for names, addresses, credit cards, passport numbers, and 50+ more entity types.

### Install

```bash
pip install "privacylens[pii]"
```

### Enable

```yaml
# privacylens.yaml
detectors:
  pii:
    enabled: true
```

### Detected entities (sample)

`PERSON`, `EMAIL_ADDRESS`, `PHONE_NUMBER`, `CREDIT_CARD`, `US_SSN`, `US_PASSPORT`, `IBAN_CODE`, `IP_ADDRESS`, `LOCATION`, `DATE_TIME`, `NRP`, `MEDICAL_LICENSE`, and more.

> Presidio uses spaCy under the hood. The first run downloads a language model (~50 MB).

---

## Optional: GLiNER (semantic / ML-based)

[GLiNER](https://github.com/urchade/GLiNER) is a lightweight NER model that detects entities by semantic meaning rather than pattern matching. Useful for names and addresses that regex can't reliably catch.

### Install

```bash
pip install "privacylens[semantic]"
```

### Enable

```yaml
# privacylens.yaml
detectors:
  semantic:
    enabled: true
```

### Default labels detected

`person`, `email`, `phone`, `address`, `organization`

> The GLiNER model (`urchade/gliner_medium-v2.1`, ~300 MB) is downloaded from HuggingFace on first use.

---

## Using multiple detectors together

Detectors can be combined. PrivacyLens merges their results and resolves overlapping spans by keeping the longest match.

```yaml
detectors:
  regex:
    enabled: true
    patterns:
      - entity_type: EMPLOYEE_ID
        pattern: 'EMP-\d{4,}'
  pii:
    enabled: true
```

---

## Writing a custom detector

See [Writing a Custom Detector](./writing-a-custom-detector.md).

---

## TypeScript

The TypeScript SDK currently ships the regex detector only. Presidio and GLiNER are Python-only.

```typescript
import { inspect } from "privacylens";

// Uses regex detector by default
const spans = inspect("SSN: 123-45-6789");
```

Custom patterns work the same way via `privacylens.yaml` or `loadConfig`:

```typescript
import { loadConfig, shield } from "privacylens";
import OpenAI from "openai";

const client = shield(new OpenAI(), loadConfig({
  overrides: {
    detectors: {
      regex: {
        patterns: [{ entityType: "EMPLOYEE_ID", pattern: "EMP-\\d{4,}" }]
      }
    }
  }
}));
```
