// @vitest-environment jsdom

import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DocumentDeleteDialog } from "./document-delete-dialog";

describe("DocumentDeleteDialog", () => {
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

  it("names the document and requires explicit irreversible confirmation", () => {
    const confirm = vi.fn();
    act(() => root.render(
      <DocumentDeleteDialog open documentName="简历.pdf" busy={false} onCancel={() => undefined} onConfirm={confirm} />,
    ));

    expect(container.querySelector('[role="dialog"]')).not.toBeNull();
    expect(container.textContent).toContain("简历.pdf");
    expect(container.textContent).toContain("无法恢复");
    const button = Array.from(container.querySelectorAll("button")).find(item => item.textContent === "确认删除");
    act(() => button?.click());
    expect(confirm).toHaveBeenCalledOnce();
  });
});
