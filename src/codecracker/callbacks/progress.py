from __future__ import annotations

from typing import Any

from langchain_core.callbacks import BaseCallbackHandler


def _tool_label(name: str) -> str:
    labels = {
        "run_ast_check": "Calling AST check",
        "run_pylint_check": "Calling PyLint check",
        "run_security_checks": "Calling security checks",
    }
    return labels.get(name, f"Calling {name}")


class ProgressCallbackHandler(BaseCallbackHandler):
    def __init__(self, progress: Any) -> None:
        self.progress = progress

    def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: dict[str, Any],
        **kwargs: Any,
    ) -> None:
        self.progress.update("Running ReAct agent")

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        **kwargs: Any,
    ) -> None:
        self.progress.update("Generating or refining code")

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        **kwargs: Any,
    ) -> None:
        name = serialized.get("name") or serialized.get("id", ["tool"])[-1]
        self.progress.update(_tool_label(name))

    def on_tool_end(self, output: Any, **kwargs: Any) -> None:
        self.progress.update("Processing tool result")

    def on_tool_error(self, error: BaseException, **kwargs: Any) -> None:
        self.progress.update(f"Tool error: {error}")

    def on_chain_end(self, outputs: dict[str, Any], **kwargs: Any) -> None:
        self.progress.update("Finalizing response")
