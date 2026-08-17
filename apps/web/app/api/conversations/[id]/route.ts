import { NextRequest } from "next/server";
import { ragFetch } from "@/lib/rag-api";

export const runtime = "nodejs";

export async function GET(_request: NextRequest, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  return ragFetch(`/rag/conversations/${encodeURIComponent(id)}`);
}

export async function PATCH(request: NextRequest, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  return ragFetch(`/rag/conversations/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(await request.json()),
  });
}
