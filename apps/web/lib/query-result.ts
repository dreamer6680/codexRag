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

function isCitation(value: unknown): value is Citation {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return false;
  }

  const {
    document_id,
    document_name,
    version,
    page,
    section,
    excerpt,
    confidence,
  } = value as Record<string, unknown>;

  return (
    typeof document_id === "string" &&
    typeof document_name === "string" &&
    typeof version === "number" &&
    Number.isInteger(version) &&
    (page === undefined || (typeof page === "number" && Number.isInteger(page))) &&
    (section === undefined || typeof section === "string") &&
    typeof excerpt === "string" &&
    typeof confidence === "number"
  );
}

function isQueryResult(value: unknown): value is QueryResult {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return false;
  }

  const { status, answer, citations } = value as Record<string, unknown>;

  return (
    (status === "answered" || status === "refused" || status === "unavailable") &&
    typeof answer === "string" &&
    Array.isArray(citations) &&
    citations.every(isCitation)
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
