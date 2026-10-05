from __future__ import annotations

import re

import pandas as pd

from fulfillment_rules import apply_fulfillment_overrides


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
REVENUE_MILESTONE_COLUMNS = {
    1000: "Portfolio_Records_1000_Revenue",
    3000: "Portfolio_Records_3000_Revenue",
    5000: "Portfolio_Records_5000_Revenue",
    10000: "Portfolio_Records_10000_Revenue",
    15000: "Portfolio_Records_15000_Revenue",
    20000: "Portfolio_Records_20000_Revenue",
}


def first_nonempty(series: pd.Series) -> str:
    for value in series:
        if pd.notna(value) and str(value).strip():
            return str(value).strip()
    return ""


def sku_code_from_sku(value: object) -> str:
    """Extract the leading 3–4 character product code (e.g. D19, D108)."""
    if pd.isna(value):
        return ""
    match = re.match(r"^([A-Z0-9]{3,4})(?=[^A-Z0-9]|$)", str(value).strip().upper())
    return match.group(1) if match else ""


def top_sku_code_frame(
    performance: pd.DataFrame,
    total_revenue: float,
    total_asins: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Rank actual Order rows by SKU code without multiplying Lark matches."""
    if performance.empty:
        return top_record_id_frame(pd.DataFrame(), total_revenue).rename(
            columns={"Record ID": "SKU CODE"}
        )
    frame = performance.copy()
    if "sku_code" not in frame:
        frame["sku_code"] = frame.get("sku", pd.Series("", index=frame.index)).map(sku_code_from_sku)
    frame["sku_code"] = frame["sku_code"].fillna("").map(sku_code_from_sku)
    frame = frame[frame["sku_code"].ne("")].copy()
    for column in RECORD_METADATA_COLUMNS:
        frame[column] = ""
    if total_asins is not None and not total_asins.empty:
        total = total_asins.copy()
        for column in RECORD_METADATA_COLUMNS:
            if column not in total:
                total[column] = ""
        for key, order_key in (("asin", "ASIN"), ("record_id", "record_id_hint")):
            if key not in total or order_key not in frame:
                continue
            lookup = total[total[key].fillna("").ne("")].groupby(key)[RECORD_METADATA_COLUMNS].agg(first_nonempty)
            for column in RECORD_METADATA_COLUMNS:
                values = frame[order_key].map(lookup[column]).fillna("")
                frame[column] = frame[column].where(frame[column].ne(""), values)
    def unique_values(values: pd.Series) -> str:
        return ", ".join(sorted({str(value).strip() for value in values if pd.notna(value) and str(value).strip()}))
    for column in ("Revenue", "Orders", "Units"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0)
    grouped = frame.groupby("sku_code", as_index=False).agg(
        **{column: (column, unique_values if column.endswith("_by") else first_nonempty) for column in RECORD_METADATA_COLUMNS},
        Revenue=("Revenue", "sum"), Orders=("Orders", "sum"), Units=("Units", "sum"),
        asin_count=("ASIN", "nunique"),
    ).rename(columns={"sku_code": "record_id"})
    return top_record_id_frame(grouped, total_revenue).rename(columns={"Record ID": "SKU CODE"})


def revenue_milestone_counts(
    records: pd.DataFrame,
    owner_column: str,
) -> pd.DataFrame:
    """Count unique owned Record IDs reaching monthly Revenue milestones."""
    columns = ["Nhân sự", *REVENUE_MILESTONE_COLUMNS.values()]
    required = {"record_id", owner_column, "Revenue"}
    if records.empty or not required.issubset(records.columns):
        return pd.DataFrame(columns=columns)
    frame = records[["record_id", owner_column, "Revenue"]].copy()
    frame["record_id"] = frame["record_id"].fillna("").astype(str).str.strip()
    frame[owner_column] = frame[owner_column].fillna("").astype(str).str.strip()
    frame["Revenue"] = pd.to_numeric(frame["Revenue"], errors="coerce").fillna(0)
    frame = frame[frame["record_id"].ne("") & frame[owner_column].ne("")]
    if frame.empty:
        return pd.DataFrame(columns=columns)
    frame = (
        frame.groupby([owner_column, "record_id"], as_index=False)
        .agg(Revenue=("Revenue", "sum"))
    )
    for threshold, column in REVENUE_MILESTONE_COLUMNS.items():
        frame[column] = frame["Revenue"].ge(threshold)
    summary = (
        frame.groupby(owner_column, as_index=False)
        .agg(**{
            column: (column, "sum")
            for column in REVENUE_MILESTONE_COLUMNS.values()
        })
        .rename(columns={owner_column: "Nhân sự"})
    )
    return summary[columns]


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


def order_fulfillment_frame(
    performance: pd.DataFrame,
    total_asins: pd.DataFrame,
) -> pd.DataFrame:
    """Attach TOTAL ASIN Fulfill By to each Order snapshot row."""
    columns = list(performance.columns)
    if "Fulfill By" not in columns:
        columns.append("Fulfill By")
    required_order = {"ASIN"}
    required_total = {"asin", "record_id", "fulfill_by"}
    if (
        performance.empty
        or total_asins.empty
        or not required_order.issubset(performance.columns)
        or not required_total.issubset(total_asins.columns)
    ):
        return pd.DataFrame(columns=columns)

    total = apply_fulfillment_overrides(total_asins)
    total["asin"] = total["asin"].fillna("").astype(str).str.strip().str.upper()
    total["record_id"] = total["record_id"].fillna("").astype(str).str.strip()
    total["fulfill_by"] = total["fulfill_by"].fillna("").astype(str).str.strip()
    asin_lookup = (
        total.sort_values(["asin", "record_id"])
        .groupby("asin")["fulfill_by"]
        .agg(first_nonempty)
    )
    record_lookup = (
        total.sort_values(["record_id", "asin"])
        .groupby("record_id")["fulfill_by"]
        .agg(first_nonempty)
    )

    frame = performance.copy()
    frame["ASIN"] = frame["ASIN"].fillna("").astype(str).str.strip().str.upper()
    frame["Fulfill By"] = frame["ASIN"].map(asin_lookup).fillna("")
    if "record_id_hint" in frame:
        missing = frame["Fulfill By"].eq("")
        frame.loc[missing, "Fulfill By"] = (
            frame.loc[missing, "record_id_hint"]
            .fillna("")
            .astype(str)
            .str.strip()
            .map(record_lookup)
            .fillna("")
        )
    frame["Fulfill By"] = frame["Fulfill By"].str.upper().where(
        frame["Fulfill By"].str.upper().isin(["FBA", "FBM"]),
        "Unmapped",
    )
    return frame


def fulfillment_revenue_frame(
    performance: pd.DataFrame,
    total_asins: pd.DataFrame,
) -> pd.DataFrame:
    """Split Order revenue by TOTAL ASIN Fulfill By, with Record ID fallback."""
    columns = ["Fulfill By", "Revenue", "Orders", "Units", "ASINs"]
    required_order = {"ASIN", "Revenue", "Orders", "Units"}
    if performance.empty or not required_order.issubset(performance.columns):
        return pd.DataFrame(columns=columns)
    frame = order_fulfillment_frame(performance, total_asins)
    if frame.empty:
        return pd.DataFrame(columns=columns)
    for column in ("Revenue", "Orders", "Units"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0)
    summary = (
        frame.groupby("Fulfill By", as_index=False)
        .agg(
            Revenue=("Revenue", "sum"),
            Orders=("Orders", "sum"),
            Units=("Units", "sum"),
            ASINs=("ASIN", "nunique"),
        )
    )
    return summary[columns]


def top_record_id_frame(
    records: pd.DataFrame,
    total_revenue: float,
    limit: int | None = None,
) -> pd.DataFrame:
    """Regroup sold Record IDs and return them ranked by Revenue descending."""
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
        .loc[lambda value: value["Revenue"].gt(0)]
        .sort_values(["Revenue", "record_id"], ascending=[False, True])
        .reset_index(drop=True)
    )
    if limit is not None:
        ranked = ranked.head(limit).reset_index(drop=True)
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
