from __future__ import annotations

import argparse
import hashlib
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from snapshot_store import SNAPSHOT_COLUMNS, save_snapshot


ORDER_COLUMNS = {
    "purchase-date",
    "order-status",
    "currency",
    "asin",
    "item-price",
    "shipping-price",
    "quantity",
    "amazon-order-id",
}
RECORD_PATTERN = re.compile(r"\b(rec[A-Za-z0-9]+)\b")


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS order_items (
            store TEXT NOT NULL,
            order_item_id TEXT NOT NULL,
            amazon_order_id TEXT NOT NULL,
            purchase_at_pacific TEXT NOT NULL,
            purchase_date_pacific TEXT NOT NULL,
            order_status TEXT NOT NULL,
            currency TEXT NOT NULL,
            fulfillment_channel TEXT NOT NULL,
            asin TEXT NOT NULL,
            sku TEXT NOT NULL,
            record_id_hint TEXT NOT NULL,
            quantity REAL NOT NULL,
            item_price REAL NOT NULL,
            shipping_price REAL NOT NULL,
            revenue REAL NOT NULL,
            source_file TEXT NOT NULL,
            report_scope TEXT NOT NULL,
            imported_at TEXT NOT NULL,
            PRIMARY KEY (store, order_item_id)
        );
        CREATE INDEX IF NOT EXISTS idx_order_store_date
            ON order_items (store, purchase_date_pacific);
        CREATE INDEX IF NOT EXISTS idx_order_asin
            ON order_items (asin);
        CREATE TABLE IF NOT EXISTS imports (
            import_id INTEGER PRIMARY KEY AUTOINCREMENT,
            imported_at TEXT NOT NULL,
            store TEXT NOT NULL,
            report_scope TEXT NOT NULL,
            source_file TEXT NOT NULL,
            source_sha256 TEXT NOT NULL,
            period_start TEXT NOT NULL,
            period_end TEXT NOT NULL,
            source_rows INTEGER NOT NULL,
            active_rows INTEGER NOT NULL
        );
        """
    )
    return connection


def read_report(path: Path) -> pd.DataFrame:
    separator = "\t" if path.suffix.lower() in {".txt", ".tsv"} else ","
    frame = pd.read_csv(path, sep=separator, dtype=str)
    missing = sorted(ORDER_COLUMNS.difference(frame.columns))
    if missing:
        raise ValueError(f"Report thiếu cột: {', '.join(missing)}")
    return frame


def prepare_order_rows(path: Path, store: str, scope: str) -> pd.DataFrame:
    frame = read_report(path)
    for column in ("item-price", "shipping-price", "quantity"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0)
    timestamps = pd.to_datetime(frame["purchase-date"], errors="coerce", utc=True)
    frame = frame[timestamps.notna()].copy()
    timestamps = timestamps[timestamps.notna()].dt.tz_convert("America/Los_Angeles")
    frame["purchase_at_pacific"] = timestamps.dt.strftime("%Y-%m-%dT%H:%M:%S%z")
    frame["purchase_date_pacific"] = timestamps.dt.strftime("%Y-%m-%d")
    frame["asin"] = frame["asin"].fillna("").str.upper().str.strip()
    frame["sku"] = frame.get("sku", pd.Series("", index=frame.index)).fillna("").astype(str)
    frame["record_id_hint"] = frame["sku"].str.extract(RECORD_PATTERN, expand=False).fillna("")
    frame["order-item-id"] = (
        frame.get("order-item-id", pd.Series("", index=frame.index)).fillna("").astype(str)
    )
    empty_ids = frame["order-item-id"].str.strip().eq("")
    frame.loc[empty_ids, "order-item-id"] = frame[empty_ids].apply(
        lambda row: hashlib.sha256(
            "|".join(
                [
                    str(row.get("amazon-order-id", "")),
                    str(row.get("asin", "")),
                    str(row.get("sku", "")),
                    str(row.get("purchase-date", "")),
                    str(row.name),
                ]
            ).encode("utf-8")
        ).hexdigest(),
        axis=1,
    )
    frame["Revenue"] = frame["item-price"] + frame["shipping-price"]
    frame["store"] = store
    frame["source_file"] = path.name
    frame["report_scope"] = scope
    frame["imported_at"] = datetime.now(timezone.utc).isoformat()
    result = pd.DataFrame(
        {
            "store": frame["store"],
            "order_item_id": frame["order-item-id"],
            "amazon_order_id": frame["amazon-order-id"].fillna(""),
            "purchase_at_pacific": frame["purchase_at_pacific"],
            "purchase_date_pacific": frame["purchase_date_pacific"],
            "order_status": frame["order-status"].fillna(""),
            "currency": frame["currency"].fillna(""),
            "fulfillment_channel": frame.get(
                "fulfillment-channel", pd.Series("", index=frame.index)
            ).fillna(""),
            "asin": frame["asin"],
            "sku": frame["sku"],
            "record_id_hint": frame["record_id_hint"],
            "quantity": frame["quantity"],
            "item_price": frame["item-price"],
            "shipping_price": frame["shipping-price"],
            "revenue": frame["Revenue"],
            "source_file": frame["source_file"],
            "report_scope": frame["report_scope"],
            "imported_at": frame["imported_at"],
        }
    )
    return result[result["asin"].ne("")].drop_duplicates("order_item_id", keep="last")


def ingest_order_report(
    db_path: Path,
    path: Path,
    store: str,
    scope: str,
    replace_start: str | None = None,
    replace_end: str | None = None,
) -> dict[str, object]:
    if scope not in {"daily", "weekly", "monthly"}:
        raise ValueError(f"Scope không hợp lệ: {scope}")
    if bool(replace_start) != bool(replace_end):
        raise ValueError("replace_start và replace_end phải được truyền cùng nhau.")
    if scope == "daily" and replace_start:
        raise ValueError("Khoảng thay thế chỉ dùng cho report weekly hoặc monthly.")
    rows = prepare_order_rows(path, store, scope)
    if rows.empty:
        raise ValueError("Report không có order hợp lệ để lưu.")
    period_start = str(rows["purchase_date_pacific"].min())
    period_end = str(rows["purchase_date_pacific"].max())
    replacement_start = replace_start or period_start
    replacement_end = replace_end or period_end
    if replacement_start > replacement_end:
        raise ValueError("Ngày bắt đầu khoảng thay thế phải trước hoặc bằng ngày kết thúc.")
    if replace_start and (period_start < replacement_start or period_end > replacement_end):
        raise ValueError(
            "Report có order nằm ngoài khoảng thay thế "
            f"{replacement_start} đến {replacement_end}."
        )
    imported_at = datetime.now(timezone.utc).isoformat()
    values = list(rows.itertuples(index=False, name=None))
    connection = connect(db_path)
    try:
        with connection:
            if scope in {"weekly", "monthly"}:
                connection.execute(
                    "DELETE FROM order_items WHERE store = ? AND purchase_date_pacific BETWEEN ? AND ?",
                    (store, replacement_start, replacement_end),
                )
            connection.executemany(
                """
                INSERT INTO order_items (
                    store, order_item_id, amazon_order_id, purchase_at_pacific,
                    purchase_date_pacific, order_status, currency, fulfillment_channel,
                    asin, sku, record_id_hint, quantity, item_price, shipping_price,
                    revenue, source_file, report_scope, imported_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(store, order_item_id) DO UPDATE SET
                    amazon_order_id=excluded.amazon_order_id,
                    purchase_at_pacific=excluded.purchase_at_pacific,
                    purchase_date_pacific=excluded.purchase_date_pacific,
                    order_status=excluded.order_status,
                    currency=excluded.currency,
                    fulfillment_channel=excluded.fulfillment_channel,
                    asin=excluded.asin,
                    sku=excluded.sku,
                    record_id_hint=excluded.record_id_hint,
                    quantity=excluded.quantity,
                    item_price=excluded.item_price,
                    shipping_price=excluded.shipping_price,
                    revenue=excluded.revenue,
                    source_file=excluded.source_file,
                    report_scope=excluded.report_scope,
                    imported_at=excluded.imported_at
                """,
                values,
            )
            active_rows = int(
                (~rows["order_status"].str.casefold().eq("cancelled") & rows["currency"].eq("USD")).sum()
            )
            connection.execute(
                """
                INSERT INTO imports (
                    imported_at, store, report_scope, source_file, source_sha256,
                    period_start, period_end, source_rows, active_rows
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    imported_at,
                    store,
                    scope,
                    path.name,
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                    replacement_start if scope in {"weekly", "monthly"} else period_start,
                    replacement_end if scope in {"weekly", "monthly"} else period_end,
                    len(rows),
                    active_rows,
                ),
            )
    finally:
        connection.close()
    return {
        "store": store,
        "scope": scope,
        "period": f"{period_start} to {period_end}",
        "replaced_period": (
            f"{replacement_start} to {replacement_end}"
            if scope in {"weekly", "monthly"}
            else None
        ),
        "rows": len(rows),
        "active_rows": active_rows,
    }


def export_snapshot(
    db_path: Path,
    output_path: Path,
    period_start: str,
    period_end: str,
) -> dict[str, object]:
    connection = connect(db_path)
    try:
        items = pd.read_sql_query(
            """
            SELECT store, purchase_date_pacific, asin, record_id_hint,
                   revenue, amazon_order_id, quantity, imported_at
            FROM order_items
            WHERE lower(order_status) <> 'cancelled'
              AND currency = 'USD'
              AND purchase_date_pacific BETWEEN ? AND ?
            """,
            connection,
            params=(period_start, period_end),
        )
    finally:
        connection.close()
    if items.empty:
        raise ValueError("Database chưa có order hợp lệ trong kỳ xuất snapshot.")
    source_updated_at = str(items["imported_at"].max())
    summary = (
        items.groupby(["store", "purchase_date_pacific", "asin"], as_index=False)
        .agg(
            Revenue=("revenue", "sum"),
            Orders=("amazon_order_id", "nunique"),
            Units=("quantity", "sum"),
            record_id_hint=(
                "record_id_hint",
                lambda values: next((str(value) for value in values if str(value).strip()), ""),
            ),
        )
        .rename(
            columns={
                "store": "Store",
                "purchase_date_pacific": "Date",
                "asin": "ASIN",
            }
        )
        .reindex(columns=SNAPSHOT_COLUMNS)
        .sort_values(["Store", "Date", "Revenue"], ascending=[True, True, False])
    )
    summary["Revenue"] = summary["Revenue"].round(2)
    summary["Orders"] = summary["Orders"].astype(int)
    summary["Units"] = summary["Units"].astype(int)
    save_snapshot(
        output_path,
        summary,
        source_updated_at=source_updated_at,
    )
    return {
        "rows": len(summary),
        "revenue": round(float(summary["Revenue"].sum()), 2),
        "period": f"{period_start} to {period_end}",
        "source_updated_at": source_updated_at,
        "output": str(output_path),
    }

def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Atlas local data pipeline")
    subparsers = root.add_subparsers(dest="command", required=True)
    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--db", type=Path, required=True)
    ingest_parser = subparsers.add_parser("ingest-order")
    ingest_parser.add_argument("--db", type=Path, required=True)
    ingest_parser.add_argument("--file", type=Path, required=True)
    ingest_parser.add_argument("--store", required=True, choices=["Wrappiness", "Pawsionate"])
    ingest_parser.add_argument("--scope", required=True, choices=["daily", "weekly", "monthly"])
    ingest_parser.add_argument(
        "--replace-start",
        help="Ngày Pacific đầu khoảng cần thay thế (weekly/monthly, YYYY-MM-DD)",
    )
    ingest_parser.add_argument(
        "--replace-end",
        help="Ngày Pacific cuối khoảng cần thay thế (weekly/monthly, YYYY-MM-DD)",
    )
    export_parser = subparsers.add_parser("export-snapshot")
    export_parser.add_argument("--db", type=Path, required=True)
    export_parser.add_argument("--output", type=Path, required=True)
    export_parser.add_argument("--start", required=True)
    export_parser.add_argument("--end", required=True)
    return root


def main() -> None:
    args = parser().parse_args()
    if args.command == "init":
        connect(args.db).close()
        print({"database": str(args.db), "status": "ready"})
    elif args.command == "ingest-order":
        print(
            ingest_order_report(
                args.db,
                args.file,
                args.store,
                args.scope,
                args.replace_start,
                args.replace_end,
            )
        )
    elif args.command == "export-snapshot":
        print(export_snapshot(args.db, args.output, args.start, args.end))


if __name__ == "__main__":
    main()
