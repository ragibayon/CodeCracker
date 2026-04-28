from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from rich.console import Console
from rich.panel import Panel
from rich.status import Status
from rich.syntax import Syntax

console = Console()
LOG_DIR = Path("logs")


def _format_json(value: Any) -> str:
    return json.dumps(value, indent=2, default=str)


def _message_attr(message: Any, key: str, default: Any = None) -> Any:
    if isinstance(message, dict):
        return message.get(key, default)
    return getattr(message, key, default)


def _extract_tool_calls(raw_agent_output: dict[str, Any]) -> list[dict[str, Any]]:
    tool_calls: list[dict[str, Any]] = []

    for message in raw_agent_output.get("messages", []):
        if _message_attr(message, "type") != "ai":
            continue

        for tool_call in _message_attr(message, "tool_calls", []) or []:
            if isinstance(tool_call, dict):
                tool_calls.append(
                    {
                        "id": tool_call.get("id"),
                        "name": tool_call.get("name"),
                        "args": tool_call.get("args"),
                    }
                )

    return tool_calls


def _parse_tool_message_content(content: Any) -> Any:
    if isinstance(content, str):
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return content
    return content


def _extract_tool_results(raw_agent_output: dict[str, Any]) -> list[dict[str, Any]]:
    tool_calls_by_id = {
        tool_call.get("id"): tool_call
        for tool_call in _extract_tool_calls(raw_agent_output)
        if tool_call.get("id")
    }
    tool_results: list[dict[str, Any]] = []

    for message in raw_agent_output.get("messages", []):
        if _message_attr(message, "type") != "tool":
            continue

        tool_call_id = _message_attr(message, "tool_call_id")
        tool_call = tool_calls_by_id.get(tool_call_id, {})

        tool_results.append(
            {
                "tool_call_id": tool_call_id,
                "name": _message_attr(message, "name"),
                "status": _message_attr(message, "status"),
                "args": tool_call.get("args"),
                "content": _parse_tool_message_content(
                    _message_attr(message, "content")
                ),
                "artifact": _message_attr(message, "artifact"),
            }
        )

    return tool_results


def _extract_cwe_ids(tool_results: list[dict[str, Any]]) -> list[str]:
    cwe_ids: list[str] = []

    for result in tool_results:
        content = result.get("llm_context") or result.get("content")
        if isinstance(content, dict):
            cwe_ids.extend(content.get("cwe_ids", []) or [])

    return sorted(set(cwe_ids))


def _build_run_record(
    *,
    run_id: str,
    model: str,
    prompt: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    raw_agent_output = result.get("raw_agent_output") or {}
    llm_metrics = result.get("llm_metrics") or {}
    tool_calls = _extract_tool_calls(raw_agent_output)
    tool_results = _extract_tool_results(raw_agent_output)
    tool_call_counts = Counter(
        call.get("name") for call in tool_calls if call.get("name")
    )
    logged_tool_results = []
    for tool_result in tool_results:
        content = tool_result.get("content")
        artifact = tool_result.get("artifact")
        if isinstance(artifact, dict) and "llm_context" in artifact:
            logged_tool_results.append(
                {
                    **tool_result,
                    "llm_context": artifact.get("llm_context"),
                    "verbose_content": artifact.get("verbose"),
                }
            )
        elif isinstance(content, dict) and "llm_context" in content:
            logged_tool_results.append(
                {
                    **tool_result,
                    "llm_context": content.get("llm_context"),
                    "verbose_content": content.get("verbose"),
                }
            )
        else:
            logged_tool_results.append(
                {
                    **tool_result,
                    "llm_context": content,
                    "verbose_content": content,
                }
            )

    return {
        "run_id": run_id,
        "logged_at": datetime.now().isoformat(),
        "model": {
            "name": model,
            "parameters": result.get("model_parameters"),
        },
        "run_parameters": result.get("run_parameters"),
        "dataset": result.get("dataset"),
        "prompt": prompt,
        "result": {
            "passed": result.get("passed"),
            "pass_at": result.get("pass_at"),
            "final_code": result.get("final_code"),
            "structured_response": result.get("structured_response"),
        },
        "metrics": {
            "ai_turns": result.get("ai_turns"),
            "tool_rounds": result.get("tool_rounds"),
            "latency_seconds": llm_metrics.get("latency"),
            "token_usage": llm_metrics.get("token_usage"),
        },
        "tooling": {
            "tool_call_counts": dict(tool_call_counts),
            "tool_results": logged_tool_results,
            "cwe_ids": _extract_cwe_ids(logged_tool_results),
        },
        "raw_agent_output": raw_agent_output,
    }


def create_run_log_dir() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
    run_id = f"{timestamp}-{uuid4().hex[:8]}"
    run_dir = LOG_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def write_run_log(
    run_dir: Path,
    *,
    model: str,
    prompt: str,
    result: dict[str, Any],
) -> None:
    run_record = _build_run_record(
        run_id=run_dir.name,
        model=model,
        prompt=prompt,
        result=result,
    )
    (run_dir / "run.json").write_text(_format_json(run_record), encoding="utf-8")


def print_run_start(
    *,
    model: str,
    prompt: str,
    parameters: dict[str, Any] | None = None,
) -> None:
    preview = prompt[:200] + ("..." if len(prompt) > 200 else "")
    parameter_lines = []
    if parameters:
        parameter_lines = [f"{key}: {value}" for key, value in parameters.items()]
    header_lines = ["Hello from CodeCracker", f"Model: {model}", *parameter_lines]

    console.print(
        Panel.fit("\n".join(header_lines), title="CodeCracker", border_style="cyan")
    )
    console.print(Panel(preview, title="Prompt Preview", border_style="cyan"))


def start_run_loader(message: str = "Running ReAct agent") -> Status:
    status = console.status(message, spinner="dots")
    status.start()
    return status


def print_run_result(result: dict[str, Any]) -> None:
    raw_agent_output = result.get("raw_agent_output") or {}
    tool_results = _extract_tool_results(raw_agent_output)
    summary = f"Passed: {result['passed']}\nPass at: {result['pass_at']}"
    if result.get("log_dir"):
        summary += f"\nLog Dir: {result['log_dir']}"
    console.print(Panel.fit(summary, title="Result", border_style="cyan"))

    console.print(
        Panel(
            Syntax(
                result["final_code"],
                "python",
                theme="monokai",
                line_numbers=True,
            ),
            title="Final Code",
            border_style="cyan",
        )
    )

    console.print(
        Panel(
            _format_json(result.get("llm_metrics")),
            title="LLM Metrics",
            border_style="cyan",
        )
    )

    for index, tool_result in enumerate(tool_results, start=1):
        tool_name = tool_result.get("name") or f"Tool #{index}"
        content = tool_result.get("content")
        llm_context = (
            content.get("llm_context")
            if isinstance(content, dict) and "llm_context" in content
            else content
        )
        tool_summary = {
            "tool_call_id": tool_result.get("tool_call_id"),
            "status": tool_result.get("status"),
            "args": tool_result.get("args"),
            "content": llm_context,
        }
        console.print(
            Panel(
                _format_json(tool_summary),
                title=f"Tool Result: {tool_name}",
                border_style="cyan",
            )
        )


def print_run_error(result: dict[str, Any]) -> None:
    summary = "Passed: False\nPass at: None"
    if result.get("log_dir"):
        summary += f"\nLog Dir: {result['log_dir']}"
    console.print(Panel.fit(summary, title="Result", border_style="red"))

    error_payload = {
        "error_type": result.get("error_type"),
        "error_message": result.get("error_message"),
    }
    console.print(
        Panel(
            _format_json(error_payload),
            title="Run Error",
            border_style="red",
        )
    )
