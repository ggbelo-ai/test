"""Embedding pipeline — OpenAI text embeddings for signal vectorization."""

from __future__ import annotations

import logging
import os
from typing import Sequence

import numpy as np
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

logger = logging.getLogger(__name__)

_client: OpenAI | None = None

DEFAULT_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
DEFAULT_DIMENSIONS = int(os.environ.get("EMBEDDING_DIMENSIONS", "1536"))

# OpenAI batch limit per request
MAX_BATCH_SIZE = 2048


def _get_client() -> OpenAI:
    """Return a singleton OpenAI client."""
    global _client
    if _client is None:
        api_key = os.environ.get("LLM_API_KEY")
        if not api_key:
            raise RuntimeError("LLM_API_KEY not set — required for embeddings")
        _client = OpenAI(api_key=api_key)
    return _client


def embed_texts(
    texts: Sequence[str],
    model: str = DEFAULT_MODEL,
    dimensions: int = DEFAULT_DIMENSIONS,
) -> np.ndarray:
    """Embed a list of texts using the OpenAI Embeddings API.

    Handles batching automatically for large input lists.

    Args:
        texts: Texts to embed.
        model: OpenAI embedding model name.
        dimensions: Output vector dimensions.

    Returns:
        numpy array of shape (len(texts), dimensions).
    """
    if not texts:
        return np.array([]).reshape(0, dimensions)

    all_embeddings: list[list[float]] = []
    client = _get_client()

    for i in range(0, len(texts), MAX_BATCH_SIZE):
        batch = list(texts[i : i + MAX_BATCH_SIZE])

        # Truncate empty strings to avoid API errors
        batch = [t if t.strip() else "empty" for t in batch]

        response = client.embeddings.create(
            model=model,
            input=batch,
            dimensions=dimensions,
        )

        # Sort by index to maintain order
        sorted_data = sorted(response.data, key=lambda x: x.index)
        all_embeddings.extend([d.embedding for d in sorted_data])

        logger.debug("Embedded batch %d-%d (%d texts)", i, i + len(batch), len(batch))

    logger.info("Embedded %d texts with model=%s dim=%d", len(texts), model, dimensions)
    return np.array(all_embeddings, dtype=np.float32)


def embed_single(text: str, model: str = DEFAULT_MODEL, dimensions: int = DEFAULT_DIMENSIONS) -> list[float]:
    """Embed a single text string. Returns a list of floats for direct DB storage."""
    result = embed_texts([text], model=model, dimensions=dimensions)
    return result[0].tolist()
