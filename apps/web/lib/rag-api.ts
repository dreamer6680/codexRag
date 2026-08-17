import { getAccessToken } from "@/lib/auth";
import { createRagGateway } from "@/lib/rag-gateway";

export const ragFetch = createRagGateway(
  getAccessToken,
  fetch,
  process.env.RAG_API_URL ?? "http://localhost:8001",
);
