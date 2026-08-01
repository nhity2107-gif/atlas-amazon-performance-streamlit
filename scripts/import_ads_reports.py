from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ads_data import (
    build_ads_employee_summary,
    build_ads_employee_summary_from_reports,
    read_advertised_products,
    read_ads_workbook,
    read_support_campaigns,
    upsert_ads_snapshot,
)
from lark_snapshot_store import load_lark_snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description="Build local employee Ads snapshot")
    parser.add_argument("--products", type=Path)
    parser.add_argument("--support", type=Path)
    parser.add_argument("--sponsored-products", type=Path)
    parser.add_argument("--sponsored-brands", type=Path)
    parser.add_argument("--sponsored-display", type=Path)
    parser.add_argument("--lark-snapshot", type=Path, default=PROJECT_ROOT / "snapshot/lark")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "snapshot/ads")
    parser.add_argument("--month", required=True, help="Reporting month in YYYY-MM")
    parser.add_argument("--store", default="Wrappiness")
    args = parser.parse_args()

    lark = load_lark_snapshot(args.lark_snapshot)
    if lark is None:
        raise SystemExit("Chưa có snapshot Lark hợp lệ để map Ads By.")
    complete_sources = [
        ("SP", args.sponsored_products),
        ("SB", args.sponsored_brands),
        ("SD", args.sponsored_display),
    ]
    if any(path is not None for _, path in complete_sources):
        missing_sources = [kind for kind, path in complete_sources if path is None]
        store_slug = args.store.strip().casefold()
        pawsionate_sp_only = (
            store_slug == "pawsionate"
            and args.sponsored_products is not None
            and args.sponsored_brands is None
            and args.sponsored_display is None
        )
        if missing_sources and not pawsionate_sp_only:
            raise SystemExit(
                "Import workbook mới cần đủ SP, SB và SD; còn thiếu: "
                + ", ".join(missing_sources)
            )
        reports = [
            read_ads_workbook(path, kind)
            for kind, path in complete_sources
            if path is not None
        ]
        summary, diagnostics = build_ads_employee_summary_from_reports(
            reports, lark["total"]
        )
        source_metadata = {
            "sponsored_products_source": args.sponsored_products.name,
            "sponsored_brands_source": (
                args.sponsored_brands.name if args.sponsored_brands else ""
            ),
            "sponsored_display_source": (
                args.sponsored_display.name if args.sponsored_display else ""
            ),
            "mapping_mode": (
                "complete-sp-only" if pawsionate_sp_only else "complete-sp-sb-sd"
            ),
        }
    else:
        if args.products is None:
            raise SystemExit(
                "Cần --sponsored-products/--sponsored-brands/--sponsored-display "
                "hoặc --products legacy."
            )
        products = read_advertised_products(args.products)
        support = (
            read_support_campaigns(args.support)
            if args.support
            else __import__("pandas").DataFrame(
                columns=[
                    "ASIN", "Campaign name", "support_spend", "support_sales",
                    "support_orders",
                ]
            )
        )
        summary, diagnostics = build_ads_employee_summary(products, support, lark["total"])
        source_metadata = {
            "products_source": args.products.name,
            "support_source": args.support.name if args.support else "",
            "mapping_mode": "legacy-advertised-product",
        }
    upsert_ads_snapshot(
        args.output,
        summary,
        {
            "month": args.month,
            "store": args.store,
            **source_metadata,
            "diagnostics": diagnostics,
        },
    )
    print(json.dumps({"summary": summary.to_dict("records"), **diagnostics}, ensure_ascii=False))


if __name__ == "__main__":
    main()
