import { describe, expect, it } from "vitest";

import { readQueryResult } from "./query-result";

describe("readQueryResult", () => {
  const validCitation = {
    document_id: "doc-1",
    document_name: "Product requirements",
    version: 3,
    page: 8,
    section: "Review",
    excerpt: "Required reviewers",
    confidence: 0.95,
  };

  const validResult = {
    status: "answered" as const,
    answer: "可核验答案",
    citations: [validCitation],
  };

  it("returns a valid successful query result", async () => {
    const response = Response.json(validResult);

    await expect(readQueryResult(response)).resolves.toEqual(validResult);
  });

  it("converts a 422 response into unavailable", async () => {
    const response = Response.json({ detail: "too long" }, { status: 422 });

    await expect(readQueryResult(response)).resolves.toMatchObject({
      status: "unavailable",
      citations: [],
    });
  });

  it("converts invalid JSON into unavailable", async () => {
    const response = new Response("not-json", { status: 200 });

    await expect(readQueryResult(response)).resolves.toMatchObject({
      status: "unavailable",
      citations: [],
    });
  });

  it("converts a malformed success payload into unavailable", async () => {
    const response = Response.json({
      status: "answered",
      answer: "missing citations",
    });

    await expect(readQueryResult(response)).resolves.toMatchObject({
      status: "unavailable",
      citations: [],
    });
  });

  it.each([
    ["a missing citation field", {}],
    ["a non-string document ID", { ...validCitation, document_id: 1 }],
    ["a non-string document name", { ...validCitation, document_name: 1 }],
    ["a non-integer version", { ...validCitation, version: 1.5 }],
    ["a non-integer page", { ...validCitation, page: 1.5 }],
    ["a non-string section", { ...validCitation, section: 1 }],
    ["a non-string excerpt", { ...validCitation, excerpt: 1 }],
    ["a non-numeric confidence", { ...validCitation, confidence: "high" }],
  ])("converts a result with %s into unavailable", async (_, citation) => {
    const response = Response.json({
      status: "answered",
      answer: "ok",
      citations: [citation],
    });

    await expect(readQueryResult(response)).resolves.toMatchObject({
      status: "unavailable",
      citations: [],
    });
  });
});
