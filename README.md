# Atlas Amazon Performance Dashboard

Streamlit dashboard for July 2026 Amazon order, Ads and employee KPI reporting.

## Standard local input database

All raw inputs follow `data/input/<YYYY-MM>/<store>/{orders,ads}`. Filenames use
`YYYY-MM__<store>__<dataset>__<scope>.<ext>`; see
[`data/input/README.md`](data/input/README.md) for the complete contract. Raw
files and monthly manifests are local-only and ignored by Git.

Validate a month before importing:

```bash
python scripts/validate_input_layout.py --month 2026-07 --store wrappiness --require-all-ads
python scripts/validate_input_layout.py --month 2026-07 --store pawsionate
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

The latest successful Lark sync is persisted under `snapshot/lark/`. Normal
dashboard visits read this local snapshot without calling Lark. Use the
`Cập nhật snapshot Lark · tất cả bảng` button on Team KPI only when fresh data
is needed. TOTAL ASIN, MRND IDEA and CLIPARTS are saved as one coherent refresh;
if a refresh fails, the dashboard continues using the previous snapshot.

Time semantics are intentionally separate: Lark workflow KPI uses the calendar
date returned by Lark without timezone conversion, while Order, Revenue and
Units use Amazon Purchase Time converted to `America/Los_Angeles` before daily
aggregation and monthly filtering.

The Overview splits Net Revenue into FBA and FBM using TOTAL ASIN `Fulfill By`.
It maps by ASIN first and falls back to the Order snapshot `record_id_hint`, so
FBA + FBM reconciles to Net Revenue for the selected store.

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
  --month 2026-07 --store Pawsionate
```

Pawsionate accepts a complete SP workbook without SB/SD because those two Ads
types are declared `not-applicable` for this store and month.

Example update:

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
