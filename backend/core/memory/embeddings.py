"""
Embedding providers for the memory system.
Supports: Ollama local embeddings (primary), LiteLLM/OpenAI (fallback), and
graceful NullEmbeddings degradation.
"""

import logging
from abc import ABC, abstractmethod

import httpx

from core.config import get_settings

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 1536  # pgvector column dimension (matches OpenAI ada-002)


class EmbeddingProvider(ABC):
    """Abstract base for embedding providers."""

    dim: int = EMBEDDING_DIM

    @abstractmethod
    async def encode(self, text: str) -> list[float]:
        """Convert text to embedding vector."""
        ...

    @abstractmethod
    async def encode_batch(self, texts: list[str]) -> list[list[float]]:
        """Batch encode multiple texts."""
        ...


class LiteLLMEmbeddings(EmbeddingProvider):
    """Embeddings via LiteLLM — routes to OpenAI, local, or other providers."""

    def __init__(self, model: str = "text-embedding-ada-002"):
        self.model = model
        self.dim = EMBEDDING_DIM

    async def encode(self, text: str) -> list[float]:
        from litellm import aembedding

        try:
            response = await aembedding(model=self.model, input=[text])
            return response.data[0]["embedding"]
        except Exception as e:
            logger.error(f"Embedding failed for model {self.model}: {e}")
            raise

    async def encode_batch(self, texts: list[str]) -> list[list[float]]:
        from litellm import aembedding

        try:
            response = await aembedding(model=self.model, input=texts)
            return [item["embedding"] for item in response.data]
        except Exception as e:
            logger.error(f"Batch embedding failed: {e}")
            raise


class OllamaEmbeddings(EmbeddingProvider):
    """Local embeddings via Ollama REST API (e.g., nomic-embed-text).

    Uses the Ollama HTTP API directly instead of relying on LiteLLM, to avoid
    LiteLLM provider-routing edge-cases and ensure reliable local operation.
    """

    def __init__(self, model: str = "nomic-embed-text", base_url: str | None = None):
        self.model = model
        self.native_dim = 768  # nomic-embed-text default
        self.dim = EMBEDDING_DIM
        settings = get_settings()
        self.base_url = base_url or settings.ollama_base_url

    async def encode(self, text: str) -> list[float]:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": self.model, "prompt": text},
                )
                resp.raise_for_status()
                vec = resp.json()["embedding"]
                return self._normalize_dim(vec)
        except Exception as e:
            logger.error(f"Ollama embedding failed for model {self.model}: {e}")
            raise

    async def encode_batch(self, texts: list[str]) -> list[list[float]]:
        # Ollama doesn't support batch — sequential fallback
        results = []
        for text in texts:
            results.append(await self.encode(text))
        return results

    def _normalize_dim(self, vec: list[float]) -> list[float]:
        """Pad with zeros or truncate to match EMBEDDING_DIM (pgvector column width)."""
        if len(vec) >= EMBEDDING_DIM:
            return vec[:EMBEDDING_DIM]
        return vec + [0.0] * (EMBEDDING_DIM - len(vec))


class NullEmbeddings(EmbeddingProvider):
    """Fallback: no embeddings available. Memory still works via FTS only.

    This is a graceful degradation path — all operations succeed without error
    but vector similarity search is effectively disabled.
    """

    _warned: bool = False

    def __init__(self):
        self.dim = EMBEDDING_DIM
        if not NullEmbeddings._warned:
            logger.warning("NullEmbeddings active — vector search disabled, FTS only")
            NullEmbeddings._warned = True

    async def encode(self, text: str) -> list[float]:
        return []

    async def encode_batch(self, texts: list[str]) -> list[list[float]]:
        return [[] for _ in texts]


def _ollama_has_embedding_model(base_url: str) -> str | None:
    """Check if Ollama has an embedding model available. Returns model name or None."""
    try:
        resp = httpx.get(f"{base_url}/api/tags", timeout=3)
        if resp.status_code == 200:
            models = [m["name"] for m in resp.json().get("models", [])]
            # Look for known embedding models in priority order
            for model in models:
                name_lower = model.lower()
                if "nomic-embed" in name_lower:
                    return model.split(":")[0]  # strip :latest tag
                if "embed" in name_lower:
                    return model.split(":")[0]
            return None
    except Exception:
        return None


def _openai_key_works(api_key: str) -> bool:
    """Quick validation that the OpenAI API key has quota (sync, for startup)."""
    try:
        resp = httpx.post(
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": "text-embedding-ada-002", "input": "test"},
            timeout=10,
        )
        return resp.status_code == 200
    except Exception:
        return False


def get_embedding_provider() -> EmbeddingProvider:
    """Factory: return the best available embedding provider.

    Priority:
    1. Ollama local embeddings (if Ollama is running and has an embedding model)
    2. OpenAI embeddings via LiteLLM (if API key is set and has quota)
    3. NullEmbeddings graceful fallback (FTS-only search)
    """
    settings = get_settings()

    # 1. Try Ollama local embeddings first (preferred — no cost, low latency)
    embed_model = _ollama_has_embedding_model(settings.ollama_base_url)
    if embed_model:
        logger.info(f"Using Ollama local embeddings (model: {embed_model})")
        return OllamaEmbeddings(model=embed_model, base_url=settings.ollama_base_url)

    # 2. Try OpenAI embeddings if API key is available and valid
    if settings.openai_api_key:
        if _openai_key_works(settings.openai_api_key):
            logger.info("Using OpenAI embeddings (text-embedding-ada-002)")
            return LiteLLMEmbeddings(model="text-embedding-ada-002")
        else:
            logger.warning(
                "OpenAI API key is set but failed validation — "
                "skipping OpenAI embeddings"
            )

    # 3. Fallback: FTS only
    logger.warning("No embedding provider available — using FTS-only memory search")
    return NullEmbeddings()
