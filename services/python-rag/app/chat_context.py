"""Bounded conversational context for retrieval and answer generation."""

from dataclasses import dataclass
from uuid import UUID

from .models import ChatMessage


@dataclass(frozen=True)
class ChatContext:
    recent_messages: list[ChatMessage]
    retrieval_query: str
    prompt_history: str
    messages_to_summarize: list[ChatMessage]


class ChatContextBuilder:
    def __init__(self, max_chars: int, recent_message_limit: int = 12) -> None:
        self.max_chars = max_chars
        self.recent_message_limit = recent_message_limit

    def build(
        self,
        summary: str,
        messages: list[ChatMessage],
        question: str,
        summarized_through_message_id: UUID | None = None,
    ) -> ChatContext:
        completed = [item for item in messages if item.status == "completed" and item.content.strip()]
        if completed and completed[-1].role == "user" and completed[-1].content.strip() == question.strip():
            completed = completed[:-1]
        recent = completed[-self.recent_message_limit :]
        unsummarized = completed
        if summarized_through_message_id:
            for index, item in enumerate(completed):
                if item.id == summarized_through_message_id:
                    unsummarized = completed[index + 1 :]
                    break
        older = unsummarized[: -self.recent_message_limit] if len(unsummarized) > self.recent_message_limit else []

        latest_user_messages = [item.content.strip() for item in completed if item.role == "user"][-2:]
        retrieval_parts = []
        if summary.strip():
            retrieval_parts.append(f"会话摘要：{summary.strip()}")
        retrieval_parts.extend(f"最近问题：{text}" for text in latest_user_messages)
        retrieval_parts.append(f"当前问题：{question.strip()}")
        retrieval_query = "\n".join(retrieval_parts)

        history_parts = []
        if summary.strip():
            history_parts.append(f"较早对话摘要：\n{summary.strip()}")
        if recent:
            rendered = "\n".join(
                f"{'用户' if item.role == 'user' else '助手'}：{item.content.strip()}"
                for item in recent
            )
            history_parts.append(f"最近对话：\n{rendered}")
        prompt_history = "\n\n".join(history_parts)
        if len(prompt_history) > self.max_chars:
            prompt_history = prompt_history[-self.max_chars :]

        return ChatContext(
            recent_messages=recent,
            retrieval_query=retrieval_query,
            prompt_history=prompt_history,
            messages_to_summarize=older,
        )
