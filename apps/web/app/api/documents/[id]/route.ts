import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";

export async function GET(_request: NextRequest, context: { params: Promise<{ id: string }> }) {
  const upstream = process.env.RAG_API_URL ?? "http://localhost:8001";
  const { id } = await context.params;
  try {
    const response = await fetch(`${upstream}/rag/documents/${id}`, { cache: "no-store" });
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
