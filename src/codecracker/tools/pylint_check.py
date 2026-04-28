from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel


console = Console()


BLOCKING_TYPES = {"error", "fatal"}


def build_pylint_llm_context(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "tool": "pylint",
        "valid": result["valid"],
        "has_error": result["has_error"],
        "num_issues": len(result["feedback"]),
        "feedback": [
            {
                "type": item["type"],
                "fault": item["fault"],
                "severity": item["severity"],
                "hint": item["hint"],
                "source": {
                    "tool": "pylint",
                    "rule_id": item["pylint_code"],
                    "rule_name": item["symbolic_name"],
                },
            }
            for item in result["feedback"]
        ],
    }


def run_pylint_check(code: str, timeout: int = 15) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmpdir:
        code_path = Path(tmpdir) / "sample.py"
        code_path.write_text(code, encoding="utf-8")

        cmd = [
            "uv",
            "run",
            "pylint",
            str(code_path),
            "--output-format=json",
            "--score=n",
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        raw_output = result.stdout.strip()

        if not raw_output:
            report = []
        else:
            try:
                report = json.loads(raw_output)
            except json.JSONDecodeError:
                full_result = {
                    "tool": "pylint",
                    "valid": False,
                    "has_error": True,
                    "feedback": [
                        {
                            "type": "pylint_internal_error",
                            "fault": {
                                "start_line": None,
                                "end_line": None,
                                "column": None,
                                "code": None,
                            },
                            "severity": "HIGH",
                            "hint": "PyLint produced invalid JSON output.",
                            "pylint_code": None,
                            "symbolic_name": None,
                        }
                    ],
                    "raw_report": [],
                    "raw_output": result.stdout,
                    "stderr": result.stderr,
                    "returncode": result.returncode,
                }
                full_result["llm_context"] = build_pylint_llm_context(full_result)
                return full_result

        feedback = []

        for item in report:
            if item.get("type") not in BLOCKING_TYPES:
                continue

            feedback.append(
                {
                    "type": "pylint_error",
                    "fault": {
                        "start_line": item.get("line"),
                        "end_line": item.get("endLine") or item.get("line"),
                        "column": item.get("column"),
                        "code": item.get("message"),
                    },
                    "severity": "HIGH",
                    "hint": item.get("message"),
                    "pylint_code": item.get("message-id"),
                    "symbolic_name": item.get("symbol"),
                }
            )

        full_result = {
            "tool": "pylint",
            "valid": len(feedback) == 0,
            "has_error": len(feedback) > 0,
            "feedback": feedback,
            "raw_report": report,
            "raw_output": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }

        full_result["llm_context"] = build_pylint_llm_context(full_result)
        return full_result


def smoke_test_pylint_check() -> None:
    valid_code = """
def add(a, b):
    return a + b
"""

    invalid_code = """
def add(a, b):
    return missing_variable
"""

    valid_result = run_pylint_check(valid_code)
    console.print(
        Panel(
            json.dumps(valid_result, indent=2),
            title="PyLint Check: Valid-ish Code",
            border_style="cyan",
        )
    )
    console.print(
        Panel(
            json.dumps(valid_result["llm_context"], indent=2),
            title="LLM Context Only",
            border_style="cyan",
        )
    )

    invalid_result = run_pylint_check(invalid_code)
    console.print(
        Panel(
            json.dumps(invalid_result, indent=2),
            title="PyLint Check: Undefined Variable",
            border_style="cyan",
        )
    )
    console.print(
        Panel(
            json.dumps(invalid_result["llm_context"], indent=2),
            title="LLM Context Only",
            border_style="cyan",
        )
    )


if __name__ == "__main__":
    smoke_test_pylint_check()
