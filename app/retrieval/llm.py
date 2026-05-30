"""
LLM factory.

Returns a LangChain BaseChatModel wired to the provider configured in settings.
All providers share the same interface so the chain code is provider-agnostic.

Supported providers:
  - ollama       → ChatOllama  (local, zero cost, built-in connection pooling)
  - openai       → ChatOpenAI (with HTTP connection pooling for concurrent requests)
  - azure_openai → AzureChatOpenAI (with HTTP connection pooling)

Connection Pooling:
  - OpenAI/Azure: Uses requests.Session with HTTPAdapter (pool_connections, pool_maxsize)
  - Ollama: Built-in connection management
"""

from functools import lru_cache

from langchain_core.language_models import BaseChatModel
from loguru import logger
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.core.config import LLMProvider, settings


def _build_requests_session_with_pooling():
    """Create a requests.Session with connection pooling for HTTP-based LLMs."""
    import requests
    
    session = requests.Session()
    
    # Configure retry strategy with exponential backoff
    retry_strategy = Retry(
        total=3,
        backoff_factor=0.5,  # 0.5s, 1s, 2s between retries
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["POST", "GET"],
    )
    
    # Configure connection pooling adapter
    adapter = HTTPAdapter(
        max_retries=retry_strategy,
        pool_connections=10,  # Max number of connections to pool
        pool_maxsize=20,      # Max concurrent connections per host
    )
    
    # Mount adapter for both HTTP and HTTPS
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    logger.info("HTTP connection pool initialized | connections=10, maxsize=20")
    return session


def _build_ollama() -> BaseChatModel:
    from langchain_community.chat_models import ChatOllama

    return ChatOllama(
        model=settings.llm_model,
        base_url=settings.ollama_base_url,
        temperature=0.0,        # deterministic for RAG
        num_predict=1024,       # max output tokens
        timeout=120,
        # Note: ChatOllama uses requests internally; connection pooling
        # handled by HTTPAdapter if we pass http_client, but Ollama
        # typically runs locally so pooling has minimal benefit
    )


def _build_openai() -> BaseChatModel:
    from langchain_openai import ChatOpenAI

    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")

    # Create HTTP session with connection pooling
    http_client = _build_requests_session_with_pooling()
    
    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_api_base,
        http_client=http_client,
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

    # Create HTTP session with connection pooling
    http_client = _build_requests_session_with_pooling()
    
    return AzureChatOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        azure_deployment=settings.azure_openai_deployment,
        api_version=settings.azure_openai_api_version,
        api_key=settings.openai_api_key,
        http_client=http_client,
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
