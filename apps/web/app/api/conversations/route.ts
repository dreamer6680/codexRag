import { NextRequest } from "next/server";
import { ragFetch } from "@/lib/rag-api";

export const runtime = "nodejs";

export async function GET() {
  return ragFetch("/rag/conversations");
}

export async function POST(request: NextRequest) {
  return ragFetch("/rag/conversations", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(await request.json().catch(() => ({}))),
  });
}
