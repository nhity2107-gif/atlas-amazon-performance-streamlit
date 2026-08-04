# Monthly input convention

Raw Amazon reports are stored locally and are never committed. Use one folder
per reporting month and store:

```text
data/input/
└── YYYY-MM/
    ├── wrappiness/
    │   ├── orders/
    │   └── ads/
    └── pawsionate/
        ├── orders/
        └── ads/
```

## Canonical filenames

Use lowercase ASCII store slugs and separate filename components with `__`.
The reporting month is the month represented by the data, not the export date.

```text
YYYY-MM__<store>__order__mtd.txt
YYYY-MM__<store>__ads__sp-advertised-product.xlsx
YYYY-MM__<store>__ads__sb-campaign.xlsx
YYYY-MM__<store>__ads__sd-campaign.xlsx
```

CSV is accepted for legacy Sponsored Products exports; retain `.csv` when the
source is CSV. Do not rename a CSV to `.xlsx`.

Use manifest status `not-applicable` when a store genuinely had no activity for
an Ads type. Use `pending-replacement` when a provisional report must not be
treated as final.

Examples for July 2026:

```text
2026-07__wrappiness__order__mtd.txt
2026-07__wrappiness__ads__sp-advertised-product.xlsx
2026-07__wrappiness__ads__sb-campaign.xlsx
2026-07__wrappiness__ads__sd-campaign.xlsx
2026-07__pawsionate__order__mtd.txt
2026-07__pawsionate__ads__sp-advertised-product.xlsx
```

For Pawsionate, an SP-only workbook import is valid when SB and SD are declared
`not-applicable` in the monthly manifest.

## Required source definitions

| Dataset | Required granularity | Date handling | Primary mapping |
|---|---|---|---|
| Order MTD | Amazon order item, day 01 through input date | Purchase Time converted to `America/Los_Angeles` | ASIN, then SKU Record ID hint |
| SP advertised product | Campaign + Advertised ASIN, day 01 through input date | Amazon report month-to-date | `Advertised ASIN` |
| SB campaign | Campaign, day 01 through input date | Amazon report month-to-date | First ASIN in `Campaign Name` |
| SD campaign | Campaign, day 01 through input date | Amazon report month-to-date | First ASIN in `Campaign Name` |
| Lark | API snapshot, not a raw file in this folder | Original Lark calendar date | TOTAL ASIN / MRND IDEA / CLIPARTS |

Every non-zero Ads row must resolve to an ASIN and then to `TOTAL ASIN`. Every
campaign whose name contains `Support` (case-insensitive) is allocated directly
to the `Nhi-Support` row. Exact campaign tokens `LINH`, `HIEU` and `HA` are
allocated to separate execution rows before FBA allocation. Joined forms such
as `LINHAMZ`, `HIEUAMZ`, `HIEUMRND` and `HAMRND` are also recognized. FBA is determined
from `TOTAL ASIN Fulfill By`, with confirmed
overrides kept in `fulfillment_rules.py`.

## Lifecycle

1. Copy exports into the month/store folders without editing their contents.
2. Use the canonical names above.
3. Run the local Order and Ads import pipelines.
4. Verify report totals against the generated snapshots.
5. Keep old month folders as read-only source history; do not overwrite them
   after a month has been signed off. If a corrected export arrives, copy the
   previous canonical file to `data/archive/<YYYY-MM>/<timestamp>/` before
   replacing it. Archive files are also local-only and ignored by Git.

Raw reports, local databases, Lark snapshots and Ads snapshots remain ignored
by Git. Only aggregate dashboard snapshots explicitly approved for publishing
belong in the repository.
