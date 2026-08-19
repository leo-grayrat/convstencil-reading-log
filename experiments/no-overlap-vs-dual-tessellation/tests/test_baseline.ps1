$ErrorActionPreference = 'Stop'

$experimentRoot = Split-Path -Parent $PSScriptRoot
$runner = Join-Path $experimentRoot 'scripts\run_correctness.py'
$outputDir = Join-Path $PSScriptRoot '.tmp\baseline-correctness'

if (-not (Test-Path -LiteralPath $runner)) {
    throw "Correctness runner is missing: $runner"
}

& python $runner `
    --kernel baseline `
    --height 32 `
    --width 448 `
    --output-directory $outputDir
if ($LASTEXITCODE -ne 0) {
    throw "Baseline correctness runner failed with exit code $LASTEXITCODE"
}

$resultPath = Join-Path $outputDir 'correctness-result.json'
if (-not (Test-Path -LiteralPath $resultPath)) {
    throw "Correctness runner did not produce $resultPath"
}

$result = Get-Content -Raw -Encoding UTF8 $resultPath | ConvertFrom-Json
if (-not $result.compile_pass) {
    throw 'Baseline compilation failed.'
}
if (-not $result.correctness_pass) {
    throw "Baseline differs from CPU reference; max error is $($result.max_abs_error)"
}
if ($result.matrix_instruction_count -ne 26) {
    throw "Expected 26 FP64 matrix instructions, got $($result.matrix_instruction_count)"
}
if ($result.height -ne 32 -or $result.width -ne 448) {
    throw "Unexpected correctness dimensions: $($result.height)x$($result.width)"
}

Write-Host 'ConvStencil baseline correctness passed.'
