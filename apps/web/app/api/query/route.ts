import { NextRequest } from "next/server";
import { ragFetch } from "@/lib/rag-api";
export async function POST(request: NextRequest) {
  return ragFetch("/rag/query", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(await request.json()),
  });
}
