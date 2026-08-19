#!/usr/bin/env python3
"""Run the fixed k=8 baseline/no-overlap experiment."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

from k8_geometry import comparison_geometry
from measurement import alternating_orders, summarize_pairs
from run_wmma_probe import (
    environment_value,
    load_msvc_environment,
    run_and_log,
)


HEIGHT = 1024
WIDTH = 7168
WARMUP_COUNT = 5
PAIR_COUNT = 21
TARGET_SAMPLE_MS = 150
TOTAL_RUNTIME_BUDGET_SECONDS = 10 * 60


def benchmark_plan() -> dict[str, object]:
    return {
        "problem_size": {"height": HEIGHT, "width": WIDTH},
        "warmups": WARMUP_COUNT,
        "pairs": PAIR_COUNT,
        "orders": alternating_orders(PAIR_COUNT),
        "target_sample_ms": TARGET_SAMPLE_MS,
        "timing_api": "CUDA Event",
        "total_runtime_budget_seconds": TOTAL_RUNTIME_BUDGET_SECONDS,
    }


def summarize_payload(
    payload: dict[str, object], *, bootstrap_samples: int
) -> dict[str, object]:
    baseline_repetitions = int(payload["baseline_repetitions"])
    no_overlap_repetitions = int(payload["no_overlap_repetitions"])
    samples = payload["samples"]
    if not isinstance(samples, list):
        raise ValueError("samples must be a list")
    baseline_ms = [
        float(sample["baseline_total_ms"]) / baseline_repetitions
        for sample in samples
    ]
    no_overlap_ms = [
        float(sample["no_overlap_total_ms"]) / no_overlap_repetitions
        for sample in samples
    ]
    useful_outputs = int(payload["height"]) * int(payload["width"])
    paired = summarize_pairs(
        baseline_ms=baseline_ms,
        variant_ms=no_overlap_ms,
        useful_outputs=useful_outputs,
        bootstrap_samples=bootstrap_samples,
        random_seed=8066,
    )
    blocks = int(payload["blocks_per_kernel"])
    baseline = dict(paired["baseline"])
    no_overlap = dict(paired["variant"])
    baseline["average_us_per_block"] = baseline["median_ms"] * 1000.0 / blocks
    no_overlap["average_us_per_block"] = (
        no_overlap["median_ms"] * 1000.0 / blocks
    )
    return {
        "k8_baseline": baseline,
        "k8_no_overlap": no_overlap,
        "throughput_ratio": paired["throughput_ratio"],
        "paired_bootstrap_95_ci": paired["paired_bootstrap_95_ci"],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--static-only", action="store_true")
    return parser.parse_args()


def compile_artifacts(
    *, experiment_root: Path, output_directory: Path, environment: dict[str, str]
) -> tuple[Path, Path, dict[str, object]]:
    search_path = environment_value(environment, "PATH")
    nvcc = shutil.which("nvcc.exe", path=search_path)
    nvdisasm = shutil.which("nvdisasm.exe", path=search_path)
    if not nvcc or not nvdisasm:
        raise RuntimeError("CUDA nvcc.exe and nvdisasm.exe must be available")

    source = experiment_root / "src" / "benchmark_k8.cu"
    executable = output_directory / "benchmark_k8.exe"
    cubin = output_directory / "benchmark_k8.cubin"
    executable_compile = run_and_log(
        [
            nvcc,
            "--std=c++17",
            "-arch=sm_120",
            "-lineinfo",
            str(source),
            "-o",
            str(executable),
        ],
        output_directory / "compile-executable.log",
        environment,
    )
    if executable_compile.returncode != 0:
        raise RuntimeError(
            f"k=8 executable compilation failed: {executable_compile.returncode}"
        )
    cubin_compile = run_and_log(
        [
            nvcc,
            "--std=c++17",
            "-arch=sm_120",
            "-lineinfo",
            "--cubin",
            str(source),
            "-o",
            str(cubin),
        ],
        output_directory / "compile-cubin.log",
        environment,
    )
    if cubin_compile.returncode != 0:
        raise RuntimeError(
            f"k=8 cubin compilation failed: {cubin_compile.returncode}"
        )
    disassembly = run_and_log(
        [nvdisasm, str(cubin)],
        output_directory / "benchmark_k8.sass",
        environment,
    )
    if disassembly.returncode != 0:
        raise RuntimeError(f"nvdisasm failed: {disassembly.returncode}")
    static_result = {
        "compile_pass": True,
        "dmma_8x8x4_static_instruction_count": disassembly.stdout.count(
            "DMMA.8x8x4"
        ),
        "expected_static_instruction_count": 64,
    }
    static_result["dmma_instruction_gate_pass"] = (
        static_result["dmma_8x8x4_static_instruction_count"]
        == static_result["expected_static_instruction_count"]
    )
    if not static_result["dmma_instruction_gate_pass"]:
        raise RuntimeError(
            "k=8 cubin did not contain exactly 32 FP64 DMMA instructions per kernel"
        )
    return executable, cubin, static_result


def run_json_command(
    *,
    command: list[str],
    log_stem: Path,
    environment: dict[str, str],
    timeout_seconds: float,
) -> dict[str, object]:
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
        timeout=timeout_seconds,
    )
    log_stem.with_suffix(".stdout.log").write_text(
        completed.stdout, encoding="utf-8"
    )
    log_stem.with_suffix(".stderr.log").write_text(
        completed.stderr, encoding="utf-8"
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"{' '.join(command[1:])} failed with exit code {completed.returncode}"
        )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"command emitted invalid JSON: {error}") from error


def write_raw_timings(
    path: Path, payload: dict[str, object]
) -> None:
    baseline_repetitions = int(payload["baseline_repetitions"])
    no_overlap_repetitions = int(payload["no_overlap_repetitions"])
    rows: list[dict[str, object]] = []
    for sample in payload["samples"]:
        for kernel, repetitions, field in (
            ("k8_baseline", baseline_repetitions, "baseline_total_ms"),
            ("k8_no_overlap", no_overlap_repetitions, "no_overlap_total_ms"),
        ):
            total_ms = float(sample[field])
            rows.append(
                {
                    "pair": sample["pair"],
                    "order": sample["order"],
                    "kernel": kernel,
                    "repetitions": repetitions,
                    "total_ms": total_ms,
                    "ms_per_launch": total_ms / repetitions,
                }
            )
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    arguments = parse_args()
    output_directory = arguments.output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    plan = benchmark_plan()
    geometry = comparison_geometry(height=HEIGHT, width=WIDTH)
    (output_directory / "benchmark-plan.json").write_text(
        json.dumps(plan, indent=2) + "\n", encoding="utf-8"
    )
    (output_directory / "geometry.json").write_text(
        json.dumps(geometry, indent=2) + "\n", encoding="utf-8"
    )
    if arguments.plan_only:
        print(json.dumps({"plan": plan, "geometry": geometry}))
        return 0

    start = time.monotonic()
    experiment_root = Path(__file__).resolve().parent.parent
    environment = load_msvc_environment()
    executable, _cubin, static_result = compile_artifacts(
        experiment_root=experiment_root,
        output_directory=output_directory,
        environment=environment,
    )
    (output_directory / "static-result.json").write_text(
        json.dumps(static_result, indent=2) + "\n", encoding="utf-8"
    )
    if arguments.static_only:
        print(json.dumps(static_result))
        return 0

    def remaining_budget() -> float:
        remaining = TOTAL_RUNTIME_BUDGET_SECONDS - (time.monotonic() - start)
        if remaining <= 0.0:
            raise RuntimeError("k=8 experiment exhausted its 10-minute budget")
        return remaining

    correctness: dict[str, object] = {}
    for kernel in ("baseline", "no-overlap"):
        result = run_json_command(
            command=[str(executable), kernel, "32", "64"],
            log_stem=output_directory / f"correctness-{kernel}",
            environment=environment,
            timeout_seconds=remaining_budget(),
        )
        correctness[kernel] = result
        if not result.get("correctness_pass"):
            raise RuntimeError(f"k=8 {kernel} correctness gate failed")
    (output_directory / "correctness.json").write_text(
        json.dumps(correctness, indent=2) + "\n", encoding="utf-8"
    )

    resources = run_json_command(
        command=[str(executable), "resources"],
        log_stem=output_directory / "resources",
        environment=environment,
        timeout_seconds=remaining_budget(),
    )
    (output_directory / "resources.json").write_text(
        json.dumps(resources, indent=2) + "\n", encoding="utf-8"
    )

    measurement = run_json_command(
        command=[str(executable), "measure", str(HEIGHT), str(WIDTH)],
        log_stem=output_directory / "measurement",
        environment=environment,
        timeout_seconds=remaining_budget(),
    )
    (output_directory / "measurement.json").write_text(
        json.dumps(measurement, indent=2) + "\n", encoding="utf-8"
    )
    write_raw_timings(output_directory / "raw-timings.csv", measurement)
    summary = summarize_payload(measurement, bootstrap_samples=10000)
    final_result = {
        "generated_at": utc_now(),
        "elapsed_seconds": time.monotonic() - start,
        "plan": plan,
        "geometry": geometry,
        "static": static_result,
        "correctness": correctness,
        "resources": resources,
        "timing": summary,
    }
    (output_directory / "summary.json").write_text(
        json.dumps(final_result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, subprocess.TimeoutExpired) as error:
        print(error, file=sys.stderr)
        raise SystemExit(1) from error
