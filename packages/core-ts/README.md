# PrivacyLens

> Transparent PII masking for LLM clients — keep sensitive data out of your AI prompts.

[![npm version](https://img.shields.io/npm/v/privacylens)](https://www.npmjs.com/package/privacylens)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.4-blue)](https://www.typescriptlang.org/)

## What it does

PrivacyLens sits between your application and any LLM API. Before a prompt is sent, it detects and replaces PII (names, emails, phone numbers, etc.) with anonymous tokens. After the LLM responds, it restores the original values — transparently.

```
Your app  →  [tokenize PII]  →  LLM API
Your app  ←  [detokenize]    ←  LLM response
```

## Features

- 🔍 Regex-based PII detection (extensible)
- 🔄 Transparent tokenize/detokenize pipeline
- 🔌 Drop-in adapters for **OpenAI** and **Vercel AI SDK**
- ⚙️ YAML/JSON config support
- 📦 Zero runtime dependencies (except `js-yaml`)
- 🧪 Fully tested with Vitest

## Installation

```bash
npm install privacylens
```

## Quick Start

### OpenAI

```ts
import OpenAI from "openai";
import { shieldOpenAI } from "privacylens/adapters/openai";

const client = shieldOpenAI(new OpenAI());

const response = await client.chat.completions.create({
  model: "gpt-4o",
  messages: [{ role: "user", content: "My name is John Doe, email: john@example.com. Summarize my profile." }],
});
// PII is masked before sending, restored in the response
```

### Vercel AI SDK

```ts
import { createPrivacyLensMiddleware } from "privacylens/adapters/vercel-ai";
import { wrapLanguageModel } from "ai";

const model = wrapLanguageModel({
  model: yourModel,
  middleware: createPrivacyLensMiddleware(),
});
```

### Low-level API

```ts
import { shield, inspect } from "privacylens";

const { pipeline, messages } = await shield(originalMessages);
const llmResponse = await callYourLLM(messages); // masked
const restored = await pipeline.detokenizeResponse(llmResponse); // original values back
```

## Configuration

Create a `privacylens.yaml` (or `.json`) in your project root:

```yaml
detectors:
  regex:
    patterns:
      - entity_type: EMAIL
        pattern: '[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
      - entity_type: PHONE
        pattern: '\b\d{3}[-.]?\d{3}[-.]?\d{4}\b'
```

## Architecture

```
src/
├── index.ts              # Public API: shield, inspect, buildDetectors
├── adapters/
│   ├── openai.ts         # OpenAI client wrapper
│   └── vercel-ai.ts      # Vercel AI SDK middleware
├── core/
│   ├── pipeline.ts       # Tokenize → LLM → Detokenize orchestration
│   ├── analyzer.ts       # Runs detectors, resolves overlapping spans
│   ├── tokenizer.ts      # Replaces PII with tokens
│   ├── detokenizer.ts    # Restores original values
│   ├── vault.ts          # In-memory token↔value store
│   ├── config.ts         # Config loading & merging
│   ├── normalize.ts      # Message format normalization
│   └── models.ts         # Shared types
└── detectors/
    └── regex.ts          # RegexDetector implementation
```

## Development

```bash
# Install dependencies
npm install

# Run tests
npm test

# Build
npm run build

# Type check
npm run typecheck

# Lint
npm run lint
```

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](./CONTRIBUTING.md) first.

## License

[MIT](./LICENSE) © 2026 Madan Gopal
