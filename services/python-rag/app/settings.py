from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPOSITORY_ROOT / ".env.local",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    ollama_base_url: str = "http://localhost:11434"
    chat_model: str = "gemma3:latest"
    fallback_chat_model: str = "qwen2.5:7b"
    embedding_model: str = "bge-m3"
    rerank_model: str = "qllama/bge-reranker-v2-m3"
    qdrant_url: str = "http://localhost:6333"
    mineru_url: str = "http://localhost:8002"
    postgres_dsn: str = "postgresql://localrag:localrag-change-me@localhost:5432/rag_state"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "localrag"
    minio_secret_key: str = "localrag-change-me"
    minio_bucket: str = "rag-documents"
    minio_secure: bool = False
    rag_host: str = "127.0.0.1"
    rag_port: int = 8001
    retrieval_strategy: str = "vector"
    retrieval_top_k: int = 12
    retrieval_score_threshold: float = 0.35
    retrieval_min_evidence_score: float = 0.52
    retrieval_medium_confidence_score: float = 0.65
    retrieval_high_confidence_score: float = 0.78
    retrieval_max_evidence: int = 6
    context_max_chars: int = 12000
    max_upload_mb: int = 50
    supabase_url: str = ""
    supabase_jwt_audience: str = "authenticated"


settings = Settings()
