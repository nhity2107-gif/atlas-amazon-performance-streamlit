from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import pandas as pd


SCHEMA_VERSION = "lark-snapshot-v2"
FRAME_NAMES = ("total", "workflow", "workflow_ideas", "ideas", "cliparts")
DATE_COLUMNS = {
    "total": (
        "date_pickup",
        "listing_done_date",
        "ps_pickup_date",
        "custom_done_date",
        "custom_check_done_date",
        "testing_start_date",
    ),
    "ideas": ("handover_date",),
    "workflow": (
        "listing_done_date",
        "custom_check_done_date",
        "testing_start_date",
    ),
    "workflow_ideas": ("handover_date",),
    "cliparts": ("created_date",),
}


class LarkSnapshotError(RuntimeError):
    pass


def snapshot_version(root: Path) -> int:
    metadata_path = root / "metadata.json"
    return metadata_path.stat().st_mtime_ns if metadata_path.exists() else 0


def save_lark_snapshot(root: Path, payload: dict[str, Any]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for name in FRAME_NAMES:
        frame = payload.get(name)
        if not isinstance(frame, pd.DataFrame):
            raise LarkSnapshotError(f"Snapshot Lark thiếu DataFrame: {name}")
        temporary = root / f"{name}.csv.tmp"
        frame.to_csv(temporary, index=False, encoding="utf-8")
        temporary.replace(root / f"{name}.csv")

    metadata = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "date_semantics": "lark_calendar_date_no_timezone_conversion",
        "frames": list(FRAME_NAMES),
        "record_counts": payload.get("record_counts", {}),
        "field_mapping": payload.get("field_mapping", {}),
        "available_fields": payload.get("available_fields", {}),
    }
    temporary_metadata = root / "metadata.json.tmp"
    temporary_metadata.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary_metadata.replace(root / "metadata.json")


def load_lark_snapshot(root: Path) -> dict[str, Any] | None:
    metadata_path = root / "metadata.json"
    if not metadata_path.exists():
        return None
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("schema_version") != SCHEMA_VERSION:
            return None
        frames: dict[str, pd.DataFrame] = {}
        for name in FRAME_NAMES:
            path = root / f"{name}.csv"
            if not path.exists():
                return None
            frame = pd.read_csv(path, dtype=str, keep_default_na=False)
            for column in DATE_COLUMNS[name]:
                if column in frame:
                    frame[column] = pd.to_datetime(frame[column], errors="coerce")
            frames[name] = frame
        total = frames["total"]
        for frame_name in ("total", "workflow"):
            for column in ("listing_lead_time", "custom_lead_time"):
                if column in frames[frame_name]:
                    frames[frame_name][column] = pd.to_numeric(
                        frames[frame_name][column], errors="coerce"
                    )
        if "ads_launched" in total:
            total["ads_launched"] = total["ads_launched"].astype(str).str.casefold().eq("true")
        if "asset_points" in frames["cliparts"]:
            frames["cliparts"]["asset_points"] = pd.to_numeric(
                frames["cliparts"]["asset_points"], errors="coerce"
            ).fillna(0)
        return {
            **frames,
            "record_counts": metadata.get("record_counts", {}),
            "field_mapping": metadata.get("field_mapping", {}),
            "available_fields": metadata.get("available_fields", {}),
            "snapshot_updated_at": metadata.get("updated_at", ""),
            "snapshot_date_semantics": metadata.get("date_semantics", ""),
            "snapshot_frames": metadata.get("frames", []),
        }
    except (OSError, ValueError, json.JSONDecodeError, pd.errors.ParserError) as exc:
        raise LarkSnapshotError("Không thể đọc snapshot Lark đã lưu.") from exc
