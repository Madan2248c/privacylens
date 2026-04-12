/**
 * Tests for the RegexDetector — DOB and IP_ADDRESS patterns.
 */

import { describe, it, expect } from "vitest";
import { RegexDetector } from "../src/detectors/regex.js";

// ---------------------------------------------------------------------------
// EMAIL patterns
// ---------------------------------------------------------------------------

describe("EmailFormats", () => {
  it("detects simple email", () => {
    const detector = new RegexDetector();
    const spans = detector.detect("Contact user@example.com for info.");
    const emails = spans.filter(s => s.entityType === "EMAIL");
    expect(emails.some(s => s.value === "user@example.com")).toBe(true);
  });

  it("detects email with plus sign", () => {
    const detector = new RegexDetector();
    const spans = detector.detect("Email: user+tag@example.com");
    const emails = spans.filter(s => s.entityType === "EMAIL");
    expect(emails.some(s => s.value === "user+tag@example.com")).toBe(true);
  });

  it("span offsets match text slice", () => {
    const text = "Email: user@example.com end";
    const detector = new RegexDetector();
    const spans = detector.detect(text);
    const emails = spans.filter(s => s.entityType === "EMAIL");
    expect(emails.length).toBe(1);
    const span = emails[0]!;
    expect(text.slice(span.start, span.end)).toBe(span.value);
  });
});

// ---------------------------------------------------------------------------
// PHONE patterns
// ---------------------------------------------------------------------------

describe("PhoneFormats", () => {
  it("detects paren format", () => {
    const detector = new RegexDetector();
    const spans = detector.detect("Call (555) 555-5555 now.");
    const phones = spans.filter(s => s.entityType === "PHONE");
    expect(phones.some(s => s.value === "(555) 555-5555")).toBe(true);
  });

  it("detects dash format", () => {
    const detector = new RegexDetector();
    const spans = detector.detect("Call 555-555-5555 now.");
    const phones = spans.filter(s => s.entityType === "PHONE");
    expect(phones.some(s => s.value === "555-555-5555")).toBe(true);
  });

  it("detects +1 format", () => {
    const detector = new RegexDetector();
    const spans = detector.detect("Call +15555555555 now.");
    const phones = spans.filter(s => s.entityType === "PHONE");
    expect(phones.some(s => s.value === "+15555555555")).toBe(true);
  });

  it("span offsets match text slice", () => {
    const text = "Phone: 555-555-5555 end";
    const detector = new RegexDetector();
    const spans = detector.detect(text);
    const phones = spans.filter(s => s.entityType === "PHONE");
    expect(phones.length).toBe(1);
    const span = phones[0]!;
    expect(text.slice(span.start, span.end)).toBe(span.value);
  });
});

// ---------------------------------------------------------------------------
// SSN patterns
// ---------------------------------------------------------------------------

describe("SSNFormats", () => {
  it("detects SSN format", () => {
    const detector = new RegexDetector();
    const spans = detector.detect("SSN: 123-45-6789");
    const ssns = spans.filter(s => s.entityType === "SSN");
    expect(ssns.some(s => s.value === "123-45-6789")).toBe(true);
  });

  it("span offsets match text slice", () => {
    const text = "SSN: 123-45-6789 end";
    const detector = new RegexDetector();
    const spans = detector.detect(text);
    const ssns = spans.filter(s => s.entityType === "SSN");
    expect(ssns.length).toBe(1);
    const span = ssns[0]!;
    expect(text.slice(span.start, span.end)).toBe(span.value);
  });
});

// ---------------------------------------------------------------------------
// Empty / no PII
// ---------------------------------------------------------------------------

describe("EmptyResults", () => {
  it("returns empty list when no PII present", () => {
    const detector = new RegexDetector();
    const spans = detector.detect("Hello world! No sensitive data here.");
    expect(spans).toEqual([]);
  });

  it("returns empty list for empty string", () => {
    const detector = new RegexDetector();
    const spans = detector.detect("");
    expect(spans).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// DOB patterns
// ---------------------------------------------------------------------------

describe("DOBFormats", () => {
  it("detects MM/DD/YYYY format", () => {
    const detector = new RegexDetector();
    const spans = detector.detect("DOB: 01/15/1990");
    const dobs = spans.filter(s => s.entityType === "DOB");
    expect(dobs.some(s => s.value === "01/15/1990")).toBe(true);
  });

  it("detects DD-MM-YYYY format", () => {
    const detector = new RegexDetector();
    const spans = detector.detect("Born on 15-06-1985.");
    const dobs = spans.filter(s => s.entityType === "DOB");
    expect(dobs.some(s => s.value === "15-06-1985")).toBe(true);
  });

  it("detects YYYY-MM-DD format", () => {
    const detector = new RegexDetector();
    const spans = detector.detect("Date of birth: 1990-01-15");
    const dobs = spans.filter(s => s.entityType === "DOB");
    expect(dobs.some(s => s.value === "1990-01-15")).toBe(true);
  });

  it("span offsets match text slice", () => {
    const text = "DOB: 01/15/1990 end";
    const detector = new RegexDetector();
    const spans = detector.detect(text);
    const dobs = spans.filter(s => s.entityType === "DOB");
    expect(dobs.length).toBe(1);
    const span = dobs[0]!;
    expect(text.slice(span.start, span.end)).toBe(span.value);
  });
});

// ---------------------------------------------------------------------------
// IP_ADDRESS patterns
// ---------------------------------------------------------------------------

describe("IPAddressFormats", () => {
  it("detects standard IPv4", () => {
    const detector = new RegexDetector();
    const spans = detector.detect("Server IP: 192.168.1.1");
    const ips = spans.filter(s => s.entityType === "IP_ADDRESS");
    expect(ips.some(s => s.value === "192.168.1.1")).toBe(true);
  });

  it("detects IP in a sentence", () => {
    const detector = new RegexDetector();
    const spans = detector.detect("Connected from 10.0.0.1 today.");
    const ips = spans.filter(s => s.entityType === "IP_ADDRESS");
    expect(ips.some(s => s.value === "10.0.0.1")).toBe(true);
  });

  it("detects IP with all max octets", () => {
    const detector = new RegexDetector();
    const spans = detector.detect("Address: 255.255.255.255");
    const ips = spans.filter(s => s.entityType === "IP_ADDRESS");
    expect(ips.some(s => s.value === "255.255.255.255")).toBe(true);
  });

  it("span offsets match text slice", () => {
    const text = "IP: 172.16.254.1 end";
    const detector = new RegexDetector();
    const spans = detector.detect(text);
    const ips = spans.filter(s => s.entityType === "IP_ADDRESS");
    expect(ips.length).toBe(1);
    const span = ips[0]!;
    expect(text.slice(span.start, span.end)).toBe(span.value);
  });
});