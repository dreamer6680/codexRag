import { describe, expect, it, vi } from "vitest";
import { createRagGateway } from "./rag-gateway";

describe("authenticated RAG gateway", () => {
  it("returns 401 without calling upstream when session is missing", async () => {
    const fetcher = vi.fn();
    const gateway = createRagGateway(async () => null, fetcher, "http://rag");

    const response = await gateway("/rag/documents");

    expect(response.status).toBe(401);
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("overwrites client authorization with the verified session token", async () => {
    const fetcher = vi.fn(async () => new Response("{}", { status: 200 }));
    const gateway = createRagGateway(async () => "verified-token", fetcher, "http://rag");

    await gateway("/rag/documents", { headers: { authorization: "forged-token", "x-test": "kept" } });

    const [, init] = fetcher.mock.calls[0];
    const headers = new Headers(init.headers);
    expect(headers.get("authorization")).toBe("Bearer verified-token");
    expect(headers.get("x-test")).toBe("kept");
  });

  it("preserves upstream status and binary response bodies", async () => {
    const bytes = new Uint8Array([37, 80, 68, 70]);
    const gateway = createRagGateway(
      async () => "verified-token",
      async () => new Response(bytes, { status: 206, headers: { "content-type": "application/pdf" } }),
      "http://rag",
    );

    const response = await gateway("/rag/documents/doc/original");

    expect(response.status).toBe(206);
    expect(response.headers.get("content-type")).toBe("application/pdf");
    expect(new Uint8Array(await response.arrayBuffer())).toEqual(bytes);
  });

});
