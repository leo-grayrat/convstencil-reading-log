#!/usr/bin/env python3
"""Build and run one fixed correctness case for an experiment kernel."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import sys

from run_wmma_probe import environment_value, load_msvc_environment, run_and_log


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kernel", choices=("baseline", "variant"), required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    output_directory = arguments.output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    result_path = output_directory / "correctness-result.json"
    result: dict[str, object] = {
        "compile_pass": False,
        "correctness_pass": False,
        "matrix_instruction_count": 0,
        "height": arguments.height,
        "width": arguments.width,
        "max_abs_error": None,
    }

    experiment_root = Path(__file__).resolve().parent.parent
    source_path = experiment_root / "src" / "benchmark.cu"
    executable_path = output_directory / "benchmark.exe"
    cubin_path = output_directory / "benchmark.cubin"
    sass_path = output_directory / "benchmark.sass"

    try:
        environment = load_msvc_environment()
        search_path = environment_value(environment, "PATH")
        nvcc = shutil.which("nvcc.exe", path=search_path)
        nvdisasm = shutil.which("nvdisasm.exe", path=search_path)
        if not nvcc or not nvdisasm:
            raise RuntimeError("CUDA nvcc.exe and nvdisasm.exe must both be available.")

        executable_compile = run_and_log(
            [
                nvcc,
                "--std=c++17",
                "-arch=sm_120",
                "-lineinfo",
                str(source_path),
                "-o",
                str(executable_path),
            ],
            output_directory / "compile-executable.log",
            environment,
        )
        if executable_compile.returncode != 0:
            raise RuntimeError(
                "benchmark executable compilation failed with exit code "
                f"{executable_compile.returncode}"
            )

        cubin_compile = run_and_log(
            [
                nvcc,
                "--std=c++17",
                "-arch=sm_120",
                "-lineinfo",
                "--cubin",
                str(source_path),
                "-o",
                str(cubin_path),
            ],
            output_directory / "compile-cubin.log",
            environment,
        )
        if cubin_compile.returncode != 0:
            raise RuntimeError(
                "benchmark cubin compilation failed with exit code "
                f"{cubin_compile.returncode}"
            )
        result["compile_pass"] = True

        benchmark_run = run_and_log(
            [
                str(executable_path),
                arguments.kernel,
                str(arguments.height),
                str(arguments.width),
            ],
            output_directory / "benchmark-stdout.log",
            environment,
        )
        if benchmark_run.stdout.strip():
            payload = json.loads(benchmark_run.stdout)
            result["correctness_pass"] = bool(payload["correctness_pass"])
            result["max_abs_error"] = payload["max_abs_error"]
        if benchmark_run.returncode != 0:
            raise RuntimeError(
                f"benchmark correctness failed with exit code {benchmark_run.returncode}"
            )

        disassembly = run_and_log(
            [nvdisasm, str(cubin_path)], sass_path, environment
        )
        if disassembly.returncode != 0:
            raise RuntimeError(
                f"benchmark disassembly failed with exit code {disassembly.returncode}"
            )
        kernel_marker = {
            "baseline": "convstencil_baseline_kernel",
            "variant": "no_overlap_variant_kernel",
        }[arguments.kernel]
        kernel_section = re.search(
            rf"//-+ \.text\.[^\r\n]*{kernel_marker}[^\r\n]* -+"
            rf"(?P<body>.*?)(?=//-+ \.|\Z)",
            disassembly.stdout,
            flags=re.DOTALL,
        )
        if not kernel_section:
            raise RuntimeError(
                f"could not find SASS section for {arguments.kernel} kernel"
            )
        result["matrix_instruction_count"] = len(
            re.findall(r"\bDMMA\.8x8x4\b", kernel_section.group("body"))
        )

        if result["matrix_instruction_count"] != 26:
            raise RuntimeError(
                "expected 26 FP64 matrix instructions, got "
                f"{result['matrix_instruction_count']}"
            )
        return_code = 0
    except (RuntimeError, json.JSONDecodeError) as error:
        print(error, file=sys.stderr)
        return_code = 1
    finally:
        result_path.write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8"
        )
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
