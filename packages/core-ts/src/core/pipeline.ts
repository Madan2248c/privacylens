/**
 * Pipeline facade for PrivacyLens (TypeScript).
 *
 * Wires together Normalizer, Analyzer, Tokenizer, Vault, and De-tokenizer
 * into a single cohesive interface used by all adapters.
 */

import { Analyzer } from "./analyzer.js";
import { detokenize } from "./detokenizer.js";
import type { Config, Detector } from "./models.js";
import { normalizeMessages, type Message } from "./normalize.js";
import { tokenize } from "./tokenizer.js";
import { MemoryVault, type SessionVault } from "./vault.js";
import { RegexDetector } from "../detectors/regex.js";

// ---------------------------------------------------------------------------
// Detector factory
// ---------------------------------------------------------------------------

/**
 * Instantiate and return the list of enabled detectors from `config`.
 *
 * Default behaviour (no `detectors` key or empty detectors): enable
 * `RegexDetector` only.
 */
function buildDetectors(config: Config): Detector[] {
  const detectorsCfg = config.detectors ?? {};
  const names = Object.keys(detectorsCfg);

  if (names.length === 0) {
    return [new RegexDetector()];
  }

  const result: Detector[] = [];

  for (const name of names) {
    const detCfg = detectorsCfg[name];
    const enabled = detCfg?.enabled ?? true;

    if (!enabled) continue;

    if (name === "regex") {
      result.push(new RegexDetector(detCfg));
    }
    // Additional detector types (pii, semantic) would be added here
    // when TypeScript equivalents are implemented.
  }

  return result;
}

// ---------------------------------------------------------------------------
// Pipeline class
// ---------------------------------------------------------------------------

/** A message dict with at least role and content. */
export type PipelineMessage = Message;

/**
 * Internal facade wiring together all core pipeline stages.
 */
export class Pipeline {
  private readonly _config: Config;
  private readonly _vault: SessionVault;
  private readonly _analyzer: Analyzer;

  constructor(config: Config) {
    this._config = config;
    this._vault = new MemoryVault();
    this._analyzer = new Analyzer(buildDetectors(config), config);
  }

  /**
   * Normalize `messages`, detect PII, and replace spans with tokens.
   *
   * @param messages - Any supported message format (string, OpenAI-style
   *   array, or Anthropic-style object).
   * @param sessionId - Identifier for the current session.
   * @returns A list of message dicts with PII replaced by `[ENTITY_TYPE_N]`
   *   tokens in the `content` field.
   */
  async tokenizeMessages(
    messages: Array<{ role: string; content: string; [key: string]: unknown }>,
    sessionId: string
  ): Promise<Array<{ role: string; content: string; [key: string]: unknown }>> {
    const normalized = normalizeMessages(messages);
    const result: Array<{ role: string; content: string; [key: string]: unknown }> = [];

    for (const msg of normalized) {
      const content = msg.content;
      if (typeof content === "string") {
        const spans = this._analyzer.analyze(content);
        const { tokenizedText } = tokenize(content, spans, this._vault, sessionId);
        result.push({ ...msg, content: tokenizedText });
      } else {
        result.push(msg);
      }
    }

    return result;
  }

  /**
   * Restore original PII values in `text` using the session vault.
   *
   * @param text - The tokenized text to restore.
   * @param sessionId - Identifier for the current session.
   * @returns The de-tokenized text with original values restored.
   */
  detokenize(text: string, sessionId: string): string {
    return detokenize(text, this._vault, sessionId);
  }

  /**
   * De-tokenize an OpenAI-style response object.
   *
   * Handles `choices[].message.content` fields. Non-OpenAI objects are
   * returned unchanged.
   *
   * @param response - An OpenAI `ChatCompletion` response object (or any
   *   object with a `choices` array).
   * @param sessionId - Identifier for the current session.
   * @returns The response object with PII tokens restored.
   */
  detokenizeResponse(response: unknown, sessionId: string): unknown {
    if (
      response === null ||
      typeof response !== "object" ||
      !("choices" in response)
    ) {
      return response;
    }

    const resp = response as {
      choices: Array<{
        message?: { content?: string | null };
        [key: string]: unknown;
      }>;
      [key: string]: unknown;
    };

    for (const choice of resp.choices) {
      if (choice.message !== undefined && typeof choice.message.content === "string") {
        choice.message.content = detokenize(
          choice.message.content,
          this._vault,
          sessionId
        );
      }
    }

    return response;
  }
}
