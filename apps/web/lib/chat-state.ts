export type Citation = {
  document_id: string;
  document_name: string;
  version: number;
  page?: number;
  section?: string;
  excerpt: string;
  confidence: number;
};

export type ChatMessage = {
  id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  status: "pending" | "completed" | "failed";
  citations: Citation[];
  confidence?: "high" | "medium" | "low" | "none";
  error?: string | null;
  has_deleted_citations?: boolean;
  created_at: string;
};

export type ConversationListItem = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
};

export type ConversationDetail = ConversationListItem & {
  summary: string;
  selected_document_ids: string[];
  messages: ChatMessage[];
};

type PendingTurn = {
  conversationId: string;
  question: string;
  userMessageId: string;
  assistantMessageId: string;
  createdAt: string;
};

export function appendPendingTurn(messages: ChatMessage[], turn: PendingTurn) {
  return {
    input: "",
    messages: [
      ...messages,
      {
        id: turn.userMessageId,
        conversation_id: turn.conversationId,
        role: "user" as const,
        content: turn.question,
        status: "completed" as const,
        citations: [],
        confidence: "none" as const,
        created_at: turn.createdAt,
      },
      {
        id: turn.assistantMessageId,
        conversation_id: turn.conversationId,
        role: "assistant" as const,
        content: "",
        status: "pending" as const,
        citations: [],
        confidence: "none" as const,
        created_at: turn.createdAt,
      },
    ],
  };
}

export function completePendingTurn(
  messages: ChatMessage[],
  userMessageId: string,
  assistantMessageId: string,
  savedUser: ChatMessage,
  savedAssistant: ChatMessage,
) {
  return messages.map(item => {
    if (item.id === userMessageId) return savedUser;
    if (item.id === assistantMessageId) return savedAssistant;
    return item;
  });
}

export function failPendingTurn(messages: ChatMessage[], assistantMessageId: string, error: string) {
  return messages.map(item => item.id === assistantMessageId
    ? { ...item, status: "failed" as const, error }
    : item);
}
