from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def aggregate_report(path: Path, store: str) -> pd.DataFrame:
    frame = pd.read_csv(path, sep="\t", dtype=str)
    for column in ("item-price", "shipping-price", "quantity"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0)
    frame["purchase_date_pacific"] = (
        pd.to_datetime(frame["purchase-date"], errors="coerce", utc=True)
        .dt.tz_convert("America/Los_Angeles")
    )
    valid = frame[
        frame["order-status"].fillna("").str.casefold().ne("cancelled")
        & frame["currency"].eq("USD")
        & frame["purchase_date_pacific"].dt.date.between(
            pd.Timestamp("2026-07-01").date(),
            pd.Timestamp("2026-07-30").date(),
        )
    ].copy()
    valid["revenue"] = valid["item-price"] + valid["shipping-price"]
    valid["record_id_hint"] = (
        valid.get("sku", pd.Series("", index=valid.index))
        .fillna("")
        .str.extract(r"\b(rec[A-Za-z0-9]+)\b", expand=False)
        .fillna("")
    )
    result = (
        valid.groupby("asin", dropna=False)
        .agg(
            Revenue=("revenue", "sum"),
            Orders=("amazon-order-id", "nunique"),
            Units=("quantity", "sum"),
            record_id_hint=(
                "record_id_hint",
                lambda values: next((str(value) for value in values if str(value).strip()), ""),
            ),
        )
        .reset_index()
        .rename(columns={"asin": "ASIN"})
    )
    result = result[result["ASIN"].notna() & result["ASIN"].ne("")]
    result.insert(0, "Store", store)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wrappiness", type=Path, required=True)
    parser.add_argument("--pawsionate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    result = pd.concat(
        [
            aggregate_report(args.wrappiness, "Wrappiness"),
            aggregate_report(args.pawsionate, "Pawsionate"),
        ],
        ignore_index=True,
    )
    result["Revenue"] = result["Revenue"].round(2)
    result["Orders"] = result["Orders"].astype(int)
    result["Units"] = result["Units"].astype(int)
    result = result.sort_values(["Store", "Revenue"], ascending=[True, False])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, index=False, encoding="utf-8")
    print(
        {
            "rows": len(result),
            "revenue": round(float(result["Revenue"].sum()), 2),
            "orders_by_store": result.groupby("Store")["Orders"].sum().to_dict(),
            "output": str(args.output),
        }
    )


if __name__ == "__main__":
    main()
