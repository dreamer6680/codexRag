import { NextResponse } from "next/server";
import { ragFetch } from "@/lib/rag-api";

export async function POST() {
  try {
    const response = await ragFetch("/rag/documents/rebuild", { method: "POST" });
    const payload = await response.json().catch(() => ({ detail: "重建服务返回了无效响应" }));
    return NextResponse.json(payload, { status: response.status });
  } catch {
    return NextResponse.json({ detail: "无法连接本地 RAG 重建服务" }, { status: 503 });
  }
}
