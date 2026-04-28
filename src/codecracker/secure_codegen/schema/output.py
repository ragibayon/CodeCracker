from __future__ import annotations

from pydantic import BaseModel, Field


class CodeGenerationOutput(BaseModel):
    code: str = Field(
        description=(
            "Complete Python code generated for the given prompt. "
            "Return only the code content here, without Markdown fences, explanations, or extra text."
        )
    )


class CodeRefinementOutput(BaseModel):
    code: str = Field(
        description=(
            "Refined complete Python code after incorporating tool feedback. "
            "Return only the corrected code content here, without Markdown fences, explanations, or extra text."
        )
    )
