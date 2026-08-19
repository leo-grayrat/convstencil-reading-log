#!/usr/bin/env python3
"""Render reproducible benchmark figures from committed CSV/JSON evidence."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import statistics

import matplotlib.pyplot as plt


BASELINE_COLOR = "#0072B2"
VARIANT_COLOR = "#D55E00"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-directory", type=Path, required=True)
    return parser.parse_args()


def configure_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "DejaVu Sans"],
            "font.size": 9,
            "axes.labelsize": 9,
            "axes.titlesize": 10,
            "legend.fontsize": 8,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "svg.fonttype": "none",
            "svg.hashsalt": "convstencil-issue-66",
        }
    )


def save_figure(figure: plt.Figure, directory: Path, stem: str) -> None:
    svg_path = directory / f"{stem}.svg"
    figure.savefig(
        svg_path,
        bbox_inches="tight",
        metadata={"Date": "2026-08-20"},
    )
    svg_lines = svg_path.read_text(encoding="utf-8").splitlines()
    svg_path.write_text(
        "\n".join(line.rstrip() for line in svg_lines) + "\n",
        encoding="utf-8",
    )
    figure.savefig(directory / f"{stem}.png", dpi=300, bbox_inches="tight")
    plt.close(figure)


def load_selected_rows(results_directory: Path) -> list[dict[str, str]]:
    summary = json.loads(
        (results_directory / "summary.json").read_text(encoding="utf-8")
    )
    selected_attempts = {
        (int(size["height"]), int(size["width"])): 1 if size["retry_used"] else 0
        for size in summary["sizes"]
    }
    with (results_directory / "raw-timings.csv").open(
        newline="", encoding="utf-8"
    ) as stream:
        rows = list(csv.DictReader(stream))
    return [
        row
        for row in rows
        if int(row["attempt"])
        == selected_attempts[(int(row["height"]), int(row["width"]))]
    ]


def render_throughput(results_directory: Path) -> None:
    rows = load_selected_rows(results_directory)
    sizes = sorted({(int(row["height"]), int(row["width"])) for row in rows})
    figure, axis = plt.subplots(figsize=(5.4, 3.25))
    offsets = {"baseline": -0.14, "variant": 0.14}
    colors = {"baseline": BASELINE_COLOR, "variant": VARIANT_COLOR}
    labels = {"baseline": "Dual Tessellation baseline", "variant": "No overlap"}

    for kernel in ("baseline", "variant"):
        for index, (height, width) in enumerate(sizes):
            values = [
                float(row["gstencil_per_second"])
                for row in rows
                if row["kernel"] == kernel
                and int(row["height"]) == height
                and int(row["width"]) == width
            ]
            x_value = index + offsets[kernel]
            axis.scatter(
                [x_value] * len(values),
                values,
                s=13,
                alpha=0.45,
                color=colors[kernel],
                edgecolors="none",
                label=labels[kernel] if index == 0 else None,
            )
            axis.plot(
                [x_value - 0.08, x_value + 0.08],
                [statistics.median(values)] * 2,
                color=colors[kernel],
                linewidth=2.2,
            )

    axis.set_xticks(range(len(sizes)))
    axis.set_xticklabels([f"{height}×{width}" for height, width in sizes])
    axis.set_xlabel("Problem size (height×width)")
    axis.set_ylabel("Useful throughput (GStencil/s)")
    axis.set_title("Paired FP64 WMMA throughput (n=21 pairs)")
    axis.grid(axis="y", color="#D9D9D9", linewidth=0.6, alpha=0.7)
    axis.legend(frameon=False, loc="best")
    figure.tight_layout()
    save_figure(figure, results_directory, "throughput")


def render_ratio(results_directory: Path) -> None:
    summary = json.loads(
        (results_directory / "summary.json").read_text(encoding="utf-8")
    )
    sizes = summary["sizes"]
    ratios = [float(size["throughput_ratio"]) for size in sizes]
    lower = [float(size["paired_bootstrap_95_ci"][0]) for size in sizes]
    upper = [float(size["paired_bootstrap_95_ci"][1]) for size in sizes]
    x_values = list(range(len(sizes)))

    figure, axis = plt.subplots(figsize=(5.4, 3.25))
    axis.axhline(1.0, color="#555555", linestyle="--", linewidth=1.0)
    axis.errorbar(
        x_values,
        ratios,
        yerr=[
            [ratio - bound for ratio, bound in zip(ratios, lower)],
            [bound - ratio for ratio, bound in zip(ratios, upper)],
        ],
        fmt="o",
        color=VARIANT_COLOR,
        markerfacecolor="white",
        markeredgewidth=1.6,
        markersize=6,
        capsize=4,
        linewidth=1.5,
    )
    for x_value, ratio in zip(x_values, ratios):
        axis.annotate(
            f"{ratio:.3f}",
            (x_value, ratio),
            xytext=(0, 9),
            textcoords="offset points",
            ha="center",
            fontsize=8,
        )
    axis.set_xticks(x_values)
    axis.set_xticklabels(
        [f"{size['height']}×{size['width']}" for size in sizes]
    )
    axis.set_xlabel("Problem size (height×width)")
    axis.set_ylabel("Throughput ratio (no overlap / baseline)")
    axis.set_title("Paired-bootstrap ratio with 95% CI")
    axis.set_ylim(min(lower) - 0.025, 1.025)
    axis.grid(axis="y", color="#D9D9D9", linewidth=0.6, alpha=0.7)
    figure.tight_layout()
    save_figure(figure, results_directory, "throughput-ratio")


def main() -> int:
    arguments = parse_args()
    results_directory = arguments.results_directory.resolve()
    configure_style()
    render_throughput(results_directory)
    render_ratio(results_directory)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
