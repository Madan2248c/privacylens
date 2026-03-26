# PrivacyLens

> Transparent PII masking for LLM clients — keep sensitive data out of your AI prompts.

[![CI](https://github.com/Madan2248c/privacylens/actions/workflows/ci.yml/badge.svg)](https://github.com/Madan2248c/privacylens/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/privacylens)](https://pypi.org/project/privacylens/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/Madan2248c/privacylens/blob/main/LICENSE)

---

## Why?

Every prompt you send to an LLM can leak PII — names, emails, phone numbers, SSNs. PrivacyLens intercepts your prompts, replaces PII with anonymous tokens, and restores the original values when the response comes back. Your LLM never sees real data.

```
Input:  "Email john@example.com about the project"
Sent:   "Email [EMAIL_1] about the project"         ← LLM sees this
Output: "I've emailed john@example.com"              ← Your app sees this
```

---

## Install

```bash
pip install privacylens
```

---

## Usage

### Step 1: Wrap your client

```python
from privacylens import shield

# Pick your LLM client — wrap it with shield()
import openai
client = shield(openai.OpenAI())
```

### Step 2: Use it normally

```python
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{
        "role": "user",
        "content": "My name is John Doe and my email is john@example.com. Write me a welcome email."
    }],
)

print(response.choices[0].message.content)
# Output contains "John Doe" and "john@example.com" — restored automatically
```

That's it. **No other code changes needed.** The PII is masked before it reaches the LLM and unmasked in the response.

---

## Works With Every Major LLM Client

```python
from privacylens import shield

# OpenAI
client = shield(openai.OpenAI())
client = shield(openai.AsyncOpenAI())

# Anthropic
client = shield(anthropic.Anthropic())
client = shield(anthropic.AsyncAnthropic())

# LangChain — returns a callback handler
handler = shield(my_langchain_chat_model)

# CrewAI
adapter = shield(my_crewai_agent)

# Strands
wrapper = shield(my_strands_model)
```

Each wrapped client behaves exactly like the original. Same methods, same parameters, same return types.

---

## What Gets Detected

### Built-in (regex, zero dependencies)

| Entity | Example Input | What LLM Sees |
|--------|--------------|---------------|
| Email | `john@example.com` | `[EMAIL_1]` |
| Phone | `555-123-4567` | `[PHONE_1]` |
| SSN | `123-45-6789` | `[SSN_1]` |

### Optional: Presidio (50+ entity types)

```bash
pip install privacylens[pii]
```

Detects names, addresses, credit card numbers, dates of birth, passport numbers, and more using Microsoft Presidio.

### Optional: GLiNER (ML-based semantic detection)

```bash
pip install privacylens[semantic]
```

Uses a neural model to detect entities that regex can't catch.

---

## Custom Detectors

Add your own patterns via `privacylens.yaml` in your project root:

```yaml
detectors:
  regex:
    patterns:
      - entity_type: EMAIL
        pattern: '[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
      - entity_type: EMPLOYEE_ID
        pattern: 'EMP-\d{5,}'
      - entity_type: PROJECT_CODE
        pattern: 'PROJ-[A-Z]{2,4}-\d{3,}'
```

---

## Vault Backends

Tokens are stored in a vault so they can be restored later. Three backends available:

```yaml
# In-memory (default) — fast, lost on restart
vault: memory

# SQLite — persists to disk
vault: sqlite

# Redis — shared across processes
vault: redis
```

For Redis:

```bash
pip install privacylens[redis]
```

---

## Inspect Without Masking

See what would be detected without actually masking anything:

```python
from privacylens import inspect

entities = inspect("Contact john@example.com or call 555-123-4567")

for entity in entities:
    print(f"{entity.entity_type}: '{entity.value}' at [{entity.start}:{entity.end}]")

# EMAIL: 'john@example.com' at [8:24]
# PHONE: '555-123-4567' at [33:45]
```

---

## Low-Level API

For full control over the pipeline:

```python
from privacylens.core.pipeline import Pipeline
from privacylens.core.config import load_config

config = load_config()
pipeline = Pipeline(config)

# Tokenize
messages = [{"role": "user", "content": "Email john@example.com"}]
tokenized = pipeline.tokenize_messages(messages, session_id="s1")

# Send to LLM (tokenized messages have PII replaced)
llm_response = call_your_llm(tokenized)

# Detokenize
restored = pipeline.detokenize(llm_response, session_id="s1")
```

---

## Links

- **GitHub**: [github.com/Madan2248c/privacylens](https://github.com/Madan2248c/privacylens)
- **TypeScript SDK**: `npm install privacylens` — [docs](https://github.com/Madan2248c/privacylens/tree/main/packages/core-ts)
- **Contributing**: [CONTRIBUTING.md](https://github.com/Madan2248c/privacylens/blob/main/CONTRIBUTING.md)

## License

[MIT](https://github.com/Madan2248c/privacylens/blob/main/LICENSE) © 2026 Madan Gopal
