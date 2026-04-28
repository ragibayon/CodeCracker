from __future__ import annotations

from datetime import datetime
from pathlib import Path


SKILL_MEMORY_PATH = Path("memory/SKILL.md")
LESSONS_HEADER = "## Lessons"
MAX_LESSONS = 30
MAX_MESSAGE_CHARS = 220
CURATED_ERROR_PATTERNS = (
    "StructuredOutputValidationError",
    "Native structured output expected valid JSON",
    "Agent did not return a structured_response",
)


def ensure_skill_memory_file() -> Path:
    if SKILL_MEMORY_PATH.exists():
        return SKILL_MEMORY_PATH

    SKILL_MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SKILL_MEMORY_PATH.write_text(
        "---\n"
        "name: codecracker-memory\n"
        "description: Concise project-specific lessons learned for the "
        "CodeCracker agent. Use only when relevant to generation, validation, "
        "or recovery from failures.\n"
        "---\n\n"
        "# CodeCracker Memory\n\n"
        "Keep entries concise and actionable. Prefer one short bullet per lesson.\n\n"
        "## Lessons\n",
        encoding="utf-8",
    )
    return SKILL_MEMORY_PATH


def read_skill_memory() -> str:
    path = ensure_skill_memory_file()
    return path.read_text(encoding="utf-8").strip()


def should_record_lesson(*, error_type: str, message: str) -> bool:
    if error_type in CURATED_ERROR_PATTERNS:
        return True
    return any(pattern in message for pattern in CURATED_ERROR_PATTERNS)


def append_skill_lesson(*, sample_id: str | None, error_type: str, message: str) -> None:
    path = ensure_skill_memory_file()
    compact_message = " ".join(message.strip().split())[:MAX_MESSAGE_CHARS]
    lesson = (
        f"- [{datetime.now().date().isoformat()}] "
        f"{sample_id or 'unknown-sample'}: {error_type}: {compact_message}"
    )
    content = path.read_text(encoding="utf-8").rstrip()
    header, _, lessons_block = content.partition(LESSONS_HEADER)
    existing_lessons = [
        line.strip()
        for line in lessons_block.splitlines()
        if line.strip().startswith("- ")
    ]

    normalized_lesson = lesson.split("] ", 1)[-1]
    normalized_existing = {line.split("] ", 1)[-1] for line in existing_lessons}
    if normalized_lesson in normalized_existing:
        return

    updated_lessons = [*existing_lessons, lesson][-MAX_LESSONS:]
    rebuilt = (
        f"{header.strip()}\n\n{LESSONS_HEADER}\n"
        + "\n".join(updated_lessons)
        + "\n"
    )
    path.write_text(rebuilt, encoding="utf-8")
