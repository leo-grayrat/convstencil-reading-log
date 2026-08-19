"""Deterministic paired-measurement statistics for the benchmark."""

from __future__ import annotations

import random
import statistics


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
