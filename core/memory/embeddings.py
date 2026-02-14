"""
Embedding providers for the memory system.
Supports: LiteLLM (OpenAI/local), with graceful degradation.
"""

import logging
from abc import ABC, abstractmethod

from config import get_settings

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 1536  # OpenAI ada-002 dimension


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
    """Local embeddings via Ollama (e.g., nomic-embed-text)."""

    def __init__(self, model: str = "nomic-embed-text"):
        self.model = f"ollama/{model}"
        self.dim = 768  # nomic-embed-text default

    async def encode(self, text: str) -> list[float]:
        from litellm import aembedding
        try:
            response = await aembedding(model=self.model, input=[text])
            vec = response.data[0]["embedding"]
            # Pad or truncate to EMBEDDING_DIM for consistency
            return self._normalize_dim(vec)
        except Exception as e:
            logger.error(f"Ollama embedding failed: {e}")
            raise

    async def encode_batch(self, texts: list[str]) -> list[list[float]]:
        # Ollama may not support batch — fall back to sequential
        results = []
        for text in texts:
            results.append(await self.encode(text))
        return results

    def _normalize_dim(self, vec: list[float]) -> list[float]:
        """Pad with zeros or truncate to match EMBEDDING_DIM."""
        if len(vec) >= EMBEDDING_DIM:
            return vec[:EMBEDDING_DIM]
        return vec + [0.0] * (EMBEDDING_DIM - len(vec))


class NullEmbeddings(EmbeddingProvider):
    """Fallback: no embeddings available. Memory still works via FTS only."""

    def __init__(self):
        self.dim = EMBEDDING_DIM
        logger.warning("NullEmbeddings active — vector search disabled, FTS only")

    async def encode(self, text: str) -> list[float]:
        return []

    async def encode_batch(self, texts: list[str]) -> list[list[float]]:
        return [[] for _ in texts]


def get_embedding_provider() -> EmbeddingProvider:
    """Factory: return the best available embedding provider."""
    settings = get_settings()

    # Prefer OpenAI embeddings if API key is available
    if settings.openai_api_key:
        logger.info("Using OpenAI embeddings (text-embedding-ada-002)")
        return LiteLLMEmbeddings(model="text-embedding-ada-002")

    # Try Ollama local embeddings
    try:
        import httpx
        resp = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=3)
        if resp.status_code == 200:
            models = [m["name"] for m in resp.json().get("models", [])]
            if any("nomic" in m or "embed" in m for m in models):
                logger.info("Using Ollama local embeddings")
                return OllamaEmbeddings()
    except Exception:
        pass

    # Fallback: FTS only
    logger.warning("No embedding provider available — using FTS-only memory search")
    return NullEmbeddings()
