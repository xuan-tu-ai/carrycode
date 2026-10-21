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
    info = traj.get("info", {})
    model_stats = info.get("model_stats", {})

    # Host tokens: sum over assistant messages.
    host_input = 0
    host_output = 0
    for msg in traj.get("messages", []):
        if msg.get("role") != "assistant":
            continue
        usage = msg.get("extra", {}).get("response", {}).get("usage", {})
        host_input += usage.get("prompt_tokens", 0) or 0
        host_output += usage.get("completion_tokens", 0) or 0

    result = TaskUsage(
        instance_id=traj.get("instance_id", ""),
        exit_status=info.get("exit_status", ""),
        host_calls=model_stats.get("api_calls", 0),
        host_input_tokens=host_input,
        host_output_tokens=host_output,
        host_cost=model_stats.get("instance_cost", 0.0),
    )

    # Runtime section (written by T016).
    carryon = info.get("carryon")
    if isinstance(carryon, dict):
        role_usage = carryon.get("role_usage", {})
        for role_name in ("tracker", "compiler"):
            role = role_usage.get(role_name, {})
            result.runtime_calls += role.get("calls", 0)
            result.runtime_input_tokens += role.get("input_tokens", 0)
            result.runtime_output_tokens += role.get("output_tokens", 0)
            result.runtime_cost += role.get("cost", 0.0)
        fold_stats = carryon.get("fold_stats", {})
        result.folds_attempted = fold_stats.get("attempts", 0)
        result.folds_committed = fold_stats.get("committed", 0)

    return result
