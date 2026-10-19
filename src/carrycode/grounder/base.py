"""Verdict rules of Appendix A.2.

A condition is supported, contradicted or unknown. A request is supported only when every
condition is supported; any contradiction makes it contradicted; otherwise it is unknown.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel


class Verdict(StrEnum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    UNKNOWN = "unknown"


class CheckResult(BaseModel):
    check_name: str
    target: str
    """What was checked, e.g. a file path or a test id."""
    verdict: Verdict
    observation: str
    """What the check saw (truncated command output, hash, ...). Kept as provenance."""


class Check(Protocol):
    """A read-only environment check. `env` is a mini-swe-agent Environment."""

    name: str

    def run(self, env, target: str, expected: str | None = None) -> CheckResult: ...


def aggregate(results: list[CheckResult]) -> Verdict:
    if not results:
        return Verdict.UNKNOWN
    verdicts = {r.verdict for r in results}
    if Verdict.CONTRADICTED in verdicts:
        return Verdict.CONTRADICTED
    if verdicts == {Verdict.SUPPORTED}:
        return Verdict.SUPPORTED
    return Verdict.UNKNOWN
