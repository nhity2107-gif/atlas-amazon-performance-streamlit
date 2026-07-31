from __future__ import annotations

from dataclasses import dataclass
import re
import time
import unicodedata
from typing import Any, Iterable

import pandas as pd
import requests


ASIN_PATTERN = re.compile(r"\bB0[A-Z0-9]{8}\b", re.IGNORECASE)
RECORD_ID_PATTERN = re.compile(r"\brecu[A-Za-z0-9]+\b", re.IGNORECASE)

LAUNCHED_ADS_STATUSES = {
    "launched",
    "soft test",
    "main test",
    "scale 1",
    "scale 2",
    "scale 3",
    "scale 123",
    "fail testing",
    "paused",
    "rewind ads",
    "maintain",
}

TOTAL_ASIN_ALIASES = {
    "record_id": ["Record ID", "RecordID", "Product Record ID"],
    "asin": ["ASIN", "ASINs", "Amazon ASIN"],
    "managed_by": ["Managed By", "Manage By", "Listing By"],
    "custom_by": ["Custom By", "PS By", "Product Support"],
    "ads_by": ["Ads By", "Ads Executive"],
    "ads_status": ["Ads Status", "Advertising Status"],
    "date_pickup": ["Date Pickup", "Pickup Date"],
    "listing_done_date": ["Listing Done Date", "Listing Done"],
    "ps_pickup_date": ["PS Pick Up Date", "PS Pickup Date"],
    "custom_done_date": ["Custom Done Date", "Custom Done"],
    "custom_check_done_date": ["Custom Check Done Date", "Custom Check Done"],
    "testing_start_date": ["Testing Start Date", "Testing Start"],
}

IDEA_ALIASES = {
    "record_id": ["Record ID", "RecordID", "Product Record ID"],
    "idea_by": ["Idea By", "Created By", "Owner"],
    "handover_date": [
        "Idea Handover Date",
        "Handover Date",
        "Qualified Date",
        "Idea Done Date",
        "Date Pickup",
    ],
}

CLIPART_ALIASES = {
    "employee": [
        "Created By",
        "Create By",
        "Creator",
        "Nhân sự",
        "Tên nhân sự",
        "Custom By",
    ],
    "asset_type": ["Asset Type", "Loại Asset", "Type", "Update Type"],
    "created_date": ["Created Time", "Create Time", "Created Date", "Date", "Ngày tạo"],
}


def normalize_label(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def find_field_name(field_names: Iterable[str], aliases: Iterable[str]) -> str | None:
    normalized = {normalize_label(name): name for name in field_names}
    for alias in aliases:
        match = normalized.get(normalize_label(alias))
        if match:
            return match
    for alias in aliases:
        target = normalize_label(alias)
        for normalized_name, original in normalized.items():
            if target and (target in normalized_name or normalized_name in target):
                return original
    return None


def text_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (int, float)):
        return [str(value)]
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(text_values(item))
        return result
    if isinstance(value, dict):
        for key in ("name", "en_name", "text", "value", "email"):
            if value.get(key):
                return text_values(value[key])
        result = []
        for item in value.values():
            result.extend(text_values(item))
        return result
    return [str(value)]


def display_value(value: Any) -> str:
    seen: list[str] = []
    for text in text_values(value):
        if text and text not in seen:
            seen.append(text)
    return " / ".join(seen)


def identifiers(value: Any, pattern: re.Pattern[str]) -> list[str]:
    found: list[str] = []
    for text in text_values(value):
        for match in pattern.findall(text):
            normalized = match.upper() if pattern is ASIN_PATTERN else match
            if normalized not in found:
                found.append(normalized)
    return found


def lark_datetime(value: Any) -> pd.Timestamp | pd.NaT:
    values = text_values(value)
    if not values:
        return pd.NaT
    raw = values[0]
    try:
        number = float(raw)
        unit = "ms" if abs(number) > 10_000_000_000 else "s"
        parsed = pd.to_datetime(number, unit=unit, utc=True)
    except (TypeError, ValueError, OverflowError):
        parsed = pd.to_datetime(raw, errors="coerce", utc=True)
    if pd.isna(parsed):
        return pd.NaT
    return parsed.tz_convert("America/Los_Angeles").tz_localize(None)


def normalize_ads_status(value: Any) -> str:
    status = normalize_label(display_value(value))
    if status.startswith("scale ") and any(number in status for number in ("1", "2", "3")):
        return status
    return status


def is_launched_status(value: Any) -> bool:
    status = normalize_ads_status(value)
    if status in LAUNCHED_ADS_STATUSES:
        return True
    return status.startswith("scale ") or any(
        marker in status
        for marker in ("launched", "soft test", "main test", "fail testing", "rewind ads", "maintain")
    )


def asset_points(asset_type: Any) -> int:
    value = normalize_label(display_value(asset_type))
    if not value:
        return 0
    if "partial" in value:
        return 5
    if "full" in value:
        return 10
    if "new" in value and ("1 layer" in value or "one layer" in value):
        return 5
    if "new" in value and ("multi" in value or "multi layer" in value):
        return 10
    return 0


@dataclass(frozen=True)
class LarkConfig:
    app_id: str
    app_secret: str
    base_token: str
    total_asin_table_id: str
    mrnd_idea_table_id: str
    cliparts_table_id: str


class LarkAPIError(RuntimeError):
    pass


class LarkClient:
    def __init__(self, app_id: str, app_secret: str, timeout: int = 30):
        self.app_id = app_id
        self.app_secret = app_secret
        self.timeout = timeout
        self.session = requests.Session()
        self._tenant_token: str | None = None

    def tenant_token(self) -> str:
        if self._tenant_token:
            return self._tenant_token
        response = self.session.post(
            "https://open.larksuite.com/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 0 or not payload.get("tenant_access_token"):
            raise LarkAPIError(payload.get("msg") or "Unable to obtain Lark tenant token")
        self._tenant_token = payload["tenant_access_token"]
        return self._tenant_token

    def list_records(self, base_token: str, table_id: str) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            params: dict[str, Any] = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
            response = self.session.get(
                f"https://open.larksuite.com/open-apis/bitable/v1/apps/{base_token}/tables/{table_id}/records",
                headers={"Authorization": f"Bearer {self.tenant_token()}"},
                params=params,
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("code") != 0:
                raise LarkAPIError(payload.get("msg") or f"Unable to read Lark table {table_id}")
            data = payload.get("data") or {}
            records.extend(data.get("items") or [])
            if not data.get("has_more"):
                break
            page_token = data.get("page_token")
            if not page_token:
                break
        return records

    def list_field_names(self, base_token: str, table_id: str) -> list[str]:
        names: list[str] = []
        page_token: str | None = None
        while True:
            params: dict[str, Any] = {"page_size": 100}
            if page_token:
                params["page_token"] = page_token
            response = self.session.get(
                f"https://open.larksuite.com/open-apis/bitable/v1/apps/{base_token}/tables/{table_id}/fields",
                headers={"Authorization": f"Bearer {self.tenant_token()}"},
                params=params,
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("code") != 0:
                raise LarkAPIError(payload.get("msg") or f"Unable to read fields for {table_id}")
            data = payload.get("data") or {}
            for field in data.get("items") or []:
                name = field.get("field_name")
                if name and name not in names:
                    names.append(name)
            if not data.get("has_more"):
                break
            page_token = data.get("page_token")
            if not page_token:
                break
        return names

    def search_records(
        self,
        base_token: str,
        table_id: str,
        field_names: Iterable[str],
    ) -> list[dict[str, Any]]:
        """Read only KPI columns, avoiding expensive unrelated formula fields."""
        selected_fields = list(dict.fromkeys(name for name in field_names if name))
        records: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            params: dict[str, Any] = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
            response = None
            for attempt in range(3):
                response = self.session.post(
                    f"https://open.larksuite.com/open-apis/bitable/v1/apps/{base_token}/tables/{table_id}/records/search",
                    headers={"Authorization": f"Bearer {self.tenant_token()}"},
                    params=params,
                    json={"field_names": selected_fields, "automatic_fields": False},
                    timeout=self.timeout,
                )
                if response.status_code not in {429, 502, 503, 504}:
                    break
                time.sleep(1.5 * (attempt + 1))
            assert response is not None
            response.raise_for_status()
            payload = response.json()
            if payload.get("code") != 0:
                raise LarkAPIError(payload.get("msg") or f"Unable to search Lark table {table_id}")
            data = payload.get("data") or {}
            records.extend(data.get("items") or [])
            if not data.get("has_more"):
                break
            page_token = data.get("page_token")
            if not page_token:
                break
        return records


def resolve_fields(records: list[dict[str, Any]], aliases: dict[str, list[str]]) -> dict[str, str | None]:
    names: list[str] = []
    for record in records[:100]:
        for name in (record.get("fields") or {}):
            if name not in names:
                names.append(name)
    return {key: find_field_name(names, candidates) for key, candidates in aliases.items()}


def resolve_field_names(
    field_names: Iterable[str],
    aliases: dict[str, list[str]],
) -> dict[str, str | None]:
    return {key: find_field_name(field_names, candidates) for key, candidates in aliases.items()}


def total_asin_frame(records: list[dict[str, Any]]) -> tuple[pd.DataFrame, dict[str, str | None]]:
    mapping = resolve_fields(records, TOTAL_ASIN_ALIASES)
    rows: list[dict[str, Any]] = []
    for record in records:
        fields = record.get("fields") or {}
        record_ids = identifiers(fields.get(mapping["record_id"]), RECORD_ID_PATTERN) if mapping["record_id"] else []
        asins = identifiers(fields.get(mapping["asin"]), ASIN_PATTERN) if mapping["asin"] else []
        for record_id in record_ids:
            for asin in asins:
                row: dict[str, Any] = {"record_id": record_id, "asin": asin}
                for owner in ("managed_by", "custom_by", "ads_by", "ads_status"):
                    row[owner] = display_value(fields.get(mapping[owner])) if mapping[owner] else ""
                for date_name in (
                    "date_pickup",
                    "listing_done_date",
                    "ps_pickup_date",
                    "custom_done_date",
                    "custom_check_done_date",
                    "testing_start_date",
                ):
                    row[date_name] = lark_datetime(fields.get(mapping[date_name])) if mapping[date_name] else pd.NaT
                row["ads_launched"] = is_launched_status(row["ads_status"])
                rows.append(row)
    columns = [
        "record_id",
        "asin",
        "managed_by",
        "custom_by",
        "ads_by",
        "ads_status",
        "date_pickup",
        "listing_done_date",
        "ps_pickup_date",
        "custom_done_date",
        "custom_check_done_date",
        "testing_start_date",
        "ads_launched",
    ]
    return pd.DataFrame(rows, columns=columns), mapping


def idea_frame(records: list[dict[str, Any]]) -> tuple[pd.DataFrame, dict[str, str | None]]:
    mapping = resolve_fields(records, IDEA_ALIASES)
    rows: list[dict[str, Any]] = []
    for record in records:
        fields = record.get("fields") or {}
        record_ids = identifiers(fields.get(mapping["record_id"]), RECORD_ID_PATTERN) if mapping["record_id"] else []
        for record_id in record_ids:
            rows.append(
                {
                    "record_id": record_id,
                    "idea_by": display_value(fields.get(mapping["idea_by"])) if mapping["idea_by"] else "",
                    "handover_date": lark_datetime(fields.get(mapping["handover_date"])) if mapping["handover_date"] else pd.NaT,
                }
            )
    return pd.DataFrame(
        rows,
        columns=["record_id", "idea_by", "handover_date"],
    ), mapping


def clipart_frame(records: list[dict[str, Any]]) -> tuple[pd.DataFrame, dict[str, str | None]]:
    mapping = resolve_fields(records, CLIPART_ALIASES)
    rows: list[dict[str, Any]] = []
    for record in records:
        fields = record.get("fields") or {}
        asset_type = fields.get(mapping["asset_type"]) if mapping["asset_type"] else None
        rows.append(
            {
                "employee": display_value(fields.get(mapping["employee"])) if mapping["employee"] else "",
                "asset_type": display_value(asset_type),
                "created_date": lark_datetime(fields.get(mapping["created_date"])) if mapping["created_date"] else pd.NaT,
                "asset_points": asset_points(asset_type),
            }
        )
    return pd.DataFrame(
        rows,
        columns=["employee", "asset_type", "created_date", "asset_points"],
    ), mapping


def fetch_lark_frames(config: LarkConfig) -> dict[str, Any]:
    client = LarkClient(config.app_id, config.app_secret)
    table_specs = {
        "total": (config.total_asin_table_id, TOTAL_ASIN_ALIASES),
        "ideas": (config.mrnd_idea_table_id, IDEA_ALIASES),
        "cliparts": (config.cliparts_table_id, CLIPART_ALIASES),
    }
    records_by_table: dict[str, list[dict[str, Any]]] = {}
    for key, (table_id, aliases) in table_specs.items():
        field_names = client.list_field_names(config.base_token, table_id)
        mapping = resolve_field_names(field_names, aliases)
        selected_fields = [name for name in mapping.values() if name]
        if not selected_fields:
            raise LarkAPIError(f"No KPI fields found in Lark table {table_id}")
        records_by_table[key] = client.search_records(
            config.base_token,
            table_id,
            selected_fields,
        )

    total_records = records_by_table["total"]
    idea_records = records_by_table["ideas"]
    clipart_records = records_by_table["cliparts"]
    total, total_mapping = total_asin_frame(total_records)
    ideas, idea_mapping = idea_frame(idea_records)
    cliparts, clipart_mapping = clipart_frame(clipart_records)
    return {
        "total": total,
        "ideas": ideas,
        "cliparts": cliparts,
        "record_counts": {
            "TOTAL ASIN": len(total_records),
            "MRND IDEA": len(idea_records),
            "CLIPARTS": len(clipart_records),
        },
        "field_mapping": {
            "TOTAL ASIN": total_mapping,
            "MRND IDEA": idea_mapping,
            "CLIPARTS": clipart_mapping,
        },
    }
