# PrivacyLens

> Transparent PII masking for LLM clients — keep sensitive data out of your AI prompts.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.4-blue)](https://www.typescriptlang.org/)
[![Python](https://img.shields.io/badge/Python-3.10+-green)](https://www.python.org/)

## What it does

PrivacyLens sits between your application and any LLM API. Before a prompt is sent, it detects and replaces PII (names, emails, phone numbers, etc.) with anonymous tokens. After the LLM responds, it restores the original values — transparently.

```
Your app  →  [tokenize PII]  →  LLM API
Your app  ←  [detokenize]    ←  LLM response
```

## Packages

| Package | Language | Description |
|---------|----------|-------------|
| [`packages/core-ts`](./packages/core-ts) | TypeScript | Drop-in adapters for OpenAI & Vercel AI SDK |
| [`packages/core-py`](./packages/core-py) | Python | Python SDK with OpenAI adapter |

## Features

- 🔍 Regex-based PII detection (extensible)
- 🔄 Transparent tokenize/detokenize pipeline
- 🔌 Drop-in adapters for **OpenAI** and **Vercel AI SDK**
- ⚙️ YAML/JSON config support
- 📦 Minimal dependencies
- 🧪 Fully tested

## Quick Start

### TypeScript

```bash
npm install privacylens
```

```ts
import OpenAI from "openai";
import { shieldOpenAI } from "privacylens/adapters/openai";

const client = shieldOpenAI(new OpenAI());
const response = await client.chat.completions.create({
  model: "gpt-4o",
  messages: [{ role: "user", content: "My name is John Doe, email: john@example.com." }],
});
// PII is masked before sending, restored in the response
```

### Python

```bash
pip install privacylens
```

```python
from privacylens import shield
import openai

client = shield(openai.OpenAI())
```

## Configuration

Create a `privacylens.yaml` in your project root:

```yaml
detectors:
  - type: regex
    name: email
    pattern: '[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
  - type: regex
    name: phone
    pattern: '\b\d{3}[-.]?\d{3}[-.]?\d{4}\b'
```

See [`privacylens.schema.json`](./privacylens.schema.json) for the full config schema.

## Repository Structure

```
privacylens/
├── packages/
│   ├── core-ts/          # TypeScript/Node.js SDK
│   └── core-py/          # Python SDK
└── privacylens.schema.json
```

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](./CONTRIBUTING.md) first.

## License

[MIT](./LICENSE) © 2026 Madan Gopal
