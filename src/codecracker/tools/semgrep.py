from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel


console = Console()

SEMGREP_TIMEOUT_SECONDS = 60


# -----------------------------
# Helpers
# -----------------------------
def extract_code_snippet(code: str, line: int, context: int = 1) -> str:
    """
    Extract code snippet around the vulnerable line.
    """
    lines = code.splitlines()

    start = max(0, line - 1 - context)
    end = min(len(lines), line + context)

    snippet = lines[start:end]
    return "\n".join(f"{i+1}: {l}" for i, l in enumerate(snippet, start=start))


def normalize_cwe(cwe_value: Any) -> list[str]:
    """
    Normalize CWE field from Semgrep metadata.
    Example:
    "CWE-78: ..." → ["CWE-78"]
    """
    if not cwe_value:
        return []

    if isinstance(cwe_value, list):
        return [c.split(":")[0] for c in cwe_value if isinstance(c, str)]

    if isinstance(cwe_value, str):
        return [cwe_value.split(":")[0]]

    return []


# -----------------------------
# Core execution
# -----------------------------
def run_semgrep_on_code(code: str) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmpdir:
        code_path = Path(tmpdir) / "sample.py"
        code_path.write_text(code, encoding="utf-8")

        cmd = [
            "uv",
            "run",
            "semgrep",
            "--config",
            "auto",
            str(code_path),
            "--json",
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=SEMGREP_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"Semgrep timed out after {SEMGREP_TIMEOUT_SECONDS} seconds."
            ) from exc

        if not result.stdout.strip():
            raise RuntimeError(
                f"Semgrep produced no JSON output.\n" f"stderr:\n{result.stderr}"
            )

        report = json.loads(result.stdout)
        report["_semgrep_returncode"] = result.returncode
        report["_semgrep_stderr"] = result.stderr

        return report


# -----------------------------
# Summarization (agent-ready)
# -----------------------------
def summarize_semgrep_report(report: dict[str, Any], code: str) -> dict[str, Any]:
    results = report.get("results", [])

    check_ids = []
    severities = []
    all_cwe_ids = []

    issues = []

    for r in results:
        check_id = r.get("check_id")
        severity = r.get("extra", {}).get("severity")
        message = r.get("extra", {}).get("message")

        line = r.get("start", {}).get("line")

        metadata = r.get("extra", {}).get("metadata", {})
        cwe = normalize_cwe(metadata.get("cwe"))

        snippet = extract_code_snippet(code, line) if line else ""

        check_ids.append(check_id)
        severities.append(severity)
        all_cwe_ids.extend(cwe)

        issues.append(
            {
                "check_id": check_id,
                "message": message,
                "severity": severity,
                "line_number": line,
                "cwe": cwe,
                "snippet": snippet,
            }
        )

    return {
        "num_issues": len(results),
        "check_ids": check_ids,
        "cwe_ids": list(set(all_cwe_ids)),
        "has_high": any(s in ["ERROR", "HIGH"] for s in severities),
        "is_insecure": len(results) > 0,
        "issues": issues,
    }


# -----------------------------
# Pipeline entry
# -----------------------------
def evaluate_code_with_semgrep(code: str) -> dict[str, Any]:
    report = run_semgrep_on_code(code)
    summary = summarize_semgrep_report(report, code)

    return {
        "tool": "semgrep",
        "summary": summary,
        "raw_report": report,
    }


# Smoke test
def smoke_test_semgrep() -> None:
    insecure_code = """
import subprocess

def run(user_input):
    subprocess.call(user_input, shell=True)
"""

    evaluation = evaluate_code_with_semgrep(insecure_code)
    report = evaluation["raw_report"]
    summary = evaluation["summary"]

    header_text = (
        f"Return code: {report.get('_semgrep_returncode')}\n"
        f"Errors: {report.get('errors')}"
    )
    console.print(
        Panel.fit(header_text, title="Semgrep Full Output", border_style="cyan")
    )

    summary_text = (
        f"Num issues: {summary['num_issues']}\n"
        f"Insecure: {summary['is_insecure']}\n"
        f"Check IDs: {summary['check_ids']}\n"
        f"CWE IDs: {summary['cwe_ids']}"
    )
    console.print(Panel(summary_text, title="Summary", border_style="cyan"))

    for i, issue in enumerate(summary["issues"], 1):
        issue_text = "\n".join(
            [
                f"Check ID: {issue['check_id']}",
                f"Severity: {issue['severity']}",
                f"Message: {issue['message']}",
                f"CWE: {issue['cwe']}",
                f"Line: {issue['line_number']}",
                "",
                "Extracted Code Snippet:",
                issue["snippet"],
            ]
        )
        console.print(Panel(issue_text, title=f"Issue #{i}", border_style="cyan"))


if __name__ == "__main__":
    smoke_test_semgrep()
