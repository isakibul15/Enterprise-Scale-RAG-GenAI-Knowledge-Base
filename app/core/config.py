from enum import Enum
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnv(str, Enum):
    development = "development"
    staging = "staging"
    production = "production"


class LLMProvider(str, Enum):
    openai = "openai"
    azure_openai = "azure_openai"
    ollama = "ollama"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_env: AppEnv = AppEnv.development
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"

    # ChromaDB
    chroma_persist_dir: Path = Path("./storage/chroma")
    collection_name: str = "knowledge_base"

    # Embedding
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_device: str = "cpu"
    embedding_batch_size: int = Field(64, gt=0, le=512)  # Aligned with ChromaDB upsert batch

    # LLM
    llm_provider: LLMProvider = LLMProvider.ollama
    llm_model: str = "llama3.1"
    openai_api_key: str = ""
    openai_api_base: str = "https://api.openai.com/v1"
    azure_openai_endpoint: str = ""
    azure_openai_api_version: str = "2024-05-01-preview"
    azure_openai_deployment: str = ""
    ollama_base_url: str = "http://localhost:11434"

    # Chunking
    chunk_size: int = Field(512, gt=0)
    chunk_overlap: int = Field(64, ge=0)

    # Retrieval
    retriever_top_k: int = Field(6, gt=0)
    parent_chunk_size: int = Field(2048, gt=0)

    # Storage
    upload_dir: Path = Path("./data/uploads")
    max_upload_size_mb: int = Field(50, gt=0)

    @field_validator("chunk_overlap")
    @classmethod
    def overlap_less_than_chunk(cls, v: int, info) -> int:
        chunk_size = info.data.get("chunk_size", 512)
        if v >= chunk_size:
            raise ValueError("chunk_overlap must be less than chunk_size")
        return v

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def is_production(self) -> bool:
        return self.app_env == AppEnv.production


# Singleton — import this everywhere instead of re-instantiating
settings = Settings()
