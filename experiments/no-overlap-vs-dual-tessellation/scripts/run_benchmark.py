#!/usr/bin/env python3
"""Run the two fixed paired benchmarks and persist lightweight evidence."""

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

from measurement import alternating_orders, summarize_pairs
from run_wmma_probe import environment_value, load_msvc_environment, run_and_log


PROBLEM_SIZES = ((1024, 7168), (2048, 7168))
WARMUP_COUNT = 5
PAIR_COUNT = 21
TARGET_SAMPLE_MS = 150
TOTAL_RUNTIME_BUDGET_SECONDS = 30 * 60
RETRY_WAIT_SECONDS = 2 * 60
RELATIVE_IQR_RETRY_THRESHOLD = 0.05


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--plan-only", action="store_true")
    return parser.parse_args()


def benchmark_plan() -> dict[str, object]:
    return {
        "problem_sizes": [
            {"height": height, "width": width}
            for height, width in PROBLEM_SIZES
        ],
        "warmups": WARMUP_COUNT,
        "pairs": PAIR_COUNT,
        "orders": alternating_orders(PAIR_COUNT),
        "target_sample_ms": TARGET_SAMPLE_MS,
        "relative_iqr_retry_threshold": RELATIVE_IQR_RETRY_THRESHOLD,
        "maximum_retries_per_size": 1,
        "total_runtime_budget_seconds": TOTAL_RUNTIME_BUDGET_SECONDS,
    }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def capture_gpu_state(environment: dict[str, str], phase: str) -> dict[str, object]:
    query = (
        "name,driver_version,temperature.gpu,pstate,clocks.current.graphics,"
        "clocks.current.memory,power.draw"
    )
    completed = subprocess.run(
        [
            "nvidia-smi",
            f"--query-gpu={query}",
            "--format=csv,noheader,nounits",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
    )
    return {
        "timestamp": utc_now(),
        "phase": phase,
        "return_code": completed.returncode,
        "query": query,
        "value": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def compile_benchmark(
    *,
    experiment_root: Path,
    build_directory: Path,
    environment: dict[str, str],
) -> Path:
    build_directory.mkdir(parents=True, exist_ok=True)
    search_path = environment_value(environment, "PATH")
    nvcc = shutil.which("nvcc.exe", path=search_path)
    if not nvcc:
        raise RuntimeError("CUDA nvcc.exe is unavailable.")

    source_path = experiment_root / "src" / "benchmark.cu"
    executable_path = build_directory / "benchmark.exe"
    compilation = run_and_log(
        [
            nvcc,
            "--std=c++17",
            "-arch=sm_120",
            "-lineinfo",
            str(source_path),
            "-o",
            str(executable_path),
        ],
        build_directory / "compile-benchmark.log",
        environment,
    )
    if compilation.returncode != 0:
        raise RuntimeError(
            f"benchmark compilation failed with exit code {compilation.returncode}"
        )
    return executable_path


def run_measurement_attempt(
    *,
    executable_path: Path,
    height: int,
    width: int,
    attempt: int,
    output_directory: Path,
    environment: dict[str, str],
    timeout_seconds: float,
) -> dict[str, object]:
    try:
        completed = subprocess.run(
            [str(executable_path), "measure", str(height), str(width)],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(
            f"measurement {height}x{width} exceeded its remaining runtime budget"
        ) from error

    log_stem = f"measure-{height}x{width}-attempt-{attempt}"
    (output_directory / f"{log_stem}.stdout.log").write_text(
        completed.stdout, encoding="utf-8"
    )
    (output_directory / f"{log_stem}.stderr.log").write_text(
        completed.stderr, encoding="utf-8"
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"measurement {height}x{width} failed with exit code "
            f"{completed.returncode}"
        )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"measurement {height}x{width} emitted invalid JSON: {error}"
        ) from error
    return payload


def payload_times(payload: dict[str, object]) -> tuple[list[float], list[float]]:
    baseline_repetitions = int(payload["baseline_repetitions"])
    variant_repetitions = int(payload["variant_repetitions"])
    samples = payload["samples"]
    if not isinstance(samples, list):
        raise RuntimeError("measurement samples must be a list")
    baseline_ms = [
        float(sample["baseline_total_ms"]) / baseline_repetitions
        for sample in samples
    ]
    variant_ms = [
        float(sample["variant_total_ms"]) / variant_repetitions
        for sample in samples
    ]
    return baseline_ms, variant_ms


def summarize_payload(payload: dict[str, object]) -> dict[str, object]:
    baseline_ms, variant_ms = payload_times(payload)
    useful_outputs = int(payload["height"]) * int(payload["width"])
    summary = summarize_pairs(
        baseline_ms=baseline_ms,
        variant_ms=variant_ms,
        useful_outputs=useful_outputs,
        bootstrap_samples=10000,
        random_seed=66 + int(payload["height"]),
    )
    baseline_relative_iqr = (
        float(summary["baseline"]["iqr_ms"])
        / float(summary["baseline"]["median_ms"])
    )
    variant_relative_iqr = (
        float(summary["variant"]["iqr_ms"])
        / float(summary["variant"]["median_ms"])
    )
    summary["maximum_relative_iqr"] = max(
        baseline_relative_iqr, variant_relative_iqr
    )
    summary["sample_window_pass"] = all(
        100.0 <= float(sample["baseline_total_ms"]) <= 300.0
        and 100.0 <= float(sample["variant_total_ms"]) <= 300.0
        for sample in payload["samples"]
    )
    return summary


def flatten_rows(
    payload: dict[str, object], attempt: int
) -> list[dict[str, object]]:
    baseline_repetitions = int(payload["baseline_repetitions"])
    variant_repetitions = int(payload["variant_repetitions"])
    useful_outputs = int(payload["height"]) * int(payload["width"])
    rows: list[dict[str, object]] = []
    for sample in payload["samples"]:
        for kernel, repetitions in (
            ("baseline", baseline_repetitions),
            ("variant", variant_repetitions),
        ):
            total_ms = float(sample[f"{kernel}_total_ms"])
            per_launch_ms = total_ms / repetitions
            rows.append(
                {
                    "height": payload["height"],
                    "width": payload["width"],
                    "attempt": attempt,
                    "pair": sample["pair"],
                    "order": sample["order"],
                    "kernel": kernel,
                    "repetitions": repetitions,
                    "total_ms": total_ms,
                    "ms_per_launch": per_launch_ms,
                    "gstencil_per_second": useful_outputs / (per_launch_ms * 1.0e6),
                }
            )
    return rows


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fieldnames = [
        "height",
        "width",
        "attempt",
        "pair",
        "order",
        "kernel",
        "repetitions",
        "total_ms",
        "ms_per_launch",
        "gstencil_per_second",
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    arguments = parse_args()
    output_directory = arguments.output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    plan = benchmark_plan()
    (output_directory / "benchmark-plan.json").write_text(
        json.dumps(plan, indent=2) + "\n", encoding="utf-8"
    )
    if arguments.plan_only:
        print(json.dumps(plan))
        return 0

    start_time = time.monotonic()
    experiment_root = Path(__file__).resolve().parent.parent
    environment = load_msvc_environment()
    executable_path = compile_benchmark(
        experiment_root=experiment_root,
        build_directory=experiment_root / "build",
        environment=environment,
    )

    environment_snapshots = [capture_gpu_state(environment, "before-all")]
    all_rows: list[dict[str, object]] = []
    size_summaries: list[dict[str, object]] = []
    for height, width in PROBLEM_SIZES:
        selected_payload: dict[str, object] | None = None
        selected_summary: dict[str, object] | None = None
        retry_used = False
        for attempt in range(2):
            remaining = TOTAL_RUNTIME_BUDGET_SECONDS - (
                time.monotonic() - start_time
            )
            if remaining <= 0.0:
                raise RuntimeError("total benchmark runtime budget was exhausted")
            environment_snapshots.append(
                capture_gpu_state(
                    environment, f"before-{height}x{width}-attempt-{attempt}"
                )
            )
            payload = run_measurement_attempt(
                executable_path=executable_path,
                height=height,
                width=width,
                attempt=attempt,
                output_directory=output_directory,
                environment=environment,
                timeout_seconds=remaining,
            )
            environment_snapshots.append(
                capture_gpu_state(
                    environment, f"after-{height}x{width}-attempt-{attempt}"
                )
            )
            summary = summarize_payload(payload)
            all_rows.extend(flatten_rows(payload, attempt))
            selected_payload = payload
            selected_summary = summary
            if (
                float(summary["maximum_relative_iqr"])
                <= RELATIVE_IQR_RETRY_THRESHOLD
                or attempt == 1
            ):
                break
            retry_used = True
            if time.monotonic() - start_time + RETRY_WAIT_SECONDS >= (
                TOTAL_RUNTIME_BUDGET_SECONDS
            ):
                break
            time.sleep(RETRY_WAIT_SECONDS)

        if selected_payload is None or selected_summary is None:
            raise RuntimeError(f"no measurement was collected for {height}x{width}")
        size_summaries.append(
            {
                "height": height,
                "width": width,
                "retry_used": retry_used,
                "baseline_repetitions": selected_payload["baseline_repetitions"],
                "variant_repetitions": selected_payload["variant_repetitions"],
                **selected_summary,
            }
        )

    environment_snapshots.append(capture_gpu_state(environment, "after-all"))
    write_csv(output_directory / "raw-timings.csv", all_rows)
    (output_directory / "summary.json").write_text(
        json.dumps(
            {
                "generated_at": utc_now(),
                "elapsed_seconds": time.monotonic() - start_time,
                "sizes": size_summaries,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (output_directory / "environment.json").write_text(
        json.dumps(environment_snapshots, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(error, file=sys.stderr)
        raise SystemExit(1) from error
