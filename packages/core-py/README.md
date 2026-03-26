# PrivacyLens

> Transparent PII masking for LLM clients — keep sensitive data out of your AI prompts.

[![CI](https://github.com/Madan2248c/privacylens/actions/workflows/ci.yml/badge.svg)](https://github.com/Madan2248c/privacylens/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/privacylens)](https://pypi.org/project/privacylens/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/Madan2248c/privacylens/blob/main/LICENSE)

## The Problem

Every time you send a prompt to an LLM, you risk leaking PII — names, emails, phone numbers, SSNs. PrivacyLens automatically detects and replaces sensitive data with anonymous tokens before the prompt leaves your app, then restores the original values when the response comes back.

```
"Email john@example.com"  →  "Email [EMAIL_1]"  →  LLM  →  "[EMAIL_1] notified"  →  "john@example.com notified"
```

Your LLM never sees real PII. Your app gets back the original values. Zero code changes needed.

## Install

```bash
pip install privacylens
```

Optional detectors:

```bash
pip install privacylens[pii]       # Presidio (names, addresses, credit cards, 50+ types)
pip install privacylens[semantic]   # GLiNER ML-based detection
pip install privacylens[redis]      # Redis vault backend
```

## Quick Start

Wrap your LLM client with `shield()` — that's it:

```python
from privacylens import shield
import openai

client = shield(openai.OpenAI())

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "My name is John Doe, email: john@example.com"}],
)
print(response.choices[0].message.content)  # Original PII restored automatically
```

## Supported Clients

```python
from privacylens import shield

client = shield(openai.OpenAI())              # OpenAI
client = shield(openai.AsyncOpenAI())         # OpenAI (async)
client = shield(anthropic.Anthropic())        # Anthropic
client = shield(anthropic.AsyncAnthropic())   # Anthropic (async)
handler = shield(my_langchain_model)          # LangChain
client = shield(my_crewai_agent)              # CrewAI
wrapper = shield(my_strands_model)            # Strands
```

## What Gets Detected

Built-in (regex):

| Entity | Example | Token |
|--------|---------|-------|
| Email | `john@example.com` | `[EMAIL_1]` |
| Phone | `555-123-4567` | `[PHONE_1]` |
| SSN | `123-45-6789` | `[SSN_1]` |

With `privacylens[pii]`: Names, addresses, credit cards, dates of birth, and 50+ entity types via Presidio.

With `privacylens[semantic]`: ML-based entity detection via GLiNER.

## Configuration

Create a `privacylens.yaml` in your project root:

```yaml
detectors:
  - type: regex
    name: email
    pattern: '[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
  - type: regex
    name: custom_id
    pattern: 'PROJ-\d{4,}'

vault: memory  # or "sqlite" or "redis"
```

## How It Works

1. **Analyze** — Detectors scan the prompt for PII
2. **Tokenize** — PII is replaced with deterministic tokens (`[EMAIL_1]`)
3. **Store** — Token↔value mappings saved in a vault (memory/SQLite/Redis)
4. **Send** — Sanitized prompt goes to the LLM
5. **Detokenize** — Tokens in the response are replaced with original values

## Links

- [GitHub](https://github.com/Madan2248c/privacylens)
- [TypeScript SDK](https://github.com/Madan2248c/privacylens/tree/main/packages/core-ts) (also available as `npm install privacylens`)
- [Contributing](https://github.com/Madan2248c/privacylens/blob/main/CONTRIBUTING.md)

## License

[MIT](https://github.com/Madan2248c/privacylens/blob/main/LICENSE) © 2026 Madan Gopal
