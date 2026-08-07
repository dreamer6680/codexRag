"""Unified embedding service shared by RAG and future memory modules."""
from abc import ABC, abstractmethod

from .ollama import OllamaClient


class BaseEmbedding(ABC):
    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


class OllamaEmbedding(BaseEmbedding):
    def __init__(self, client: OllamaClient | None = None) -> None:
        self.client = client or OllamaClient()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return await self.client.embed(texts)
