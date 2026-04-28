from __future__ import annotations

import time
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler


class LLMRunMetrics(BaseCallbackHandler):
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.start_time: float | None = None
        self.end_time: float | None = None
        self.latency: float | None = None
        self.token_usage: dict[str, Any] | None = None
        self.model_name: str | None = None

    def on_llm_start(
        self, serialized: dict[str, Any], prompts: list[str], **kwargs: Any
    ) -> None:
        self.start_time = time.time()

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        self.end_time = time.time()
        if self.start_time is not None:
            self.latency = self.end_time - self.start_time

        try:
            gen = response.generations[0][0]
            msg = getattr(gen, "message", None)

            if msg is not None:
                usage_metadata = getattr(msg, "usage_metadata", None)
                if usage_metadata:
                    self.token_usage = dict(usage_metadata)

                response_metadata = getattr(msg, "response_metadata", None)
                if isinstance(response_metadata, dict):
                    self.model_name = response_metadata.get(
                        "model_name"
                    ) or response_metadata.get("model")
        except Exception:
            pass

        llm_output = getattr(response, "llm_output", None)
        if isinstance(llm_output, dict):
            if self.token_usage is None:
                self.token_usage = (
                    llm_output.get("token_usage")
                    or llm_output.get("usage")
                    or llm_output.get("usage_metadata")
                )

            if self.model_name is None:
                self.model_name = llm_output.get("model_name") or llm_output.get(
                    "model"
                )

    def on_llm_error(self, error: BaseException, **kwargs: Any) -> None:
        self.end_time = time.time()
        if self.start_time is not None:
            self.latency = self.end_time - self.start_time

    def as_dict(self) -> dict[str, Any]:
        return {
            "latency": self.latency,
            "token_usage": self.token_usage,
            "model_name": self.model_name,
        }
