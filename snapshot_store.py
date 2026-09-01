from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import pandas as pd


SNAPSHOT_COLUMNS = [
    "Store",
    "Date",
    "ASIN",
    "Revenue",
    "Orders",
    "Units",
    "record_id_hint",
]
SNAPSHOT_SCHEMA_VERSION = "order-snapshot-v3"


class SnapshotError(RuntimeError):
    pass


def empty_snapshot() -> pd.DataFrame:
    return pd.DataFrame(columns=SNAPSHOT_COLUMNS)


def normalize_snapshot(frame: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in SNAPSHOT_COLUMNS if column not in frame]
    if missing:
        raise SnapshotError("Snapshot thiếu cột: " + ", ".join(missing))
    normalized = frame.reindex(columns=SNAPSHOT_COLUMNS).copy()
    for column in ("Store", "Date", "ASIN", "record_id_hint"):
        normalized[column] = normalized[column].fillna("").astype(str)
    for column in ("Revenue", "Orders", "Units"):
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce").fillna(0)
    return normalized


def load_snapshot(path: Path) -> pd.DataFrame:
    if not path.exists():
        return empty_snapshot()
    try:
        frame = pd.read_csv(
            path,
            dtype={"Store": str, "Date": str, "ASIN": str, "record_id_hint": str},
        )
    except (OSError, pd.errors.ParserError, UnicodeDecodeError) as exc:
        raise SnapshotError("Không thể đọc snapshot Order.") from exc
    return normalize_snapshot(frame)


def metadata_path(path: Path) -> Path:
    return path.with_suffix(".metadata.json")


def load_snapshot_metadata(path: Path) -> dict[str, Any]:
    sidecar = metadata_path(path)
    if not sidecar.exists():
        if not path.exists():
            return {}
        return {
            "schema_version": "legacy",
            "updated_at": datetime.fromtimestamp(
                path.stat().st_mtime, tz=timezone.utc
            ).isoformat(),
        }
    try:
        return json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SnapshotError("Không thể đọc metadata snapshot Order.") from exc


def save_snapshot(
    path: Path,
    frame: pd.DataFrame,
    *,
    source_updated_at: str | None = None,
    report_as_of_date: str | None = None,
) -> None:
    normalized = normalize_snapshot(frame)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    normalized.to_csv(temporary_path, index=False, encoding="utf-8")
    temporary_path.replace(path)
    dates = pd.to_datetime(normalized["Date"], errors="coerce").dropna()
    metadata = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source_updated_at": source_updated_at or "",
        "report_as_of_date": report_as_of_date or "",
        "timezone": "America/Los_Angeles",
        "date_min": dates.min().date().isoformat() if not dates.empty else "",
        "date_max": dates.max().date().isoformat() if not dates.empty else "",
        "rows": len(normalized),
    }
    sidecar = metadata_path(path)
    temporary_metadata = sidecar.with_suffix(sidecar.suffix + ".tmp")
    temporary_metadata.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary_metadata.replace(sidecar)


def upsert_snapshot_period(
    path: Path,
    frame: pd.DataFrame,
    period_start: str,
    period_end: str,
    *,
    source_updated_at: str | None = None,
    report_as_of_date: str | None = None,
) -> None:
    """Replace one reporting period while preserving every other saved month."""
    incoming = normalize_snapshot(frame)
    existing = load_snapshot(path)
    if existing.empty:
        combined = incoming
    else:
        existing_dates = pd.to_datetime(existing["Date"], errors="coerce")
        start = pd.Timestamp(period_start)
        end = pd.Timestamp(period_end)
        keep = existing_dates.isna() | existing_dates.lt(start) | existing_dates.gt(end)
        combined = pd.concat([existing.loc[keep], incoming], ignore_index=True)
    combined = combined.sort_values(
        ["Store", "Date", "Revenue"], ascending=[True, True, False], kind="stable"
    )
    save_snapshot(
        path,
        combined,
        source_updated_at=source_updated_at,
        report_as_of_date=report_as_of_date,
    )
