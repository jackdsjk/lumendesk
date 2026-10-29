"""Offline embedding function used by the demo's Chroma collections."""

from __future__ import annotations

import hashlib
import math
import re
from typing import List, Sequence

import numpy as np


class DemoEmbeddingFunction:
    """Deterministic 384-dimensional feature hashing with no network dependency."""

    dimension = 384
    _token_pattern = re.compile(r"\w+|[^\w\s]", re.UNICODE)

    def __call__(self, input: Sequence[str]) -> List[np.ndarray]:
        return [self._embed(text) for text in input]

    @classmethod
    def _embed(cls, text: str) -> np.ndarray:
        vector = [0.0] * cls.dimension
        tokens = cls._token_pattern.findall(str(text).lower())
        if not tokens:
            return np.asarray(vector, dtype=np.float32)
        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
            index = int.from_bytes(digest[:4], "big") % cls.dimension
            vector[index] += 1.0 if digest[4] & 1 else -1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return np.asarray([value / norm for value in vector], dtype=np.float32)
