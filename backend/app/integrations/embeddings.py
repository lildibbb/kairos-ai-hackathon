"""Embedding providers selected by ``EMBEDDING_PROVIDER``.

The local provider is deterministic and key-free, so the app and tests run
without an external model. A hosted OpenAI-compatible provider can replace it.
"""

import hashlib
import math
import re
from collections.abc import Sequence

import httpx

from app.ai.ports import EmbeddingProvider
from app.config import Settings, get_settings
from app.integrations.http import post_json, verify_setting

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


class EmbeddingError(RuntimeError):
    """Safe to display: messages never include credentials or gateway responses."""


class LocalDeterministicEmbeddingProvider:
    """Stable hashed bag-of-words vectors; no network and no API key."""

    def __init__(self, dimension: int = 1024) -> None:
        if dimension <= 0:
            raise ValueError("Embedding dimension must be a positive integer")
        self.dimension = dimension

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for feature in _features(text):
            digest = hashlib.sha256(feature.encode("utf-8")).digest()
            vector[int.from_bytes(digest[:8], "big") % self.dimension] += 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            fallback = [0.0] * self.dimension
            fallback[0] = 1.0
            return fallback
        return [value / norm for value in vector]


class HostedEmbeddingProvider:
    """OpenAI-compatible ``/embeddings`` calls for a configured provider.

    The provider follows the model's own vector size: it does not send a
    ``dimensions`` hint, and it rejects a response whose length differs from the
    configured ``embedding_dimensions`` so the schema and index stay aligned.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        dimension: int,
        client: httpx.Client | None = None,
        verify: bool | str = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        if not self.base_url.startswith("https://") and "localhost" not in self.base_url and "127.0.0.1" not in self.base_url:
            raise ValueError("Hosted embedding API must use HTTPS")
        self.api_key = api_key
        self.model = model
        self.dimension = dimension
        self.verify = verify
        self._client = client

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._request(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._request(text)

    def _request(self, text: str) -> list[float]:
        if not self.api_key or self.api_key.startswith("LOCAL_ONLY"):
            raise EmbeddingError("EMBEDDING_PROVIDER=hosted requires a configured MODEL_API_KEY")
        client = self._client or httpx.Client(timeout=30.0, verify=self.verify)
        try:
            response = post_json(
                client,
                f"{self.base_url}/embeddings",
                headers={"Authorization": f"Bearer {self.api_key}"},
                payload={"model": self.model, "input": text},
            )
            response.raise_for_status()
            vector = response.json()["data"][0]["embedding"]
            if not isinstance(vector, list) or len(vector) != self.dimension:
                actual = len(vector) if isinstance(vector, list) else "invalid"
                raise EmbeddingError(
                    f"Embedding model {self.model} returned {actual} dimensions, but "
                    f"EMBEDDING_DIMENSIONS={self.dimension}. Set EMBEDDING_DIMENSIONS to the model's "
                    "size, run a new migration, then re-ingest with --reembed."
                )
            if any(not isinstance(value, (float, int)) for value in vector):
                raise EmbeddingError("Embedding model returned non-numeric vector values")
            return [float(value) for value in vector]
        finally:
            if self._client is None:
                client.close()


def build_embedding_provider(settings: Settings) -> EmbeddingProvider:
    provider = settings.embedding_provider.strip().lower()
    if provider in ("", "local", "deterministic"):
        return LocalDeterministicEmbeddingProvider(settings.embedding_dimensions)
    if provider == "hosted":
        if not settings.model_api_key or settings.model_api_key.startswith("LOCAL_ONLY"):
            raise RuntimeError("Hosted embedding providers require MODEL_API_KEY")
        return HostedEmbeddingProvider(
            base_url=settings.model_base_url,
            api_key=settings.model_api_key,
            model=settings.embedding_model,
            dimension=settings.embedding_dimensions,
            verify=verify_setting(settings),
        )
    raise ValueError(f"Unknown EMBEDDING_PROVIDER: {settings.embedding_provider}")


def _features(text: str) -> list[str]:
    tokens = _TOKEN_PATTERN.findall(text.lower())
    bigrams = [f"{first} {second}" for first, second in zip(tokens, tokens[1:])]
    return tokens + bigrams


def main() -> None:
    """Print the configured dimension and the provider's actual output size.

    Run ``python -m app.integrations.embeddings`` after configuring a hosted
    provider to confirm the model's vector size before migrating and re-ingesting.
    """
    settings = get_settings()
    provider = build_embedding_provider(settings)
    vector = provider.embed_query("embedding dimension probe")
    model = getattr(provider, "model", "local-deterministic")
    print(f"Provider: {model}")
    print(f"Configured EMBEDDING_DIMENSIONS: {settings.embedding_dimensions}")
    print(f"Returned dimensions: {len(vector)}")


if __name__ == "__main__":
    main()
