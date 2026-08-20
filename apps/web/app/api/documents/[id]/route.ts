import { NextRequest, NextResponse } from "next/server";
import { ragFetch } from "@/lib/rag-api";

export const runtime = "nodejs";

export async function GET(_request: NextRequest, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  try {
    const response = await ragFetch(`/rag/documents/${encodeURIComponent(id)}`);
    const payload = await response.json();
    return NextResponse.json(
      typeof payload === "object" && payload !== null
        ? { ...payload, original_url: `/api/documents/${id}/original` }
        : payload,
      { status: response.status },
    );
  } catch {
    return NextResponse.json({ detail: "无法连接本地 RAG 文档详情服务" }, { status: 503 });
  }
}

export async function DELETE(_request: NextRequest, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  try {
    const response = await ragFetch(`/rag/documents/${encodeURIComponent(id)}`, { method: "DELETE" });
    return new Response(await response.text(), {
      status: response.status,
      headers: { "content-type": response.headers.get("content-type") || "application/json" },
    });
  } catch {
    return NextResponse.json({ detail: "无法连接本地 RAG 删除服务" }, { status: 503 });
  }
}
