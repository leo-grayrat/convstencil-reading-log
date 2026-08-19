from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest


EXPERIMENT_ROOT = Path(__file__).resolve().parent.parent


class ResourceProbeIntegrationTests(unittest.TestCase):
    def test_runtime_probe_reports_comparable_kernel_resources(self) -> None:
        output_directory = EXPERIMENT_ROOT / "tests" / ".tmp" / "resource-probe"
        completed = subprocess.run(
            [
                sys.executable,
                str(EXPERIMENT_ROOT / "scripts" / "run_resource_probe.py"),
                "--output-directory",
                str(output_directory),
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

        payload = json.loads(
            (output_directory / "resource-result.json").read_text(encoding="utf-8")
        )
        self.assertEqual(payload["thread_count"], 256)
        self.assertGreater(payload["device"]["multiprocessor_count"], 0)
        baseline = payload["kernels"]["baseline"]
        variant = payload["kernels"]["variant"]
        self.assertEqual(baseline["registers_per_thread"], 76)
        self.assertEqual(variant["registers_per_thread"], 76)
        self.assertLess(
            variant["static_shared_bytes"], baseline["static_shared_bytes"]
        )
        for kernel in (baseline, variant):
            self.assertGreater(kernel["max_active_blocks_per_sm"], 0)
            self.assertEqual(
                kernel["max_active_warps_per_sm"],
                kernel["max_active_blocks_per_sm"] * 8,
            )


if __name__ == "__main__":
    unittest.main()
