/**
 * Configuration loading for PrivacyLens (TypeScript).
 *
 * Priority order (highest to lowest):
 * 1. Overrides passed directly as a Partial<Config> argument
 * 2. File path passed as configPath argument (YAML or JSON)
 * 3. privacylens.yaml in the current working directory
 * 4. Built-in defaults
 */

import * as fs from "fs";
import * as path from "path";
import type { Config, DetectorConfig } from "./models.js";

// ---------------------------------------------------------------------------
// Defaults
// ---------------------------------------------------------------------------

const DEFAULT_CONFIG: Config = {
  version: "1",
  detectors: {
    regex: { enabled: true },
  },
  vault: "memory",
};

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

type PlainConfig = Omit<Config, "onDetection">;

function loadYamlOrJson(filePath: string): Record<string, unknown> {
  const content = fs.readFileSync(filePath, "utf-8");
  const ext = path.extname(filePath).toLowerCase();
  if (ext === ".json") {
    return JSON.parse(content) as Record<string, unknown>;
  }
  // YAML (or unknown extension — treat as YAML, superset of JSON)
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const yaml = require("js-yaml") as typeof import("js-yaml");
  return (yaml.load(content) as Record<string, unknown>) ?? {};
}

function deepMerge(
  base: Record<string, unknown>,
  override: Record<string, unknown>
): Record<string, unknown> {
  const result: Record<string, unknown> = { ...base };
  for (const [key, value] of Object.entries(override)) {
    if (
      key in result &&
      typeof result[key] === "object" &&
      result[key] !== null &&
      !Array.isArray(result[key]) &&
      typeof value === "object" &&
      value !== null &&
      !Array.isArray(value)
    ) {
      result[key] = deepMerge(
        result[key] as Record<string, unknown>,
        value as Record<string, unknown>
      );
    } else {
      result[key] = value;
    }
  }
  return result;
}

function toConfig(raw: Record<string, unknown>): Config {
  const detectors: Record<string, DetectorConfig> = {};
  if (raw["detectors"] && typeof raw["detectors"] === "object") {
    for (const [name, det] of Object.entries(
      raw["detectors"] as Record<string, unknown>
    )) {
      if (det && typeof det === "object") {
        const raw_det = det as Record<string, unknown>;
        const detCfg: DetectorConfig = {
          enabled: typeof raw_det["enabled"] === "boolean" ? raw_det["enabled"] : true,
        };
        if (Array.isArray(raw_det["patterns"])) {
          detCfg.patterns = raw_det["patterns"] as NonNullable<DetectorConfig["patterns"]>;
        }
        detectors[name] = detCfg;
      }
    }
  }

  return {
    version: typeof raw["version"] === "string" ? raw["version"] : DEFAULT_CONFIG.version,
    detectors: Object.keys(detectors).length > 0 ? detectors : DEFAULT_CONFIG.detectors,
    vault: (["memory", "redis", "sqlite"] as const).includes(
      raw["vault"] as "memory" | "redis" | "sqlite"
    )
      ? (raw["vault"] as Config["vault"])
      : DEFAULT_CONFIG.vault,
  };
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export interface LoadConfigOptions {
  /** Explicit path to a YAML or JSON config file. */
  configPath?: string;
  /** Direct config overrides (highest priority). */
  overrides?: Partial<Omit<Config, "onDetection">>;
  /** onDetection callback (not serialisable, passed separately). */
  onDetection?: Config["onDetection"];
}

/**
 * Load and merge configuration from all sources.
 *
 * @throws {Error} if configPath is given but the file does not exist.
 */
export function loadConfig(options: LoadConfigOptions = {}): Config {
  let merged: Record<string, unknown> = { ...DEFAULT_CONFIG } as Record<
    string,
    unknown
  >;

  // Layer 3: privacylens.yaml in cwd
  const cwdYaml = path.join(process.cwd(), "privacylens.yaml");
  if (fs.existsSync(cwdYaml)) {
    const fileData = loadYamlOrJson(cwdYaml);
    merged = deepMerge(merged, fileData);
  }

  // Layer 2: explicit configPath
  if (options.configPath !== undefined) {
    if (!fs.existsSync(options.configPath)) {
      throw new Error(`Config file not found: ${options.configPath}`);
    }
    const fileData = loadYamlOrJson(options.configPath);
    merged = deepMerge(merged, fileData);
  }

  // Layer 1: direct overrides
  if (options.overrides) {
    merged = deepMerge(merged, options.overrides as Record<string, unknown>);
  }

  const config = toConfig(merged);

  if (options.onDetection !== undefined) {
    config.onDetection = options.onDetection;
  }

  return config;
}

/**
 * Serialize a Config object to a YAML string.
 * The onDetection callback is excluded (not serialisable).
 */
export function dumpConfig(config: Config): string {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const yaml = require("js-yaml") as typeof import("js-yaml");
  const { onDetection: _omit, ...serialisable } = config;
  return yaml.dump(serialisable, { sortKeys: true });
}
