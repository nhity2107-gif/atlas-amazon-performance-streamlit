from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path
from typing import Any

import pandas as pd
from cryptography.fernet import Fernet, InvalidToken


SNAPSHOT_COLUMNS = [
    "Store",
    "ASIN",
    "Revenue",
    "Orders",
    "Units",
    "record_id_hint",
]


class SnapshotError(RuntimeError):
    pass


def empty_snapshot() -> pd.DataFrame:
    return pd.DataFrame(columns=SNAPSHOT_COLUMNS)


def build_snapshot_envelope(
    frame: pd.DataFrame,
    *,
    period_start: str,
    period_end: str,
    generated_at: str,
) -> bytes:
    normalized = frame.reindex(columns=SNAPSHOT_COLUMNS).copy()
    csv_bytes = normalized.to_csv(index=False).encode("utf-8")
    envelope = {
        "schema_version": 1,
        "generated_at": generated_at,
        "period_start": period_start,
        "period_end": period_end,
        "row_count": len(normalized),
        "sha256": hashlib.sha256(csv_bytes).hexdigest(),
        "payload": base64.b64encode(csv_bytes).decode("ascii"),
    }
    return json.dumps(envelope, separators=(",", ":")).encode("utf-8")


def encrypt_snapshot(envelope: bytes, key: str | bytes) -> bytes:
    key_bytes = key.encode("ascii") if isinstance(key, str) else key
    try:
        return Fernet(key_bytes).encrypt(envelope)
    except (TypeError, ValueError) as exc:
        raise SnapshotError("DASHBOARD_DATA_KEY không hợp lệ.") from exc


def decrypt_snapshot_bytes(token: bytes, key: str | bytes) -> tuple[pd.DataFrame, dict[str, Any]]:
    key_bytes = key.encode("ascii") if isinstance(key, str) else key
    try:
        envelope_bytes = Fernet(key_bytes).decrypt(token)
    except (InvalidToken, TypeError, ValueError) as exc:
        raise SnapshotError("Không thể giải mã snapshot. Kiểm tra DASHBOARD_DATA_KEY.") from exc
    try:
        envelope = json.loads(envelope_bytes)
        csv_bytes = base64.b64decode(envelope["payload"], validate=True)
    except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise SnapshotError("Snapshot không đúng định dạng.") from exc
    if hashlib.sha256(csv_bytes).hexdigest() != envelope.get("sha256"):
        raise SnapshotError("Snapshot không vượt qua kiểm tra toàn vẹn.")
    frame = pd.read_csv(io.BytesIO(csv_bytes), dtype={"Store": str, "ASIN": str, "record_id_hint": str})
    for column in SNAPSHOT_COLUMNS:
        if column not in frame:
            frame[column] = "" if column in {"Store", "ASIN", "record_id_hint"} else 0
    frame["record_id_hint"] = frame["record_id_hint"].fillna("")
    for column in ("Revenue", "Orders", "Units"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0)
    metadata = {key: value for key, value in envelope.items() if key != "payload"}
    return frame[SNAPSHOT_COLUMNS], metadata


def load_encrypted_snapshot(path: Path, key: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    if not path.exists() or not key:
        return empty_snapshot(), {}
    return decrypt_snapshot_bytes(path.read_bytes(), key)
