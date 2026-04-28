from __future__ import annotations

import json
import re
from typing import Any

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_ollama import ChatOllama
from langgraph.errors import GraphRecursionError

from codecracker.callbacks.metrics import LLMRunMetrics
from codecracker.callbacks.progress import ProgressCallbackHandler
from codecracker.secure_codegen.schema.output import CodeGenerationOutput
from codecracker.tools import (
    run_ast_check_tool,
    # run_pylint_check_tool,
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


def _flatten_message_content(content: Any) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif isinstance(item.get("content"), str):
                    parts.append(item["content"])
        return "".join(parts)

    if isinstance(content, dict):
        if isinstance(content.get("text"), str):
            return content["text"]
        if isinstance(content.get("content"), str):
            return content["content"]

    return str(content)


def _extract_code_from_text(text: Any) -> str:
    stripped = _flatten_message_content(text).strip()

    if stripped.startswith("```"):
        match = re.search(r"```(?:python)?\n(.*?)```", stripped, re.DOTALL)
        if match:
            return match.group(1).strip()

    try:
        parsed = json.loads(stripped)
    except Exception:
        parsed = None

    if isinstance(parsed, dict) and isinstance(parsed.get("code"), str):
        return parsed["code"].strip()

    if isinstance(parsed, list):
        for item in parsed:
            if isinstance(item, dict):
                candidate = item.get("text") or item.get("content")
                if isinstance(candidate, str):
                    try:
                        nested = json.loads(candidate)
                    except Exception:
                        nested = None
                    if isinstance(nested, dict) and isinstance(nested.get("code"), str):
                        return nested["code"].strip()
                    if candidate.strip():
                        return candidate.strip()

    return stripped


def _last_ai_message(raw_agent_output: dict[str, Any]) -> Any:
    messages = raw_agent_output.get("messages", [])
    for message in reversed(messages):
        if _message_type(message) == "ai":
            return message
    return None


class CodeGenAgent:
    def __init__(
        self,
        model: str,
        temperature: float = 0.0,
        seed: int | None = None,
        max_security_calls: int = 3,
        recursion_limit: int = 30,
    ) -> None:
        self.model = model
        self.max_security_calls = max_security_calls
        self.recursion_limit = recursion_limit

        llm_kwargs: dict[str, Any] = {
            "model": model,
            "temperature": temperature,
            "disable_streaming": True,
        }
        if seed is not None:
            llm_kwargs["seed"] = seed

        self.llm = ChatOllama(**llm_kwargs)
        self.structured_llm = self.llm.with_structured_output(CodeGenerationOutput)

        system_prompt = render_prompt(
            "system_prompt.j2",
            skill_memory="",
            max_security_calls=max_security_calls,
        )

        self.agent = create_agent(
            model=self.llm,
            tools=[
                run_ast_check_tool,
                # run_pylint_check_tool,
                run_security_checks_tool,
            ],
            system_prompt=system_prompt,
            response_format=ToolStrategy(CodeGenerationOutput),
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

        try:
            raw_agent_output = self.agent.invoke(
                {
                    "messages": [
                        {
                            "role": "user",
                            "content": rendered_prompt,
                        }
                    ]
                },
                config={
                    "callbacks": callbacks,
                    "recursion_limit": self.recursion_limit,
                },
            )
        except GraphRecursionError as exc:
            return {
                "passed": False,
                "pass_at": None,
                "ai_turns": 0,
                "tool_rounds": 0,
                "final_code": "",
                "structured_response": None,
                "raw_agent_output": {},
                "llm_metrics": metrics.as_dict(),
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "attempts": [
                    {
                        "attempt": 1,
                        "stage": "recursion_limit",
                        "passed": False,
                        "code": "",
                        "structured_response": None,
                        "raw_agent_output": {},
                        "llm_metrics": metrics.as_dict(),
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    }
                ],
            }
        except Exception as exc:
            fallback_metrics = LLMRunMetrics()
            fallback_response = self.llm.invoke(
                rendered_prompt,
                config={"callbacks": [fallback_metrics]},
            )
            code = _extract_code_from_text(getattr(fallback_response, "content", ""))

            return {
                "passed": False,
                "pass_at": None,
                "ai_turns": 1,
                "tool_rounds": 0,
                "final_code": code,
                "structured_response": None,
                "raw_agent_output": {},
                "llm_metrics": fallback_metrics.as_dict(),
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "attempts": [
                    {
                        "attempt": 1,
                        "stage": "fallback_plain_llm",
                        "passed": False,
                        "code": code,
                        "structured_response": None,
                        "raw_agent_output": {},
                        "llm_metrics": fallback_metrics.as_dict(),
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    }
                ],
            }

        structured_response = raw_agent_output.get("structured_response")
        if structured_response is not None:
            code = structured_response.code.strip()
            structured_response_payload = structured_response.model_dump()
        else:
            last_ai_message = _last_ai_message(raw_agent_output)
            code = _extract_code_from_text(
                getattr(last_ai_message, "content", "")
                if last_ai_message is not None
                else ""
            )
            structured_response_payload = {"code": code}

        round_counts = _count_agent_rounds(raw_agent_output)

        return {
            "passed": True,
            "pass_at": 1,
            "ai_turns": round_counts["ai_turns"],
            "tool_rounds": round_counts["tool_rounds"],
            "final_code": code,
            "structured_response": structured_response_payload,
            "raw_agent_output": raw_agent_output,
            "llm_metrics": metrics.as_dict(),
            "attempts": [
                {
                    "attempt": 1,
                    "stage": "react_agent",
                    "passed": True,
                    "code": code,
                    "structured_response": structured_response_payload,
                    "ai_turns": round_counts["ai_turns"],
                    "tool_rounds": round_counts["tool_rounds"],
                    "raw_agent_output": raw_agent_output,
                    "llm_metrics": metrics.as_dict(),
                }
            ],
        }
