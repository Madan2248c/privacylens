/**
 * Unit tests for shield() entry point (Task 14.2, 14.3)
 */

import { describe, it, expect } from "vitest";
import { shield } from "../src/index.js";

// ---------------------------------------------------------------------------
// Helpers — fake clients whose constructor.name matches what shield() checks
// ---------------------------------------------------------------------------

class OpenAI {}
class AzureOpenAI {}
class UnknownClient {}

// ---------------------------------------------------------------------------
// shield() with OpenAI-named clients
// ---------------------------------------------------------------------------

describe("shield() with OpenAI client", () => {
  it("returns a wrapped client for OpenAI constructor name", () => {
    const client = new OpenAI();
    const result = shield(client);
    // Returns a Proxy wrapping the client — not the same reference
    expect(result).not.toBeNull();
    expect(typeof result).toBe("object");
  });

  it("returns a wrapped client for AzureOpenAI constructor name", () => {
    const client = new AzureOpenAI();
    const result = shield(client);
    expect(result).not.toBeNull();
    expect(typeof result).toBe("object");
  });
});

// ---------------------------------------------------------------------------
// shield() TypeError for unsupported types
// ---------------------------------------------------------------------------

describe("shield() TypeError for unsupported types", () => {
  it("throws TypeError for an unrecognized class", () => {
    expect(() => shield(new UnknownClient())).toThrow(TypeError);
  });

  it("TypeError message contains 'Unsupported client type'", () => {
    expect(() => shield(new UnknownClient())).toThrow("Unsupported client type");
  });

  it("TypeError message lists openai.OpenAI as supported", () => {
    try {
      shield(new UnknownClient());
      expect.fail("should have thrown");
    } catch (err) {
      expect(err).toBeInstanceOf(TypeError);
      expect((err as TypeError).message).toContain("openai.OpenAI");
    }
  });

  it("throws TypeError for a plain object literal", () => {
    // Object literal has constructor name "Object"
    expect(() => shield({} as object)).toThrow(TypeError);
  });
});

// ---------------------------------------------------------------------------
// shield() default config
// ---------------------------------------------------------------------------

describe("shield() default config", () => {
  it("applies default config when no options passed", () => {
    const client = new OpenAI();
    expect(() => shield(client)).not.toThrow();
  });

  it("accepts config options without throwing", () => {
    const client = new OpenAI();
    expect(() => shield(client, { vault: "memory" })).not.toThrow();
  });
});
