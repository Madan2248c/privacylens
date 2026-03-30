# Contributing to PrivacyLens

Thanks for your interest in contributing to PrivacyLens.

## Prerequisites

- Python 3.10+
- Node.js 20+
- Git
- macOS or Linux shell environment (Windows contributors can use WSL2)

## Local setup

Run these commands from the repository root.

### Python

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e "packages/core-py[dev]"
```

### TypeScript

```bash
cd packages/core-ts
npm install
```

## Running tests

### Python tests

```bash
cd packages/core-py
pytest
```

### TypeScript tests

```bash
cd packages/core-ts
npm test
```

## Running linters and type checks

### Python (`ruff`, `mypy`)

```bash
cd packages/core-py
ruff check .
mypy src
```

### TypeScript (`eslint`, `tsc`)

```bash
cd packages/core-ts
npm run lint
npm run typecheck
```

## PR process

1. Fork the repository.
2. Create a branch from `main`.
3. Use one of these branch prefixes:
   - `feat/` for features
   - `fix/` for bug fixes
   - `docs/` for documentation changes
4. Open a PR against `main`.

### PR checklist

- [ ] Tests pass for changed package(s)
- [ ] No new lint/type-check errors (`ruff`, `mypy`, `eslint`, `tsc`)
- [ ] Documentation updated when behavior or usage changes

## Coding conventions

This repository does not currently include `.kiro/steering/tech.md` in source control, so follow the enforced standards below:

- **Python**: format and lint with `ruff`; keep `mypy` strict checks passing
- **TypeScript**: keep `eslint` and strict TypeScript (`tsc --noEmit`) passing; avoid `any` unless justified
