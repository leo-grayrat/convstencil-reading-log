"""Static accounting for the fixed k=8 comparison."""

from __future__ import annotations


def input_leading_dimension(width: int) -> int:
    if width <= 0:
        raise ValueError("width must be positive")
    minimum_columns = width + 9
    return ((minimum_columns + 3) // 4) * 4


def comparison_geometry(*, height: int, width: int) -> dict[str, dict[str, object]]:
    block_rows = 32
    block_columns = 64
    if (
        height <= 0
        or width <= 0
        or height % block_rows != 0
        or width % block_columns != 0
    ):
        raise ValueError("dimensions must tile 32 rows and 64 columns")

    stencil_length = 8
    data_rows = block_rows + stencil_length - 1
    source_columns = block_columns + stencil_length
    source_elements = data_rows * source_columns
    useful_outputs_per_block = block_rows * block_columns
    block_count = (height // block_rows) * (width // block_columns)
    mma_count = stencil_length * stencil_length // 4
    dmma_per_block = (
        32  # 8 warps, 4 output tiles per warp
        * 2  # lower and upper triangular weight matrices
        * mma_count
    )

    common: dict[str, object] = {
        "useful_outputs_per_block": useful_outputs_per_block,
        "blocks": block_count,
        "dmma_per_block": dmma_per_block,
        "total_dmma": block_count * dmma_per_block,
        "candidate_outputs_per_tile": 8,
        "useful_outputs_per_tile": 8,
        "discarded_outputs_per_block": 0,
        "duplicate_outputs_per_block": 0,
        "uses_output_staging": False,
        "unique_input_elements_per_block": source_elements,
        "unique_input_elements_per_useful_output": (
            source_elements / useful_outputs_per_block
        ),
    }

    baseline_shared_slots = 2 * 8 * data_rows * stencil_length
    no_overlap_shared_slots = 9 * data_rows * stencil_length
    baseline = {
        **common,
        "shared_input_slots_per_block": baseline_shared_slots,
        "duplicate_shared_input_slots": baseline_shared_slots - source_elements,
        "shared_input_slots_per_useful_output": (
            baseline_shared_slots / useful_outputs_per_block
        ),
        "explicit_shared_bytes": baseline_shared_slots * 8,
    }
    no_overlap = {
        **common,
        "shared_input_slots_per_block": no_overlap_shared_slots,
        "duplicate_shared_input_slots": no_overlap_shared_slots - source_elements,
        "shared_input_slots_per_useful_output": (
            no_overlap_shared_slots / useful_outputs_per_block
        ),
        "explicit_shared_bytes": no_overlap_shared_slots * 8,
    }
    return {"k8_baseline": baseline, "k8_no_overlap": no_overlap}
