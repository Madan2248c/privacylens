/**
 * Core data models for PrivacyLens.
 */

export interface EntitySpan {
  readonly start: number;
  readonly end: number;
  readonly entityType: string;
  readonly value: string;
}

export interface DetectorConfig {
  enabled: boolean;
  patterns?: Array<{ entityType: string; pattern: string }>;
}

export interface Config {
  version: string;
  detectors: Record<string, DetectorConfig>;
  vault: "memory" | "redis" | "sqlite";
  onDetection?: (entityType: string) => void;
}

export interface Detector {
  detect(text: string): EntitySpan[];
}

/**
 * Creates an EntitySpan, validating that start <= end.
 *
 * @throws {Error} if start > end
 */
export function createEntitySpan(
  start: number,
  end: number,
  entityType: string,
  value: string
): EntitySpan {
  if (start > end) {
    throw new Error(
      `EntitySpan.start (${start}) must be <= end (${end})`
    );
  }
  return { start, end, entityType, value };
}
