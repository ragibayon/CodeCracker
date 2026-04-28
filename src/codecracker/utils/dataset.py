from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def extract_cwe_id(sample_id: str) -> str | None:
    match = re.match(r"(CWE-\d+)", sample_id)
    return match.group(1) if match else None


def load_securityeval_sample(
    dataset_path: Path,
    *,
    sample_index: int = 0,
) -> dict[str, Any]:
    return load_securityeval_samples(dataset_path)[sample_index]


def load_securityeval_samples(dataset_path: Path) -> list[dict[str, Any]]:
    rows = load_jsonl(dataset_path)
    return [
        {
            "ID": row["ID"],
            "expected_cwe": extract_cwe_id(row["ID"]),
            "prompt": row["Prompt"],
            "insecure_code": row.get("Insecure_code"),
        }
        for row in rows
    ]
