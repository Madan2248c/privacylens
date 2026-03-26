/**
 * Task 22.2 — Zero-dependency validation for the TypeScript core package.
 *
 * Validates: Requirement 22.3
 */

import { readFileSync } from "fs";
import { resolve } from "path";
import { describe, it, expect } from "vitest";

const ML_LIBRARIES = [
  "spacy",
  "transformers",
  "torch",
  "@tensorflow",
  "onnxruntime",
  "gliner",
  "presidio",
];

describe("zero-dependency validation", () => {
  it("package.json dependencies field contains no ML libraries", () => {
    const pkgPath = resolve(__dirname, "../package.json");
    const pkg = JSON.parse(readFileSync(pkgPath, "utf-8")) as {
      dependencies?: Record<string, string>;
    };

    const deps = Object.keys(pkg.dependencies ?? {});

    const found = deps.filter((dep) =>
      ML_LIBRARIES.some((ml) => dep === ml || dep.startsWith(`${ml}/`))
    );

    expect(found).toEqual([]);
  });
});
