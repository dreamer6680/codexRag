import { NextRequest } from "next/server";
import { ragFetch } from "@/lib/rag-api";

export const runtime = "nodejs";

export async function GET(_request: NextRequest, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  try {
    const response = await ragFetch(`/rag/documents/${encodeURIComponent(id)}/original`);
    const body = await response.arrayBuffer();
    return new Response(body, {
      status: response.status,
      headers: {
        "content-type": response.headers.get("content-type") ?? "application/octet-stream",
        "content-length": response.headers.get("content-length") ?? String(body.byteLength),
      },
    });
  } catch {
    return Response.json({ detail: "无法读取原始文件" }, { status: 503 });
  }
}
