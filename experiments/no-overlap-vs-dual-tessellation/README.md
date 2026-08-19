# No-overlap vs. ConvStencil Dual Tessellation

This experiment answers one narrow question: on the same FP64 `8x8x4`
WMMA path, what performance trend does a non-overlapping input layout show
relative to ConvStencil's Box-2D49P Dual Tessellation kernel?

The experiment is tracked in [issue #66](https://github.com/leo-grayrat/convstencil-reading-log/issues/66).

## Provenance

The baseline is derived from Microsoft ConvStencil commit
`89688a1b51ec41b4a81028b0661363ba3afd6050`, especially
[`src/2d/gpu.cu`](https://github.com/microsoft/ConvStencil/blob/89688a1b51ec41b4a81028b0661363ba3afd6050/src/2d/gpu.cu).
ConvStencil is licensed under the MIT License. Any adapted source retains an
explicit provenance notice.

## Mandatory gate

Before either benchmark is implemented or run, the local RTX 5060 Laptop must
compile, execute, and expose a matrix instruction for FP64 WMMA `8x8x4` when
targeting `sm_120`. If any part of this gate fails, the performance comparison
stops. CUDA Core and lower-precision Tensor Core substitutes are not accepted
as evidence for the primary question.

## Fixed comparison

- Baseline: FP64 Box-2D49P, 256 threads, 13+13 WMMA operations, 32x64 useful
  outputs per block.
- Variant: the same FP64 weights and WMMA sequence, with adjacent 7-column
  chunks paired as `(P_i, P_{i+1})`; seven of each eight candidate outputs are
  committed, giving 32x56 useful outputs per block.
- Global widths are multiples of 448, so 64-wide and 56-wide output blocks
  cover the same domain without tails.
- The primary statistic is useful throughput ratio, variant divided by
  baseline. No arbitrary competitiveness threshold is imposed.

## Runtime boundary

Only the documented capability probe, correctness case, and two fixed problem
sizes may run. Total GPU test time is capped at 30 minutes. The full upstream
benchmark suite and unbounded parameter searches are out of scope.

## Reproduction

The capability probe, fixed correctness checks, and benchmark plan are exposed
through Python runners so that PowerShell is not required:

```text
python scripts/run_wmma_probe.py --output-directory tests/.tmp/wmma-probe
python scripts/run_correctness.py --kernel baseline --height 32 --width 448 --output-directory tests/.tmp/baseline
python scripts/run_correctness.py --kernel variant --height 32 --width 448 --output-directory tests/.tmp/variant
python scripts/run_benchmark.py --output-directory results/latest --plan-only
python scripts/run_benchmark.py --output-directory results/latest
python scripts/run_resource_probe.py --output-directory tests/.tmp/resource-probe
python scripts/run_equal_block_probe.py --height 2048 --grid-columns 112 --output-directory tests/.tmp/equal-block-probe
```

The last command launches the two fixed GPU measurements and therefore must
only be used within the documented runtime budget. Figures can be regenerated
without launching the GPU:

```text
python scripts/plot_results.py --results-directory results/rtx5060-2026-08-20
```

The resource probe queries CUDA Runtime attributes without launching a kernel.
The equal-block probe is a bounded diagnostic run: both kernels launch the
same 7168 blocks so their per-block cost can be separated from the 64-versus-56
useful-output geometry.

The separate `k=8` experiment keeps the original `k=7` sources unchanged and
compares a dual-plane paper-style kernel against the original no-overlap idea
at one fixed size:

```text
python scripts/run_k8_experiment.py --output-directory tests/.tmp/k8-plan --plan-only
python scripts/run_k8_experiment.py --output-directory tests/.tmp/k8-static --static-only
python scripts/run_k8_experiment.py --output-directory results/k8-rtx5060-2026-08-20
```

The full command is capped at ten minutes. It stops before timing if either
the static DMMA gate or the two `32x64` CPU-reference correctness cases fail.

## Recorded result

The RTX 5060 Laptop run is documented in
[`results/rtx5060-2026-08-20/REPORT.md`](results/rtx5060-2026-08-20/REPORT.md).
Across the two fixed sizes, the no-overlap variant reached 0.875--0.881 of the
baseline's useful throughput.

The fixed `k=8` follow-up is documented in
[`results/k8-rtx5060-2026-08-20/REPORT.md`](results/k8-rtx5060-2026-08-20/REPORT.md).
At `1024x7168`, both k=8 kernels use the same block and DMMA counts; the
no-overlap kernel reached 1.0270 of the same-k baseline throughput. This is a
within-k comparison, not a direct k=7-to-k=8 speedup claim.

## Repository boundaries

All generated sources and lightweight results stay under this experiment
directory. Existing reading notes, demos, translations, paper files, and
assets are not modified.
