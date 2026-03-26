/**
 * Tests for the Tokenizer module (Property 12 and unit tests).
 */

import { describe, it, expect } from "vitest";
import fc from "fast-check";
import { tokenize } from "../src/core/tokenizer.js";
import { MemoryVault } from "../src/core/vault.js";
import type { EntitySpan } from "../src/core/models.js";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeSpan(
  entityType: string,
  value: string,
  offset = 0
): EntitySpan {
  return { start: offset, end: offset + value.length, entityType, value };
}

// ---------------------------------------------------------------------------
// Property 12: Stable token assignment within session
// ---------------------------------------------------------------------------

describe("Property 12: stable token assignment", () => {
  it("same value repeated in text always gets the same token", () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 40 }), // sessionId
        fc.stringMatching(/^[A-Z][A-Z0-9_]{0,19}$/),  // entityType
        fc.string({ minLength: 1, maxLength: 50 }),   // value
        fc.integer({ min: 2, max: 5 }),               // repetitions
        (sessionId, entityType, value, repetitions) => {
          const vault = new MemoryVault();
          const separator = " | ";
          const text = Array(repetitions).fill(value).join(separator);

          const spans: EntitySpan[] = [];
          let cursor = 0;
          for (let i = 0; i < repetitions; i++) {
            spans.push({
              start: cursor,
              end: cursor + value.length,
              entityType,
              value,
            });
            cursor += value.length + separator.length;
          }

          const { pairs } = tokenize(text, spans, vault, sessionId);
          const tokensUsed = new Set(pairs.map(([t]) => t));
          expect(tokensUsed.size).toBe(1);
        }
      ),
      { numRuns: 200 }
    );
  });

  it("same value across multiple tokenize() calls in same session gets same token", () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 40 }),
        fc.stringMatching(/^[A-Z][A-Z0-9_]{0,19}$/),
        fc.string({ minLength: 1, maxLength: 50 }),
        (sessionId, entityType, value) => {
          const vault = new MemoryVault();
          const span = makeSpan(entityType, value);

          const { pairs: pairs1 } = tokenize(value, [span], vault, sessionId);
          const { pairs: pairs2 } = tokenize(value, [span], vault, sessionId);

          expect(pairs1[0]?.[0]).toBe(pairs2[0]?.[0]);
        }
      ),
      { numRuns: 200 }
    );
  });
});

// ---------------------------------------------------------------------------
// Unit tests: empty spans
// ---------------------------------------------------------------------------

describe("empty spans", () => {
  it("returns original text unchanged with empty pairs", () => {
    const vault = new MemoryVault();
    const text = "Hello, alice@example.com!";
    const { tokenizedText, pairs } = tokenize(text, [], vault, "s1");
    expect(tokenizedText).toBe(text);
    expect(pairs).toEqual([]);
  });

  it("handles empty text with empty spans", () => {
    const vault = new MemoryVault();
    const { tokenizedText, pairs } = tokenize("", [], vault, "s1");
    expect(tokenizedText).toBe("");
    expect(pairs).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// Unit tests: basic tokenization
// ---------------------------------------------------------------------------

describe("basic tokenization", () => {
  it("replaces a single span with a token", () => {
    const vault = new MemoryVault();
    const text = "Email: alice@example.com";
    const span: EntitySpan = { start: 7, end: 24, entityType: "EMAIL", value: "alice@example.com" };
    const { tokenizedText, pairs } = tokenize(text, [span], vault, "s1");
    expect(tokenizedText).toBe("Email: [EMAIL_1]");
    expect(pairs).toEqual([["[EMAIL_1]", "alice@example.com"]]);
  });

  it("assigns distinct tokens to distinct values", () => {
    const vault = new MemoryVault();
    const text = "alice@example.com and bob@example.com";
    const spans: EntitySpan[] = [
      { start: 0, end: 17, entityType: "EMAIL", value: "alice@example.com" },
      { start: 22, end: 37, entityType: "EMAIL", value: "bob@example.com" },
    ];
    const { tokenizedText, pairs } = tokenize(text, spans, vault, "s1");
    expect(tokenizedText).toContain("[EMAIL_1]");
    expect(tokenizedText).toContain("[EMAIL_2]");
    expect(tokenizedText).not.toContain("alice@example.com");
    expect(tokenizedText).not.toContain("bob@example.com");
    expect(pairs).toHaveLength(2);
  });

  it("assigns the same token to the same value appearing twice", () => {
    const vault = new MemoryVault();
    const text = "alice@example.com and alice@example.com";
    const spans: EntitySpan[] = [
      { start: 0, end: 17, entityType: "EMAIL", value: "alice@example.com" },
      { start: 22, end: 39, entityType: "EMAIL", value: "alice@example.com" },
    ];
    const { tokenizedText, pairs } = tokenize(text, spans, vault, "s1");
    expect(tokenizedText).toBe("[EMAIL_1] and [EMAIL_1]");
    const tokens = new Set(pairs.map(([t]) => t));
    expect(tokens).toEqual(new Set(["[EMAIL_1]"]));
  });

  it("uses independent counters per entity type", () => {
    const vault = new MemoryVault();
    const text = "alice@example.com 555-1234";
    const spans: EntitySpan[] = [
      { start: 0, end: 17, entityType: "EMAIL", value: "alice@example.com" },
      { start: 18, end: 26, entityType: "PHONE", value: "555-1234" },
    ];
    const { tokenizedText } = tokenize(text, spans, vault, "s1");
    expect(tokenizedText).toContain("[EMAIL_1]");
    expect(tokenizedText).toContain("[PHONE_1]");
  });

  it("stores the token in the vault", () => {
    const vault = new MemoryVault();
    const span = makeSpan("EMAIL", "alice@example.com");
    tokenize("alice@example.com", [span], vault, "s1");
    expect(vault.retrieve("s1", "[EMAIL_1]")).toBe("alice@example.com");
  });

  it("preserves text before and after the span", () => {
    const vault = new MemoryVault();
    const text = "Hello alice@example.com, how are you?";
    const span: EntitySpan = { start: 6, end: 23, entityType: "EMAIL", value: "alice@example.com" };
    const { tokenizedText } = tokenize(text, [span], vault, "s1");
    expect(tokenizedText).toBe("Hello [EMAIL_1], how are you?");
  });
});

// ---------------------------------------------------------------------------
// Unit tests: overlap handling
// ---------------------------------------------------------------------------

describe("overlap handling", () => {
  it("skips a span fully contained within an already-processed span", () => {
    const vault = new MemoryVault();
    const text = "alice@example.com";
    const outer: EntitySpan = { start: 0, end: 17, entityType: "EMAIL", value: "alice@example.com" };
    const inner: EntitySpan = { start: 0, end: 5, entityType: "NAME", value: "alice" };
    const { tokenizedText, pairs } = tokenize(text, [outer, inner], vault, "s1");
    expect(tokenizedText).toBe("[EMAIL_1]");
    expect(pairs).toHaveLength(1);
    expect(pairs[0]?.[0]).toBe("[EMAIL_1]");
  });

  it("processes partially overlapping spans (second not fully contained)", () => {
    const vault = new MemoryVault();
    const text = "0123456789abcde";
    const span1: EntitySpan = { start: 0, end: 10, entityType: "TYPE_A", value: "0123456789" };
    const span2: EntitySpan = { start: 5, end: 15, entityType: "TYPE_B", value: "56789abcde" };
    const { tokenizedText } = tokenize(text, [span1, span2], vault, "s1");
    expect(tokenizedText).toContain("[TYPE_A_1]");
    expect(tokenizedText).toContain("[TYPE_B_1]");
  });

  it("tokenizes adjacent (non-overlapping) spans", () => {
    const vault = new MemoryVault();
    const text = "alice@example.com555-1234";
    const spans: EntitySpan[] = [
      { start: 0, end: 17, entityType: "EMAIL", value: "alice@example.com" },
      { start: 17, end: 25, entityType: "PHONE", value: "555-1234" },
    ];
    const { tokenizedText, pairs } = tokenize(text, spans, vault, "s1");
    expect(tokenizedText).toBe("[EMAIL_1][PHONE_1]");
    expect(pairs).toHaveLength(2);
  });
});

// ---------------------------------------------------------------------------
// Unit tests: session isolation
// ---------------------------------------------------------------------------

describe("session isolation", () => {
  it("different sessions independently assign [ENTITY_1] for the same value", () => {
    const vault = new MemoryVault();
    const span = makeSpan("EMAIL", "alice@example.com");

    const { pairs: pairs1 } = tokenize("alice@example.com", [span], vault, "session-1");
    const { pairs: pairs2 } = tokenize("alice@example.com", [span], vault, "session-2");

    expect(pairs1[0]?.[0]).toBe("[EMAIL_1]");
    expect(pairs2[0]?.[0]).toBe("[EMAIL_1]");
    expect(vault.retrieve("session-1", "[EMAIL_1]")).toBe("alice@example.com");
    expect(vault.retrieve("session-2", "[EMAIL_1]")).toBe("alice@example.com");
  });

  it("stable token across calls in the same session", () => {
    const vault = new MemoryVault();
    const span = makeSpan("EMAIL", "alice@example.com");

    const { pairs: pairs1 } = tokenize("alice@example.com", [span], vault, "s1");
    const { pairs: pairs2 } = tokenize("alice@example.com", [span], vault, "s1");

    expect(pairs1[0]?.[0]).toBe("[EMAIL_1]");
    expect(pairs2[0]?.[0]).toBe("[EMAIL_1]");
  });
});
