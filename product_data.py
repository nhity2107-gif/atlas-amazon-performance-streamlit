from __future__ import annotations

import pandas as pd


RECORD_METADATA_COLUMNS = [
    "idea_by",
    "managed_by",
    "custom_by",
    "ads_by",
    "product_name",
    "image_url",
    "image_token",
    "image_record_id",
    "image_field_id",
]


def first_nonempty(series: pd.Series) -> str:
    for value in series:
        if pd.notna(value) and str(value).strip():
            return str(value).strip()
    return ""


def records_from_order_hints(performance: pd.DataFrame) -> pd.DataFrame:
    """Build Record ID totals from SKU hints when Lark is unavailable."""
    frame = performance.copy()
    if "record_id_hint" not in frame:
        return pd.DataFrame()
    frame["record_id"] = frame["record_id_hint"].fillna("").astype(str).str.strip()
    frame = frame[frame["record_id"].ne("")]
    if frame.empty:
        return pd.DataFrame()
    records = (
        frame.groupby("record_id", as_index=False)
        .agg(
            Revenue=("Revenue", "sum"),
            Orders=("Orders", "sum"),
            Units=("Units", "sum"),
            asin_count=("ASIN", "nunique"),
        )
    )
    for column in RECORD_METADATA_COLUMNS:
        records[column] = ""
    return records


def top_record_id_frame(
    records: pd.DataFrame,
    total_revenue: float,
    limit: int = 50,
) -> pd.DataFrame:
    """Regroup revenue by Record ID and return the ranked display frame."""
    columns = [
        "#",
        "Image",
        "Record ID",
        "Product",
        "Idea By",
        "Managed By",
        "Custom By",
        "Ads By",
        "ASIN count",
        "Revenue",
        "Orders",
        "Units",
        "Share",
        "image_token",
        "image_record_id",
        "image_field_id",
    ]
    if records.empty:
        return pd.DataFrame(columns=columns)

    frame = records.copy()
    for column in RECORD_METADATA_COLUMNS:
        if column not in frame:
            frame[column] = ""
    for column in ("Revenue", "Orders", "Units", "asin_count"):
        if column not in frame:
            frame[column] = 0
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0)
    frame["record_id"] = frame["record_id"].fillna("").astype(str).str.strip()
    frame = frame[frame["record_id"].ne("")]
    if frame.empty:
        return pd.DataFrame(columns=columns)

    aggregation = {
        **{column: first_nonempty for column in RECORD_METADATA_COLUMNS},
        "Revenue": "sum",
        "Orders": "sum",
        "Units": "sum",
        "asin_count": "sum",
    }
    ranked = (
        frame.groupby("record_id", as_index=False)
        .agg(aggregation)
        .sort_values(["Revenue", "record_id"], ascending=[False, True])
        .head(limit)
        .reset_index(drop=True)
    )
    for owner_column in ("idea_by", "managed_by", "custom_by", "ads_by"):
        ranked[owner_column] = ranked[owner_column].fillna("")
    ranked["Share"] = ranked["Revenue"].div(total_revenue or 1).mul(100)
    ranked.insert(0, "#", range(1, len(ranked) + 1))
    return ranked.rename(
        columns={
            "record_id": "Record ID",
            "product_name": "Product",
            "idea_by": "Idea By",
            "managed_by": "Managed By",
            "custom_by": "Custom By",
            "ads_by": "Ads By",
            "image_url": "Image",
            "asin_count": "ASIN count",
        }
    )[columns]
