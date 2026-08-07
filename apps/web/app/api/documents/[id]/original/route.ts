import { NextRequest } from "next/server";

export const runtime = "nodejs";

export async function GET(_request: NextRequest, context: { params: Promise<{ id: string }> }) {
  const upstream = process.env.RAG_API_URL ?? "http://localhost:8001";
  const { id } = await context.params;
  try {
    const response = await fetch(`${upstream}/rag/documents/${id}/original`, { cache: "no-store" });
    const body = await response.arrayBuffer();
    return new Response(body, {
      status: response.status,
      headers: {
        "content-type": response.headers.get("content-type") ?? "application/octet-stream",
      },
    });
  } catch {
    return Response.json({ detail: "无法读取原始文件" }, { status: 503 });
  }
}
