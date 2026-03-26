/**
 * Unit tests for the Vercel AI SDK middleware (Task 21.2).
 *
 * Tests verify:
 *  - PII is masked in transformParams (outgoing prompt)
 *  - Original values are restored in wrapGenerate (non-streaming response)
 *  - Original values are restored in wrapStream (streaming response)
 *  - Middleware is composable via wrapLanguageModel
 *
 * No real LLM API calls are made — doGenerate / doStream are mocked directly.
 */

import { describe, it, expect, vi } from "vitest";
import { wrapLanguageModel } from "ai";
import type {
  LanguageModelV1,
  LanguageModelV1CallOptions,
  LanguageModelV1StreamPart,
} from "@ai-sdk/provider";
import { Pipeline } from "../src/core/pipeline.js";
import { loadConfig } from "../src/core/config.js";
import { createPrivacyLensMiddleware } from "../src/adapters/vercel-ai.js";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makePipeline(): Pipeline {
  return new Pipeline(loadConfig());
}

/**
 * Build a minimal LanguageModelV1 stub.
 * doGenerate and doStream are vi.fn() so tests can control their return values.
 */
function makeStubModel(
  doGenerateFn?: () => ReturnType<LanguageModelV1["doGenerate"]>,
  doStreamFn?: () => ReturnType<LanguageModelV1["doStream"]>
): LanguageModelV1 {
  return {
    specificationVersion: "v1",
    provider: "test-provider",
    modelId: "test-model",
    defaultObjectGenerationMode: undefined,
    doGenerate: vi.fn(doGenerateFn ?? (() => Promise.resolve({
      text: "default response",
      finishReason: "stop",
      usage: { promptTokens: 5, completionTokens: 5 },
      rawCall: { rawPrompt: null, rawSettings: {} },
    }))),
    doStream: vi.fn(doStreamFn ?? (() => Promise.resolve({
      stream: new ReadableStream({ start(c) { c.close(); } }),
      rawCall: { rawPrompt: null, rawSettings: {} },
    }))),
  };
}

/**
 * Build a minimal LanguageModelV1CallOptions for a user message.
 */
function makeParams(text: string): LanguageModelV1CallOptions {
  return {
    inputFormat: "messages",
    mode: { type: "regular" },
    prompt: [
      {
        role: "user",
        content: [{ type: "text", text }],
      },
    ],
  };
}

/**
 * Build a ReadableStream of LanguageModelV1StreamPart from an array of text deltas.
 */
function makeTextStream(
  deltas: string[]
): ReadableStream<LanguageModelV1StreamPart> {
  return new ReadableStream({
    start(controller) {
      for (const delta of deltas) {
        controller.enqueue({ type: "text-delta", textDelta: delta });
      }
      controller.enqueue({
        type: "finish",
        finishReason: "stop",
        usage: { promptTokens: 5, completionTokens: 5 },
      } as LanguageModelV1StreamPart);
      controller.close();
    },
  });
}

/**
 * Collect all text-delta parts from a ReadableStream into a single string.
 */
async function collectStream(
  stream: ReadableStream<LanguageModelV1StreamPart>
): Promise<string> {
  const reader = stream.getReader();
  let result = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    if (value.type === "text-delta") result += value.textDelta;
  }
  return result;
}

/**
 * Extract the text content from the first user message in a prompt.
 */
function firstUserText(params: LanguageModelV1CallOptions): string {
  const msg = params.prompt[0];
  if (!msg || msg.role !== "user") return "";
  const part = (msg.content as Array<{ type: string; text?: string }>)[0];
  return part?.text ?? "";
}

// ---------------------------------------------------------------------------
// transformParams: PII masking
// ---------------------------------------------------------------------------

describe("createPrivacyLensMiddleware — transformParams", () => {
  it("masks email PII in the outgoing prompt", async () => {
    const pipeline = makePipeline();
    const middleware = createPrivacyLensMiddleware(pipeline);

    const params = makeParams("My email is alice@example.com");
    const transformed = await middleware.transformParams!({
      type: "generate",
      params,
    });

    const text = firstUserText(transformed);
    expect(text).not.toContain("alice@example.com");
    expect(text).toMatch(/\[EMAIL_\d+\]/);
  });

  it("masks SSN PII in the outgoing prompt", async () => {
    const pipeline = makePipeline();
    const middleware = createPrivacyLensMiddleware(pipeline);

    const params = makeParams("SSN: 123-45-6789");
    const transformed = await middleware.transformParams!({
      type: "generate",
      params,
    });

    const text = firstUserText(transformed);
    expect(text).not.toContain("123-45-6789");
    expect(text).toMatch(/\[SSN_\d+\]/);
  });

  it("passes through text with no PII unchanged", async () => {
    const pipeline = makePipeline();
    const middleware = createPrivacyLensMiddleware(pipeline);

    const params = makeParams("What is the capital of France?");
    const transformed = await middleware.transformParams!({
      type: "generate",
      params,
    });

    expect(firstUserText(transformed)).toBe("What is the capital of France?");
  });

  it("tokenizes system message content", async () => {
    const pipeline = makePipeline();
    const middleware = createPrivacyLensMiddleware(pipeline);

    const params: LanguageModelV1CallOptions = {
      inputFormat: "messages",
      mode: { type: "regular" },
      prompt: [
        { role: "system", content: "User email: alice@example.com" },
        {
          role: "user",
          content: [{ type: "text", text: "Hello" }],
        },
      ],
    };

    const transformed = await middleware.transformParams!({
      type: "generate",
      params,
    });

    const systemMsg = transformed.prompt[0];
    expect(systemMsg?.role).toBe("system");
    if (systemMsg?.role === "system") {
      expect(systemMsg.content).not.toContain("alice@example.com");
      expect(systemMsg.content).toMatch(/\[EMAIL_\d+\]/);
    }
  });
});

// ---------------------------------------------------------------------------
// wrapGenerate: response de-tokenization
// ---------------------------------------------------------------------------

describe("createPrivacyLensMiddleware — wrapGenerate", () => {
  it("restores PII in the generated text", async () => {
    const pipeline = makePipeline();
    const middleware = createPrivacyLensMiddleware(pipeline);

    // First tokenize to populate the vault
    const params = makeParams("My email is alice@example.com");
    const transformed = await middleware.transformParams!({
      type: "generate",
      params,
    });

    // The "model" echoes back the token
    const token = firstUserText(transformed).match(/\[EMAIL_\d+\]/)?.[0] ?? "[EMAIL_1]";

    const result = await middleware.wrapGenerate!({
      doGenerate: () =>
        Promise.resolve({
          text: `Your email is ${token}.`,
          finishReason: "stop",
          usage: { promptTokens: 5, completionTokens: 5 },
          rawCall: { rawPrompt: null, rawSettings: {} },
        }),
      doStream: makeStubModel().doStream,
      params: transformed,
      model: makeStubModel(),
    });

    expect(result.text).toContain("alice@example.com");
    expect(result.text).not.toMatch(/\[EMAIL_\d+\]/);
  });

  it("leaves response unchanged when no tokens present", async () => {
    const pipeline = makePipeline();
    const middleware = createPrivacyLensMiddleware(pipeline);

    const params = makeParams("Hello");
    const transformed = await middleware.transformParams!({
      type: "generate",
      params,
    });

    const result = await middleware.wrapGenerate!({
      doGenerate: () =>
        Promise.resolve({
          text: "Hi there!",
          finishReason: "stop",
          usage: { promptTokens: 2, completionTokens: 3 },
          rawCall: { rawPrompt: null, rawSettings: {} },
        }),
      doStream: makeStubModel().doStream,
      params: transformed,
      model: makeStubModel(),
    });

    expect(result.text).toBe("Hi there!");
  });

  it("leaves unknown tokens unchanged in response", async () => {
    const pipeline = makePipeline();
    const middleware = createPrivacyLensMiddleware(pipeline);

    const params = makeParams("Hello");
    const transformed = await middleware.transformParams!({
      type: "generate",
      params,
    });

    const result = await middleware.wrapGenerate!({
      doGenerate: () =>
        Promise.resolve({
          text: "Token [EMAIL_99] is unknown.",
          finishReason: "stop",
          usage: { promptTokens: 2, completionTokens: 5 },
          rawCall: { rawPrompt: null, rawSettings: {} },
        }),
      doStream: makeStubModel().doStream,
      params: transformed,
      model: makeStubModel(),
    });

    expect(result.text).toContain("[EMAIL_99]");
  });

  it("preserves non-text fields in the generate result", async () => {
    const pipeline = makePipeline();
    const middleware = createPrivacyLensMiddleware(pipeline);

    const params = makeParams("Hello");
    const transformed = await middleware.transformParams!({
      type: "generate",
      params,
    });

    const result = await middleware.wrapGenerate!({
      doGenerate: () =>
        Promise.resolve({
          text: "Hi",
          finishReason: "stop",
          usage: { promptTokens: 2, completionTokens: 1 },
          rawCall: { rawPrompt: "raw", rawSettings: { temperature: 0.5 } },
        }),
      doStream: makeStubModel().doStream,
      params: transformed,
      model: makeStubModel(),
    });

    expect(result.finishReason).toBe("stop");
    expect(result.usage.promptTokens).toBe(2);
    expect(result.rawCall.rawSettings).toEqual({ temperature: 0.5 });
  });
});

// ---------------------------------------------------------------------------
// wrapStream: streaming de-tokenization
// ---------------------------------------------------------------------------

describe("createPrivacyLensMiddleware — wrapStream", () => {
  it("restores PII in streamed text-delta parts", async () => {
    const pipeline = makePipeline();
    const middleware = createPrivacyLensMiddleware(pipeline);

    const params = makeParams("My email is alice@example.com");
    const transformed = await middleware.transformParams!({
      type: "stream",
      params,
    });

    const token = firstUserText(transformed).match(/\[EMAIL_\d+\]/)?.[0] ?? "[EMAIL_1]";

    const result = await middleware.wrapStream!({
      doGenerate: makeStubModel().doGenerate,
      doStream: () =>
        Promise.resolve({
          stream: makeTextStream(["Your email is ", token, "."]),
          rawCall: { rawPrompt: null, rawSettings: {} },
        }),
      params: transformed,
      model: makeStubModel(),
    });

    const text = await collectStream(result.stream);
    expect(text).toContain("alice@example.com");
    expect(text).not.toMatch(/\[EMAIL_\d+\]/);
  });

  it("handles split tokens across chunks", async () => {
    const pipeline = makePipeline();
    const middleware = createPrivacyLensMiddleware(pipeline);

    const params = makeParams("My email is alice@example.com");
    const transformed = await middleware.transformParams!({
      type: "stream",
      params,
    });

    const token = firstUserText(transformed).match(/\[EMAIL_\d+\]/)?.[0] ?? "[EMAIL_1]";
    // Split the token across two chunks
    const half = Math.floor(token.length / 2);
    const part1 = token.slice(0, half);
    const part2 = token.slice(half);

    const result = await middleware.wrapStream!({
      doGenerate: makeStubModel().doGenerate,
      doStream: () =>
        Promise.resolve({
          stream: makeTextStream(["Email: ", part1, part2]),
          rawCall: { rawPrompt: null, rawSettings: {} },
        }),
      params: transformed,
      model: makeStubModel(),
    });

    const text = await collectStream(result.stream);
    expect(text).toContain("alice@example.com");
    expect(text).not.toMatch(/\[EMAIL_\d+\]/);
  });

  it("passes through non-text-delta stream parts unchanged", async () => {
    const pipeline = makePipeline();
    const middleware = createPrivacyLensMiddleware(pipeline);

    const params = makeParams("Hello");
    const transformed = await middleware.transformParams!({
      type: "stream",
      params,
    });

    const finishPart: LanguageModelV1StreamPart = {
      type: "finish",
      finishReason: "stop",
      usage: { promptTokens: 2, completionTokens: 1 },
    } as LanguageModelV1StreamPart;

    const result = await middleware.wrapStream!({
      doGenerate: makeStubModel().doGenerate,
      doStream: () =>
        Promise.resolve({
          stream: new ReadableStream({
            start(c) {
              c.enqueue({ type: "text-delta", textDelta: "Hi" });
              c.enqueue(finishPart);
              c.close();
            },
          }),
          rawCall: { rawPrompt: null, rawSettings: {} },
        }),
      params: transformed,
      model: makeStubModel(),
    });

    const parts: LanguageModelV1StreamPart[] = [];
    const reader = result.stream.getReader();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      parts.push(value);
    }

    const types = parts.map((p) => p.type);
    expect(types).toContain("text-delta");
    expect(types).toContain("finish");
  });
});

// ---------------------------------------------------------------------------
// Composability via wrapLanguageModel
// ---------------------------------------------------------------------------

describe("createPrivacyLensMiddleware — wrapLanguageModel composability", () => {
  it("can be applied via wrapLanguageModel and masks PII in doGenerate", async () => {
    const pipeline = makePipeline();

    // Capture what the stub model receives
    let capturedParams: LanguageModelV1CallOptions | null = null;

    const stubModel = makeStubModel(() => {
      return Promise.resolve({
        text: "I received your message.",
        finishReason: "stop",
        usage: { promptTokens: 5, completionTokens: 5 },
        rawCall: { rawPrompt: null, rawSettings: {} },
      });
    });

    // Override doGenerate to capture params
    (stubModel.doGenerate as ReturnType<typeof vi.fn>).mockImplementation(
      (opts: LanguageModelV1CallOptions) => {
        capturedParams = opts;
        return Promise.resolve({
          text: "I received your message.",
          finishReason: "stop",
          usage: { promptTokens: 5, completionTokens: 5 },
          rawCall: { rawPrompt: null, rawSettings: {} },
        });
      }
    );

    const wrappedModel = wrapLanguageModel({
      model: stubModel,
      middleware: createPrivacyLensMiddleware(pipeline),
    });

    await wrappedModel.doGenerate({
      inputFormat: "messages",
      mode: { type: "regular" },
      prompt: [
        {
          role: "user",
          content: [{ type: "text", text: "My email is alice@example.com" }],
        },
      ],
    });

    expect(capturedParams).not.toBeNull();
    const sentText = firstUserText(capturedParams!);
    expect(sentText).not.toContain("alice@example.com");
    expect(sentText).toMatch(/\[EMAIL_\d+\]/);
  });

  it("can be composed with a second middleware via wrapLanguageModel", async () => {
    const pipeline = makePipeline();

    // A simple pass-through middleware to verify composability
    const passthroughMiddleware = {
      async transformParams({ params }: { type: string; params: LanguageModelV1CallOptions }) {
        return params;
      },
    };

    const stubModel = makeStubModel();

    // Should not throw — composing two middlewares
    expect(() =>
      wrapLanguageModel({
        model: stubModel,
        middleware: [createPrivacyLensMiddleware(pipeline), passthroughMiddleware],
      })
    ).not.toThrow();
  });

  it("restores PII in the response returned by wrapLanguageModel", async () => {
    const pipeline = makePipeline();

    // We need to capture the token the model receives, then echo it back
    let capturedToken = "";

    const stubModel = makeStubModel();
    (stubModel.doGenerate as ReturnType<typeof vi.fn>).mockImplementation(
      (opts: LanguageModelV1CallOptions) => {
        const text = firstUserText(opts);
        capturedToken = text.match(/\[EMAIL_\d+\]/)?.[0] ?? "";
        return Promise.resolve({
          text: `Your email token is ${capturedToken}.`,
          finishReason: "stop",
          usage: { promptTokens: 5, completionTokens: 5 },
          rawCall: { rawPrompt: null, rawSettings: {} },
        });
      }
    );

    const wrappedModel = wrapLanguageModel({
      model: stubModel,
      middleware: createPrivacyLensMiddleware(pipeline),
    });

    const result = await wrappedModel.doGenerate({
      inputFormat: "messages",
      mode: { type: "regular" },
      prompt: [
        {
          role: "user",
          content: [{ type: "text", text: "My email is alice@example.com" }],
        },
      ],
    });

    expect(result.text).toContain("alice@example.com");
    expect(result.text).not.toMatch(/\[EMAIL_\d+\]/);
  });
});
