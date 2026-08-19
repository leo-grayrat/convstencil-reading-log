from pathlib import Path
import sys
import unittest


SCRIPTS_DIRECTORY = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIRECTORY))

from run_k8_experiment import benchmark_plan, summarize_payload  # noqa: E402


class K8ExperimentTests(unittest.TestCase):
    def test_plan_is_one_fixed_bounded_cuda_event_comparison(self) -> None:
        plan = benchmark_plan()

        self.assertEqual(plan["problem_size"], {"height": 1024, "width": 7168})
        self.assertEqual(plan["warmups"], 5)
        self.assertEqual(plan["pairs"], 21)
        self.assertEqual(plan["orders"][:4], ["AB", "BA", "AB", "BA"])
        self.assertEqual(plan["target_sample_ms"], 150)
        self.assertEqual(plan["timing_api"], "CUDA Event")
        self.assertEqual(plan["total_runtime_budget_seconds"], 600)

    def test_summary_reports_per_block_time_and_no_overlap_throughput_ratio(self) -> None:
        payload = {
            "height": 1024,
            "width": 7168,
            "blocks_per_kernel": 3584,
            "baseline_repetitions": 2,
            "no_overlap_repetitions": 4,
            "samples": [
                {
                    "baseline_total_ms": 12.0,
                    "no_overlap_total_ms": 16.0,
                },
                {
                    "baseline_total_ms": 10.0,
                    "no_overlap_total_ms": 12.0,
                },
                {
                    "baseline_total_ms": 14.0,
                    "no_overlap_total_ms": 20.0,
                },
            ],
        }

        summary = summarize_payload(payload, bootstrap_samples=200)

        self.assertEqual(summary["k8_baseline"]["median_ms"], 6.0)
        self.assertEqual(summary["k8_no_overlap"]["median_ms"], 4.0)
        self.assertAlmostEqual(
            summary["k8_baseline"]["average_us_per_block"],
            6.0 * 1000.0 / 3584,
        )
        self.assertAlmostEqual(
            summary["k8_no_overlap"]["average_us_per_block"],
            4.0 * 1000.0 / 3584,
        )
        self.assertEqual(summary["throughput_ratio"], 1.5)


if __name__ == "__main__":
    unittest.main()
