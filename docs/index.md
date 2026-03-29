# PrivacyLens

> Transparent PII masking for LLM clients — keep sensitive data out of your AI prompts.

[![CI](https://github.com/Madan2248c/privacylens/actions/workflows/ci.yml/badge.svg)](https://github.com/Madan2248c/privacylens/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/privacylens)](https://pypi.org/project/privacylens/)
[![npm](https://img.shields.io/npm/v/privacylens)](https://www.npmjs.com/package/privacylens)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

## The Problem

Every time you send a prompt to an LLM, you risk leaking PII — names, emails, phone numbers, SSNs. PrivacyLens fixes this by automatically detecting and replacing sensitive data with anonymous tokens before the prompt leaves your app, then restoring the original values when the response comes back.

```
"Email john@example.com"  →  "Email [EMAIL_1]"  →  LLM  →  "[EMAIL_1] notified"  →  "john@example.com notified"
```

Your LLM never sees real PII. Your app gets back the original values. Zero code changes needed.

## Supported SDKs

| Package | Install | Adapters |
|---------|---------|----------|
| [Python SDK](./packages/core-py) | `pip install privacylens` | OpenAI, Anthropic, LangChain, CrewAI, Strands |
| [TypeScript SDK](./packages/core-ts) | `npm install privacylens` | OpenAI, Vercel AI SDK |

## Quick Start

### Python — one line to shield any client

```python
from privacylens import shield
import openai

# Wrap your client — that's it
client = shield(openai.OpenAI())

# Use it exactly as before. PII is masked/unmasked automatically.
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "My name is John Doe, email: john@example.com"}],
)
print(response.choices[0].message.content)  # Original PII restored
```

Works the same way with Anthropic, LangChain, CrewAI, and Strands:

```python
client = shield(anthropic.Anthropic())       # Anthropic
handler = shield(my_langchain_model)          # LangChain
client = shield(my_crewai_agent)              # CrewAI
```

Use `inspect()` to preview what would be masked without actually masking it — handy for testing:

```python
from privacylens import inspect

results = inspect("Call me at 555-123-4567 or email john@example.com")
# [EntitySpan(type='PHONE', value='555-123-4567', ...), EntitySpan(type='EMAIL', value='john@example.com', ...)]
```

### TypeScript — drop-in OpenAI wrapper

```typescript
import OpenAI from "openai";
import { shieldOpenAI } from "privacylens/adapters/openai";

const client = shieldOpenAI(new OpenAI());

// Use normally — PII is masked before sending, restored in the response
const response = await client.chat.completions.create({
  model: "gpt-4o",
  messages: [{ role: "user", content: "Contact john@example.com about the project" }],
});
```

Works with Vercel AI SDK too:

```typescript
import { shield } from "privacylens";
import { openai } from "@ai-sdk/openai";

const { text } = await generateText({
  model: shield(openai("gpt-4o")),
  prompt: "Summarise the contract for john@example.com",
});
```

## What Gets Detected

Out of the box (regex-based, extensible):

| Entity | Example |
|--------|---------|
| Email | `john@example.com` → `[EMAIL_1]` |
| Phone | `555-123-4567` → `[PHONE_1]` |
| SSN | `123-45-6789` → `[SSN_1]` |

With optional detectors:

| Detector | Install | Entities |
|----------|---------|----------|
| Presidio | `pip install privacylens[pii]` | Names, addresses, credit cards, 50+ types |
| GLiNER (semantic) | `pip install privacylens[semantic]` | ML-based entity detection |

## Configuration

Create a `privacylens.yaml` in your project root to customize detection:

```yaml
detectors:
  regex:
    patterns:
      - entity_type: EMAIL
        pattern: '[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
      - entity_type: PHONE
        pattern: '\b\d{3}[-.]?\d{3}[-.]?\d{4}\b'
      - entity_type: CUSTOM_ID
        pattern: 'PROJ-\d{4,}'

vault: memory  # or "sqlite" or "redis"
```

## How It Works

```
┌──────────┐     ┌───────────┐     ┌─────────┐     ┌──────────────┐
│ Your App │ ──▶ │ Tokenizer │ ──▶ │ LLM API │ ──▶ │ Detokenizer  │ ──▶ Response
│          │     │           │     │         │     │              │    (PII restored)
│ "Email   │     │ "Email    │     │         │     │ "[EMAIL_1]   │
│  john@.."│     │ [EMAIL_1]"│     │         │     │  confirmed"  │
└──────────┘     └───────────┘     └─────────┘     └──────────────┘
                       │                                  ▲
                       ▼                                  │
                 ┌───────────┐                            │
                 │   Vault   │ ────────────────────────────
                 │ [EMAIL_1] │
                 │ =john@..  │
                 └───────────┘
```

1. **Analyze** — Detectors scan the prompt for PII entities
2. **Tokenize** — Each PII value is replaced with a deterministic token (`[EMAIL_1]`, `[PHONE_1]`)
3. **Store** — Token↔value mappings are stored in a session vault (memory, SQLite, or Redis)
4. **Send** — The sanitized prompt goes to the LLM
5. **Detokenize** — Tokens in the LLM response are replaced with original values

## Repository Structure

```
privacylens/
├── packages/
│   ├── core-py/          # Python SDK
│   │   ├── src/privacylens/
│   │   │   ├── adapters/     # OpenAI, Anthropic, LangChain, CrewAI, Strands
│   │   │   ├── core/         # Pipeline, Analyzer, Tokenizer, Vault
│   │   │   └── detectors/    # Regex, Presidio, GLiNER
│   │   └── tests/
│   └── core-ts/          # TypeScript SDK
│       ├── src/
│       │   ├── adapters/     # OpenAI, Vercel AI SDK
│       │   ├── core/         # Pipeline, Analyzer, Tokenizer, Vault
│       │   └── detectors/    # Regex
│       └── tests/
└── privacylens.schema.json   # Config schema
```

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](./CONTRIBUTING.md) first.

## Documentation

- [Getting Started](./docs/getting-started.md)
- [Configuration](./docs/configuration.md)
- [Detectors](./docs/detectors.md)
- [Adapters](./docs/adapters.md)
- [Writing a Custom Detector](./docs/writing-a-custom-detector.md)

## Releases

Both packages are published automatically on GitHub release:
- Python SDK → [PyPI](https://pypi.org/project/privacylens/) via `publish-pypi.yml`
- TypeScript SDK → [npm](https://www.npmjs.com/package/privacylens) via `publish-npm.yml`

## License

[MIT](./LICENSE) © 2026 Madan Gopal
