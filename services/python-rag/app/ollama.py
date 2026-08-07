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
        if settings.chat_model in models:
            return settings.chat_model, None
        if settings.fallback_chat_model in models:
            return settings.fallback_chat_model, f"未找到 {settings.chat_model}，已降级到 {settings.fallback_chat_model}"
        return None, f"未拉取问答模型：{settings.chat_model} 或 {settings.fallback_chat_model}"

    async def chat(self, model: str, system: str, prompt: str) -> str:
        payload = {"model": model, "stream": False, "messages": [
            {"role": "system", "content": system}, {"role": "user", "content": prompt}
        ], "options": {"temperature": 0}}
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            return response.json()["message"]["content"]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(f"{self.base_url}/api/embed", json={"model": settings.embedding_model, "input": texts})
            response.raise_for_status()
            return response.json()["embeddings"]
