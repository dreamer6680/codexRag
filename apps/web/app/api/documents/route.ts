import { ragFetch } from "@/lib/rag-api";

export const runtime = "nodejs";

export async function GET() {
  return ragFetch("/rag/documents");
}
