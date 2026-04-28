from __future__ import annotations

from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from codecracker.tools.pylint_check import run_pylint_check


class PylintCheckInput(BaseModel):
    code: str = Field(
        description="Complete Python code string to check with PyLint. Do not pass a file path."
    )


@tool("run_pylint_check", args_schema=PylintCheckInput)
def run_pylint_check_tool(code: str) -> dict[str, Any]:
    """
    Check generated Python code for blocking correctness errors using PyLint.

    Returns only compact LLM-facing feedback. Does not execute the code.
    """
    result = run_pylint_check(code)
    return result["llm_context"]
