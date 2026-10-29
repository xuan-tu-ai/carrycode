"""Candidate registry and versioned carrier store (Appendix A.1)."""

import posixpath

from carrycode.records import Candidate, CarrierEdit, CarrierRecord, CarrierType


def make_carrier_id(carrier_type: CarrierType, subject: str) -> str:
    """Stable identity from type and normalized subject (App. A.1).

    external_object: strip whitespace, drop a leading "/testbed/" or "./", then posixpath.normpath.
    other types: collapse runs of whitespace to one space and strip.
    Result: f"{carrier_type.value}:{normalized}".
    """
    if carrier_type == CarrierType.EXTERNAL_OBJECT:
        s = subject.strip()
        if s.startswith("/testbed/"):
            s = s.removeprefix("/testbed/")
        elif s.startswith("./"):
            s = s.removeprefix("./")
        normalized = posixpath.normpath(s)
    else:
        normalized = " ".join(subject.split())
    return f"{carrier_type.value}:{normalized}"


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

    def materialize(self, edits: list[CarrierEdit], fold_number: int) -> list[CarrierRecord]:
        """Turn edits into records: version 1 for new carriers, current + 1 (predecessor = current) for updates.
        Does not change the store."""
        records: list[CarrierRecord] = []
        for edit in edits:
            cid = edit.carrier_id or make_carrier_id(edit.carrier_type, edit.subject)
            current = self.get(cid)
            if current is None:
                version = 1
                predecessor_version = None
            else:
                version = current.version + 1
                predecessor_version = current.version
            records.append(
                CarrierRecord(
                    carrier_id=cid,
                    version=version,
                    predecessor_version=predecessor_version,
                    carrier_type=edit.carrier_type,
                    subject=edit.subject,
                    summary=edit.summary,
                    conditions=list(edit.conditions),
                    claims=list(edit.claims),
                    committed_at_fold=fold_number,
                )
            )
        return records

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
