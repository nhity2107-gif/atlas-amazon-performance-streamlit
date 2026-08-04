param(
    [string]$AsOfDate = (Get-Date -Format "yyyy-MM-dd"),
    [string]$Month = (Get-Date -Format "yyyy-MM"),
    [string]$WrappinessOrder,
    [string]$PawsionateOrder,
    [string]$WrappinessSP,
    [string]$WrappinessSB,
    [string]$WrappinessSD,
    [string]$PawsionateSP,
    [switch]$PublishOrderSnapshot
)

$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"

if (-not $AsOfDate.StartsWith("$Month-")) {
    throw "AsOfDate phải nằm trong Month đã chọn."
}
if (-not ($WrappinessOrder -or $PawsionateOrder -or $WrappinessSP -or
          $WrappinessSB -or $WrappinessSD -or $PawsionateSP)) {
    throw "Cần cung cấp ít nhất một Order hoặc Ads report để cập nhật."
}

$dashboardRoot = Split-Path $PSScriptRoot -Parent
$atlasRoot = Split-Path $dashboardRoot -Parent
$database = Join-Path $atlasRoot "database\atlas.db"
$orderPipeline = Join-Path $dashboardRoot "scripts\local_data_pipeline.py"
$adsPipeline = Join-Path $dashboardRoot "scripts\import_ads_reports.py"
$orderSnapshot = Join-Path $dashboardRoot "snapshot\dashboard_snapshot.csv"

function Import-MtdOrder {
    param([string]$Store, [string]$Report)
    if (-not $Report) { return }
    $resolved = (Resolve-Path -LiteralPath $Report).Path
    python $orderPipeline ingest-order `
        --db $database `
        --file $resolved `
        --store $Store `
        --scope mtd `
        --as-of-date $AsOfDate
    if ($LASTEXITCODE -ne 0) { throw "Không thể import Order MTD cho $Store." }
}

Import-MtdOrder -Store "Wrappiness" -Report $WrappinessOrder
Import-MtdOrder -Store "Pawsionate" -Report $PawsionateOrder

if ($WrappinessOrder -or $PawsionateOrder) {
    python $orderPipeline export-snapshot --db $database --output $orderSnapshot
    if ($LASTEXITCODE -ne 0) { throw "Không thể xuất Order snapshot tổng hợp." }
}

if ($WrappinessSP -or $WrappinessSB -or $WrappinessSD) {
    if (-not ($WrappinessSP -and $WrappinessSB -and $WrappinessSD)) {
        throw "Wrappiness cần đủ ba report SP, SB và SD."
    }
    python $adsPipeline `
        --sponsored-products (Resolve-Path -LiteralPath $WrappinessSP).Path `
        --sponsored-brands (Resolve-Path -LiteralPath $WrappinessSB).Path `
        --sponsored-display (Resolve-Path -LiteralPath $WrappinessSD).Path `
        --month $Month `
        --as-of-date $AsOfDate `
        --store Wrappiness
    if ($LASTEXITCODE -ne 0) { throw "Không thể import Ads MTD cho Wrappiness." }
}

if ($PawsionateSP) {
    python $adsPipeline `
        --sponsored-products (Resolve-Path -LiteralPath $PawsionateSP).Path `
        --month $Month `
        --as-of-date $AsOfDate `
        --store Pawsionate
    if ($LASTEXITCODE -ne 0) { throw "Không thể import Ads MTD cho Pawsionate." }
}

if ($PublishOrderSnapshot) {
    git -C $dashboardRoot add snapshot/dashboard_snapshot.csv snapshot/dashboard_snapshot.metadata.json
    $changes = git -C $dashboardRoot diff --cached --name-only
    if ($changes) {
        git -C $dashboardRoot commit -m "Update live dashboard through $AsOfDate"
        git -C $dashboardRoot push origin main
    } else {
        Write-Host "Order snapshot không thay đổi; không cần publish."
    }
}

Write-Host "Hoàn tất dashboard MTD $Month đến hết $AsOfDate."
