from __future__ import annotations
from pprint import pprint
import json
from typing import Any

from langchain_ollama import ChatOllama

from codecracker.callbacks.metrics import LLMRunMetrics
from codecracker.secure_codegen.schema.output import CodeGenerationOutput
from codecracker.tools.ast_check import run_ast_check
from codecracker.tools.bandit_tool import run_bandit_tool
from codecracker.tools.pylint_check import run_pylint_check
from codecracker.utils.prompt_utils import render_prompt


class CodeGenAgent:
    def __init__(
        self,
        model: str,
        temperature: float = 0.0,
        max_iters: int = 5,
    ) -> None:
        self.model = model
        self.max_iters = max_iters

        self.llm = ChatOllama(model=model, temperature=temperature)
        self.structured_llm = self.llm.with_structured_output(CodeGenerationOutput)

    def call_llm_for_code(self, prompt: str) -> dict[str, Any]:
        metrics = LLMRunMetrics()

        response = self.structured_llm.invoke(
            prompt,
            config={"callbacks": [metrics]},
        )

        return {
            "code": response.code.strip(),
            "metrics": metrics.as_dict(),
            "raw_response": response,
        }

    def generate_initial_code(
        self,
        prompt: str,
        condition: str = "clean",
        injection: str = "",
    ) -> dict[str, Any]:
        rendered = render_prompt(
            "naive_code_generation.j2",
            prompt=prompt,
            condition=condition,
            injection=injection,
        )
        return self.call_llm_for_code(rendered)

    def refine_code(
        self,
        prompt: str,
        code: str,
        feedback: dict[str, Any],
        condition: str = "clean",
        injection: str = "",
    ) -> dict[str, Any]:
        rendered = render_prompt(
            "naive_code_generation.j2",
            prompt=prompt,
            condition=condition,
            injection=injection,
        )

        refinement_prompt = f"""
{rendered}

The previous generated code was:

{code}

The following validation feedback was produced:

{json.dumps(feedback, indent=2)}

Revise the code to address the feedback while preserving the original task.
Return structured output with only the `code` field.
"""
        return self.call_llm_for_code(refinement_prompt)

    def validate_code(self, code: str) -> dict[str, Any]:
        ast_result = run_ast_check(code)
        if ast_result["has_error"]:
            return {
                "stage": "ast",
                "passed": False,
                "result": ast_result,
                "llm_feedback": {
                    "tool": "ast",
                    "valid": ast_result["valid"],
                    "has_error": ast_result["has_error"],
                    "num_issues": len(ast_result["feedback"]),
                    "feedback": ast_result["feedback"],
                },
            }

        pylint_result = run_pylint_check(code)
        if pylint_result["has_error"]:
            return {
                "stage": "pylint",
                "passed": False,
                "result": pylint_result,
                "llm_feedback": pylint_result["llm_context"],
            }

        bandit_result = run_bandit_tool.invoke({"code": code})
        if bandit_result["is_insecure"]:
            return {
                "stage": "bandit",
                "passed": False,
                "result": bandit_result,
                "llm_feedback": bandit_result,
            }

        return {
            "stage": "passed",
            "passed": True,
            "result": {
                "ast": ast_result,
                "pylint": pylint_result["llm_context"],
                "bandit": bandit_result,
            },
            "llm_feedback": {},
        }

    def run_loop(
        self,
        prompt: str,
        condition: str = "clean",
        injection: str = "",
    ) -> dict[str, Any]:
        attempts: list[dict[str, Any]] = []

        generation = self.generate_initial_code(
            prompt=prompt,
            condition=condition,
            injection=injection,
        )
        code = generation["code"]
        llm_metrics = generation["metrics"]

        for attempt_idx in range(1, self.max_iters + 1):
            validation = self.validate_code(code)

            attempts.append(
                {
                    "attempt": attempt_idx,
                    "code": code,
                    "llm_metrics": llm_metrics,
                    "stage": validation["stage"],
                    "passed": validation["passed"],
                    "validation": validation["result"],
                    "llm_feedback": validation["llm_feedback"],
                }
            )

            if validation["passed"]:
                return {
                    "passed": True,
                    "pass_at": attempt_idx,
                    "final_code": code,
                    "attempts": attempts,
                }

            generation = self.refine_code(
                prompt=prompt,
                code=code,
                feedback=validation["llm_feedback"],
                condition=condition,
                injection=injection,
            )
            code = generation["code"]
            llm_metrics = generation["metrics"]

        return {
            "passed": False,
            "pass_at": None,
            "final_code": code,
            "attempts": attempts,
        }
