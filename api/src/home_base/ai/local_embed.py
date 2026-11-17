"""Embeddings on this machine (ADR-009, D-84): BAAI/bge-small-en-v1.5 through fastembed.

Free and private: no key, nothing sent anywhere. The model (67 MB, MIT licence) is
downloaded from Hugging Face on first use into ~/.cache/home-base/fastembed. Its 384
numbers are zero-padded to the database's EMBEDDING_DIMENSIONS, which leaves cosine
distance unchanged, so the column stays the same for every provider.
"""

from collections.abc import Sequence
from functools import cache
from pathlib import Path
from typing import Any

from home_base.ai.provider import normalised
from home_base.config import EMBEDDING_DIMENSIONS

MODEL = "BAAI/bge-small-en-v1.5"
NAME = "bge-small-en-v1.5"
CACHE = Path.home() / ".cache" / "home-base" / "fastembed"


def padded(vector: Sequence[float]) -> list[float]:
    """The vector normalised and zero-padded to EMBEDDING_DIMENSIONS."""
    if len(vector) > EMBEDDING_DIMENSIONS:
        raise ValueError(f"{len(vector)} numbers do not fit in {EMBEDDING_DIMENSIONS}")
    return normalised(list(vector)) + [0.0] * (EMBEDDING_DIMENSIONS - len(vector))


@cache
def _model() -> Any:  # fastembed has no type information
    from fastembed import TextEmbedding

    return TextEmbedding(MODEL, cache_dir=str(CACHE))


class LocalEmbedder:
    embedding_model = NAME

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        return [padded([float(x) for x in v]) for v in _model().embed(list(texts))]
