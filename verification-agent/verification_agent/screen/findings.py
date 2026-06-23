"""Judged-findings fetch + parse (Move B) — land an answer key for scoring.

A blind run can only be SCORED against the contest's judged H/M findings. They live
in Code4rena's public findings repos (`<contest>-findings`, containing `report.md`),
reachable by git. This module fetches that report and parses it into the scorer's
ANSWER_KEYS format: (id, title, mechanism, severity, hosts).

HARD SEPARATION (the wall): this module WRITES answer keys; it is fetch+score
infrastructure that runs AFTER a blind run is frozen. The BlindRunner still cannot
read answer keys (asserted by a test) — fetch never feeds the run.

Honesty: id / title / severity are parsed exactly from the report's structure. HOSTS
(contract.function) and MECHANISM are best-effort heuristics (regex over code refs;
keyword classification) — they are derived, not authoritative, and flagged as such.
If the findings host is unreachable offline, `fetch_findings_repo` returns None and
the caller must supply a saved `report.md` (manual-fetch documented, not faked).

State label: IMPLEMENTED (parser) / fetch depends on git reachability.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

# Section header -> severity. C4 reports group findings under these.
_SECTION = re.compile(r"^#+\s*(High|Medium)\s+Risk\s+Findings", re.I)
# A finding heading: ## [[H-01] Title ...](url)  (url optional)
_FINDING = re.compile(r"^#+\s*\[+\s*([HM]-\d+)\]\s*(.+?)\](?:\((.*?)\))?\s*$")
# A code reference in title/body: Contract.fn / Contract:fn / Contract::fn
_HOSTREF = re.compile(r"\b([A-Z][A-Za-z0-9]+)\s*[:.]{1,2}\s*([a-z_][A-Za-z0-9_]*)\b")

# Keyword -> mechanism class (matches the scorer's lane vocabulary). Heuristic.
_MECH = [
    ("access-control", ("access control", "anyone can", "without ", "directly",
                         "missing access", "permission", "unauthorized", "bypass")),
    ("signature-verification", ("signature", "ecrecover", "permit", "signed")),
    ("cross-domain-auth", ("cross-chain", "cross chain", "lzreceive", "origin",
                           "trusted remote", "messenger")),
    ("replay", ("replay", "nonce", "reused")),
    ("gas", ("gas", "minimum gas", "out of gas")),
    ("fund-routing", ("funds will be sent", "refund", "stuck", "random address",
                      "lose their", "loss of tokens")),
    ("rounding", ("rounding", "round up", "round down", "precision")),
    ("accounting", ("fee calculation", "fixed fee", "capital", "accounting")),
]


@dataclass
class JudgedFinding:
    id: str
    title: str
    severity: str            # "High" | "Medium"
    hosts: list[str]
    mechanism: str
    url: str = ""

    def to_answer_key_tuple(self) -> tuple:
        # (id, title, mechanism, severity, hosts) — the ANSWER_KEYS row format.
        return (self.id, self.title, self.mechanism, self.severity, self.hosts)


def _classify(text: str) -> str:
    t = text.lower()
    for mech, kws in _MECH:
        if any(k in t for k in kws):
            return mech
    return "unknown"


_NOT_FN = {"sol", "t", "s", "md", "io", "com"}  # file extensions / non-functions


def _hosts(text: str, limit: int = 4) -> list[str]:
    seen: list[str] = []
    for c, f in _HOSTREF.findall(text):
        if f in _NOT_FN:            # drop Contract.sol filename refs
            continue
        h = f"{c}.{f}"
        if h not in seen:
            seen.append(h)
        if len(seen) >= limit:
            break
    return seen


def parse_c4_report(markdown: str) -> list[JudgedFinding]:
    """Parse a Code4rena report.md into judged H/M findings."""
    lines = markdown.splitlines()
    findings: list[JudgedFinding] = []
    severity = ""
    # Index finding-heading line numbers to grab a body slice for host extraction.
    heads: list[tuple[int, str, str, str, str]] = []  # (lineno, id, title, url, sev)
    for i, line in enumerate(lines):
        sec = _SECTION.match(line)
        if sec:
            severity = sec.group(1).capitalize()
            continue
        m = _FINDING.match(line)
        if m and severity:
            heads.append((i, m.group(1), m.group(2).strip(), m.group(3) or "", severity))
    for idx, (lineno, fid, title, url, sev) in enumerate(heads):
        end = heads[idx + 1][0] if idx + 1 < len(heads) else len(lines)
        body = "\n".join(lines[lineno:end])
        hosts = _hosts(title) or _hosts(body)
        mech = _classify(title + " " + body[:400])
        findings.append(JudgedFinding(id=fid, title=title, severity=sev,
                                      hosts=hosts, mechanism=mech, url=url))
    return findings


def to_answer_key(findings: list[JudgedFinding]) -> list[tuple]:
    return [f.to_answer_key_tuple() for f in findings]


def fetch_findings_repo(contest_id: str, dest: Path) -> Path | None:
    """Clone `code-423n4/<contest_id>-findings` and return its report.md, or None.

    Real retrieval via git. If the host is unreachable (offline), returns None —
    the caller must supply a saved report.md (manual-fetch, documented, not faked).
    """
    url = f"https://github.com/code-423n4/{contest_id}-findings"
    try:
        subprocess.run(["git", "clone", "--depth", "1", "-q", url, str(dest)],
                       check=True, capture_output=True, text=True, timeout=120)
    except Exception:
        return None
    report = dest / "report.md"
    return report if report.exists() else None
