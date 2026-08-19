from pathlib import Path
import sys
import unittest


SCRIPTS_DIRECTORY = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIRECTORY))

from measurement import (  # noqa: E402
    alternating_orders,
    block_geometry,
    normalized_block_cost_ratio,
    summarize_equal_block_pairs,
    summarize_pairs,
)


class MeasurementTests(unittest.TestCase):
    def test_block_geometry_exposes_seven_eighths_efficiency(self) -> None:
        geometry = block_geometry(height=1024, width=7168)

        self.assertEqual(geometry["baseline_blocks"], 3584)
        self.assertEqual(geometry["variant_blocks"], 4096)
        self.assertEqual(geometry["block_count_ratio"], 8 / 7)
        self.assertEqual(geometry["ideal_throughput_ratio"], 7 / 8)

    def test_normalized_cost_removes_extra_block_count(self) -> None:
        self.assertAlmostEqual(
            normalized_block_cost_ratio(
                baseline_ms=6.011731227272727,
                variant_ms=6.8249405,
                baseline_blocks=3584,
                variant_blocks=4096,
            ),
            0.9933615978053578,
        )

    def test_equal_block_summary_reports_variant_cost_ratio(self) -> None:
        summary = summarize_equal_block_pairs(
            baseline_ms=[4.0, 6.0, 8.0],
            variant_ms=[2.0, 3.0, 4.0],
            bootstrap_samples=200,
            random_seed=66,
        )

        self.assertEqual(summary["baseline_median_ms"], 6.0)
        self.assertEqual(summary["variant_median_ms"], 3.0)
        self.assertEqual(summary["variant_to_baseline_block_cost"], 0.5)
        self.assertEqual(summary["paired_bootstrap_95_ci"], [0.5, 0.5])

    def test_alternating_orders_cancels_first_position_bias(self) -> None:
        self.assertEqual(
            alternating_orders(5),
            ["AB", "BA", "AB", "BA", "AB"],
        )

    def test_summary_uses_paired_samples_and_useful_outputs(self) -> None:
        summary = summarize_pairs(
            baseline_ms=[4.0, 6.0, 8.0],
            variant_ms=[2.0, 3.0, 4.0],
            useful_outputs=12_000_000,
            bootstrap_samples=200,
            random_seed=66,
        )

        self.assertEqual(summary["baseline"]["median_ms"], 6.0)
        self.assertEqual(summary["baseline"]["iqr_ms"], 2.0)
        self.assertEqual(summary["baseline"]["gstencil_per_second"], 2.0)
        self.assertEqual(summary["variant"]["median_ms"], 3.0)
        self.assertEqual(summary["variant"]["iqr_ms"], 1.0)
        self.assertEqual(summary["variant"]["gstencil_per_second"], 4.0)
        self.assertEqual(summary["throughput_ratio"], 2.0)
        self.assertEqual(summary["paired_bootstrap_95_ci"], [2.0, 2.0])

    def test_summary_rejects_unpaired_samples(self) -> None:
        with self.assertRaisesRegex(ValueError, "paired samples"):
            summarize_pairs(
                baseline_ms=[1.0, 2.0],
                variant_ms=[1.0],
                useful_outputs=1,
                bootstrap_samples=10,
                random_seed=66,
            )


if __name__ == "__main__":
    unittest.main()
