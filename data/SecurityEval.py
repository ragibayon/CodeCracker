from pathlib import Path
import json
import re

import pandas as pd
from datasets import load_dataset


OUT_DIR = Path("data/securityeval")
OUT_PATH = OUT_DIR / "dataset.jsonl"
CSV_PATH = OUT_DIR / "securityeval.csv"


def download_securityeval() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = load_dataset("s2e-lab/SecurityEval")
    split = dataset["train"]

    with OUT_PATH.open("w", encoding="utf-8") as f:
        for row in split:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"Saved {len(split)} rows to {OUT_PATH}")
    print("Columns:", split.column_names)


def extract_cwe_id(sample_id: str) -> str:
    """
    Example:
    CWE-020_author_1.py -> CWE-020
    CWE-089_codeql_1.py -> CWE-089
    """
    match = re.match(r"(CWE-\d+)", sample_id)
    if not match:
        raise ValueError(f"Could not extract CWE ID from: {sample_id}")
    return match.group(1)


def convert_securityeval_jsonl_to_csv(
    input_path: Path = OUT_PATH,
    output_path: Path = CSV_PATH,
) -> None:
    rows = []

    with input_path.open("r", encoding="utf-8") as f:
        for line in f:
            item = json.loads(line)

            sample_id = item["ID"]
            cwe_id = extract_cwe_id(sample_id)

            rows.append(
                {
                    "id": sample_id,
                    "cwe_id": cwe_id,
                    "prompt": item["Prompt"],
                    "insecure_code": item["Insecure_code"],
                }
            )

    df = pd.DataFrame(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)

    print(f"Saved {len(df)} rows to {output_path}")
    print(df["cwe_id"].value_counts().head(10))


# def main():
#     download_securityeval()


if __name__ == "__main__":
    convert_securityeval_jsonl_to_csv()
