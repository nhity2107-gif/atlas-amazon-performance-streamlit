param(
    [ValidateSet("Wrappiness", "Pawsionate")]
    [string]$Store,
    [string]$Report,
    [ValidateSet("daily", "weekly", "monthly", "mtd")]
    [string]$Scope = "mtd",
    [string]$Start = (Get-Date -Day 1 -Format "yyyy-MM-dd"),
    [string]$End = (Get-Date -Format "yyyy-MM-dd"),
    [switch]$Publish
)

$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
$dashboardRoot = Split-Path $PSScriptRoot -Parent
$projectRoot = Split-Path $dashboardRoot -Parent
$database = Join-Path $projectRoot "database\atlas.db"
$pipeline = Join-Path $dashboardRoot "scripts\local_data_pipeline.py"
$dashboardSnapshot = Join-Path $dashboardRoot "snapshot\dashboard_snapshot.csv"

if (($Store -and -not $Report) -or ($Report -and -not $Store)) {
    throw "Store và Report phải được truyền cùng nhau."
}

if ($Report) {
    $resolvedReport = (Resolve-Path -LiteralPath $Report).Path
    $ingestArgs = @(
        $pipeline, "ingest-order", "--db", $database, "--file", $resolvedReport,
        "--store", $Store, "--scope", $Scope
    )
    if ($Scope -eq "mtd") {
        $ingestArgs += @("--as-of-date", $End)
    } elseif ($Scope -in @("weekly", "monthly")) {
        $ingestArgs += @("--replace-start", $Start, "--replace-end", $End)
    }
    python @ingestArgs
    if ($LASTEXITCODE -ne 0) { throw "Không thể ingest order report." }
}

python $pipeline export-snapshot `
    --db $database `
    --output $dashboardSnapshot `
    --start $Start `
    --end $End `
    --as-of-date $End
if ($LASTEXITCODE -ne 0) { throw "Không thể sinh snapshot dashboard." }

if ($Publish) {
    git -C $dashboardRoot add snapshot/dashboard_snapshot.csv
    $changes = git -C $dashboardRoot diff --cached --name-only
    if ($changes) {
        git -C $dashboardRoot commit -m "Update dashboard snapshot"
        git -C $dashboardRoot push origin main
    } else {
        Write-Host "Snapshot không thay đổi; không cần publish."
    }
}

Write-Host "Hoàn tất. Snapshot: $dashboardSnapshot"
