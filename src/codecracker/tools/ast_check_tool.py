from __future__ import annotations

from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from codecracker.tools.ast_check import run_ast_check


class AstCheckInput(BaseModel):
    code: str = Field(
        description="Complete Python code string to parse with AST. Do not pass a file path."
    )


@tool("run_ast_check", args_schema=AstCheckInput)
def run_ast_check_tool(code: str) -> dict[str, Any]:
    """
    Check whether generated Python code is syntactically valid using Python AST.

    Does not execute the code. Returns syntax validity and compact feedback if parsing fails.
    """
    return run_ast_check(code)
