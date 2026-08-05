import { describe, expect, it } from "vitest";

import { readQueryResult } from "./query-result";

describe("readQueryResult", () => {
  const validResult = {
    status: "answered" as const,
    answer: "可核验答案",
    citations: [],
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
});
