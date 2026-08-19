"""Deterministic paired-measurement statistics for the benchmark."""

from __future__ import annotations

import random
import statistics


def block_geometry(*, height: int, width: int) -> dict[str, float | int]:
    if height <= 0 or width <= 0 or height % 32 != 0 or width % 448 != 0:
        raise ValueError("dimensions must tile 32 rows and both output widths")
    baseline_blocks = (height // 32) * (width // 64)
    variant_blocks = (height // 32) * (width // 56)
    return {
        "baseline_blocks": baseline_blocks,
        "variant_blocks": variant_blocks,
        "block_count_ratio": variant_blocks / baseline_blocks,
        "ideal_throughput_ratio": baseline_blocks / variant_blocks,
    }


def normalized_block_cost_ratio(
    *,
    baseline_ms: float,
    variant_ms: float,
    baseline_blocks: int,
    variant_blocks: int,
) -> float:
    if baseline_ms <= 0.0 or variant_ms <= 0.0:
        raise ValueError("timings must be positive")
    if baseline_blocks <= 0 or variant_blocks <= 0:
        raise ValueError("block counts must be positive")
    return (variant_ms / baseline_ms) / (variant_blocks / baseline_blocks)


def alternating_orders(pair_count: int) -> list[str]:
    if pair_count <= 0:
        raise ValueError("pair_count must be positive")
    return ["AB" if index % 2 == 0 else "BA" for index in range(pair_count)]


def percentile(values: list[float], probability: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")
    if not 0.0 <= probability <= 1.0:
        raise ValueError("probability must be between zero and one")

    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def kernel_summary(samples_ms: list[float], useful_outputs: int) -> dict[str, float]:
    median_ms = statistics.median(samples_ms)
    return {
        "median_ms": median_ms,
        "iqr_ms": percentile(samples_ms, 0.75) - percentile(samples_ms, 0.25),
        "gstencil_per_second": useful_outputs / (median_ms * 1.0e6),
    }


def summarize_pairs(
    *,
    baseline_ms: list[float],
    variant_ms: list[float],
    useful_outputs: int,
    bootstrap_samples: int,
    random_seed: int,
) -> dict[str, object]:
    if not baseline_ms or len(baseline_ms) != len(variant_ms):
        raise ValueError("baseline and variant must contain equal paired samples")
    if any(value <= 0.0 for value in baseline_ms + variant_ms):
        raise ValueError("timing samples must be positive")
    if useful_outputs <= 0:
        raise ValueError("useful_outputs must be positive")
    if bootstrap_samples <= 0:
        raise ValueError("bootstrap_samples must be positive")

    baseline = kernel_summary(baseline_ms, useful_outputs)
    variant = kernel_summary(variant_ms, useful_outputs)
    throughput_ratio = baseline["median_ms"] / variant["median_ms"]

    generator = random.Random(random_seed)
    pair_count = len(baseline_ms)
    bootstrap_ratios: list[float] = []
    for _ in range(bootstrap_samples):
        indices = [generator.randrange(pair_count) for _ in range(pair_count)]
        baseline_sample = [baseline_ms[index] for index in indices]
        variant_sample = [variant_ms[index] for index in indices]
        bootstrap_ratios.append(
            statistics.median(baseline_sample)
            / statistics.median(variant_sample)
        )

    return {
        "baseline": baseline,
        "variant": variant,
        "throughput_ratio": throughput_ratio,
        "paired_bootstrap_95_ci": [
            percentile(bootstrap_ratios, 0.025),
            percentile(bootstrap_ratios, 0.975),
        ],
    }


def summarize_equal_block_pairs(
    *,
    baseline_ms: list[float],
    variant_ms: list[float],
    bootstrap_samples: int,
    random_seed: int,
) -> dict[str, object]:
    if not baseline_ms or len(baseline_ms) != len(variant_ms):
        raise ValueError("baseline and variant must contain equal paired samples")
    if any(value <= 0.0 for value in baseline_ms + variant_ms):
        raise ValueError("timing samples must be positive")
    if bootstrap_samples <= 0:
        raise ValueError("bootstrap_samples must be positive")

    baseline_median = statistics.median(baseline_ms)
    variant_median = statistics.median(variant_ms)
    generator = random.Random(random_seed)
    pair_count = len(baseline_ms)
    bootstrap_ratios: list[float] = []
    for _ in range(bootstrap_samples):
        indices = [generator.randrange(pair_count) for _ in range(pair_count)]
        bootstrap_ratios.append(
            statistics.median(variant_ms[index] for index in indices)
            / statistics.median(baseline_ms[index] for index in indices)
        )

    return {
        "baseline_median_ms": baseline_median,
        "variant_median_ms": variant_median,
        "variant_to_baseline_block_cost": variant_median / baseline_median,
        "paired_bootstrap_95_ci": [
            percentile(bootstrap_ratios, 0.025),
            percentile(bootstrap_ratios, 0.975),
        ],
    }
