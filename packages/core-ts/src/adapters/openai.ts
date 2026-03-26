/**
 * TypeScript OpenAI adapter for PrivacyLens.
 *
 * Uses a Proxy to intercept `chat.completions.create`, tokenize messages
 * before sending to OpenAI, and de-tokenize the response on return.
 * Supports both non-streaming and streaming modes.
 * No `any` in the public API surface.
 */

import type { Pipeline } from "../core/pipeline.js";

// ---------------------------------------------------------------------------
// Minimal OpenAI type surface (avoids hard runtime dependency on openai pkg)
// ---------------------------------------------------------------------------

/** A single message in an OpenAI chat completion request. */
export interface ChatMessage {
  role: string;
  content: string;
  [key: string]: unknown;
}

/** Parameters for chat.completions.create (non-streaming). */
export interface ChatCompletionCreateParamsNonStreaming {
  messages: ChatMessage[];
  stream?: false;
  [key: string]: unknown;
}

/** Parameters for chat.completions.create (streaming). */
export interface ChatCompletionCreateParamsStreaming {
  messages: ChatMessage[];
  stream: true;
  [key: string]: unknown;
}

export type ChatCompletionCreateParams =
  | ChatCompletionCreateParamsNonStreaming
  | ChatCompletionCreateParamsStreaming;

/** A single choice in a non-streaming chat completion response. */
export interface ChatCompletionChoice {
  message: { role: string; content: string | null; [key: string]: unknown };
  [key: string]: unknown;
}

/** A non-streaming chat completion response. */
export interface ChatCompletion {
  choices: ChatCompletionChoice[];
  [key: string]: unknown;
}

/** A delta in a streaming chunk. */
export interface ChatCompletionChunkDelta {
  content?: string | null;
  role?: string;
  [key: string]: unknown;
}

/** A single choice in a streaming chunk. */
export interface ChatCompletionChunkChoice {
  delta: ChatCompletionChunkDelta;
  [key: string]: unknown;
}

/** A single streaming chunk. */
export interface ChatCompletionChunk {
  choices: ChatCompletionChunkChoice[];
  [key: string]: unknown;
}

/** Minimal async-iterable stream returned by OpenAI when stream=true. */
export interface ChatCompletionStream
  extends AsyncIterable<ChatCompletionChunk> {
  [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// Session ID generator
// ---------------------------------------------------------------------------

function newSessionId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

// ---------------------------------------------------------------------------
// _StreamBuffer — handles tokens split across chunks
// ---------------------------------------------------------------------------

/**
 * Accumulates partial `[TOKEN_N]` strings across streaming chunks and flushes
 * complete tokens through the de-tokenizer as soon as they are fully received.
 *
 * A token looks like `[ENTITY_TYPE_N]`. If a chunk ends mid-token (e.g. the
 * chunk ends with `[EMA` and the next starts with `IL_1]`), the buffer holds
 * the partial token until the closing `]` arrives.
 */
export class _StreamBuffer {
  private _buf = "";
  private readonly _pipeline: Pipeline;
  private readonly _sessionId: string;

  // Matches a complete token: [UPPER_DIGITS]
  private static readonly COMPLETE_TOKEN_RE = /\[[A-Z][A-Z0-9_]*_\d+\]/g;
  // Detects the start of a possible partial token at the end of the buffer
  private static readonly PARTIAL_TOKEN_RE = /\[[A-Z][A-Z0-9_]*(?:_\d*)?$/;

  constructor(pipeline: Pipeline, sessionId: string) {
    this._pipeline = pipeline;
    this._sessionId = sessionId;
  }

  /**
   * Feed a new chunk of text. Returns the safe, de-tokenized prefix that can
   * be emitted immediately. Any partial token at the end is held in the buffer.
   */
  feed(chunk: string): string {
    this._buf += chunk;

    // Find the last position that is definitely not inside a partial token.
    const partialMatch = _StreamBuffer.PARTIAL_TOKEN_RE.exec(this._buf);
    const safeEnd =
      partialMatch !== null ? partialMatch.index : this._buf.length;

    const safe = this._buf.slice(0, safeEnd);
    this._buf = this._buf.slice(safeEnd);

    return this._pipeline.detokenize(safe, this._sessionId);
  }

  /**
   * Flush any remaining buffered content (called when the stream ends).
   * Partial tokens that never completed are left unchanged.
   */
  flush(): string {
    const remaining = this._buf;
    this._buf = "";
    return this._pipeline.detokenize(remaining, this._sessionId);
  }
}

// ---------------------------------------------------------------------------
// Streaming wrapper
// ---------------------------------------------------------------------------

/**
 * Wraps an OpenAI streaming response, de-tokenizing each chunk's delta
 * content through a `_StreamBuffer` as it arrives.
 */
async function* detokenizeStream(
  stream: ChatCompletionStream,
  pipeline: Pipeline,
  sessionId: string
): AsyncGenerator<ChatCompletionChunk> {
  const buffer = new _StreamBuffer(pipeline, sessionId);

  for await (const chunk of stream) {
    const choices = chunk.choices.map((choice) => {
      const deltaContent = choice.delta.content;
      if (typeof deltaContent === "string") {
        const detokenized = buffer.feed(deltaContent);
        return {
          ...choice,
          delta: { ...choice.delta, content: detokenized },
        };
      }
      return choice;
    });

    yield { ...chunk, choices };
  }

  // Flush any remaining partial token at stream end.
  const tail = buffer.flush();
  if (tail.length > 0) {
    // Emit a synthetic final chunk carrying the flushed tail on the first choice.
    yield {
      choices: [
        {
          delta: { content: tail },
          index: 0,
          finish_reason: null,
        },
      ],
    } as ChatCompletionChunk;
  }
}

// ---------------------------------------------------------------------------
// Completions proxy
// ---------------------------------------------------------------------------

/**
 * Proxy for `client.chat.completions` that intercepts `create`.
 */
function makeCompletionsProxy(
  realCompletions: {
    create(params: ChatCompletionCreateParamsNonStreaming): Promise<ChatCompletion>;
    create(params: ChatCompletionCreateParamsStreaming): Promise<ChatCompletionStream>;
    create(params: ChatCompletionCreateParams): Promise<ChatCompletion | ChatCompletionStream>;
    [key: string]: unknown;
  },
  pipeline: Pipeline
): typeof realCompletions {
  return new Proxy(realCompletions, {
    get(target, prop: string | symbol) {
      if (prop === "create") {
        return async (
          params: ChatCompletionCreateParams
        ): Promise<ChatCompletion | ChatCompletionStream | AsyncGenerator<ChatCompletionChunk>> => {
          const sessionId = newSessionId();

          // Tokenize messages before sending to OpenAI.
          const tokenizedMessages = await pipeline.tokenizeMessages(
            params.messages,
            sessionId
          );

          if (params.stream === true) {
            // Streaming path
            const streamParams: ChatCompletionCreateParamsStreaming = {
              ...params,
              messages: tokenizedMessages,
              stream: true,
            };
            const rawStream = await (
              target.create as (
                p: ChatCompletionCreateParamsStreaming
              ) => Promise<ChatCompletionStream>
            )(streamParams);

            return detokenizeStream(rawStream, pipeline, sessionId);
          }

          // Non-streaming path
          const nonStreamParams: ChatCompletionCreateParamsNonStreaming = {
            ...params,
            messages: tokenizedMessages,
            stream: false,
          };
          const response = await (
            target.create as (
              p: ChatCompletionCreateParamsNonStreaming
            ) => Promise<ChatCompletion>
          )(nonStreamParams);

          // De-tokenize each choice's message content.
          const detokenizedChoices = response.choices.map((choice) => {
            if (typeof choice.message.content === "string") {
              return {
                ...choice,
                message: {
                  ...choice.message,
                  content: pipeline.detokenize(
                    choice.message.content,
                    sessionId
                  ),
                },
              };
            }
            return choice;
          });

          return { ...response, choices: detokenizedChoices };
        };
      }

      return Reflect.get(target, prop);
    },
  });
}

// ---------------------------------------------------------------------------
// Chat proxy
// ---------------------------------------------------------------------------

function makeChatProxy(
  realChat: { completions: Parameters<typeof makeCompletionsProxy>[0]; [key: string]: unknown },
  pipeline: Pipeline
): typeof realChat {
  return new Proxy(realChat, {
    get(target, prop: string | symbol) {
      if (prop === "completions") {
        return makeCompletionsProxy(target.completions, pipeline);
      }
      return Reflect.get(target, prop);
    },
  });
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/** Minimal shape of an OpenAI client that shieldOpenAI requires. */
export interface OpenAIClientLike {
  chat: {
    completions: {
      create(params: ChatCompletionCreateParamsNonStreaming): Promise<ChatCompletion>;
      create(params: ChatCompletionCreateParamsStreaming): Promise<ChatCompletionStream>;
      create(params: ChatCompletionCreateParams): Promise<ChatCompletion | ChatCompletionStream>;
      [key: string]: unknown;
    };
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

/**
 * Wrap an OpenAI client with PII masking via a Proxy.
 *
 * Intercepts `client.chat.completions.create`, tokenizes messages before
 * sending to OpenAI, and de-tokenizes the response (or each streaming chunk)
 * before returning to the caller.
 *
 * All non-`messages` parameters are forwarded unmodified.
 * No `any` in the public API surface.
 *
 * @param client - An OpenAI (or compatible) client instance.
 * @param pipeline - The PrivacyLens pipeline to use for masking.
 * @returns A Proxy wrapping `client` with PII masking applied.
 */
export function shieldOpenAI<T extends OpenAIClientLike>(
  client: T,
  pipeline: Pipeline
): T {
  return new Proxy(client, {
    get(target, prop: string | symbol) {
      if (prop === "chat") {
        return makeChatProxy(target.chat, pipeline);
      }
      return Reflect.get(target, prop);
    },
  });
}
