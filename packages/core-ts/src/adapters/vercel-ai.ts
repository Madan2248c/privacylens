/**
 * Vercel AI SDK middleware for PrivacyLens (Task 21.1).
 *
 * Implements `LanguageModelV1Middleware` to intercept language model calls,
 * tokenize PII in prompts before they reach the provider, and de-tokenize
 * responses before returning them to the caller.
 *
 * Usage:
 *   import { wrapLanguageModel } from "ai";
 *   import { createPrivacyLensMiddleware } from "privacylens/adapters/vercel-ai";
 *
 *   const model = wrapLanguageModel({
 *     model: openai("gpt-4o"),
 *     middleware: createPrivacyLensMiddleware(pipeline),
 *   });
 */

import type { LanguageModelV1Middleware } from "ai";
import type {
  LanguageModelV1,
  LanguageModelV1CallOptions,
  LanguageModelV1StreamPart,
} from "@ai-sdk/provider";
import type { Pipeline } from "../core/pipeline.js";

// ---------------------------------------------------------------------------
// Session ID threading
//
// transformParams returns a new params object. We use a WeakMap keyed on that
// object to carry the sessionId into wrapGenerate / wrapStream without
// mutating the params or relying on global state.
// ---------------------------------------------------------------------------

const sessionMap = new WeakMap<LanguageModelV1CallOptions, string>();

function newSessionId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

// ---------------------------------------------------------------------------
// Prompt tokenization helpers
// ---------------------------------------------------------------------------

/**
 * Tokenize all text content in a `LanguageModelV1Prompt` (array of messages).
 *
 * The Vercel AI SDK uses a low-level prompt format where:
 *  - system messages have a plain `content: string`
 *  - user/assistant messages have `content: Array<{type, text, ...}>`
 *
 * We tokenize every text string we find and return the mutated copy.
 */
async function tokenizePrompt(
  prompt: LanguageModelV1CallOptions["prompt"],
  pipeline: Pipeline,
  sessionId: string
): Promise<LanguageModelV1CallOptions["prompt"]> {
  const result: LanguageModelV1CallOptions["prompt"] = [];

  for (const message of prompt) {
    if (message.role === "system") {
      const tokenized = await pipeline.tokenizeMessages(
        [{ role: "system", content: message.content }],
        sessionId
      );
      result.push({ ...message, content: tokenized[0]?.content ?? message.content });
    } else if (message.role === "user" || message.role === "assistant") {
      // content is an array of parts; tokenize text parts
      const newContent = await Promise.all(
        (message.content as Array<{ type: string; text?: string; [key: string]: unknown }>).map(
          async (part) => {
            if (part.type === "text" && typeof part.text === "string") {
              const tokenized = await pipeline.tokenizeMessages(
                [{ role: message.role as string, content: part.text }],
                sessionId
              );
              return { ...part, text: tokenized[0]?.content ?? part.text };
            }
            return part;
          }
        )
      );
      // Cast back — we only changed text fields, structure is preserved
      result.push({ ...message, content: newContent } as typeof message);
    } else {
      // tool messages — pass through unchanged
      result.push(message);
    }
  }

  return result;
}

// ---------------------------------------------------------------------------
// Stream de-tokenization
// ---------------------------------------------------------------------------

/**
 * Wrap a `ReadableStream<LanguageModelV1StreamPart>` to de-tokenize
 * `text-delta` parts as they arrive.
 *
 * Tokens like `[EMAIL_1]` may be split across chunks, so we use a simple
 * accumulation buffer that holds back any partial `[...]` sequence and
 * flushes it once the closing `]` arrives.
 */
function detokenizeStream(
  stream: ReadableStream<LanguageModelV1StreamPart>,
  pipeline: Pipeline,
  sessionId: string
): ReadableStream<LanguageModelV1StreamPart> {
  // Regex that matches a complete token
  const TOKEN_RE = /\[[A-Z_]+_\d+\]/g;

  /**
   * Flush safe prefix: everything up to the last `[` that might be the start
   * of an incomplete token. If no `[` is present, flush everything.
   */
  function flushSafe(text: string): { safe: string; held: string } {
    const lastOpen = text.lastIndexOf("[");
    if (lastOpen === -1) {
      return { safe: text, held: "" };
    }
    // Check if there's a complete token after lastOpen
    const afterOpen = text.slice(lastOpen);
    if (/^\[[A-Z_]+_\d+\]/.test(afterOpen)) {
      // Complete token present — safe to flush all
      return { safe: text, held: "" };
    }
    // Partial token — hold from lastOpen onward
    return { safe: text.slice(0, lastOpen), held: text.slice(lastOpen) };
  }

  function detokenizeText(text: string): string {
    return text.replace(TOKEN_RE, (token) => {
      try {
        return pipeline.detokenize(token, sessionId);
      } catch {
        return token;
      }
    });
  }

  let buffer = "";

  const transformer = new TransformStream<LanguageModelV1StreamPart, LanguageModelV1StreamPart>({
    transform(chunk, controller) {
      if (chunk.type === "text-delta") {
        buffer += chunk.textDelta;
        const { safe, held } = flushSafe(buffer);
        buffer = held;
        if (safe.length > 0) {
          controller.enqueue({ type: "text-delta", textDelta: detokenizeText(safe) });
        }
      } else {
        controller.enqueue(chunk);
      }
    },
    flush(controller) {
      if (buffer.length > 0) {
        controller.enqueue({ type: "text-delta", textDelta: detokenizeText(buffer) });
        buffer = "";
      }
    },
  });

  return stream.pipeThrough(transformer);
}

// ---------------------------------------------------------------------------
// Middleware factory
// ---------------------------------------------------------------------------

/**
 * Create a PrivacyLens `LanguageModelV1Middleware` that tokenizes PII in
 * prompts and de-tokenizes responses.
 *
 * @param pipeline - A configured `Pipeline` instance.
 * @returns A `LanguageModelV1Middleware` compatible with `wrapLanguageModel`.
 */
export function createPrivacyLensMiddleware(
  pipeline: Pipeline
): LanguageModelV1Middleware {
  return {
    /**
     * Tokenize PII in the prompt before it reaches the model provider.
     * Stores the sessionId in a WeakMap keyed on the returned params object
     * so that wrapGenerate / wrapStream can retrieve it.
     */
    async transformParams({ params }: { type: "generate" | "stream"; params: LanguageModelV1CallOptions }) {
      const sessionId = newSessionId();
      const tokenizedPrompt = await tokenizePrompt(params.prompt, pipeline, sessionId);
      const newParams: LanguageModelV1CallOptions = { ...params, prompt: tokenizedPrompt };
      sessionMap.set(newParams, sessionId);
      return newParams;
    },

    /**
     * De-tokenize the generated text before returning to the caller.
     */
    async wrapGenerate({ doGenerate, params }: {
      doGenerate: () => ReturnType<LanguageModelV1["doGenerate"]>;
      doStream: () => ReturnType<LanguageModelV1["doStream"]>;
      params: LanguageModelV1CallOptions;
      model: LanguageModelV1;
    }) {
      const sessionId = sessionMap.get(params) ?? newSessionId();
      const result = await doGenerate();

      if (result.text === undefined) {
        return result;
      }
      return {
        ...result,
        text: pipeline.detokenize(result.text, sessionId),
      };
    },

    /**
     * De-tokenize each text-delta stream part before returning to the caller.
     */
    async wrapStream({ doStream, params }: {
      doGenerate: () => ReturnType<LanguageModelV1["doGenerate"]>;
      doStream: () => ReturnType<LanguageModelV1["doStream"]>;
      params: LanguageModelV1CallOptions;
      model: LanguageModelV1;
    }) {
      const sessionId = sessionMap.get(params) ?? newSessionId();
      const result = await doStream();

      return {
        ...result,
        stream: detokenizeStream(result.stream, pipeline, sessionId),
      };
    },
  };
}
