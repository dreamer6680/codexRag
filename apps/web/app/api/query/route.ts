import { NextRequest, NextResponse } from "next/server";
export async function POST(request: NextRequest) {
  const payload = await request.json();
  const upstream = process.env.RAG_API_URL ?? "http://localhost:8001";
  try {
    const response = await fetch(`${upstream}/rag/query`, { method:"POST", headers:{"content-type":"application/json"}, body:JSON.stringify(payload), cache:"no-store" });
    return NextResponse.json(await response.json(), {status:response.status});
  } catch { return NextResponse.json({status:"unavailable",answer:"本地 RAG 服务未启动。",citations:[],confidence:"none"},{status:503}); }
}
