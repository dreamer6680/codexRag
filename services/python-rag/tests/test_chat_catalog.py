from uuid import UUID

from app.chat_catalog import default_title


def test_default_title_normalizes_whitespace_and_limits_length():
    title = default_title("  这是一个   很长的聊天问题，需要生成稳定标题并避免把整段问题都放进侧栏  ")

    assert title == "这是一个 很长的聊天问题，需要生成稳定标题并避免把整段问题都放进侧栏"
    assert len(title) <= 36


def test_default_title_uses_new_chat_for_empty_text():
    assert default_title("   ") == "新聊天"
