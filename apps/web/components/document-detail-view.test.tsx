// @vitest-environment jsdom

import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { DocumentDetailView, type DocumentDetail } from "./document-detail-view";

const detail: DocumentDetail = {
  document_id: "doc-1",
  document_name: "规范.pdf",
  version: 1,
  content_type: "application/pdf",
  parser: "pdf-inspector",
  status: "ready",
  page_count: 8,
  pdf_type: "TextBased",
  chunk_count: 2,
  original_url: "/api/documents/doc-1/original",
  markdown: "# 解析标题\n\n正文",
  chunks: [
    {
      index: 4,
      text: "公司：珠海环届云有限公司\n岗位：全栈研发\n项目：FastGPT",
      page: 2,
      section: "工作经历 / 珠海环届云有限公司",
      chunk_type: "resume_experience",
      section_path: ["工作经历", "珠海环届云有限公司"],
      parent_context: "工作经历 / 珠海环届云有限公司",
      entities: { companies: ["珠海环届云有限公司"], roles: ["全栈研发"], projects: ["FastGPT"] },
      parser_confidence: 0.94,
      char_start: 0,
      char_end: 3,
      confidence: 1,
    },
    { index: 9, text: "第二块", page: 7, section: "结尾", char_start: 4, char_end: 7, confidence: 0.9 },
  ],
};

describe("DocumentDetailView", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  function renderDetail() {
    act(() => root.render(<DocumentDetailView detail={detail} onBack={() => undefined} onDelete={() => undefined} deleting={false} />));
  }

  function click(element: Element | null) {
    expect(element).not.toBeNull();
    act(() => element?.dispatchEvent(new MouseEvent("click", { bubbles: true })));
  }

  function modeButton(label: string) {
    return Array.from(container.querySelectorAll("button")).find(button => button.textContent === label) ?? null;
  }

  it("renders the chunk rail, parsed heading, and initial PDF page", () => {
    renderDetail();

    expect(container.querySelector('[aria-label="查看 Chunk 5"]')).not.toBeNull();
    expect(container.querySelector('[aria-label="查看 Chunk 10"]')).not.toBeNull();
    expect(container.querySelector('[aria-label="Markdown 解析内容"] h1')?.textContent).toBe("解析标题");
    expect(container.querySelector("iframe")?.getAttribute("src")).toBe("/api/documents/doc-1/original#page=2");
  });

  it("shows structural type, section path, and resume entities for a chunk", () => {
    renderDetail();
    click(modeButton("当前 Chunk"));

    expect(container.textContent).toContain("工作经历 / 珠海环届云有限公司");
    expect(container.textContent).toContain("简历经历");
    expect(container.textContent).toContain("公司：珠海环届云有限公司");
    expect(container.textContent).toContain("岗位：全栈研发");
    expect(container.textContent).toContain("项目：FastGPT");
  });

  it("selects a sparse chunk index by array position and follows its PDF page", () => {
    renderDetail();

    click(container.querySelector('[aria-label="查看 Chunk 10"]'));
    click(modeButton("当前 Chunk"));

    expect(container.textContent).toContain("第二块");
    expect(container.querySelector("iframe")?.getAttribute("src")).toBe("/api/documents/doc-1/original#page=7");
  });

  it("switches between raw Markdown and rendered Markdown", () => {
    renderDetail();

    click(modeButton("原始 Markdown"));
    expect(container.querySelector('[aria-label="Markdown 解析内容"] pre')?.textContent).toContain("# 解析标题");
    expect(container.querySelector('[aria-label="Markdown 解析内容"] h1')).toBeNull();

    click(modeButton("渲染视图"));
    expect(container.querySelector('[aria-label="Markdown 解析内容"] h1')?.textContent).toBe("解析标题");
  });

  it("offers document deletion from the detail header", () => {
    renderDetail();
    expect(modeButton("删除资料")).not.toBeNull();
  });
});
