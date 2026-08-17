# Restore Document Detail Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore chunk navigation, original-source positioning, rendered Markdown, raw Markdown, and current-chunk inspection inside the authenticated workspace.

**Architecture:** Keep `Workspace` responsible for navigation and authenticated data loading, then move document inspection into a focused `DocumentDetailView`. Put the dependency-free safe Markdown renderer in its own module so rendering behavior and interactive workbench behavior can be tested independently.

**Tech Stack:** Next.js 15, React 19, TypeScript, Tailwind CSS 4, Vitest 3, jsdom, React DOM test utilities.

## Global Constraints

- Preserve the current sidebar, login flow, per-user document isolation, conversations, and authenticated API gateway.
- Do not change authentication, ownership filtering, storage keys, upload behavior, chat behavior, or Python API contracts.
- Do not inject parsed document HTML; Markdown content must become escaped React text nodes.
- Add no runtime dependency for Markdown rendering.
- Use selected array position instead of backend `chunk.index` as the component's selection state.
- Keep the current zinc-and-blue visual language and responsive stacked layout on narrow screens.

---

### Task 1: Safe Markdown Renderer

**Files:**
- Create: `apps/web/components/document-markdown.tsx`
- Test: `apps/web/components/document-markdown.test.tsx`

**Interfaces:**
- Consumes: `markdown: string` supplied by the authenticated document detail response.
- Produces: `export function DocumentMarkdown({ markdown }: { markdown: string }): ReactNode`, which renders headings, paragraphs, unordered and ordered lists, blockquotes, fenced code blocks, horizontal rules, inline code, bold text, simple pipe tables, and an empty state without using `dangerouslySetInnerHTML`.

- [ ] **Step 1: Write the failing renderer tests**

Create `document-markdown.test.tsx` with literal Markdown fixtures and render the real component using `renderToStaticMarkup`:

```tsx
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { DocumentMarkdown } from "./document-markdown";

describe("DocumentMarkdown", () => {
  it("renders document structure instead of showing Markdown markers", () => {
    const html = renderToStaticMarkup(<DocumentMarkdown markdown={"# 标题\n\n- 条目\n\n> 引用\n\n| 列 | 值 |\n| --- | --- |\n| A | **B** |"} />);
    expect(html).toContain("<h1");
    expect(html).toContain("<ul");
    expect(html).toContain("<blockquote");
    expect(html).toContain("<table");
    expect(html).toContain("<strong>B</strong>");
    expect(html).not.toContain("# 标题");
  });

  it("escapes document HTML instead of injecting it", () => {
    const html = renderToStaticMarkup(<DocumentMarkdown markdown={'<img src=x onerror="alert(1)">'} />);
    expect(html).toContain("&lt;img");
    expect(html).not.toContain("<img");
  });
});
```

The first test catches replacement of structured rendering with a raw `<pre>`. The second catches unsafe HTML injection.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `pnpm test --run components/document-markdown.test.tsx`

Expected: FAIL because `./document-markdown` does not exist.

- [ ] **Step 3: Implement the renderer with React nodes**

Create `document-markdown.tsx`. Parse line blocks with an index loop, create semantic React elements, and split inline text only for backtick code and `**bold**`. Return this literal empty-state paragraph when the parsed node list is empty:

```tsx
<p className="text-sm text-zinc-500">暂无 Markdown 内容。</p>
```

Use React children for all document strings. Do not use `dangerouslySetInnerHTML`.

- [ ] **Step 4: Run the focused renderer tests and verify GREEN**

Run: `pnpm test --run components/document-markdown.test.tsx`

Expected: 2 tests pass with no warnings.

- [ ] **Step 5: Commit the renderer cycle**

```powershell
git add -- apps/web/components/document-markdown.tsx apps/web/components/document-markdown.test.tsx
git commit -m "feat: restore safe document markdown rendering"
```

---

### Task 2: Interactive Document Detail Workbench

**Files:**
- Create: `apps/web/components/document-detail-view.tsx`
- Test: `apps/web/components/document-detail-view.test.tsx`
- Modify: `apps/web/components/workspace.tsx:1-13,150-166`

**Interfaces:**
- Consumes: `DocumentDetail` containing document metadata, `original_url`, `markdown`, and `chunks`; consumes `onBack: () => void`.
- Produces: `export type DocumentChunk`, `export type DocumentDetail`, and `export function DocumentDetailView({ detail, onBack })`.
- Uses: `DocumentMarkdown` from Task 1 for rendered mode.

- [ ] **Step 1: Write the failing interaction tests**

Create a jsdom test that mounts the real component with React `createRoot` and `act`. Use a complete fixture with sparse backend indexes `4` and `9`, pages `2` and `7`, character ranges, and Markdown containing `# 解析标题`.

```tsx
// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
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
    { index: 4, text: "第一块", page: 2, section: "开头", char_start: 0, char_end: 3, confidence: 1 },
    { index: 9, text: "第二块", page: 7, section: "结尾", char_start: 4, char_end: 7, confidence: 0.9 },
  ],
};
```

Add these behavior tests:

1. Initial render has two buttons named `查看 Chunk 5` and `查看 Chunk 10`, a rendered `<h1>` containing `解析标题`, and an iframe ending in `#page=2`.
2. Clicking `查看 Chunk 10`, then `当前 Chunk`, shows `第二块` and updates the iframe to `#page=7`. This specifically catches treating sparse index `9` as array position `9`.
3. Clicking `原始 Markdown` exposes the literal `# 解析标题`; clicking `渲染视图` returns to the semantic heading.

- [ ] **Step 2: Run the workbench test and verify RED**

Run: `pnpm test --run components/document-detail-view.test.tsx`

Expected: FAIL because `./document-detail-view` does not exist.

- [ ] **Step 3: Implement the workbench component**

Create `document-detail-view.tsx` as a client component. Define the API types with optional `content_type`, `page_count`, `pdf_type`, dates, chunk page, section, character offsets, and confidence. Keep `selectedPosition` and `mode` as local state, derive `selectedChunk = detail.chunks[selectedPosition]`, and reset both values in an effect keyed by `detail.document_id` and `detail.version`.

Render:

- Back button and document metadata.
- Four compact metrics: chunk count, page count, source type, and current location.
- A horizontally scrollable rail using `detail.chunks.map((chunk, position) => ...)`; call `setSelectedPosition(position)` and label each button `aria-label={`查看 Chunk ${chunk.index + 1}`}`.
- An authenticated PDF iframe whose source is `${detail.original_url}#page=${selectedChunk.page}` when a page exists.
- A text-source `<pre>` for non-PDF documents.
- Three mode buttons with `aria-pressed`, visible focus rings, and labels `渲染视图`, `原始 Markdown`, and `当前 Chunk`.
- `DocumentMarkdown`, raw `<pre>`, or selected chunk content according to mode.
- Explicit empty states when Markdown or chunks are empty.

- [ ] **Step 4: Replace the simplified inline detail view**

In `workspace.tsx`, import `DocumentDetailView` and its `DocumentDetail` type. Remove the local `DocumentDetail` type and the inline function at the end of the file. Preserve the current `openDocument` request and this render contract:

```tsx
{view === "detail" && (
  <DocumentDetailView detail={detail} onBack={() => setView("documents")} />
)}
```

- [ ] **Step 5: Run the interaction tests and verify GREEN**

Run: `pnpm test --run components/document-detail-view.test.tsx`

Expected: 3 tests pass, including the sparse-index and PDF-page test.

- [ ] **Step 6: Run both new component suites**

Run: `pnpm test --run components/document-markdown.test.tsx components/document-detail-view.test.tsx`

Expected: 5 tests pass with no failures or React act warnings.

- [ ] **Step 7: Commit the workbench cycle**

```powershell
git add -- apps/web/components/document-detail-view.tsx apps/web/components/document-detail-view.test.tsx apps/web/components/workspace.tsx
git commit -m "feat: restore document detail workbench"
```

---

### Task 3: Full Verification and Visual QA

**Files:**
- Modify only if verification exposes a defect in files changed by Tasks 1-2.

**Interfaces:**
- Consumes: the completed renderer and detail workbench.
- Produces: fresh evidence that the migration works with the existing web application.

- [ ] **Step 1: Run the complete frontend test suite**

Run: `pnpm test --run`

Expected: all existing and new Vitest suites pass.

- [ ] **Step 2: Run a production build**

Run: `pnpm build`

Expected: Next.js production compilation and TypeScript validation complete with exit code 0.

- [ ] **Step 3: Check the final diff**

Run: `git diff --check HEAD^ -- apps/web/components/document-markdown.tsx apps/web/components/document-markdown.test.tsx apps/web/components/document-detail-view.tsx apps/web/components/document-detail-view.test.tsx apps/web/components/workspace.tsx`

Expected: no whitespace errors. Inspect `git diff` and confirm no auth, API, Python, chat, or ownership code changed.

- [ ] **Step 4: Perform visual verification when the stack is available**

Open an authenticated document detail page and verify at desktop and narrow widths:

- The existing sidebar and account workspace remain intact.
- The chunk rail scrolls horizontally and the selected cell is visibly distinct.
- PDF selection follows chunks with page metadata.
- Rendered, raw, and current-chunk modes switch without layout clipping.
- Non-PDF source content remains readable in the stacked narrow layout.

If the local authenticated stack cannot start because an external service is unavailable, report the exact unavailable dependency and retain the automated test and build evidence without claiming manual verification.

- [ ] **Step 5: Record verification status**

Update the working plan with the exact test count, build exit status, and whether visual verification was completed or externally blocked. Do not create unrelated cleanup changes.
