"""Offline tests for the M2 knowledge base.

Cover the properties the design notes demand: mechanism beats vocabulary,
dual-source separation with provenance, and the prior-not-verdict guardrail.
No network or model downloads.
"""

from verification_agent.kb import (
    KnowledgeBase,
    Source,
    query_for_m03_surface,
)
from verification_agent.kb.schema import KBQuery


def _kb():
    return KnowledgeBase.from_data()


def test_corpus_loads_both_sources():
    kb = _kb()
    sources = {e.source for e in kb.entries}
    assert Source.OAK_TAXONOMY in sources
    assert Source.CONTEST_FINDING in sources
    assert Source.PUBLIC_INCIDENT in sources
    assert len(kb.entries) >= 15


def test_m03_surface_retrieves_same_mechanism_first():
    kb = _kb()
    matches = kb.retrieve_priors(query_for_m03_surface(), k=3)
    # Top hit is the real M-03 finding, by mechanism.
    assert matches[0].entry.id == "c4.2024-01-decent.M-03"
    # The same bug-class shows up across sources (OAK taxonomy of the same class).
    classes = {m.entry.bug_class for m in matches}
    assert "alt-entrypoint-auth-bypass" in classes


def test_vocabulary_decoy_ranks_low():
    kb = _kb()
    full = kb.retrieve_priors(query_for_m03_surface(), k=len(kb.entries))
    order = [m.entry.id for m in full]
    decoy_rank = order.index("decoy.bridge-fee-rounding")
    # Despite heavy bridge/fee vocabulary, the rounding decoy must sit in the
    # bottom third — mechanism, not words.
    assert decoy_rank > 2 * len(order) // 3


def test_mechanism_hint_reranks_within_surface():
    kb = _kb()
    q = query_for_m03_surface()
    hinted = KBQuery(surfaces=q.surfaces, text=q.text,
                     root_cause_hint="access control bypass alternate entrypoint",
                     invariant_hint="access-control-consistency")
    ids = [m.entry.id for m in kb.retrieve_priors(hinted, k=4)]
    # Access-control mechanism entries dominate; the proof-forgery Nomad
    # incident (same bridge surface, different mechanism) is not top-tier.
    assert "incident.nomad.2022" not in ids


def test_sources_are_separable():
    kb = _kb()
    oak = kb.enumerate_mechanisms(
        ["bridge_inbound_handler", "cross_domain_auth"], k=5)
    assert oak and all(m.entry.source is Source.OAK_TAXONOMY for m in oak)

    grounded = kb.ground_mechanism(query_for_m03_surface(), k=5)
    assert grounded and all(
        m.entry.source in (Source.CONTEST_FINDING, Source.PUBLIC_INCIDENT)
        for m in grounded)


def test_prior_is_never_a_verdict():
    kb = _kb()
    for m in kb.retrieve_priors(query_for_m03_surface(), k=5):
        # Hard guardrail: a retrieved prior carries no confirmation.
        assert m.is_verdict is False
        assert "is_verdict" in m.to_record()
        assert m.to_record()["is_verdict"] is False
