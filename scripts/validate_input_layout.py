from __future__ import annotations

import argparse
import csv
from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MONTH_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
STORE_SLUGS = {"wrappiness", "pawsionate"}
MANIFEST_DATASETS = {
    "order": "order",
    "sp": "sp-advertised-product",
    "sb": "sb-campaign",
    "sd": "sd-campaign",
}


def manifest_statuses(root: Path, month: str, store: str) -> dict[str, str]:
    manifest = root / month / "manifest.csv"
    if not manifest.exists():
        return {}
    with manifest.open(newline="", encoding="utf-8") as handle:
        rows = csv.DictReader(handle)
        return {
            key: str(row.get("status", "")).strip().casefold()
            for row in rows
            for key, dataset in MANIFEST_DATASETS.items()
            if row.get("store") == store and row.get("dataset") == dataset
        }


def expected_paths(root: Path, month: str, store: str) -> dict[str, tuple[Path, ...]]:
    store_root = root / month / store
    return {
        "order": (
            store_root / "orders" / f"{month}__{store}__order__mtd.txt",
            store_root / "orders" / f"{month}__{store}__order__mtd.tsv",
            store_root / "orders" / f"{month}__{store}__order__mtd.csv",
            store_root / "orders" / f"{month}__{store}__order__monthly.txt",
            store_root / "orders" / f"{month}__{store}__order__monthly.tsv",
            store_root / "orders" / f"{month}__{store}__order__monthly.csv",
        ),
        "sp": (
            store_root / "ads" / f"{month}__{store}__ads__sp-advertised-product.xlsx",
            store_root / "ads" / f"{month}__{store}__ads__sp-advertised-product.csv",
        ),
        "sb": (
            store_root / "ads" / f"{month}__{store}__ads__sb-campaign.xlsx",
        ),
        "sd": (
            store_root / "ads" / f"{month}__{store}__ads__sd-campaign.xlsx",
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate canonical monthly input files")
    parser.add_argument("--month", required=True, help="Reporting month in YYYY-MM")
    parser.add_argument("--store", required=True, choices=sorted(STORE_SLUGS))
    parser.add_argument("--require-all-ads", action="store_true")
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT / "data/input")
    args = parser.parse_args()
    if not MONTH_PATTERN.fullmatch(args.month):
        raise SystemExit("Month phải có định dạng YYYY-MM.")

    candidates = expected_paths(args.root, args.month, args.store)
    declared = manifest_statuses(args.root, args.month, args.store)
    required = {"order", "sp"}
    if args.require_all_ads:
        required.update({"sb", "sd"})
    missing: list[str] = []
    for dataset, paths in candidates.items():
        matches = [path for path in paths if path.exists()]
        manifest_status = declared.get(dataset, "")
        if manifest_status == "not-applicable" and not matches:
            status = "N/A"
        elif manifest_status == "pending-replacement":
            status = "PENDING"
        else:
            status = "OK" if len(matches) == 1 else "MISSING" if not matches else "DUPLICATE"
        selected = str(matches[0]) if len(matches) == 1 else ", ".join(map(str, matches))
        print(f"{dataset.upper():5} {status:9} {selected}")
        valid = status in {"OK", "N/A"}
        if dataset in required and not valid:
            missing.append(dataset)
    if missing:
        raise SystemExit("Input chưa hợp lệ: " + ", ".join(missing))


if __name__ == "__main__":
    main()
