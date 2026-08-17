from datetime import datetime, timezone
from uuid import uuid4

from app.chat_context import ChatContextBuilder
from app.models import ChatMessage


def message(role: str, content: str) -> ChatMessage:
    return ChatMessage(
        id=uuid4(),
        conversation_id=uuid4(),
        role=role,
        content=content,
        status="completed",
        created_at=datetime.now(timezone.utc),
    )


def test_context_keeps_only_latest_six_turns_verbatim():
    messages = []
    for index in range(8):
        messages.extend([message("user", f"问题 {index}"), message("assistant", f"答案 {index}")])

    context = ChatContextBuilder(max_chars=4000).build("早期摘要", messages, "继续说明")

    assert len(context.recent_messages) == 12
    assert context.recent_messages[0].content == "问题 2"
    assert context.recent_messages[-1].content == "答案 7"
    assert "早期摘要" in context.prompt_history


def test_retrieval_query_uses_summary_and_latest_two_user_messages_without_full_history():
    messages = [
        message("user", "最早且不相关的问题"),
        message("assistant", "旧答案"),
        message("user", "发布流程有哪些阶段"),
        message("assistant", "有三个阶段"),
        message("user", "第二阶段由谁负责"),
    ]

    context = ChatContextBuilder(max_chars=4000).build("讨论的是新版发布流程", messages, "需要哪些材料")

    assert "讨论的是新版发布流程" in context.retrieval_query
    assert "发布流程有哪些阶段" in context.retrieval_query
    assert "第二阶段由谁负责" in context.retrieval_query
    assert "需要哪些材料" in context.retrieval_query
    assert "最早且不相关的问题" not in context.retrieval_query


def test_context_does_not_resummarize_messages_already_in_rolling_summary():
    messages = []
    for index in range(14):
        messages.extend([message("user", f"问题 {index}"), message("assistant", f"答案 {index}")])
    summarized_through = messages[11].id

    context = ChatContextBuilder(max_chars=4000).build(
        "已有摘要",
        messages,
        "继续",
        summarized_through_message_id=summarized_through,
    )

    assert all(item.id != messages[0].id for item in context.messages_to_summarize)
    assert context.messages_to_summarize[0].id == messages[12].id
