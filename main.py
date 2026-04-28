from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

from codecracker.secure_codegen.agent import CodeGenAgent
from codecracker.utils.dataset import (
    load_securityeval_sample,
    load_securityeval_samples,
)
from codecracker.utils.log import (
    create_run_log_dir,
    print_run_error,
    print_run_result,
    print_run_start,
    start_run_loader,
    write_run_log,
)


def run_sample(
    *,
    agent: CodeGenAgent,
    model: str,
    dataset_path: Path,
    sample: dict[str, str | None],
    model_parameters: dict[str, str | int | float | None],
    run_parameters: dict[str, str | int | float | None],
) -> None:
    prompt = sample["prompt"]
    sample_run_parameters = {
        **run_parameters,
        "file_id": sample["ID"],
    }
    header_parameters = {
        **model_parameters,
        **sample_run_parameters,
    }
    print_run_start(model=model, prompt=prompt, parameters=header_parameters)

    run_dir = create_run_log_dir()
    loader = start_run_loader()
    try:
        try:
            result = agent.run_loop(
                prompt=prompt,
                condition="clean",
                progress=loader,
            )
        except Exception as exc:
            result = {
                "passed": False,
                "pass_at": None,
                "final_code": "",
                "structured_response": None,
                "raw_agent_output": None,
                "llm_metrics": None,
                "ai_turns": 0,
                "tool_rounds": 0,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }
    finally:
        loader.stop()
    result["dataset"] = {
        "path": str(dataset_path),
        "ID": sample["ID"],
        "expected_cwe": sample["expected_cwe"],
    }
    result["model_parameters"] = model_parameters
    result["run_parameters"] = sample_run_parameters
    result["log_dir"] = str(run_dir)
    write_run_log(
        run_dir,
        model=model,
        prompt=prompt,
        result=result,
    )
    if result["passed"]:
        print_run_result(result)
        return

    print_run_error(result)


def main() -> None:
    load_dotenv()

    model = "gpt-oss:latest"
    temperature = 0.0
    seed = 42
    dataset_path = Path("data/securityeval/dataset.jsonl")
    sample_index: int | None = None
    model_parameters = {
        "temperature": temperature,
        "seed": seed,
    }
    run_parameters = {
        "sample_index": sample_index,
        "dataset_path": str(dataset_path),
    }

    agent = CodeGenAgent(
        model=model,
        temperature=temperature,
        seed=seed,
    )

    if sample_index is None:
        samples = load_securityeval_samples(dataset_path)
        for sample in samples:
            run_sample(
                agent=agent,
                model=model,
                dataset_path=dataset_path,
                sample=sample,
                model_parameters=model_parameters,
                run_parameters=run_parameters,
            )
        return

    sample = load_securityeval_sample(dataset_path, sample_index=sample_index)
    run_sample(
        agent=agent,
        model=model,
        dataset_path=dataset_path,
        sample=sample,
        model_parameters=model_parameters,
        run_parameters=run_parameters,
    )


if __name__ == "__main__":
    main()
