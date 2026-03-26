/**
 * Tokenizer for PrivacyLens (TypeScript).
 *
 * Replaces detected EntitySpan ranges in text with stable placeholder tokens
 * of the form `[ENTITY_TYPE_N]`, storing the original values in the vault.
 */

import type { EntitySpan } from "./models.js";
import type { SessionVault } from "./vault.js";

export interface TokenizeResult {
  /** The text with PII replaced by tokens. */
  tokenizedText: string;
  /** Pairs of [token, originalValue] produced during this call. */
  pairs: Array<[string, string]>;
}

/**
 * Replace entity spans in `text` with stable `[ENTITY_TYPE_N]` tokens.
 *
 * Algorithm:
 * 1. Sort spans by `start` ascending (ties: longer span first).
 * 2. Walk spans left-to-right, skipping any span fully contained within an
 *    already-processed span.
 * 3. For each span, look up whether the same *value* already has a token in
 *    this session; if not, assign the next counter token and store it.
 * 4. Build the output string by copying verbatim text between spans and
 *    inserting tokens in place of spans.
 *
 * @param text - The original input text.
 * @param spans - Detected entity spans (need not be pre-sorted).
 * @param vault - Session vault for storing token↔value mappings.
 * @param sessionId - Identifier for the current session.
 * @returns TokenizeResult with tokenized text and (token, originalValue) pairs.
 */
export function tokenize(
  text: string,
  spans: EntitySpan[],
  vault: SessionVault,
  sessionId: string
): TokenizeResult {
  if (spans.length === 0) {
    return { tokenizedText: text, pairs: [] };
  }

  // Sort by start ascending; ties broken by longer span first.
  const sorted = [...spans].sort(
    (a, b) => a.start - b.start || (b.end - b.start) - (a.end - a.start)
  );

  // value → token cache (populated from vault lookups + new assignments).
  const valueToToken = new Map<string, string>();

  /**
   * Find or create a stable token for the given (entityType, value) pair.
   * Scans existing vault tokens for this entity type before assigning a new one.
   */
  function getOrCreateToken(entityType: string, value: string): string {
    const cached = valueToToken.get(value);
    if (cached !== undefined) return cached;

    // Scan existing tokens in the vault for this entity type.
    let n = 1;
    while (true) {
      const candidate = `[${entityType}_${n}]`;
      try {
        const stored = vault.retrieve(sessionId, candidate);
        if (stored === value) {
          valueToToken.set(value, candidate);
          return candidate;
        }
        n++;
      } catch {
        // KeyError / Error — no more tokens of this type in the vault.
        break;
      }
    }

    // Assign the next unused slot (n is already pointing at it).
    const token = `[${entityType}_${n}]`;
    vault.store(sessionId, token, value);
    valueToToken.set(value, token);
    return token;
  }

  const parts: string[] = [];
  const pairs: Array<[string, string]> = [];
  let cursor = 0;
  let lastEnd = -1;

  for (const span of sorted) {
    // Skip spans fully contained within an already-processed span.
    if (span.start < lastEnd && span.end <= lastEnd) {
      continue;
    }

    // Copy verbatim text between the previous span and this one.
    parts.push(text.slice(cursor, span.start));

    const token = getOrCreateToken(span.entityType, span.value);
    parts.push(token);
    pairs.push([token, span.value]);

    cursor = span.end;
    lastEnd = span.end;
  }

  // Append any remaining text after the last span.
  parts.push(text.slice(cursor));

  return { tokenizedText: parts.join(""), pairs };
}
