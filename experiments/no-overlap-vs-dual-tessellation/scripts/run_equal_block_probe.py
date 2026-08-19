#!/usr/bin/env python3
"""Measure baseline and variant with exactly the same CUDA grid."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

from measurement import summarize_equal_block_pairs
from run_benchmark import compile_benchmark
from run_wmma_probe import load_msvc_environment


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--grid-columns", type=int, required=True)
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
    completed = subprocess.run(
        [
            str(executable_path),
            "equal-block",
            str(arguments.height),
            str(arguments.grid_columns),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
        timeout=120,
    )
    (output_directory / "equal-block.stdout.log").write_text(
        completed.stdout, encoding="utf-8"
    )
    (output_directory / "equal-block.stderr.log").write_text(
        completed.stderr, encoding="utf-8"
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"equal-block probe failed with exit code {completed.returncode}"
        )
    payload = json.loads(completed.stdout)
    baseline_repetitions = int(payload["baseline_repetitions"])
    variant_repetitions = int(payload["variant_repetitions"])
    baseline_ms = [
        float(sample["baseline_total_ms"]) / baseline_repetitions
        for sample in payload["samples"]
    ]
    variant_ms = [
        float(sample["variant_total_ms"]) / variant_repetitions
        for sample in payload["samples"]
    ]
    payload["summary"] = summarize_equal_block_pairs(
        baseline_ms=baseline_ms,
        variant_ms=variant_ms,
        bootstrap_samples=10000,
        random_seed=660112,
    )
    (output_directory / "equal-block-result.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, json.JSONDecodeError, subprocess.TimeoutExpired) as error:
        print(error, file=sys.stderr)
        raise SystemExit(1) from error
