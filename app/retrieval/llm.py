"""
LLM factory.

Returns a LangChain BaseChatModel wired to the provider configured in settings.
All providers share the same interface so the chain code is provider-agnostic.

Supported providers:
  - ollama       → ChatOllama  (local, zero cost)
  - openai       → ChatOpenAI
  - azure_openai → AzureChatOpenAI
"""

from functools import lru_cache

from langchain_core.language_models import BaseChatModel
from loguru import logger

from app.core.config import LLMProvider, settings


def _build_ollama() -> BaseChatModel:
    from langchain_community.chat_models import ChatOllama

    return ChatOllama(
        model=settings.llm_model,
        base_url=settings.ollama_base_url,
        temperature=0.0,        # deterministic for RAG
        num_predict=1024,       # max output tokens
        timeout=120,
    )


def _build_openai() -> BaseChatModel:
    from langchain_openai import ChatOpenAI

    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")

    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_api_base,
        temperature=0.0,
        max_tokens=1024,
        timeout=60,
        max_retries=3,
    )


def _build_azure_openai() -> BaseChatModel:
    from langchain_openai import AzureChatOpenAI

    if not settings.azure_openai_endpoint or not settings.azure_openai_deployment:
        raise ValueError(
            "AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_DEPLOYMENT are required "
            "when LLM_PROVIDER=azure_openai"
        )

    return AzureChatOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        azure_deployment=settings.azure_openai_deployment,
        api_version=settings.azure_openai_api_version,
        api_key=settings.openai_api_key,
        temperature=0.0,
        max_tokens=1024,
        timeout=60,
        max_retries=3,
    )


_BUILDERS = {
    LLMProvider.ollama: _build_ollama,
    LLMProvider.openai: _build_openai,
    LLMProvider.azure_openai: _build_azure_openai,
}


@lru_cache(maxsize=1)
def get_llm() -> BaseChatModel:
    """Return the cached LLM instance for the configured provider."""
    provider = settings.llm_provider
    builder = _BUILDERS.get(provider)
    if builder is None:
        raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")

    logger.info("Initialising LLM | provider={} model={}", provider, settings.llm_model)
    llm = builder()
    logger.info("LLM ready")
    return llm
