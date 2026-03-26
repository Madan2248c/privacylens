/**
 * Tests for the De-tokenizer module (Property 13 and unit tests).
 */

import { describe, it, expect } from "vitest";
import fc from "fast-check";
import { detokenize } from "../src/core/detokenizer.js";
import { tokenize } from "../src/core/tokenizer.js";
import { MemoryVault } from "../src/core/vault.js";
import type { EntitySpan } from "../src/core/models.js";

// ---------------------------------------------------------------------------
// Property 13: tokenize → detokenize round-trip
// ---------------------------------------------------------------------------

describe("Property 13: tokenize → detokenize round-trip", () => {
  it("restores original text after tokenizing a single entity", () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 40 }),              // sessionId
        fc.stringMatching(/^[A-Z][A-Z0-9_]{0,19}$/),            // entityType
        fc.string({ minLength: 1, maxLength: 50 }).filter(       // value
          (v) => !v.startsWith("[") || !v.endsWith("]")
        ),
        fc.string({ minLength: 0, maxLength: 50 }).filter(       // prefix
          (s) => !s.includes("[") && !s.includes("]")
        ),
        fc.string({ minLength: 0, maxLength: 50 }).filter(       // suffix
          (s) => !s.includes("[") && !s.includes("]")
        ),
        (sessionId, entityType, value, prefix, suffix) => {
          const vault = new MemoryVault();
          const text = prefix + value + suffix;
          const span: EntitySpan = {
            start: prefix.length,
            end: prefix.length + value.length,
            entityType,
            value,
          };

          const { tokenizedText } = tokenize(text, [span], vault, sessionId);
          const restored = detokenize(tokenizedText, vault, sessionId);

          expect(restored).toBe(text);
        }
      ),
      { numRuns: 200 }
    );
  });

  it("restores original text after tokenizing multiple distinct entities", () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 40 }),
        fc.uniqueArray(
          fc.tuple(
            fc.stringMatching(/^[A-Z][A-Z0-9_]{0,19}$/),
            fc.string({ minLength: 1, maxLength: 30 }).filter(
              (v) => !v.startsWith("[") || !v.endsWith("]")
            )
          ),
          { minLength: 1, maxLength: 4, selector: ([, v]) => v }
        ),
        (sessionId, entries) => {
          const vault = new MemoryVault();
          const separator = "---";
          const text = entries.map(([, v]) => v).join(separator);

          const spans: EntitySpan[] = [];
          let cursor = 0;
          for (const [entityType, value] of entries) {
            spans.push({ start: cursor, end: cursor + value.length, entityType, value });
            cursor += value.length + separator.length;
          }

          const { tokenizedText } = tokenize(text, spans, vault, sessionId);
          const restored = detokenize(tokenizedText, vault, sessionId);

          expect(restored).toBe(text);
        }
      ),
      { numRuns: 150 }
    );
  });
});

// ---------------------------------------------------------------------------
// Unit tests: no-token passthrough
// ---------------------------------------------------------------------------

describe("no-token passthrough", () => {
  it("returns text unchanged when no tokens present", () => {
    const vault = new MemoryVault();
    const text = "Hello, world! No PII here.";
    expect(detokenize(text, vault, "s1")).toBe(text);
  });

  it("returns empty string unchanged", () => {
    const vault = new MemoryVault();
    expect(detokenize("", vault, "s1")).toBe("");
  });
});

// ---------------------------------------------------------------------------
// Unit tests: unknown token passthrough
// ---------------------------------------------------------------------------

describe("unknown token passthrough", () => {
  it("leaves unknown token unchanged", () => {
    const vault = new MemoryVault();
    const text = "Contact [EMAIL_1] for details.";
    expect(detokenize(text, vault, "s1")).toBe(text);
  });

  it("replaces known token and leaves unknown token unchanged", () => {
    const vault = new MemoryVault();
    vault.store("s1", "[EMAIL_1]", "alice@example.com");
    const result = detokenize("Email: [EMAIL_1], phone: [PHONE_1]", vault, "s1");
    expect(result).toBe("Email: alice@example.com, phone: [PHONE_1]");
  });

  it("leaves token unchanged when session differs", () => {
    const vault = new MemoryVault();
    vault.store("s1", "[EMAIL_1]", "alice@example.com");
    expect(detokenize("[EMAIL_1]", vault, "s2")).toBe("[EMAIL_1]");
  });
});

// ---------------------------------------------------------------------------
// Unit tests: basic detokenization
// ---------------------------------------------------------------------------

describe("basic detokenization", () => {
  it("replaces a single token", () => {
    const vault = new MemoryVault();
    vault.store("s1", "[EMAIL_1]", "alice@example.com");
    expect(detokenize("Email: [EMAIL_1]", vault, "s1")).toBe("Email: alice@example.com");
  });

  it("replaces multiple distinct tokens", () => {
    const vault = new MemoryVault();
    vault.store("s1", "[EMAIL_1]", "alice@example.com");
    vault.store("s1", "[PHONE_1]", "555-1234");
    expect(detokenize("[EMAIL_1] / [PHONE_1]", vault, "s1")).toBe(
      "alice@example.com / 555-1234"
    );
  });

  it("replaces all occurrences of a repeated token (single-pass)", () => {
    const vault = new MemoryVault();
    vault.store("s1", "[EMAIL_1]", "alice@example.com");
    expect(detokenize("[EMAIL_1] and [EMAIL_1]", vault, "s1")).toBe(
      "alice@example.com and alice@example.com"
    );
  });

  it("preserves surrounding text", () => {
    const vault = new MemoryVault();
    vault.store("s1", "[SSN_1]", "123-45-6789");
    expect(detokenize("SSN is [SSN_1] on file.", vault, "s1")).toBe(
      "SSN is 123-45-6789 on file."
    );
  });

  it("handles tokens with high counters", () => {
    const vault = new MemoryVault();
    vault.store("s1", "[EMAIL_42]", "user@example.com");
    expect(detokenize("Contact [EMAIL_42].", vault, "s1")).toBe(
      "Contact user@example.com."
    );
  });
});

// ---------------------------------------------------------------------------
// Unit tests: round-trip with tokenizer
// ---------------------------------------------------------------------------

describe("round-trip with tokenizer", () => {
  it("full round-trip for a single entity", () => {
    const vault = new MemoryVault();
    const text = "Please email alice@example.com today.";
    const span: EntitySpan = { start: 13, end: 30, entityType: "EMAIL", value: "alice@example.com" };
    const { tokenizedText } = tokenize(text, [span], vault, "s1");
    expect(detokenize(tokenizedText, vault, "s1")).toBe(text);
  });

  it("full round-trip with no spans", () => {
    const vault = new MemoryVault();
    const text = "No PII in this message.";
    const { tokenizedText } = tokenize(text, [], vault, "s1");
    expect(detokenize(tokenizedText, vault, "s1")).toBe(text);
  });
});
