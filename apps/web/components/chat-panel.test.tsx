// @vitest-environment jsdom

import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { ChatPanel } from "./chat-panel";
import type { ChatMessage } from "@/lib/chat-state";

const message: ChatMessage = {
  id: "assistant-1",
  conversation_id: "conversation-1",
  role: "assistant",
  content: "谨慎回答。[1]",
  status: "completed",
  confidence: "low",
  citations: [{
    document_id: "doc-1",
    document_name: "规范.pdf",
    version: 1,
    excerpt: "相关性较弱的依据",
    confidence: 0.55,
  }],
  created_at: "2026-08-17T00:00:00Z",
};

describe("ChatPanel evidence confidence", () => {
  let container: HTMLDivElement;

  beforeEach(() => {
    (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
    container = document.createElement("div");
    document.body.appendChild(container);
  });

  afterEach(() => container.remove());

  it("renders the persisted backend confidence instead of inferring it from citation count", () => {
    const root = createRoot(container);
    act(() => root.render(
      <ChatPanel
        messages={[message]}
        input=""
        sending={false}
        documents={[]}
        selectedDocumentIds={[]}
        filterSaving={false}
        onInput={() => undefined}
        onSend={() => undefined}
        onFilter={() => undefined}
      />,
    ));

    expect(container.textContent).toContain("检索到 1 条相关性较弱的证据，请结合原文核验");
    expect(container.textContent).not.toContain("高相关证据");
    act(() => root.unmount());
  });
});
