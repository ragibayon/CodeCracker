from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


LOG_DIR = Path("logs")


def _load_run(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _token_total(token_usage: dict[str, Any] | None) -> int | None:
    if not isinstance(token_usage, dict):
        return None

    for key in ("total_tokens", "total_token_count", "input_tokens", "output_tokens"):
        value = token_usage.get(key)
        if isinstance(value, int) and key.startswith("total"):
            return value

    input_tokens = token_usage.get("input_tokens")
    output_tokens = token_usage.get("output_tokens")
    if isinstance(input_tokens, int) and isinstance(output_tokens, int):
        return input_tokens + output_tokens

    return None


def analyze_runs(log_dir: Path = LOG_DIR) -> dict[str, Any]:
    run_files = sorted(log_dir.glob("*/run.json"))
    runs = [_load_run(path) for path in run_files]

    tool_call_totals: list[int] = []
    cwe_counter: Counter[str] = Counter()
    model_stats: dict[str, dict[str, list[float | int]]] = defaultdict(
        lambda: {"latencies": [], "tokens": [], "tool_calls": []}
    )

    for run in runs:
        metrics = run.get("metrics", {})
        tooling = run.get("tooling", {})
        model = run.get("model") or "unknown"

        total_tool_calls = sum((tooling.get("tool_call_counts") or {}).values())
        tool_call_totals.append(total_tool_calls)
        model_stats[model]["tool_calls"].append(total_tool_calls)

        latency = metrics.get("latency_seconds")
        if isinstance(latency, (int, float)):
            model_stats[model]["latencies"].append(latency)

        tokens = _token_total(metrics.get("token_usage"))
        if isinstance(tokens, int):
            model_stats[model]["tokens"].append(tokens)

        cwe_counter.update(tooling.get("cwe_ids", []))

    def avg(values: list[float | int]) -> float | None:
        return round(sum(values) / len(values), 3) if values else None

    return {
        "num_runs": len(runs),
        "average_tool_calls_per_run": avg(tool_call_totals),
        "common_cwes": cwe_counter.most_common(),
        "per_model": {
            model: {
                "average_latency_seconds": avg(stats["latencies"]),
                "average_total_tokens": avg(stats["tokens"]),
                "average_tool_calls": avg(stats["tool_calls"]),
                "num_runs": len(stats["tool_calls"]),
            }
            for model, stats in sorted(model_stats.items())
        },
    }


def main() -> None:
    print(json.dumps(analyze_runs(), indent=2))


if __name__ == "__main__":
    main()
