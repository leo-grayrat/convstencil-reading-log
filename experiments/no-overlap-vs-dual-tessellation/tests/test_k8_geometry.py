from pathlib import Path
import sys
import unittest


SCRIPTS_DIRECTORY = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIRECTORY))

from k8_geometry import comparison_geometry  # noqa: E402


class K8GeometryTests(unittest.TestCase):
    def test_no_overlap_has_no_extra_blocks_or_dmmas(self) -> None:
        geometry = comparison_geometry(height=1024, width=7168)

        baseline = geometry["k8_baseline"]
        no_overlap = geometry["k8_no_overlap"]
        self.assertEqual(baseline["useful_outputs_per_block"], 2048)
        self.assertEqual(no_overlap["useful_outputs_per_block"], 2048)
        self.assertEqual(baseline["blocks"], 3584)
        self.assertEqual(no_overlap["blocks"], 3584)
        self.assertEqual(baseline["dmma_per_block"], 1024)
        self.assertEqual(no_overlap["dmma_per_block"], 1024)
        self.assertEqual(baseline["total_dmma"], 3_670_016)
        self.assertEqual(no_overlap["total_dmma"], 3_670_016)

    def test_no_overlap_commits_all_eight_candidate_columns_directly(self) -> None:
        geometry = comparison_geometry(height=1024, width=7168)
        no_overlap = geometry["k8_no_overlap"]

        self.assertEqual(no_overlap["candidate_outputs_per_tile"], 8)
        self.assertEqual(no_overlap["useful_outputs_per_tile"], 8)
        self.assertEqual(no_overlap["discarded_outputs_per_block"], 0)
        self.assertEqual(no_overlap["duplicate_outputs_per_block"], 0)
        self.assertFalse(no_overlap["uses_output_staging"])

    def test_input_accounting_separates_unique_source_from_shared_copies(self) -> None:
        geometry = comparison_geometry(height=1024, width=7168)
        baseline = geometry["k8_baseline"]
        no_overlap = geometry["k8_no_overlap"]

        self.assertEqual(baseline["unique_input_elements_per_block"], 2808)
        self.assertEqual(no_overlap["unique_input_elements_per_block"], 2808)
        self.assertEqual(baseline["shared_input_slots_per_block"], 4992)
        self.assertEqual(no_overlap["shared_input_slots_per_block"], 2808)
        self.assertEqual(baseline["duplicate_shared_input_slots"], 2184)
        self.assertEqual(no_overlap["duplicate_shared_input_slots"], 0)
        self.assertAlmostEqual(
            no_overlap["unique_input_elements_per_useful_output"],
            1.37109375,
        )
        self.assertAlmostEqual(
            baseline["shared_input_slots_per_useful_output"],
            2.4375,
        )

    def test_static_shared_memory_excludes_cubin_only_overhead(self) -> None:
        geometry = comparison_geometry(height=1024, width=7168)

        self.assertEqual(geometry["k8_baseline"]["explicit_shared_bytes"], 39_936)
        self.assertEqual(
            geometry["k8_no_overlap"]["explicit_shared_bytes"],
            22_464,
        )

    def test_dimensions_must_tile_full_output_blocks(self) -> None:
        with self.assertRaisesRegex(ValueError, "32 rows and 64 columns"):
            comparison_geometry(height=33, width=7168)
        with self.assertRaisesRegex(ValueError, "32 rows and 64 columns"):
            comparison_geometry(height=1024, width=7000)


if __name__ == "__main__":
    unittest.main()
