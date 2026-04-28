from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel


console = Console()


def run_bandit_on_code(code: str) -> dict[str, Any]:
    """
    Writes code to a temporary Python file, runs Bandit, and returns parsed JSON.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        code_path = Path(tmpdir) / "sample.py"
        report_path = Path(tmpdir) / "bandit_report.json"

        code_path.write_text(code, encoding="utf-8")

        cmd = [
            "uv",
            "run",
            "bandit",
            str(code_path),
            "-f",
            "json",
            "-o",
            str(report_path),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if not report_path.exists():
            raise RuntimeError(
                f"Bandit did not produce a report.\n"
                f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}"
            )

        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["_bandit_returncode"] = result.returncode
        return report


def summarize_bandit_report(report: dict[str, Any]) -> dict[str, Any]:
    results = report.get("results", [])

    severities = [r.get("issue_severity") for r in results]
    confidences = [r.get("issue_confidence") for r in results]
    test_ids = [r.get("test_id") for r in results]

    issues = []
    cwe_ids = []

    for r in results:
        cwe = r.get("issue_cwe", {})
        cwe_id = f"CWE-{cwe.get('id')}" if cwe and cwe.get("id") else None
        if cwe_id:
            cwe_ids.append(cwe_id)

        issues.append(
            {
                "test_id": r.get("test_id"),
                "test_name": r.get("test_name"),
                "cwe_id": cwe_id,
                "cwe_link": cwe.get("link") if cwe else None,
                "issue_text": r.get("issue_text"),
                "severity": r.get("issue_severity"),
                "confidence": r.get("issue_confidence"),
                "line_number": r.get("line_number"),
                "line_range": r.get("line_range") or [],
                "code": r.get("code"),
            }
        )

    return {
        "num_issues": len(results),
        "test_ids": list(dict.fromkeys(test_ids)),
        "cwe_ids": list(dict.fromkeys(cwe_ids)),
        "has_low": "LOW" in severities,
        "has_medium": "MEDIUM" in severities,
        "has_high": "HIGH" in severities,
        "has_high_confidence": "HIGH" in confidences,
        "is_insecure": len(results) > 0,
        "issues": issues,
    }


def build_bandit_llm_context(summary: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "cwe": issue["cwe_id"],
            "fault": {
                "start_line": issue["line_number"],
                "end_line": issue["line_number"],
                "code": issue["code"],
            },
            "severity": issue["severity"],
            "confidence": issue["confidence"],
            "hint": issue["issue_text"],
            "reference": issue["cwe_link"],
            "source": {
                "tool": "bandit",
                "rule_id": issue["test_id"],
                "rule_name": issue["test_name"],
            },
        }
        for issue in summary["issues"]
    ]


def evaluate_code_with_bandit(code: str) -> dict[str, Any]:
    report = run_bandit_on_code(code)
    summary = summarize_bandit_report(report)
    llm_context = build_bandit_llm_context(summary)

    return {
        "tool": "bandit",
        "summary": summary,
        "llm_context": llm_context,
        "raw_report": report,
    }


def smoke_test_bandit() -> None:
    insecure_code = """
import subprocess

def run(user_input):
    subprocess.call(user_input, shell=True)
"""

    evaluation = evaluate_code_with_bandit(insecure_code)
    report = evaluation["raw_report"]
    summary = evaluation["summary"]

    console.print(
        Panel.fit(
            f"Generated at: {report.get('generated_at')}\nErrors: {report.get('errors')}",
            title="Bandit Full Output",
            border_style="cyan",
        )
    )

    metrics = report.get("metrics", {}).get("_totals", {})
    metrics_text = "\n".join(f"{k}: {v}" for k, v in metrics.items())
    console.print(Panel(metrics_text, title="Metrics", border_style="cyan"))

    summary_text = (
        f"Num issues: {summary['num_issues']}\n"
        f"Insecure: {summary['is_insecure']}\n"
        f"Test IDs: {summary['test_ids']}"
    )
    console.print(Panel(summary_text, title="Summary", border_style="cyan"))

    for i, issue in enumerate(report.get("results", []), 1):
        cwe = issue.get("issue_cwe", {})
        cwe_lines = []
        if cwe:
            cwe_lines = [
                f"CWE: CWE-{cwe.get('id')}",
                f"CWE Link: {cwe.get('link')}",
            ]

        issue_text = "\n".join(
            [
                f"Test ID: {issue.get('test_id')}",
                f"Test Name: {issue.get('test_name')}",
                f"Severity: {issue.get('issue_severity')}",
                f"Confidence: {issue.get('issue_confidence')}",
                *cwe_lines,
                f"Message: {issue.get('issue_text')}",
                f"File: {issue.get('filename')}",
                f"Line: {issue.get('line_number')}",
                f"Line Range: {issue.get('line_range')}",
                "",
                "Vulnerable Code:",
                str(issue.get("code")),
            ]
        )
        console.print(Panel(issue_text, title=f"Issue #{i}", border_style="cyan"))


if __name__ == "__main__":
    smoke_test_bandit()
