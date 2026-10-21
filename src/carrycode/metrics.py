"""Implements the per-task accounting of App. B.3 (tokens and cost of host plus runtime calls)."""

from __future__ import annotations

from pydantic import BaseModel


class TaskUsage(BaseModel):
    instance_id: str = ""
    exit_status: str = ""
    host_calls: int = 0
    host_input_tokens: int = 0
    host_output_tokens: int = 0
    host_cost: float = 0.0
    runtime_calls: int = 0
    runtime_input_tokens: int = 0
    runtime_output_tokens: int = 0
    runtime_cost: float = 0.0
    folds_attempted: int = 0
    folds_committed: int = 0

    def total_tokens(self) -> int:
        return self.host_input_tokens + self.host_output_tokens + self.runtime_input_tokens + self.runtime_output_tokens

    def total_cost(self) -> float:
        return self.host_cost + self.runtime_cost


def trajectory_usage(traj: dict) -> TaskUsage:
    """Extract token, cost and fold counts from a saved trajectory dict."""
    info = traj.get("info") or {}
    model_stats = info.get("model_stats") or {}

    # Host tokens: every message that carries a billed API response. This includes the
    # user-role message mini-swe-agent stores when a reply fails to parse (FormatError).
    host_input = 0
    host_output = 0
    for msg in traj.get("messages") or []:
        response = (msg.get("extra") or {}).get("response")
        if not isinstance(response, dict):
            continue
        usage = response.get("usage") or {}
        host_input += usage.get("prompt_tokens") or 0
        host_output += usage.get("completion_tokens") or 0

    result = TaskUsage(
        instance_id=traj.get("instance_id") or "",
        exit_status=info.get("exit_status") or "",
        host_calls=model_stats.get("api_calls") or 0,
        host_input_tokens=host_input,
        host_output_tokens=host_output,
        host_cost=model_stats.get("instance_cost") or 0.0,
    )

    # Runtime section (written by T016).
    carryon = info.get("carryon")
    if isinstance(carryon, dict):
        role_usage = carryon.get("role_usage") or {}
        for role_name in ("tracker", "compiler"):
            role = role_usage.get(role_name) or {}
            result.runtime_calls += role.get("calls") or 0
            result.runtime_input_tokens += role.get("input_tokens") or 0
            result.runtime_output_tokens += role.get("output_tokens") or 0
            result.runtime_cost += role.get("cost") or 0.0
        fold_stats = carryon.get("fold_stats") or {}
        result.folds_attempted = fold_stats.get("attempts") or 0
        result.folds_committed = fold_stats.get("committed") or 0

    return result
