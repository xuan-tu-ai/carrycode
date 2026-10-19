"""Candidate registry and versioned carrier store (Appendix A.1)."""

from __future__ import annotations

from carrycode.records import Candidate, CarrierRecord


class CarrierStore:
    """Keeps every carrier version. The latest version of each carrier is the current one."""

    def __init__(self) -> None:
        self._history: dict[str, list[CarrierRecord]] = {}

    def current(self) -> list[CarrierRecord]:
        return [versions[-1] for versions in self._history.values()]

    def get(self, carrier_id: str) -> CarrierRecord | None:
        versions = self._history.get(carrier_id)
        return versions[-1] if versions else None

    def history(self, carrier_id: str) -> list[CarrierRecord]:
        return list(self._history.get(carrier_id, []))

    def apply(self, edits: list[CarrierRecord]) -> None:
        """Commit carrier edits atomically: validate all first, then write all.

        A new `carrier_id` must be version 1. An existing one must be exactly
        current version + 1 and name the current version as its predecessor.
        """
        for edit in edits:
            existing = self.get(edit.carrier_id)
            if existing is None:
                if edit.version != 1 or edit.predecessor_version is not None:
                    raise ValueError(f"new carrier {edit.carrier_id} must start at version 1")
            elif edit.version != existing.version + 1 or edit.predecessor_version != existing.version:
                raise ValueError(
                    f"carrier {edit.carrier_id}: expected successor of v{existing.version}, "
                    f"got v{edit.version} (predecessor {edit.predecessor_version})"
                )
        for edit in edits:
            self._history.setdefault(edit.carrier_id, []).append(edit)


class CandidateRegistry:
    """Tracks candidates across Tracker invocations. Registering one never triggers a fold."""

    def __init__(self) -> None:
        self._candidates: dict[str, Candidate] = {}

    def upsert(self, candidate: Candidate) -> None:
        self._candidates[candidate.candidate_id] = candidate

    def get(self, candidate_id: str) -> Candidate | None:
        return self._candidates.get(candidate_id)

    def all(self) -> list[Candidate]:
        return list(self._candidates.values())

    def remove(self, candidate_id: str) -> None:
        self._candidates.pop(candidate_id, None)
