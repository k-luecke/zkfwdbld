# M2 — The knowledge base (hypothesis priors)

> **State: IMPLEMENTED.** Lane-curated, mechanism-structured, dual-source.
> Demo on the M-03 surface: [`examples/m2_kb_m03_query.txt`](../examples/m2_kb_m03_query.txt)
> (+ structured [`.json`](../examples/m2_kb_m03_query.json)).

The KB grounds M3's hypotheses. Its job is **precise retrieval in our lane**, not
coverage. Three design commitments shape it.

## 1. Retrieve on mechanism, not prose

Raw finding text retrieves on vocabulary ("bridge", "signature") and returns
surface matches that poison hypotheses with confident-but-irrelevant neighbours.
So every entry is **mechanism-structured** ([`schema.py`](../verification_agent/kb/schema.py)):

- `surfaces` — M0's lane tags (signature/merkle/bridge/cross-domain/slashing)
- `bug_class` — e.g. `alt-entrypoint-auth-bypass`
- `root_cause_category` — e.g. `access-control`, `replay`, `proof-forgery`
- `invariant_violated` — e.g. `access-control-consistency`, `replay-resistance`
- `entrypoint_shape` — e.g. "public fn reaching a privileged action w/o the auth modifier"
- `mechanism` — 1–3 sentences of *how* it breaks (the prose, used only as a tiebreaker)

Scoring ([`store.py`](../verification_agent/kb/store.py)) weights mechanism
fields ~0.86 and lexical prose ~0.14, renormalized over the signals the query
actually carries. The result: "same *class* of invariant broke the same *way*",
not "mentions bridges".

### Proof: mechanism beats vocabulary

Querying the **M-03 surface** with only surfaces + free text (the M0-derivable
signal), top hits are the real M-03 finding, then the *same bug-class* OAK
taxonomy entry, then access-control/cross-domain mechanisms across **different
protocols** (Poly Network, DcntEth). A deliberate **vocabulary decoy** — a
"bridge fee rounding" finding stuffed with `bridge`/`fee` words but whose
mechanism is integer rounding — ranks **#18 of 20**. Vocabulary overlap did not
pull it up, because its surface/mechanism don't match.

## 2. Dual-source, blended at retrieval, provenance-tagged

OAK and the worked-examples corpus answer different questions and stay separate
([`Source`](../verification_agent/kb/schema.py)):

- **`oak_taxonomy`** — the space of *what kinds* of attacks exist on a surface
  (M3's hypothesis-generation scaffold). Taxonomy only; no contest is claimed.
- **`contest_finding` / `public_incident`** — *worked examples* of those attacks
  in real code (M3's concrete priors). Real, named, public sources only — e.g.
  Code4rena 2024-01-decent M-03/H-01/H-03, Nomad (2022), Wormhole (2022), Poly
  Network (2021).

`retrieve_priors` blends them; every `PriorMatch` carries `entry.source`, and
`source_breakdown()` reports the mix — the knob to later measure which source is
carrying M3's hypotheses. `enumerate_mechanisms()` (OAK-only) and
`ground_mechanism()` (findings-only) expose each source directly. In the demo,
the M-03 top-6 is a balanced 2 contest / 2 OAK / 2 incident.

## 3. A prior is never a verdict (bright code boundary)

The KB makes the agent *fast*; the M1 gate keeps it *honest*. They stay separate
by construction:

- results are `PriorMatch` objects with `is_verdict = False` and **no field that
  could carry a confirmation**;
- the method is `retrieve_priors`, and its docstring states a prior is a reason
  to investigate, never to report;
- nothing in `kb/` imports or touches the gate.

A retrieved finding that looks like the target is a reason to *run the gate*,
never to surface a finding. The gate confirms every time.

## Curation & corpus

Source of truth is [`tools/build_corpus.py`](../tools/build_corpus.py) →
`kb/data/{oak_matrix,findings_corpus}.jsonl` (editable JSONL; extend without
code). Bias is deliberately verification / cross-chain / ZK. A smaller corpus
that retrieves precisely beats a giant one that retrieves noise.

## Embedding & the offline constraint

Neural embedding models download from hosts blocked in this environment (the
same wall that blocks the public `solc` host). A stock vocabulary-embedding
vector store is also exactly the "retrieves on words" failure mode. So retrieval
uses a **mechanism-feature retriever** with a deterministic lexical tiebreaker
([`embedder.py`](../verification_agent/kb/embedder.py)). The lexical component
sits behind an `Embedder` protocol so a neural backend (Voyage / local model) or
a Chroma/sqlite vector backend can drop in for the prose component without
touching the mechanism scoring.

State: mechanism retriever IMPLEMENTED; neural/Chroma backend PROPOSED.

## Run it

```bash
python -m verification_agent kb --demo                       # the M-03 surface demo
python -m verification_agent kb --surface bridge_inbound_handler \
       --surface cross_domain_auth --text "receiveFromBridge swapAndExecute"
python -m verification_agent kb --surface signature_proof_verification \
       --root-cause replay --invariant replay-resistance     # mechanism-narrowed
```
