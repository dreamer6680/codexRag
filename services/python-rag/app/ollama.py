import httpx
from .settings import settings


class OllamaClient:
    def __init__(self) -> None:
        self.base_url = settings.ollama_base_url.rstrip("/")

    async def tags(self) -> set[str]:
        async with httpx.AsyncClient(timeout=8) as client:
            response = await client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            return {model["name"] for model in response.json().get("models", [])}

    async def choose_chat_model(self) -> tuple[str | None, str | None]:
        try:
            models = await self.tags()
        except httpx.HTTPError as exc:
            return None, f"Ollama 不可用：{exc}"
        def resolve(requested: str) -> str | None:
            if requested in models:
                return requested
            latest = f"{requested}:latest"
            return latest if ":" not in requested and latest in models else None

        primary = resolve(settings.chat_model)
        if primary:
            return primary, None
        fallback = resolve(settings.fallback_chat_model)
        if fallback:
            return fallback, f"未找到 {settings.chat_model}，已降级到 {fallback}"
        return None, f"未拉取问答模型：{settings.chat_model} 或 {settings.fallback_chat_model}"

    async def chat(self, model: str, system: str, prompt: str) -> str:
        payload = {"model": model, "stream": False, "messages": [
            {"role": "system", "content": system}, {"role": "user", "content": prompt}
        ], "options": {"temperature": 0}}
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            return response.json()["message"]["content"]

    async def summarize_conversation(self, existing_summary: str, transcript: str) -> str | None:
        model, _ = await self.choose_chat_model()
        if not model:
            return None
        prompt = (
            "把下面对话压缩成不超过 1000 个中文字符的长期记忆。"
            "只保留用户目标、已确认事实、约束、决定、未解决问题和提及的文档；删除寒暄和重复。\n\n"
            f"已有摘要：\n{existing_summary or '无'}\n\n新增对话：\n{transcript}"
        )
        summary = await self.chat(model, "你负责维护准确、紧凑的会话记忆。", prompt)
        return summary.strip()[:1000]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(f"{self.base_url}/api/embed", json={"model": settings.embedding_model, "input": texts})
            response.raise_for_status()
            return response.json()["embeddings"]
