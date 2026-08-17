export type ConfidenceLevel = "high" | "medium" | "low" | "none";

export type EvidenceBanner = {
  className: string;
  label: string;
};

export function evidenceBanner(confidence: ConfidenceLevel, count: number): EvidenceBanner | null {
  if (count <= 0 || confidence === "none") return null;
  if (confidence === "high") {
    return {
      className: "border-emerald-500 bg-emerald-50 text-emerald-800",
      label: `检索到 ${count} 条高相关证据`,
    };
  }
  if (confidence === "medium") {
    return {
      className: "border-blue-500 bg-blue-50 text-blue-800",
      label: `检索到 ${count} 条中等相关证据，请结合原文核验`,
    };
  }
  return {
    className: "border-amber-500 bg-amber-50 text-amber-800",
    label: `检索到 ${count} 条相关性较弱的证据，请结合原文核验`,
  };
}
