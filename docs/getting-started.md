# Getting Started

PrivacyLens wraps your LLM client with one line of code. PII is masked before every request and restored in every response — your app code stays unchanged.

## Prerequisites

- **Python SDK**: Python 3.10+
- **TypeScript SDK**: Node.js 20+

## Install

```bash
# Python
pip install privacylens

# TypeScript
npm install privacylens
```

## Your first shielded client

### Python

```python
from privacylens import shield
import openai

client = shield(openai.OpenAI())

response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "My email is john@example.com"}],
)
print(response.choices[0].message.content)  # john@example.com is restored
```

### TypeScript

```typescript
import OpenAI from "openai";
import { shield } from "privacylens";

const client = shield(new OpenAI());

const response = await client.chat.completions.create({
  model: "gpt-4o-mini",
  messages: [{ role: "user", content: "My email is john@example.com" }],
});
console.log(response.choices[0].message.content); // john@example.com is restored
```

That's it. No other changes needed.

## Preview what gets masked

Use `inspect()` to see what PrivacyLens would mask without actually masking it — useful for testing and debugging.

### Python

```python
from privacylens import inspect

spans = inspect("Call me at 555-123-4567 or email john@example.com")
for span in spans:
    print(f"{span.entity_type}: '{span.value}'")
# PHONE: '555-123-4567'
# EMAIL: 'john@example.com'
```

### TypeScript

```typescript
import { inspect } from "privacylens";

const spans = inspect("Call me at 555-123-4567 or email john@example.com");
spans.forEach(s => console.log(`${s.entityType}: '${s.value}'`));
// PHONE: '555-123-4567'
// EMAIL: 'john@example.com'
```

## What happens under the hood

```
Your prompt  →  Analyzer  →  Tokenizer  →  Vault  →  LLM API
"john@..."       detects       replaces      stores    "[EMAIL_1]"
                 EMAIL         with token    mapping

LLM response  →  Detokenizer  →  Your app
"[EMAIL_1]"       restores        "john@..."
```

1. **Analyze** — detectors scan the prompt for PII
2. **Tokenize** — each PII value is replaced with `[ENTITY_TYPE_N]`
3. **Store** — the token↔value mapping is saved in a session vault
4. **Send** — the sanitized prompt goes to the LLM
5. **Detokenize** — tokens in the response are replaced with original values

## Next steps

- [Configuration](./configuration.md) — customize detectors, vault, and patterns
- [Detectors](./detectors.md) — add Presidio or GLiNER for 50+ entity types
- [Adapters](./adapters.md) — full list of supported LLM clients
