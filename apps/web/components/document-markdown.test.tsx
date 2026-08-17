import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { DocumentMarkdown } from "./document-markdown";

describe("DocumentMarkdown", () => {
  it("renders document structure instead of showing Markdown markers", () => {
    const html = renderToStaticMarkup(
      <DocumentMarkdown
        markdown={"# 标题\n\n- 条目\n\n> 引用\n\n| 列 | 值 |\n| --- | --- |\n| A | **B** |"}
      />,
    );

    expect(html).toContain("<h1");
    expect(html).toContain("<ul");
    expect(html).toContain("<blockquote");
    expect(html).toContain("<table");
    expect(html).toContain("<strong>B</strong>");
    expect(html).not.toContain("# 标题");
  });

  it("escapes document HTML instead of injecting it", () => {
    const html = renderToStaticMarkup(
      <DocumentMarkdown markdown={'<img src=x onerror="alert(1)">'} />,
    );

    expect(html).toContain("&lt;img");
    expect(html).not.toContain("<img");
  });
});
