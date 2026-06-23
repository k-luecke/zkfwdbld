"""Embedder interface + an offline lexical default.

The retriever keys on structured mechanism fields; lexical similarity is only a
low-weight tiebreaker over prose. This module isolates that lexical component
behind an `Embedder` protocol so a neural embedder (Voyage/local model) can drop
in later without touching the mechanism scoring — when the network allows model
weights, which it does not here.

State label: IMPLEMENTED (lexical). Neural backend: PROPOSED.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Protocol

_STOP = {
    "the", "a", "an", "to", "of", "and", "or", "is", "are", "in", "on", "for",
    "with", "that", "this", "it", "as", "be", "by", "at", "from", "via", "no",
    "not", "any", "so", "if", "then", "into", "via", "via", "fn", "function",
}

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def tokenize(text: str) -> list[str]:
    """Lowercase tokens, splitting camelCase so receiveFromBridge -> receive from bridge."""
    if not text:
        return []
    spaced = _CAMEL.sub(" ", text)
    raw = re.split(r"[^A-Za-z0-9]+", spaced)
    return [t.lower() for t in raw if t and t.lower() not in _STOP and len(t) > 1]


class Embedder(Protocol):
    def vector(self, text: str) -> Counter: ...
    def similarity(self, a: Counter, b: Counter) -> float: ...


class LexicalEmbedder:
    """Bag-of-terms TF vectors with cosine similarity. Deterministic, offline."""

    def vector(self, text: str) -> Counter:
        return Counter(tokenize(text))

    def similarity(self, a: Counter, b: Counter) -> float:
        if not a or not b:
            return 0.0
        common = set(a) & set(b)
        if not common:
            return 0.0
        dot = sum(a[t] * b[t] for t in common)
        na = math.sqrt(sum(v * v for v in a.values()))
        nb = math.sqrt(sum(v * v for v in b.values()))
        return dot / (na * nb) if na and nb else 0.0
