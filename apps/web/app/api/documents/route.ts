import { NextResponse } from "next/server";

export const runtime = "nodejs";

export async function GET() {
  const upstream = process.env.RAG_API_URL ?? "http://localhost:8001";
  try {
    const response = await fetch(`${upstream}/rag/documents`, { cache: "no-store" });
    const payload = await response.json();
    return NextResponse.json(payload, { status: response.status });
  } catch {
    return NextResponse.json({ detail: "无法连接本地 RAG 文档服务" }, { status: 503 });
  }
}
