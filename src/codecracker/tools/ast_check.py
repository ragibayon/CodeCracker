from __future__ import annotations

import ast
import json
from typing import Any

from rich.console import Console
from rich.panel import Panel


console = Console()


def run_ast_check(code: str) -> dict[str, Any]:
    try:
        ast.parse(code)
        return {
            "tool": "ast",
            "valid": True,
            "has_error": False,
            "feedback": [],
        }

    except SyntaxError as e:
        return {
            "tool": "ast",
            "valid": False,
            "has_error": True,
            "feedback": [
                {
                    "type": "syntax_error",
                    "fault": {
                        "start_line": e.lineno,
                        "end_line": e.lineno,
                        "code": e.text.strip() if e.text else None,
                    },
                    "severity": "HIGH",
                    "hint": e.msg,
                }
            ],
        }


def smoke_test_ast_check() -> None:
    valid_code = """
def add(a, b):
    return a + b
"""

    invalid_code = """
def add(a, b)
    return a + b
"""

    console.print(
        Panel(
            json.dumps(run_ast_check(valid_code), indent=2),
            title="AST Check: Valid Code",
            border_style="cyan",
        )
    )

    console.print(
        Panel(
            json.dumps(run_ast_check(invalid_code), indent=2),
            title="AST Check: Invalid Code",
            border_style="cyan",
        )
    )


if __name__ == "__main__":
    smoke_test_ast_check()
