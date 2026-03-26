/**
 * Built-in regex-based detector for common PII patterns.
 * Zero runtime dependencies beyond the JS standard library.
 */

import { createEntitySpan, type DetectorConfig, type EntitySpan } from "../core/models.js";

// ---------------------------------------------------------------------------
// Built-in patterns
// ---------------------------------------------------------------------------

// EMAIL: RFC 5321 local-part + @ + domain
const EMAIL_RE =
  /[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}/g;

// PHONE: (NNN) NNN-NNNN | NNN-NNN-NNNN | +1NNNNNNNNNN
const PHONE_RE =
  /(?:\(\d{3}\)\s?\d{3}-\d{4}|\d{3}-\d{3}-\d{4}|\+1\d{10})/g;

// SSN: NNN-NN-NNNN
const SSN_RE = /\b\d{3}-\d{2}-\d{4}\b/g;

interface BuiltinPattern {
  entityType: string;
  source: string;
  flags: string;
}

const BUILTIN_PATTERNS: BuiltinPattern[] = [
  { entityType: "EMAIL", source: EMAIL_RE.source, flags: "g" },
  { entityType: "PHONE", source: PHONE_RE.source, flags: "g" },
  { entityType: "SSN", source: SSN_RE.source, flags: "g" },
];

// ---------------------------------------------------------------------------
// RegexDetector
// ---------------------------------------------------------------------------

interface CompiledPattern {
  entityType: string;
  regex: RegExp;
}

/**
 * Detects PII using regular expressions.
 *
 * Built-in patterns cover EMAIL, PHONE, and SSN. Custom patterns supplied
 * via `config.patterns` are compiled once at construction time and appended
 * to the built-in set.
 */
export class RegexDetector {
  private readonly patterns: CompiledPattern[];

  constructor(config?: Pick<DetectorConfig, "patterns">) {
    this.patterns = BUILTIN_PATTERNS.map(({ entityType, source, flags }) => ({
      entityType,
      regex: new RegExp(source, flags),
    }));

    if (config?.patterns) {
      for (const entry of config.patterns) {
        this.patterns.push({
          entityType: entry.entityType,
          regex: new RegExp(entry.pattern, "g"),
        });
      }
    }
  }

  detect(text: string): EntitySpan[] {
    const spans: EntitySpan[] = [];

    for (const { entityType, regex } of this.patterns) {
      // Reset lastIndex before each scan (regex is reused across calls)
      regex.lastIndex = 0;
      let match: RegExpExecArray | null;
      while ((match = regex.exec(text)) !== null) {
        spans.push(
          createEntitySpan(match.index, match.index + match[0].length, entityType, match[0])
        );
      }
    }

    return spans;
  }
}
