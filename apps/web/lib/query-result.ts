export type Citation = {
  document_id: string;
  document_name: string;
  version: number;
  page?: number;
  section?: string;
  excerpt: string;
  confidence: number;
};

export type QueryResult = {
  status: "answered" | "refused" | "unavailable";
  answer: string;
  citations: Citation[];
  reason?: string;
};

export const UNAVAILABLE_RESULT: QueryResult = {
  status: "unavailable",
  answer: "无法完成本次查询，请稍后重试。",
  citations: [],
};

function unavailableResult(): QueryResult {
  return { ...UNAVAILABLE_RESULT, citations: [] };
}

function isQueryResult(value: unknown): value is QueryResult {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return false;
  }

  const { status, answer, citations } = value as Record<string, unknown>;

  return (
    (status === "answered" || status === "refused" || status === "unavailable") &&
    typeof answer === "string" &&
    Array.isArray(citations)
  );
}

export async function readQueryResult(response: Response): Promise<QueryResult> {
  try {
    const result: unknown = await response.json();

    return response.ok && isQueryResult(result) ? result : unavailableResult();
  } catch {
    return unavailableResult();
  }
}
