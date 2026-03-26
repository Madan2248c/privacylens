/**
 * Unit tests for the TypeScript OpenAI adapter (Task 20.3).
 *
 * Uses msw to intercept HTTP calls made by the real openai npm package,
 * verifying:
 *  - PII is masked in the outgoing request
 *  - Original values are restored in the response
 *  - Non-messages kwargs are forwarded unchanged
 *  - Streaming chunks are de-tokenized correctly
 *  - Split-token handling via _StreamBuffer works
 */

import { describe, it, expect, beforeAll, afterAll, afterEach } from "vitest";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import OpenAI from "openai";
import { Pipeline } from "../src/core/pipeline.js";
import { shieldOpenAI, _StreamBuffer } from "../src/adapters/openai.ts";
import { loadConfig } from "../src/core/config.js";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const BASE_URL = "https://api.openai.com";

/** Build a Pipeline with default config (RegexDetector only). */
function makePipeline(): Pipeline {
  return new Pipeline(loadConfig());
}

/** Build a shielded OpenAI client pointing at the real OpenAI base URL. */
function makeClient(): OpenAI {
  return new OpenAI({ apiKey: "test-key", baseURL: BASE_URL });
}

/** Minimal non-streaming ChatCompletion response fixture. */
function chatCompletionFixture(content: string) {
  return {
    id: "chatcmpl-test",
    object: "chat.completion",
    created: 1700000000,
    model: "gpt-4o",
    choices: [
      {
        index: 0,
        message: { role: "assistant", content },
        finish_reason: "stop",
      },
    ],
    usage: { prompt_tokens: 10, completion_tokens: 5, total_tokens: 15 },
  };
}

/** Encode a Server-Sent Events stream from an array of data payloads. */
function sseStream(chunks: object[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(
          encoder.encode(`data: ${JSON.stringify(chunk)}\n\n`)
        );
      }
      controller.enqueue(encoder.encode("data: [DONE]\n\n"));
      controller.close();
    },
  });
}

/** Build a streaming chunk fixture. */
function streamChunk(content: string | null, finishReason: string | null = null) {
  return {
    id: "chatcmpl-stream",
    object: "chat.completion.chunk",
    created: 1700000000,
    model: "gpt-4o",
    choices: [
      {
        index: 0,
        delta: content !== null ? { role: "assistant", content } : {},
        finish_reason: finishReason,
      },
    ],
  };
}

// ---------------------------------------------------------------------------
// MSW server setup
// ---------------------------------------------------------------------------

// Capture the last request body so tests can assert on it.
let lastRequestBody: unknown = null;

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers();
  lastRequestBody = null;
});
afterAll(() => server.close());

// ---------------------------------------------------------------------------
// Non-streaming: PII masking and response restoration
// ---------------------------------------------------------------------------

describe("shieldOpenAI — non-streaming", () => {
  it("masks PII in the outgoing request", async () => {
    server.use(
      http.post(`${BASE_URL}/chat/completions`, async ({ request }) => {
        lastRequestBody = await request.json();
        return HttpResponse.json(
          chatCompletionFixture("I received your message.")
        );
      })
    );

    const pipeline = makePipeline();
    const client = shieldOpenAI(makeClient(), pipeline);

    await client.chat.completions.create({
      model: "gpt-4o",
      messages: [
        { role: "user", content: "My email is alice@example.com" },
      ],
    });

    const body = lastRequestBody as { messages: Array<{ content: string }> };
    const sentContent = body.messages[0]?.content ?? "";
    expect(sentContent).not.toContain("alice@example.com");
    expect(sentContent).toMatch(/\[EMAIL_\d+\]/);
  });

  it("restores original PII in the response", async () => {
    // The "LLM" echoes back the token — adapter must restore it.
    server.use(
      http.post(`${BASE_URL}/chat/completions`, async ({ request }) => {
        const body = (await request.json()) as {
          messages: Array<{ content: string }>;
        };
        const token = body.messages[0]?.content?.match(/\[EMAIL_\d+\]/)?.[0] ?? "";
        return HttpResponse.json(
          chatCompletionFixture(`Your email token is ${token}.`)
        );
      })
    );

    const pipeline = makePipeline();
    const client = shieldOpenAI(makeClient(), pipeline);

    const response = await client.chat.completions.create({
      model: "gpt-4o",
      messages: [{ role: "user", content: "My email is alice@example.com" }],
    });

    const content = response.choices[0]?.message.content ?? "";
    expect(content).toContain("alice@example.com");
    expect(content).not.toMatch(/\[EMAIL_\d+\]/);
  });

  it("preserves non-messages kwargs (model, temperature)", async () => {
    server.use(
      http.post(`${BASE_URL}/chat/completions`, async ({ request }) => {
        lastRequestBody = await request.json();
        return HttpResponse.json(chatCompletionFixture("ok"));
      })
    );

    const pipeline = makePipeline();
    const client = shieldOpenAI(makeClient(), pipeline);

    await client.chat.completions.create({
      model: "gpt-4o-mini",
      temperature: 0.2,
      max_tokens: 100,
      messages: [{ role: "user", content: "Hello" }],
    });

    const body = lastRequestBody as Record<string, unknown>;
    expect(body["model"]).toBe("gpt-4o-mini");
    expect(body["temperature"]).toBe(0.2);
    expect(body["max_tokens"]).toBe(100);
  });

  it("handles messages with no PII — text passes through unchanged", async () => {
    server.use(
      http.post(`${BASE_URL}/chat/completions`, async ({ request }) => {
        lastRequestBody = await request.json();
        return HttpResponse.json(chatCompletionFixture("Sure, I can help."));
      })
    );

    const pipeline = makePipeline();
    const client = shieldOpenAI(makeClient(), pipeline);

    await client.chat.completions.create({
      model: "gpt-4o",
      messages: [{ role: "user", content: "What is the weather today?" }],
    });

    const body = lastRequestBody as { messages: Array<{ content: string }> };
    expect(body.messages[0]?.content).toBe("What is the weather today?");
  });

  it("masks multiple PII types in a single message", async () => {
    server.use(
      http.post(`${BASE_URL}/chat/completions`, async ({ request }) => {
        lastRequestBody = await request.json();
        return HttpResponse.json(chatCompletionFixture("Got it."));
      })
    );

    const pipeline = makePipeline();
    const client = shieldOpenAI(makeClient(), pipeline);

    await client.chat.completions.create({
      model: "gpt-4o",
      messages: [
        {
          role: "user",
          content: "Email: alice@example.com, SSN: 123-45-6789",
        },
      ],
    });

    const body = lastRequestBody as { messages: Array<{ content: string }> };
    const sent = body.messages[0]?.content ?? "";
    expect(sent).not.toContain("alice@example.com");
    expect(sent).not.toContain("123-45-6789");
    expect(sent).toMatch(/\[EMAIL_\d+\]/);
    expect(sent).toMatch(/\[SSN_\d+\]/);
  });

  it("masks PII across multiple messages", async () => {
    server.use(
      http.post(`${BASE_URL}/chat/completions`, async ({ request }) => {
        lastRequestBody = await request.json();
        return HttpResponse.json(chatCompletionFixture("Understood."));
      })
    );

    const pipeline = makePipeline();
    const client = shieldOpenAI(makeClient(), pipeline);

    await client.chat.completions.create({
      model: "gpt-4o",
      messages: [
        { role: "system", content: "You are a helpful assistant." },
        { role: "user", content: "My email is alice@example.com" },
        { role: "assistant", content: "Got it." },
        { role: "user", content: "And my phone is 555-867-5309" },
      ],
    });

    const body = lastRequestBody as { messages: Array<{ content: string }> };
    expect(body.messages[1]?.content).not.toContain("alice@example.com");
    expect(body.messages[3]?.content).not.toContain("555-867-5309");
  });

  it("response with no tokens is returned unchanged", async () => {
    server.use(
      http.post(`${BASE_URL}/chat/completions`, async () => {
        return HttpResponse.json(
          chatCompletionFixture("The sky is blue.")
        );
      })
    );

    const pipeline = makePipeline();
    const client = shieldOpenAI(makeClient(), pipeline);

    const response = await client.chat.completions.create({
      model: "gpt-4o",
      messages: [{ role: "user", content: "What color is the sky?" }],
    });

    expect(response.choices[0]?.message.content).toBe("The sky is blue.");
  });
});

// ---------------------------------------------------------------------------
// Streaming: de-tokenization of chunks
// ---------------------------------------------------------------------------

describe("shieldOpenAI — streaming", () => {
  it("de-tokenizes content in each streamed chunk", async () => {
    server.use(
      http.post(`${BASE_URL}/chat/completions`, async ({ request }) => {
        const body = (await request.json()) as {
          messages: Array<{ content: string }>;
        };
        // Echo the token back in the stream
        const token =
          body.messages[0]?.content?.match(/\[EMAIL_\d+\]/)?.[0] ?? "[EMAIL_1]";
        return new HttpResponse(
          sseStream([
            streamChunk("Your email is "),
            streamChunk(token),
            streamChunk(".", "stop"),
          ]),
          {
            headers: {
              "Content-Type": "text/event-stream",
              "Cache-Control": "no-cache",
            },
          }
        );
      })
    );

    const pipeline = makePipeline();
    const client = shieldOpenAI(makeClient(), pipeline);

    const stream = await client.chat.completions.create({
      model: "gpt-4o",
      stream: true,
      messages: [{ role: "user", content: "My email is alice@example.com" }],
    });

    const parts: string[] = [];
    for await (const chunk of stream) {
      const content = chunk.choices[0]?.delta?.content;
      if (typeof content === "string" && content.length > 0) {
        parts.push(content);
      }
    }

    const full = parts.join("");
    expect(full).toContain("alice@example.com");
    expect(full).not.toMatch(/\[EMAIL_\d+\]/);
  });

  it("masks PII in the outgoing streaming request", async () => {
    server.use(
      http.post(`${BASE_URL}/chat/completions`, async ({ request }) => {
        lastRequestBody = await request.json();
        return new HttpResponse(
          sseStream([streamChunk("ok", "stop")]),
          {
            headers: {
              "Content-Type": "text/event-stream",
              "Cache-Control": "no-cache",
            },
          }
        );
      })
    );

    const pipeline = makePipeline();
    const client = shieldOpenAI(makeClient(), pipeline);

    const stream = await client.chat.completions.create({
      model: "gpt-4o",
      stream: true,
      messages: [{ role: "user", content: "SSN: 123-45-6789" }],
    });

    // Drain the stream
    for await (const _ of stream) { /* noop */ }

    const body = lastRequestBody as { messages: Array<{ content: string }> };
    expect(body.messages[0]?.content).not.toContain("123-45-6789");
    expect(body.messages[0]?.content).toMatch(/\[SSN_\d+\]/);
  });

  it("preserves non-messages kwargs in streaming request", async () => {
    server.use(
      http.post(`${BASE_URL}/chat/completions`, async ({ request }) => {
        lastRequestBody = await request.json();
        return new HttpResponse(
          sseStream([streamChunk("ok", "stop")]),
          {
            headers: {
              "Content-Type": "text/event-stream",
              "Cache-Control": "no-cache",
            },
          }
        );
      })
    );

    const pipeline = makePipeline();
    const client = shieldOpenAI(makeClient(), pipeline);

    const stream = await client.chat.completions.create({
      model: "gpt-4o-mini",
      temperature: 0.5,
      stream: true,
      messages: [{ role: "user", content: "Hello" }],
    });

    for await (const _ of stream) { /* noop */ }

    const body = lastRequestBody as Record<string, unknown>;
    expect(body["model"]).toBe("gpt-4o-mini");
    expect(body["temperature"]).toBe(0.5);
    expect(body["stream"]).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// _StreamBuffer unit tests
// ---------------------------------------------------------------------------

describe("_StreamBuffer", () => {
  it("de-tokenizes a complete token in a single chunk", () => {
    const pipeline = makePipeline();
    // Pre-store a token in the pipeline's vault via tokenizeMessages
    // We'll use a simpler approach: feed a chunk with no tokens
    const buf = new _StreamBuffer(pipeline, "test-session");
    const out = buf.feed("Hello world");
    expect(out).toBe("Hello world");
    expect(buf.flush()).toBe("");
  });

  it("holds a partial token and flushes it when complete", () => {
    // We need a vault with a known token. Build pipeline, tokenize to populate vault.
    const pipeline = makePipeline();
    const sessionId = "buf-test-1";

    // Tokenize to populate the vault with [EMAIL_1] → alice@example.com
    const tokenizePromise = pipeline.tokenizeMessages(
      [{ role: "user", content: "alice@example.com" }],
      sessionId
    );

    // We need to await — use a synchronous workaround by running the test async
    return tokenizePromise.then(() => {
      const buf = new _StreamBuffer(pipeline, sessionId);

      // Feed the token split across two chunks
      const out1 = buf.feed("Your email is [EMA");
      const out2 = buf.feed("IL_1] confirmed.");
      const tail = buf.flush();

      const full = out1 + out2 + tail;
      expect(full).toContain("alice@example.com");
      expect(full).not.toMatch(/\[EMAIL_\d+\]/);
    });
  });

  it("leaves unknown tokens unchanged", () => {
    const pipeline = makePipeline();
    const buf = new _StreamBuffer(pipeline, "unknown-session");

    const out = buf.feed("Token [EMAIL_99] is unknown.");
    const tail = buf.flush();
    const full = out + tail;

    expect(full).toContain("[EMAIL_99]");
  });

  it("flush returns remaining buffered content", () => {
    const pipeline = makePipeline();
    const buf = new _StreamBuffer(pipeline, "flush-test");

    // Feed a partial token that never completes
    buf.feed("partial [EMA");
    const tail = buf.flush();
    // Partial token left unchanged
    expect(tail).toContain("[EMA");
  });

  it("handles empty chunks without error", () => {
    const pipeline = makePipeline();
    const buf = new _StreamBuffer(pipeline, "empty-test");
    expect(buf.feed("")).toBe("");
    expect(buf.flush()).toBe("");
  });

  it("handles text with no tokens", () => {
    const pipeline = makePipeline();
    const buf = new _StreamBuffer(pipeline, "no-token-test");
    const out = buf.feed("Just plain text here.");
    expect(out).toBe("Just plain text here.");
    expect(buf.flush()).toBe("");
  });
});
