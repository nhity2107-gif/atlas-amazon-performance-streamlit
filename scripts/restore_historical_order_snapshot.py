from __future__ import annotations

import argparse
from io import StringIO
from pathlib import Path
import subprocess
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from snapshot_store import load_snapshot, save_snapshot
from scripts.local_data_pipeline import export_snapshot


def historical_snapshot(revision: str, path: str = "snapshot/dashboard_snapshot.csv") -> pd.DataFrame:
    result = subprocess.run(
        ["git", "show", f"{revision}:{path}"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return pd.read_csv(StringIO(result.stdout))


def restore_snapshot(
    database: Path,
    output: Path,
    history_revision: str,
    history_through: str,
    as_of_date: str,
) -> dict[str, object]:
    temporary = output.with_suffix(output.suffix + ".database.tmp")
    try:
        database_result = export_snapshot(
            database,
            temporary,
            as_of_date=as_of_date,
        )
        database_frame = load_snapshot(temporary)
    finally:
        temporary.unlink(missing_ok=True)
        temporary.with_suffix(".metadata.json").unlink(missing_ok=True)

    history = historical_snapshot(history_revision)
    history_dates = pd.to_datetime(history["Date"], errors="coerce")
    historical_frame = history.loc[history_dates.le(pd.Timestamp(history_through))].copy()
    if historical_frame.empty:
        raise ValueError("Git revision không có dữ liệu lịch sử trong khoảng yêu cầu.")

    database_dates = pd.to_datetime(database_frame["Date"], errors="coerce")
    database_frame = database_frame.loc[
        database_dates.gt(pd.Timestamp(history_through))
    ].copy()
    combined = pd.concat([historical_frame, database_frame], ignore_index=True)
    combined_dates = pd.to_datetime(combined["Date"], errors="coerce")
    months = sorted(combined_dates.dt.strftime("%Y-%m").dropna().unique())
    if len(months) < 2:
        raise ValueError("Bản phục hồi không có đủ dữ liệu nhiều tháng.")

    save_snapshot(
        output,
        combined,
        source_updated_at=str(database_result["source_updated_at"]),
        report_as_of_date=as_of_date,
    )
    return {
        "months": months,
        "rows": len(combined),
        "date_min": combined_dates.min().date().isoformat(),
        "date_max": combined_dates.max().date().isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore historical Order months into the published snapshot.")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--history-revision", required=True)
    parser.add_argument("--history-through", required=True)
    parser.add_argument("--as-of-date", required=True)
    args = parser.parse_args()
    print(
        restore_snapshot(
            args.db,
            args.output,
            args.history_revision,
            args.history_through,
            args.as_of_date,
        )
    )


if __name__ == "__main__":
    main()
