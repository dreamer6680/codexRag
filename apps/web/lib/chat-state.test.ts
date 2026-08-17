import { describe, expect, it } from "vitest";
import { appendPendingTurn, completePendingTurn, failPendingTurn, type ChatMessage } from "./chat-state";

const existing: ChatMessage = {
  id: "old",
  conversation_id: "conversation",
  role: "assistant",
  content: "旧回答",
  status: "completed",
  citations: [],
  created_at: "2026-08-17T00:00:00Z",
};

describe("optimistic chat state", () => {
  it("keeps the user question and adds exactly one pending answer", () => {
    const result = appendPendingTurn([existing], {
      conversationId: "conversation",
      question: "新问题",
      userMessageId: "temp-user",
      assistantMessageId: "temp-assistant",
      createdAt: "2026-08-17T01:00:00Z",
    });

    expect(result.input).toBe("");
    expect(result.messages.map(item => [item.role, item.content, item.status])).toEqual([
      ["assistant", "旧回答", "completed"],
      ["user", "新问题", "completed"],
      ["assistant", "", "pending"],
    ]);
  });

  it("replaces only the optimistic turn with persisted messages", () => {
    const pending = appendPendingTurn([existing], {
      conversationId: "conversation",
      question: "新问题",
      userMessageId: "temp-user",
      assistantMessageId: "temp-assistant",
      createdAt: "2026-08-17T01:00:00Z",
    }).messages;
    const user = { ...pending[1], id: "saved-user" };
    const assistant = { ...pending[2], id: "saved-assistant", content: "新回答", status: "completed" as const };

    const completed = completePendingTurn(pending, "temp-user", "temp-assistant", user, assistant);

    expect(completed.map(item => item.id)).toEqual(["old", "saved-user", "saved-assistant"]);
    expect(completed[2].content).toBe("新回答");
  });

  it("keeps the question and turns the pending answer into a retryable failure", () => {
    const pending = appendPendingTurn([], {
      conversationId: "conversation",
      question: "新问题",
      userMessageId: "temp-user",
      assistantMessageId: "temp-assistant",
      createdAt: "2026-08-17T01:00:00Z",
    }).messages;

    const failed = failPendingTurn(pending, "temp-assistant", "网络连接失败");

    expect(failed[0].content).toBe("新问题");
    expect(failed[1]).toMatchObject({ status: "failed", error: "网络连接失败" });
  });
});
