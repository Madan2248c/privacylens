/**
 * PrivacyLens — transparent PII masking for LLM clients.
 *
 * Public API exports: shield, inspect
 */

import { Analyzer } from "./core/analyzer.js";
import { loadConfig } from "./core/config.js";
import type { Config, EntitySpan } from "./core/models.js";
import { Pipeline } from "./core/pipeline.js";
import { RegexDetector } from "./detectors/regex.js";
import { shieldOpenAI } from "./adapters/openai.js";

// ---------------------------------------------------------------------------
// Detector factory (mirrors Python's _build_detectors)
// ---------------------------------------------------------------------------

function buildDetectors(config: Config): import("./core/models.js").Detector[] {
  const detectorsCfg = config.detectors ?? {};
  const names = Object.keys(detectorsCfg);

  if (names.length === 0) {
    return [new RegexDetector()];
  }

  const result: import("./core/models.js").Detector[] = [];
  for (const name of names) {
    const detCfg = detectorsCfg[name];
    const enabled = detCfg?.enabled ?? true;
    if (!enabled) continue;
    if (name === "regex") {
      result.push(new RegexDetector(detCfg));
    }
  }
  return result;
}

// ---------------------------------------------------------------------------
// inspect()
// ---------------------------------------------------------------------------

/**
 * Return what would be masked without performing masking.
 *
 * Runs the Analyzer pipeline only — no vault writes, no tokenization.
 *
 * @param text - The input text to inspect.
 * @param config - Optional Config. Uses defaults if not provided.
 * @returns Array of EntitySpan objects representing detected entities.
 */
export function inspect(text: string, config?: Config): EntitySpan[] {
  const cfg = config ?? loadConfig();
  const analyzer = new Analyzer(buildDetectors(cfg), cfg);
  return analyzer.analyze(text);
}

// ---------------------------------------------------------------------------
// shield()
// ---------------------------------------------------------------------------

/**
 * Wrap an LLM client with PII masking.
 *
 * Auto-detects the client type and returns the appropriate adapter.
 * Currently supports OpenAI clients (openai npm package).
 *
 * @param client - An LLM client instance.
 * @param options - Optional configuration overrides.
 * @returns A privacy-protected wrapper around the client.
 * @throws {TypeError} If the client type is not supported.
 */
export function shield<T extends object>(client: T, options?: Partial<Config>): T {
  const cfg = loadConfig(options ?? {});
  const pipeline = new Pipeline(cfg);

  // Check constructor name for lazy openai detection (avoids hard import).
  // instanceof cannot be used without importing the module, so we rely on
  // the constructor name which is stable across openai package versions.
  const ctorName: string =
    (client as { constructor?: { name?: string } }).constructor?.name ?? "";

  if (ctorName === "OpenAI" || ctorName === "AzureOpenAI" || ctorName === "AsyncOpenAI") {
    return shieldOpenAI(client as import("./adapters/openai.js").OpenAIClientLike, pipeline) as T;
  }

  throw new TypeError(
    `Unsupported client type: ${ctorName || typeof client}. ` +
      "Supported: openai.OpenAI"
  );
}

// Re-export core types for consumers
export type { Config, EntitySpan } from "./core/models.js";
export { loadConfig } from "./core/config.js";
export { Pipeline } from "./core/pipeline.js";
