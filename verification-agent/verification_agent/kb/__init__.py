"""Knowledge base (M2) — lane-curated, mechanism-structured, dual-source.

A hypothesis PRIOR, never a verdict. Retrieval makes the agent fast; the M1 gate
keeps it honest. The two stay separate by construction (see schema.PriorMatch).
"""

from .embedder import Embedder, LexicalEmbedder
from .query import query_for_m03_surface, query_from_surface_function
from .schema import KBEntry, KBQuery, PriorMatch, Source
from .store import KnowledgeBase

__all__ = [
    "KnowledgeBase",
    "KBEntry",
    "KBQuery",
    "PriorMatch",
    "Source",
    "Embedder",
    "LexicalEmbedder",
    "query_for_m03_surface",
    "query_from_surface_function",
]
