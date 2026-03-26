/**
 * De-tokenizer for PrivacyLens (TypeScript).
 *
 * Restores original PII values in text by replacing `[ENTITY_TYPE_N]` tokens
 * with the values stored in the session vault. Uses a single-pass regex
 * replace with a callback so every token is visited exactly once.
 */

import type { SessionVault } from "./vault.js";

// Matches tokens of the form [ENTITY_TYPE_N], e.g. [EMAIL_1], [PHONE_2].
const TOKEN_RE = /\[([A-Z][A-Z0-9_]*)_(\d+)\]/g;

/**
 * Replace `[ENTITY_TYPE_N]` tokens in `text` with their original values.
 *
 * Performs a single pass using `String.replace` with a callback. Tokens not
 * present in the vault for the given session are left unchanged in the output.
 *
 * @param text - The tokenized text to restore.
 * @param vault - Session vault holding token→value mappings.
 * @param sessionId - Identifier for the current session.
 * @returns The de-tokenized text with original values restored.
 */
export function detokenize(
  text: string,
  vault: SessionVault,
  sessionId: string
): string {
  return text.replace(TOKEN_RE, (token) => {
    try {
      return vault.retrieve(sessionId, token);
    } catch {
      return token; // leave unknown tokens unchanged
    }
  });
}
