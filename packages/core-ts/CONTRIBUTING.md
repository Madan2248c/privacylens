# Contributing to PrivacyLens

Thanks for your interest in contributing! Here's how to get started.

## Getting Started

1. Fork the repo and clone it locally
2. Install dependencies: `npm install`
3. Run tests to make sure everything works: `npm test`

## Development Workflow

- **Branch**: Create a feature branch from `main` (`git checkout -b feat/my-feature`)
- **Code**: Make your changes in `src/`
- **Test**: Add or update tests in `tests/`
- **Lint**: Run `npm run lint` and `npm run typecheck`
- **Commit**: Use clear, descriptive commit messages
- **PR**: Open a pull request against `main` with a description of what and why

## Commit Message Format

Use conventional commits:

```
feat: add support for custom detectors
fix: handle overlapping spans correctly
docs: update README with Vercel AI example
test: add edge cases for detokenizer
```

## Adding a New Detector

1. Create `src/detectors/<name>.ts` implementing the `Detector` interface
2. Export it from `src/index.ts`
3. Add tests in `tests/<name>.test.ts`
4. Document it in the README

## Code Style

- TypeScript strict mode is enforced
- ESLint rules must pass (`npm run lint`)
- No `any` types without justification
- Keep functions small and focused

## Reporting Issues

- Search existing issues before opening a new one
- Include a minimal reproduction case
- Specify your Node.js version and OS

## Questions?

Open a [GitHub Discussion](https://github.com/Madan2248c/privacylens/discussions) for questions or ideas.
