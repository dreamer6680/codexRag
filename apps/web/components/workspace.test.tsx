import { describe, expect, it } from "vitest";
import { rebuildNotice, removeDeletedDocument } from "./workspace";


describe("rebuildNotice", () => {
  it("summarizes a successful rebuild", () => {
    expect(rebuildNotice({ succeeded: 3, failed: 0, results: [] })).toBe("已重建 3 份文档的结构化索引");
  });

  it("lists documents that failed while preserving successful results", () => {
    expect(rebuildNotice({
      succeeded: 1,
      failed: 1,
      results: [
        { document_id: "ok", document_name: "论文.pdf", status: "ready" },
        { document_id: "bad", document_name: "简历.pdf", status: "failed", error: "parse failed" },
      ],
    })).toBe("已重建 1 份，失败 1 份：简历.pdf");
  });
});

describe("removeDeletedDocument", () => {
  it("removes a tombstoned document from list and conversation scope", () => {
    expect(removeDeletedDocument(
      [{ document_id: "doc-1" }, { document_id: "doc-2" }],
      ["doc-1", "doc-2"],
      "doc-1",
    )).toEqual({
      documents: [{ document_id: "doc-2" }],
      selectedDocumentIds: ["doc-2"],
    });
  });
});
