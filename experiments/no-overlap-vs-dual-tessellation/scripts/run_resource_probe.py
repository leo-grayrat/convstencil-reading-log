#!/usr/bin/env python3
"""Compile the benchmark and query CUDA Runtime kernel resource limits."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from run_benchmark import compile_benchmark
from run_wmma_probe import load_msvc_environment, run_and_log


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-directory", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    output_directory = arguments.output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    experiment_root = Path(__file__).resolve().parent.parent
    environment = load_msvc_environment()
    executable_path = compile_benchmark(
        experiment_root=experiment_root,
        build_directory=output_directory,
        environment=environment,
    )
    completed = run_and_log(
        [str(executable_path), "resources"],
        output_directory / "resource-stdout.log",
        environment,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"resource probe failed with exit code {completed.returncode}"
        )
    payload = json.loads(completed.stdout)
    (output_directory / "resource-result.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, json.JSONDecodeError) as error:
        print(error, file=sys.stderr)
        raise SystemExit(1) from error
