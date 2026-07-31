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
$keyFile = Join-Path $projectRoot ".secrets\dashboard_data_key.txt"
$pipeline = Join-Path $projectRoot "pipeline\local_data_pipeline.py"
$localSnapshot = Join-Path $projectRoot "snapshot\dashboard_snapshot.enc"
$dashboardRoot = Join-Path $projectRoot "dashboard"
$dashboardSnapshot = Join-Path $dashboardRoot "snapshot\dashboard_snapshot.enc"

if (($Store -and -not $Report) -or ($Report -and -not $Store)) {
    throw "Store và Report phải được truyền cùng nhau."
}

if ($Report) {
    $resolvedReport = (Resolve-Path -LiteralPath $Report).Path
    python $pipeline ingest-order --db $database --file $resolvedReport --store $Store --scope $Scope
    if ($LASTEXITCODE -ne 0) { throw "Không thể ingest order report." }
}

python $pipeline export-snapshot --db $database --output $localSnapshot --key-file $keyFile --start $Start --end $End
if ($LASTEXITCODE -ne 0) { throw "Không thể sinh snapshot dashboard." }

New-Item -ItemType Directory -Force -Path (Split-Path $dashboardSnapshot) | Out-Null
Copy-Item -LiteralPath $localSnapshot -Destination $dashboardSnapshot -Force

if ($Publish) {
    git -C $dashboardRoot add snapshot/dashboard_snapshot.enc
    $changes = git -C $dashboardRoot diff --cached --name-only
    if ($changes) {
        git -C $dashboardRoot commit -m "Update encrypted dashboard snapshot"
        git -C $dashboardRoot push origin main
    } else {
        Write-Host "Snapshot không thay đổi; không cần publish."
    }
}

Write-Host "Hoàn tất. Snapshot: $localSnapshot"
