/**
 * Message normalization for PrivacyLens.
 *
 * Converts any supported message format into a canonical list of message dicts.
 */

/** A canonical message dict with at least role and content. */
export interface Message {
  role: string;
  content: string;
  [key: string]: unknown;
}

/** Anthropic-style input: a dict with a "messages" key. */
interface AnthropicStyleInput {
  messages: Message[];
  [key: string]: unknown;
}

/** All supported input types for normalizeMessages. */
export type MessageInput = string | Message[] | AnthropicStyleInput;

/**
 * Normalize any supported message format to a canonical list of message dicts.
 *
 * Supported input formats:
 * - Plain string → `[{ role: "user", content: input }]`
 * - OpenAI-style array of message dicts → returned unchanged
 * - Anthropic-style object with a `messages` key → `input.messages`
 *
 * @param input - The message input in any supported format.
 * @returns A list of message dicts, each containing at least `role` and `content`.
 * @throws {TypeError} If the input is not a string, array, or recognized object structure.
 */
export function normalizeMessages(input: MessageInput): Message[] {
  if (typeof input === "string") {
    return [{ role: "user", content: input }];
  }

  if (Array.isArray(input)) {
    return input;
  }

  if (typeof input === "object" && input !== null) {
    if ("messages" in input) {
      return (input as AnthropicStyleInput).messages;
    }
    throw new TypeError(
      `Unrecognized object format: expected an object with a 'messages' key ` +
        `(Anthropic-style), but got keys: ${JSON.stringify(Object.keys(input))}`
    );
  }

  throw new TypeError(
    `Unsupported message format: expected a string, array, or object with a 'messages' key, ` +
      `but got ${typeof input}`
  );
}
