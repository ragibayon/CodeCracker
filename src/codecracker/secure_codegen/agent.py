from __future__ import annotations

from typing import Any

from langchain.agents import create_agent
from langchain_ollama import ChatOllama

from codecracker.callbacks.metrics import LLMRunMetrics
from codecracker.callbacks.progress import ProgressCallbackHandler
from codecracker.secure_codegen.schema.output import CodeGenerationOutput
from codecracker.tools import (
    run_ast_check_tool,
    run_pylint_check_tool,
    run_security_checks_tool,
)
from codecracker.utils.prompt_utils import render_prompt


def _message_type(message: Any) -> str | None:
    if isinstance(message, dict):
        return message.get("type")
    return getattr(message, "type", None)


def _tool_calls(message: Any) -> list[Any]:
    if isinstance(message, dict):
        return message.get("tool_calls") or []
    return getattr(message, "tool_calls", []) or []


def _count_agent_rounds(raw_agent_output: dict[str, Any]) -> dict[str, int]:
    messages = raw_agent_output.get("messages", [])
    ai_turns = [message for message in messages if _message_type(message) == "ai"]
    tool_rounds = [message for message in ai_turns if _tool_calls(message)]

    return {
        "ai_turns": len(ai_turns),
        "tool_rounds": len(tool_rounds),
    }


class CodeGenAgent:
    def __init__(
        self,
        model: str,
        temperature: float = 0.0,
        seed: int | None = 42,
    ) -> None:
        self.model = model

        self.llm = ChatOllama(model=model, temperature=temperature, seed=seed)
        system_prompt = render_prompt("system_prompt.j2", skill_memory="")

        self.agent = create_agent(
            model=self.llm,
            tools=[
                run_ast_check_tool,
                run_pylint_check_tool,
                run_security_checks_tool,
            ],
            system_prompt=system_prompt,
            response_format=CodeGenerationOutput,
        )

    def run_loop(
        self,
        prompt: str,
        condition: str = "clean",
        injection: str = "",
        progress: Any | None = None,
    ) -> dict[str, Any]:
        rendered_prompt = render_prompt(
            "code_generation.j2",
            prompt=prompt,
            condition=condition,
            injection=injection,
        )
        metrics = LLMRunMetrics()
        callbacks: list[Any] = [metrics]
        if progress is not None:
            callbacks.append(ProgressCallbackHandler(progress))

        raw_agent_output = self.agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": rendered_prompt,
                    }
                ]
            },
            config={"callbacks": callbacks},
        )

        structured_response = raw_agent_output.get("structured_response")
        if structured_response is None:
            raise RuntimeError(
                "Agent did not return a structured_response. "
                "Check whether the model supports tool calling and structured output."
            )

        code = structured_response.code.strip()
        round_counts = _count_agent_rounds(raw_agent_output)

        return {
            "passed": True,
            "pass_at": 1,
            "ai_turns": round_counts["ai_turns"],
            "tool_rounds": round_counts["tool_rounds"],
            "final_code": code,
            "structured_response": structured_response.model_dump(),
            "raw_agent_output": raw_agent_output,
            "llm_metrics": metrics.as_dict(),
            "attempts": [
                {
                    "attempt": 1,
                    "stage": "react_agent",
                    "passed": True,
                    "code": code,
                    "structured_response": structured_response.model_dump(),
                    "ai_turns": round_counts["ai_turns"],
                    "tool_rounds": round_counts["tool_rounds"],
                    "raw_agent_output": raw_agent_output,
                    "llm_metrics": metrics.as_dict(),
                }
            ],
        }
