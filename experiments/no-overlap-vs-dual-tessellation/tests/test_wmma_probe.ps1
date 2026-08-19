$ErrorActionPreference = 'Stop'

$experimentRoot = Split-Path -Parent $PSScriptRoot
$runner = Join-Path $experimentRoot 'scripts\run_wmma_probe.py'
$outputDir = Join-Path $PSScriptRoot '.tmp\wmma-probe'

if (-not (Test-Path -LiteralPath $runner)) {
    throw "WMMA probe runner is missing: $runner"
}

& python $runner --output-directory $outputDir
if ($LASTEXITCODE -ne 0) {
    throw "WMMA probe runner failed with exit code $LASTEXITCODE"
}

$resultPath = Join-Path $outputDir 'probe-result.json'
if (-not (Test-Path -LiteralPath $resultPath)) {
    throw "WMMA probe did not produce $resultPath"
}

$result = Get-Content -Raw -Encoding UTF8 $resultPath | ConvertFrom-Json
foreach ($field in 'compile_pass', 'numeric_pass', 'matrix_instruction_pass') {
    if (-not $result.$field) {
        throw "WMMA gate failed: $field is false"
    }
}

if ($result.compute_capability -ne '12.0') {
    throw "Expected compute capability 12.0, got $($result.compute_capability)"
}

Write-Host 'FP64 WMMA 8x8x4 gate passed.'
