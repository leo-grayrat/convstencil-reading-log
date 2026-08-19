#!/usr/bin/env python3
"""Build and run the mandatory FP64 WMMA 8x8x4 capability gate."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


class GateError(RuntimeError):
    """Raised when one stage of the capability gate fails."""


def environment_value(environment: dict[str, str], name: str) -> str | None:
    target = name.casefold()
    return next(
        (value for key, value in environment.items() if key.casefold() == target),
        None,
    )


def load_msvc_environment() -> dict[str, str]:
    environment = os.environ.copy()
    if shutil.which("cl.exe", path=environment_value(environment, "PATH")):
        return environment

    program_files_x86 = environment_value(environment, "ProgramFiles(x86)")
    if not program_files_x86:
        raise GateError("ProgramFiles(x86) is unavailable; cannot locate Visual Studio.")

    vswhere = (
        Path(program_files_x86)
        / "Microsoft Visual Studio"
        / "Installer"
        / "vswhere.exe"
    )
    if not vswhere.is_file():
        raise GateError(f"Visual Studio locator is missing: {vswhere}")

    discovery = subprocess.run(
        [
            str(vswhere),
            "-latest",
            "-products",
            "*",
            "-requires",
            "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
            "-property",
            "installationPath",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    installation_path = discovery.stdout.strip()
    if discovery.returncode != 0 or not installation_path:
        raise GateError("No Visual Studio installation with the x64 C++ toolchain was found.")

    vcvars = Path(installation_path) / "VC" / "Auxiliary" / "Build" / "vcvars64.bat"
    if not vcvars.is_file():
        raise GateError(f"Visual Studio x64 environment script is missing: {vcvars}")

    command_processor = environment_value(environment, "ComSpec") or "cmd.exe"
    activation = subprocess.run(
        [
            command_processor,
            "/d",
            "/c",
            "call",
            str(vcvars),
            "&&",
            "set",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
    )
    if activation.returncode != 0:
        raise GateError(f"Failed to load the Visual Studio x64 environment from {vcvars}")

    for line in activation.stdout.splitlines():
        name, separator, value = line.partition("=")
        if separator and name:
            environment[name] = value

    if not shutil.which("cl.exe", path=environment_value(environment, "PATH")):
        raise GateError("Visual Studio environment loaded, but cl.exe is unavailable.")
    return environment


def run_and_log(
    command: list[str], log_path: Path, environment: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
    )
    log_path.write_text(completed.stdout + completed.stderr, encoding="utf-8")
    return completed


def run_gate(output_directory: Path) -> dict[str, object]:
    result: dict[str, object] = {
        "compile_pass": False,
        "numeric_pass": False,
        "matrix_instruction_pass": False,
        "compute_capability": None,
    }

    experiment_root = Path(__file__).resolve().parent.parent
    source_path = experiment_root / "src" / "wmma_probe.cu"
    if not source_path.is_file():
        raise GateError(f"WMMA probe source is missing: {source_path}")

    environment = load_msvc_environment()
    search_path = environment_value(environment, "PATH")
    nvcc = shutil.which("nvcc.exe", path=search_path)
    nvdisasm = shutil.which("nvdisasm.exe", path=search_path)
    if not nvcc or not nvdisasm:
        raise GateError("CUDA nvcc.exe and nvdisasm.exe must both be available.")

    executable_path = output_directory / "wmma-probe.exe"
    cubin_path = output_directory / "wmma-probe.cubin"
    sass_path = output_directory / "wmma-probe.sass"

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
        raise GateError(
            f"nvcc executable compilation failed with exit code "
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
        raise GateError(
            f"nvcc cubin compilation failed with exit code {cubin_compile.returncode}"
        )
    result["compile_pass"] = True

    probe_run = run_and_log(
        [str(executable_path)], output_directory / "probe-stdout.log", environment
    )
    if probe_run.returncode != 0:
        raise GateError(f"WMMA probe execution failed with exit code {probe_run.returncode}")

    try:
        payload = json.loads(probe_run.stdout)
    except json.JSONDecodeError as error:
        raise GateError(f"WMMA probe emitted invalid JSON: {error}") from error
    result["compute_capability"] = str(payload.get("compute_capability"))
    result["numeric_pass"] = bool(payload.get("numeric_pass"))

    disassembly = run_and_log(
        [nvdisasm, str(cubin_path)], sass_path, environment
    )
    if disassembly.returncode != 0:
        raise GateError(f"nvdisasm failed with exit code {disassembly.returncode}")
    result["matrix_instruction_pass"] = bool(
        re.search(r"\bDMMA\.8x8x4\b", disassembly.stdout)
    )

    if not result["numeric_pass"]:
        raise GateError("FP64 WMMA numeric check failed.")
    if not result["matrix_instruction_pass"]:
        raise GateError("No FP64 DMMA.8x8x4 instruction was found in the sm_120 cubin.")
    if result["compute_capability"] != "12.0":
        raise GateError(
            "Expected compute capability 12.0, got "
            f"{result['compute_capability']}"
        )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-directory", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    output_directory = arguments.output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    result_path = output_directory / "probe-result.json"

    result: dict[str, object] = {
        "compile_pass": False,
        "numeric_pass": False,
        "matrix_instruction_pass": False,
        "compute_capability": None,
    }
    try:
        result = run_gate(output_directory)
    except GateError as error:
        print(error, file=sys.stderr)
        return_code = 1
    else:
        return_code = 0
    finally:
        result_path.write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8"
        )
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
