from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timezone
import json
from pathlib import Path
from typing import Any

import pandas as pd


TARGET_SHEET = "Revenue Forecast Q1&2 - 2026"
TARGET_SOURCE_COLUMN = "2026 Forecast Rev Monthly"
TARGET_COLUMNS = ["Month", "Target Revenue"]
TARGET_SCHEMA_VERSION = "fbm-target-v1"


class TargetError(RuntimeError):
    pass


def empty_fbm_target() -> pd.DataFrame:
    return pd.DataFrame(columns=TARGET_COLUMNS)


def normalize_fbm_target(frame: pd.DataFrame, *, year: int = 2026) -> pd.DataFrame:
    missing = [column for column in ("Month", TARGET_SOURCE_COLUMN) if column not in frame]
    if missing:
        raise TargetError("Sheet target thiếu cột: " + ", ".join(missing))

    normalized = frame[["Month", TARGET_SOURCE_COLUMN]].copy()
    normalized["Month Number"] = pd.to_numeric(normalized["Month"], errors="coerce")
    normalized["Target Revenue"] = pd.to_numeric(
        normalized[TARGET_SOURCE_COLUMN], errors="coerce"
    )
    normalized = normalized[
        normalized["Month Number"].between(1, 12)
        & normalized["Target Revenue"].notna()
        & normalized["Target Revenue"].ge(0)
    ].copy()
    if normalized.empty:
        raise TargetError("Không tìm thấy target tháng hợp lệ trong sheet đã chọn.")

    normalized["Month Number"] = normalized["Month Number"].astype(int)
    if normalized["Month Number"].duplicated().any():
        duplicated = sorted(
            normalized.loc[normalized["Month Number"].duplicated(False), "Month Number"]
            .astype(int)
            .unique()
        )
        raise TargetError(
            "Target bị trùng tháng: " + ", ".join(f"{month:02d}/{year}" for month in duplicated)
        )

    normalized["Month"] = normalized["Month Number"].map(
        lambda month: f"{year}-{month:02d}"
    )
    return (
        normalized[TARGET_COLUMNS]
        .sort_values("Month", kind="stable")
        .reset_index(drop=True)
    )


def read_fbm_target_workbook(path: Path, *, year: int = 2026) -> pd.DataFrame:
    try:
        source = pd.read_excel(path, sheet_name=TARGET_SHEET)
    except ValueError as exc:
        raise TargetError(f"Không tìm thấy sheet `{TARGET_SHEET}`.") from exc
    except (OSError, ImportError) as exc:
        raise TargetError("Không thể đọc file target FBM.") from exc
    return normalize_fbm_target(source, year=year)


def target_metadata_path(path: Path) -> Path:
    return path.with_suffix(".metadata.json")


def save_fbm_target_snapshot(
    path: Path,
    frame: pd.DataFrame,
    *,
    source_name: str = "",
) -> None:
    missing = [column for column in TARGET_COLUMNS if column not in frame]
    if missing:
        raise TargetError("Snapshot target thiếu cột: " + ", ".join(missing))
    normalized = frame[TARGET_COLUMNS].copy()
    normalized["Month"] = normalized["Month"].fillna("").astype(str)
    normalized["Target Revenue"] = pd.to_numeric(
        normalized["Target Revenue"], errors="coerce"
    )
    if normalized["Target Revenue"].isna().any():
        raise TargetError("Snapshot target có giá trị Revenue không hợp lệ.")

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    normalized.to_csv(temporary, index=False, encoding="utf-8")
    temporary.replace(path)

    metadata = {
        "schema_version": TARGET_SCHEMA_VERSION,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source_name": source_name,
        "source_sheet": TARGET_SHEET,
        "source_column": TARGET_SOURCE_COLUMN,
        "scope": "All Stores · FBM",
        "rows": len(normalized),
    }
    sidecar = target_metadata_path(path)
    temporary_metadata = sidecar.with_suffix(sidecar.suffix + ".tmp")
    temporary_metadata.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary_metadata.replace(sidecar)


def load_fbm_target_snapshot(path: Path) -> pd.DataFrame:
    if not path.exists():
        return empty_fbm_target()
    try:
        frame = pd.read_csv(path, dtype={"Month": str})
    except (OSError, pd.errors.ParserError, UnicodeDecodeError) as exc:
        raise TargetError("Không thể đọc snapshot target FBM.") from exc
    missing = [column for column in TARGET_COLUMNS if column not in frame]
    if missing:
        raise TargetError("Snapshot target thiếu cột: " + ", ".join(missing))
    frame = frame[TARGET_COLUMNS].copy()
    frame["Target Revenue"] = pd.to_numeric(frame["Target Revenue"], errors="coerce")
    return frame.dropna(subset=["Target Revenue"]).reset_index(drop=True)


def load_fbm_target_metadata(path: Path) -> dict[str, Any]:
    sidecar = target_metadata_path(path)
    if not sidecar.exists():
        return {}
    try:
        return json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise TargetError("Không thể đọc metadata target FBM.") from exc


def target_for_month(frame: pd.DataFrame, month: str) -> float | None:
    if frame.empty or not set(TARGET_COLUMNS).issubset(frame.columns):
        return None
    selected = frame.loc[frame["Month"].astype(str).eq(month), "Target Revenue"]
    if selected.empty:
        return None
    value = pd.to_numeric(selected.iloc[0], errors="coerce")
    return None if pd.isna(value) else float(value)


def target_progress(
    month: str,
    monthly_target: float,
    actual: float,
    as_of_date: date | pd.Timestamp | str,
) -> dict[str, float | int]:
    month_start = pd.Timestamp(f"{month}-01")
    as_of = pd.Timestamp(as_of_date).normalize()
    days_in_month = monthrange(month_start.year, month_start.month)[1]
    month_end = month_start + pd.offsets.MonthEnd(1)
    if as_of < month_start:
        elapsed_days = 0
    elif as_of > month_end:
        elapsed_days = days_in_month
    else:
        elapsed_days = int(as_of.day)

    monthly_target = float(monthly_target)
    daily_target = monthly_target / days_in_month if days_in_month else 0.0
    target_mtd = daily_target * elapsed_days
    actual = float(actual)
    return {
        "days_in_month": days_in_month,
        "elapsed_days": elapsed_days,
        "daily_target": daily_target,
        "target_mtd": target_mtd,
        "achievement": actual / target_mtd if target_mtd else 0.0,
        "gap": actual - target_mtd,
        "monthly_target": monthly_target,
    }
