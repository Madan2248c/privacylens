/**
 * Analyzer for PrivacyLens (TypeScript).
 *
 * Orchestrates all detectors, resolves overlapping EntitySpans, and emits
 * structured logs and onDetection callbacks — never including original PII values.
 */

import type { Config, Detector, EntitySpan } from "./models.js";

// ---------------------------------------------------------------------------
// Module-level detector plugin registry
// ---------------------------------------------------------------------------

const _registry = new Map<string, Detector>();

/**
 * Register a detector under the given name.
 */
export function registerDetector(name: string, detector: Detector): void {
  _registry.set(name, detector);
}

/**
 * Retrieve a previously registered detector by name.
 *
 * @throws {Error} if no detector is registered under `name`.
 */
export function getDetector(name: string): Detector {
  const detector = _registry.get(name);
  if (detector === undefined) {
    throw new Error(`No detector registered under name: "${name}"`);
  }
  return detector;
}

// ---------------------------------------------------------------------------
// Overlap resolution helper
// ---------------------------------------------------------------------------

function resolveOverlaps(spans: EntitySpan[]): EntitySpan[] {
  if (spans.length === 0) return [];

  // Sort by start asc, ties broken by longer span first.
  const sorted = [...spans].sort(
    (a, b) => a.start - b.start || (b.end - b.start) - (a.end - a.start)
  );

  const result: EntitySpan[] = [];
  let lastEnd = -1;

  for (const span of sorted) {
    if (span.start >= lastEnd) {
      result.push(span);
      lastEnd = span.end;
    } else if (span.end > lastEnd) {
      // Longer span starts before lastEnd — replace the last appended span.
      result[result.length - 1] = span;
      lastEnd = span.end;
    }
    // else: fully contained — discard.
  }

  return result;
}

// ---------------------------------------------------------------------------
// Analyzer class
// ---------------------------------------------------------------------------

export class Analyzer {
  private readonly _detectors: Detector[];
  private readonly _config: Config;

  constructor(detectors: Detector[], config?: Partial<Config>) {
    this._detectors = detectors;
    this._config = {
      version: "1",
      detectors: {},
      vault: "memory",
      ...config,
    };
  }

  /**
   * Run all detectors against `text` and return a resolved EntitySpan list.
   *
   * Steps:
   * 1. Invoke each detector's `detect()` method; catch and warn on any exception.
   * 2. Merge all returned spans.
   * 3. Resolve overlaps (retain longest span).
   * 4. Sort by `start` ascending.
   * 5. Invoke `onDetection` callback with entity type only (never value).
   * 6. Emit a structured console.info log with entity types and count (never values).
   */
  analyze(text: string): EntitySpan[] {
    const allSpans: EntitySpan[] = [];

    for (const detector of this._detectors) {
      try {
        const spans = detector.detect(text);
        allSpans.push(...spans);
      } catch (err) {
        const name = (detector as object).constructor?.name ?? "UnknownDetector";
        const msg = err instanceof Error ? err.message : String(err);
        console.warn(`[privacylens] Detector ${name} raised an exception: ${msg}`);
      }
    }

    const resolved = resolveOverlaps(allSpans);

    // Invoke onDetection callback with entity type only — never the value.
    if (this._config.onDetection !== undefined) {
      for (const span of resolved) {
        this._config.onDetection(span.entityType);
      }
    }

    // Structured INFO log — entity types and count, never values.
    if (resolved.length > 0) {
      const entityTypes = resolved.map((s) => s.entityType).join(", ");
      console.info(
        `[privacylens] Detected ${resolved.length} entit${resolved.length === 1 ? "y" : "ies"}: ${entityTypes}`
      );
    }

    return resolved;
  }
}
