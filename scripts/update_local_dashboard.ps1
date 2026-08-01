param(
    [ValidateSet("Wrappiness", "Pawsionate")]
    [string]$Store,
    [string]$Report,
    [ValidateSet("daily", "weekly", "monthly")]
    [string]$Scope = "daily",
    [string]$Start = "2026-07-01",
    [string]$End = "2026-07-30",
    [switch]$Publish
)

$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
$projectRoot = "D:\Atlas Amazon Performance"
$database = Join-Path $projectRoot "database\atlas.db"
$pipeline = Join-Path $projectRoot "pipeline\local_data_pipeline.py"
$localSnapshot = Join-Path $projectRoot "snapshot\dashboard_snapshot.csv"
$dashboardRoot = Join-Path $projectRoot "dashboard"
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
    if ($Scope -in @("weekly", "monthly")) {
        $ingestArgs += @("--replace-start", $Start, "--replace-end", $End)
    }
    python @ingestArgs
    if ($LASTEXITCODE -ne 0) { throw "Không thể ingest order report." }
}

python $pipeline export-snapshot --db $database --output $localSnapshot --start $Start --end $End
if ($LASTEXITCODE -ne 0) { throw "Không thể sinh snapshot dashboard." }

New-Item -ItemType Directory -Force -Path (Split-Path $dashboardSnapshot) | Out-Null
Copy-Item -LiteralPath $localSnapshot -Destination $dashboardSnapshot -Force

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

Write-Host "Hoàn tất. Snapshot: $localSnapshot"
