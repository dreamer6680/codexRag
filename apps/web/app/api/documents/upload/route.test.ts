import { NextRequest } from "next/server";
import { describe, expect, it, vi } from "vitest";

const processPdf = vi.hoisted(() => vi.fn());

vi.mock("@firecrawl/pdf-inspector", () => ({ processPdf }));

import { MAX_UPLOAD_BYTES, POST } from "./route";

describe("POST /api/documents/upload", () => {
  it("rejects an oversized file before reading or parsing it", async () => {
    const file = new File([], "large.pdf", { type: "application/pdf" });
    const arrayBuffer = vi.fn(() => Promise.reject(new Error("must not read")));
    Object.defineProperty(file, "size", { value: MAX_UPLOAD_BYTES + 1 });
    Object.defineProperty(file, "arrayBuffer", { value: arrayBuffer });
    const form = new FormData();
    form.append("file", file);

    const response = await POST({ formData: async () => form } as NextRequest);

    expect(response.status).toBe(413);
    await expect(response.json()).resolves.toEqual({ detail: "鏂囦欢涓嶈兘瓒呰繃 50 MB" });
    expect(arrayBuffer).not.toHaveBeenCalled();
    expect(processPdf).not.toHaveBeenCalled();
  });
});
