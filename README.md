# Atlas Amazon Performance Dashboard

Streamlit dashboard for live month-to-date Amazon order, Ads and employee KPI reporting.

## Daily month-to-date update

Each daily Order export must cover the first day of the selected month through
the input date. Daily updates require only the two Order reports:

```powershell
& "D:\Atlas Amazon Performance\dashboard\scripts\update_month_to_date.ps1" `
  -Month 2026-08 `
  -AsOfDate 2026-08-04 `
  -WrappinessOrder "D:\reports\wrappiness-orders.txt" `
  -PawsionateOrder "D:\reports\pawsionate-orders.txt"
```

Ads are imported once at month end with all six reports:

```powershell
& "D:\Atlas Amazon Performance\dashboard\scripts\update_month_to_date.ps1" `
  -Month 2026-08 `
  -AsOfDate 2026-08-31 `
  -WrappinessSP "D:\reports\wrappiness-sp.xlsx" `
  -WrappinessSB "D:\reports\wrappiness-sb.xlsx" `
  -WrappinessSD "D:\reports\wrappiness-sd.xlsx" `
  -PawsionateSP "D:\reports\pawsionate-sp.xlsx" `
  -PawsionateSB "D:\reports\pawsionate-sb.xlsx" `
  -PawsionateSD "D:\reports\pawsionate-sd.xlsx"
```

The `mtd` import deletes the existing Store interval from day 01 through
`AsOfDate` before inserting the new Order report. This handles late orders,
cancellations and omitted rows without double counting. Ads imports replace the
same Store + Month snapshot. The dashboard reads the saved snapshots, exposes a
global month selector and displays the latest covered Order/Ads date.

`AsOfDate` is also persisted as `report_as_of_date`. Team workflow output uses
this input date instead of the last Purchase Date (a day with no orders no longer
shortens the KPI window). The graphical daily tool refreshes all three Lark
tables before generating the dashboard; if Lark is unavailable it clearly warns
that the previous local snapshot is being used. Revenue/Orders remain based only
on actual Amazon Purchase Dates.

Add `-PublishOrderSnapshot` only when the aggregate Order snapshot should be
committed and pushed. Raw Order files, the SQLite database and Ads/Lark snapshots
remain local and gitignored.

### Local graphical update tool

Run the PC-only uploader on `http://127.0.0.1:8502`:

```powershell
& "D:\Atlas Amazon Performance\dashboard\scripts\run_update_tool.ps1"
```

For a PC that should keep the uploader available, run
`scripts/watch_update_tool.ps1` in the background and add it to the current
Windows user's Startup folder. The watchdog checks the local service every 60
seconds and restarts it when port 8502 is unavailable. The Startup shortcut on
the configured PC is named `Atlas Amazon Import Tool`.

The tool defaults to daily mode with only two Order MTD files. Enable
`Import 6 Ads report cuối tháng` only on the final Ads import; the tool then
requires SP/SB/SD for both stores. It validates inputs, updates the relevant
snapshots, runs tests, then publishes only the
aggregate Order snapshot plus an encrypted Ads snapshot. Because the GitHub
repository is public, initialize a Fernet key once:

```powershell
python scripts/setup_publish_key.py
```

Open `D:\\Atlas Amazon Performance\\STREAMLIT-CLOUD-SECRET.txt`, then copy its
`DASHBOARD_DATA_KEY` line into Streamlit Cloud App settings
→ Secrets. Never commit the plaintext key or `snapshot/ads/`.

## Standard local input database

All raw inputs follow `data/input/<YYYY-MM>/<store>/{orders,ads}`. Filenames use
`YYYY-MM__<store>__<dataset>__<scope>.<ext>`; see
[`data/input/README.md`](data/input/README.md) for the complete contract. Raw
files and monthly manifests are local-only and ignored by Git.

Validate a month before importing:

```bash
python scripts/validate_input_layout.py --month 2026-07 --store wrappiness --require-all-ads
python scripts/validate_input_layout.py --month 2026-07 --store pawsionate --require-all-ads
```

## Persistent Order data workflow

Raw Amazon reports and the SQLite database remain only under
`D:\Atlas Amazon Performance`. The repository stores the aggregate file
`snapshot/dashboard_snapshot.csv`, containing only Store, Pacific Date, ASIN,
Revenue, Orders, Units and Record ID hint. It does not contain customer or
order-level data. Daily aggregation enables dashboard time-window filters.
Its sidecar `snapshot/dashboard_snapshot.metadata.json` records the latest
source-report update, covered date range and the `America/Los_Angeles` time
basis.

Streamlit loads this CSV automatically, so viewers do not need a dashboard key
or need to upload reports on every visit. Order reports are processed only by the
local pipeline and are never uploaded through the dashboard UI.

## Lark mapping

Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and configure
the Lark app, Base and table IDs. The Product page then maps each Record ID to
Product, Idea By, Managed By, Custom By and Ads By. The real secrets file is
ignored by Git.

The latest successful Lark sync is persisted locally under `snapshot/lark/` and
published as the encrypted `snapshot/published_lark_snapshot.enc`. Normal
dashboard visits read this shared snapshot without calling Lark. Use the
`Cập nhật snapshot Lark · tất cả bảng` button on Team KPI only when fresh data
is needed. TOTAL ASIN, MRND IDEA and CLIPARTS are saved as one coherent refresh;
if a refresh fails, the dashboard continues using the previous snapshot. The
local import tool refreshes and republishes this encrypted Lark snapshot whenever
new Order reports are processed, so Streamlit and another machine use the same
KPI source. `DASHBOARD_DATA_KEY` must match across local and Streamlit Secrets.
The legacy name `PUBLISHED_SNAPSHOT_KEY` remains supported for older machines.

Time semantics are intentionally separate: Lark workflow KPI uses the calendar
date returned by Lark without timezone conversion, while Order, Revenue and
Units use Amazon Purchase Time converted to `America/Los_Angeles` before daily
aggregation and monthly filtering.

The Overview splits Net Revenue into FBA and FBM using TOTAL ASIN `Fulfill By`.
It maps by ASIN first and falls back to the Order snapshot `record_id_hint`, so
FBA + FBM reconciles to Net Revenue for the selected store.

Team KPI is intentionally FBM-only. All employee Order-derived metrics
(Revenue, Units, winners, milestones, Portfolio/New Revenue and ASIN counts)
filter to `Fulfill By = FBM`. Employee Ads KPI uses separate FBM-only Spend,
Sales and Orders fields, so FBA is excluded even when a campaign is assigned to
Support or an execution marker. Overview and aggregate Ads Performance continue
to show FBA + FBM for store reconciliation.

## Local Ads allocation

Complete Sponsored Products, Sponsored Brands and Sponsored Display workbooks
are processed locally and saved under the gitignored `snapshot/ads/`. SP maps
with `Advertised ASIN`; SB/SD map with the first ASIN in `Campaign Name` so a
collection campaign total is allocated once. Every campaign whose name contains
`Support` (case-insensitive, including forms such as `NhiSupport`) is assigned
directly to the separate `Nhi-Support` row. Campaign markers containing `LINH`,
`HIEU` or `HA` are likewise assigned to execution-only rows `Linh`, `Hieu` and
`Ha`, including joined forms such as `HIEUAMZ` and `HIEUMRND`. Those metrics are
removed from the original Ads By owner. FBA is identified
from TOTAL ASIN `Fulfill By = FBA`, then
assigned from `Custom By`: Trương Ý Nhi becomes `Nhi-FBA` and Phương Linh/MRnD
becomes `Linh-FBA`. The Ads snapshot stores multiple Store/Month imports.

Confirmed source corrections are centralized in `fulfillment_rules.py`.
`B0F1XZT333` and `B0F1XPZ1JX` are treated as FBA even while TOTAL ASIN still
marks them as FBM, so Overview revenue and Ads allocation remain consistent.

```bash
python scripts/import_ads_reports.py \
  --sponsored-products "data/input/2026-07/wrappiness/ads/2026-07__wrappiness__ads__sp-advertised-product.xlsx" \
  --sponsored-brands "data/input/2026-07/wrappiness/ads/2026-07__wrappiness__ads__sb-campaign.xlsx" \
  --sponsored-display "data/input/2026-07/wrappiness/ads/2026-07__wrappiness__ads__sd-campaign.xlsx" \
  --month 2026-07 --store Wrappiness

python scripts/import_ads_reports.py \
  --sponsored-products "data/input/2026-07/pawsionate/ads/2026-07__pawsionate__ads__sp-advertised-product.xlsx" \
  --sponsored-brands "data/input/2026-07/pawsionate/ads/2026-07__pawsionate__ads__sb-campaign.xlsx" \
  --sponsored-display "data/input/2026-07/pawsionate/ads/2026-07__pawsionate__ads__sd-campaign.xlsx" \
  --month 2026-07 --store Pawsionate
```

Legacy interval update:

```powershell
& "D:\Atlas Amazon Performance\update_dashboard.ps1" `
  -Store Wrappiness `
  -Report "D:\Atlas Amazon Performance\reports\orders\new-report.txt" `
  -Scope weekly `
  -Start 2026-07-01 `
  -End 2026-07-30 `
  -Publish
```

Daily imports upsert by `order-item-id`. Weekly and monthly imports replace the
store's complete Pacific-date interval (`-Start` through `-End`) before inserting
the new report, ensuring new late orders are added and cancelled or omitted
orders are removed. The pipeline rejects a report containing orders outside that
replacement window to prevent an accidental partial refresh.

For the standard daily full-month export, use scope `mtd` with an explicit
`--as-of-date`; the first replacement date is derived automatically as day 01:

```powershell
python scripts/local_data_pipeline.py ingest-order `
  --db "D:\Atlas Amazon Performance\database\atlas.db" `
  --file "D:\reports\wrappiness-orders.txt" `
  --store Wrappiness --scope mtd --as-of-date 2026-08-04
```

When invoking the Python pipeline directly, pass the interval explicitly:

```powershell
python scripts/local_data_pipeline.py ingest-order `
  --db database/atlas.db --file reports/orders/weekly.txt `
  --store Wrappiness --scope weekly `
  --replace-start 2026-07-01 --replace-end 2026-07-07

python scripts/local_data_pipeline.py export-snapshot `
  --db database/atlas.db --output snapshot/dashboard_snapshot.csv `
  --start 2026-07-01 --end 2026-07-30
```
