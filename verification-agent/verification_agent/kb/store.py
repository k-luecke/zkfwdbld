"""The knowledge base — lane-curated, mechanism-structured, dual-source.

Retrieval ranks on *mechanism* (surface tags, root-cause, invariant, entrypoint
shape) with prose lexical similarity as a low-weight tiebreaker. OAK and the
findings/incident corpus are loaded as distinct sources, blended at query time,
and every result carries its provenance so M3 can later measure which source is
carrying the hypotheses.

Guardrail: results are `PriorMatch` objects — hypothesis priors, never verdicts.
There is no method here that returns a confirmation. The gate confirms.

State label: IMPLEMENTED.
"""

from __future__ import annotations

from pathlib import Path

from .embedder import Embedder, LexicalEmbedder, tokenize
from .schema import KBEntry, KBQuery, PriorMatch, Source

_DATA = Path(__file__).resolve().parent / "data"

# Mechanism dominates; prose is a tiebreaker. Components are renormalized over
# the signals the query actually provides (see _score).
_WEIGHTS = {
    "surface": 0.34,
    "root_cause": 0.24,
    "invariant": 0.18,
    "entrypoint": 0.10,
    "lexical": 0.14,
}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _token_overlap(a: str, b: str) -> float:
    ta, tb = set(tokenize(a)), set(tokenize(b))
    return _jaccard(ta, tb)


class KnowledgeBase:
    def __init__(self, entries: list[KBEntry], embedder: Embedder | None = None):
        self.entries = entries
        self.embedder = embedder or LexicalEmbedder()
        # Precompute the lexical vector per entry (mechanism + title + tags).
        self._vec = {
            e.id: self.embedder.vector(self._lexical_blob(e)) for e in entries
        }

    # ---- loading --------------------------------------------------------

    @classmethod
    def from_data(cls, data_dir: Path | None = None,
                  embedder: Embedder | None = None) -> "KnowledgeBase":
        data_dir = Path(data_dir) if data_dir else _DATA
        entries: list[KBEntry] = []
        for name in ("oak_matrix.jsonl", "findings_corpus.jsonl"):
            entries.extend(cls._load_jsonl(data_dir / name))
        return cls(entries, embedder=embedder)

    @staticmethod
    def _load_jsonl(path: Path) -> list[KBEntry]:
        import json
        if not path.exists():
            return []
        out = []
        for line in path.read_text().splitlines():
            line = line.strip()
            if line:
                out.append(KBEntry.from_dict(json.loads(line)))
        return out

    # ---- retrieval ------------------------------------------------------

    def retrieve_priors(
        self,
        query: KBQuery,
        k: int = 5,
        sources: list[Source] | None = None,
    ) -> list[PriorMatch]:
        """Return up to k hypothesis PRIORS, highest mechanism-match first.

        A prior is a reason to investigate, never a reason to report — the gate
        confirms every finding independently.
        """
        pool = self.entries
        if sources:
            allow = set(sources)
            pool = [e for e in pool if e.source in allow]

        scored = [self._score(query, e) for e in pool]
        scored.sort(key=lambda m: m.score, reverse=True)
        return scored[:k]

    def enumerate_mechanisms(self, surfaces: list[str], k: int = 8) -> list[PriorMatch]:
        """OAK-only: 'what kinds of attacks exist on these surfaces' (scaffold)."""
        return self.retrieve_priors(
            KBQuery(surfaces=surfaces), k=k, sources=[Source.OAK_TAXONOMY])

    def ground_mechanism(self, query: KBQuery, k: int = 5) -> list[PriorMatch]:
        """Worked-examples-only: how this mechanism manifested in real code."""
        return self.retrieve_priors(
            query, k=k,
            sources=[Source.CONTEST_FINDING, Source.PUBLIC_INCIDENT])

    def source_breakdown(self, matches: list[PriorMatch]) -> dict[str, int]:
        out: dict[str, int] = {}
        for m in matches:
            out[m.entry.source.value] = out.get(m.entry.source.value, 0) + 1
        return out

    # ---- scoring --------------------------------------------------------

    def _score(self, q: KBQuery, e: KBEntry) -> PriorMatch:
        comps: dict[str, float] = {}
        active: list[str] = []

        # surface (always active if the query names surfaces)
        if q.surfaces:
            comps["surface"] = _jaccard(set(q.surfaces), set(e.surfaces))
            active.append("surface")

        # mechanism narrowings — only when the query provides the hint
        if q.root_cause_hint:
            comps["root_cause"] = _token_overlap(
                q.root_cause_hint, f"{e.root_cause_category} {e.bug_class}")
            active.append("root_cause")
        if q.invariant_hint:
            comps["invariant"] = _token_overlap(q.invariant_hint, e.invariant_violated)
            active.append("invariant")
        if q.entrypoint_shape:
            comps["entrypoint"] = _token_overlap(q.entrypoint_shape, e.entrypoint_shape)
            active.append("entrypoint")
        if q.text:
            comps["lexical"] = self.embedder.similarity(
                self.embedder.vector(q.text), self._vec[e.id])
            active.append("lexical")

        # Renormalize weights over the signals actually present in the query, so
        # a surface+text query isn't penalized for omitting hints it doesn't have.
        total_w = sum(_WEIGHTS[c] for c in active) or 1.0
        score = sum(_WEIGHTS[c] * comps[c] for c in active) / total_w
        return PriorMatch(entry=e, score=score, component_scores=comps)

    @staticmethod
    def _lexical_blob(e: KBEntry) -> str:
        return " ".join([e.title, e.mechanism, e.entrypoint_shape,
                         e.bug_class, " ".join(e.tags)])
