from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined


PROMPT_DIR = Path(__file__).parents[1] / "secure_codegen" / "prompt"


def build_prompt_environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(PROMPT_DIR),
        undefined=StrictUndefined,
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_prompt(template_name: str, **kwargs: Any) -> str:
    env = build_prompt_environment()
    template = env.get_template(template_name)
    return template.render(**kwargs)
