# Contributing to PrivacyLens

Thanks for your interest in contributing! This is a monorepo with a TypeScript SDK and a Python SDK.

## Repository Structure

```
packages/
├── core-ts/   # TypeScript SDK (Node.js, OpenAI, Vercel AI)
└── core-py/   # Python SDK
```

## Getting Started

### TypeScript (`packages/core-ts`)

```bash
cd packages/core-ts
npm install
npm test
```

### Python (`packages/core-py`)

```bash
cd packages/core-py
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Workflow

1. Fork the repo and create a branch from `main`: `git checkout -b feat/my-feature`
2. Make your changes
3. Add or update tests
4. Run lint + typecheck + tests for the affected package
5. Open a pull request against `main` with a clear description

## Commit Message Format

Use conventional commits:

```
feat: add support for custom detectors
fix: handle overlapping spans correctly
docs: update README with Python example
test: add edge cases for detokenizer
```

## Adding a New Detector

1. Implement the `Detector` interface in the relevant package
2. Export it from the package's public API
3. Add tests
4. Document it in the package README

## Code Style

- **TypeScript**: ESLint + strict TypeScript, no `any` without justification
- **Python**: Ruff for linting, mypy strict for type checking

## Reporting Issues

- Search existing issues before opening a new one
- Include a minimal reproduction case
- Specify your runtime version and OS

## Questions?

Open a [GitHub Discussion](https://github.com/Madan2248c/privacylens/discussions).
