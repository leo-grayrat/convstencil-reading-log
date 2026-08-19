from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest


EXPERIMENT_ROOT = Path(__file__).resolve().parent.parent


class EqualBlockProbeIntegrationTests(unittest.TestCase):
    def test_probe_times_equal_grid_with_bounded_samples(self) -> None:
        output_directory = EXPERIMENT_ROOT / "tests" / ".tmp" / "equal-block-probe"
        completed = subprocess.run(
            [
                sys.executable,
                str(EXPERIMENT_ROOT / "scripts" / "run_equal_block_probe.py"),
                "--height",
                "2048",
                "--grid-columns",
                "112",
                "--output-directory",
                str(output_directory),
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

        payload = json.loads(
            (output_directory / "equal-block-result.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(payload["height"], 2048)
        self.assertEqual(payload["grid_columns"], 112)
        self.assertEqual(payload["blocks_per_kernel"], 7168)
        self.assertEqual(payload["pairs"], 21)
        self.assertEqual(len(payload["samples"]), 21)
        for sample in payload["samples"]:
            self.assertGreaterEqual(sample["baseline_total_ms"], 100.0)
            self.assertLessEqual(sample["baseline_total_ms"], 300.0)
            self.assertGreaterEqual(sample["variant_total_ms"], 100.0)
            self.assertLessEqual(sample["variant_total_ms"], 300.0)


if __name__ == "__main__":
    unittest.main()
