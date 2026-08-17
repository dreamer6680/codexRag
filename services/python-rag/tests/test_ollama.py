import asyncio

from app.ollama import OllamaClient
from app.settings import settings


def test_chat_model_name_without_tag_resolves_installed_latest_tag(monkeypatch):
    client = OllamaClient()

    async def fake_tags():
        return {"gemma3:latest", "qwen2.5:7b"}

    monkeypatch.setattr(client, "tags", fake_tags)
    monkeypatch.setattr(settings, "chat_model", "gemma3")
    monkeypatch.setattr(settings, "fallback_chat_model", "qwen2.5:7b")

    model, reason = asyncio.run(client.choose_chat_model())

    assert model == "gemma3:latest"
    assert reason is None
