from __future__ import annotations

from datetime import datetime, timezone
from io import StringIO
import json
from pathlib import Path
import re
from typing import Any, Iterable
import unicodedata

import pandas as pd
from cryptography.fernet import Fernet, InvalidToken

from fulfillment_rules import apply_fulfillment_overrides


ASIN_PATTERN = re.compile(r"(?i)(?<![A-Z0-9])(B0[A-Z0-9]{8})(?![A-Z0-9])")
PRODUCT_ASIN_PATTERN = re.compile(r"(?i)^\s*(B0[A-Z0-9]{8})(?:-|$)")
SUPPORT_PATTERN = re.compile(r"(?i)support")
EXECUTION_PATTERNS = {
    "Linh": re.compile(r"(?i)LINH(?:\s*(?:AMZ|MRND))?"),
    "Hieu": re.compile(r"(?i)HIEU(?:\s*(?:AMZ|MRND))?"),
    "Ha": re.compile(
        r"(?i)(?:^|[^A-Z0-9])HA(?:\s*(?:AMZ|MRND))?(?:[^A-Z0-9]|$)"
    ),
}
SUMMARY_COLUMNS = [
    "Nhân sự",
    "ASINs",
    "Ads_Spend",
    "Ads_Sales",
    "Ads_Orders",
    "ACOS",
]
FBM_METRIC_COLUMNS = [
    "FBM_ASINs",
    "FBM_Ads_Spend",
    "FBM_Ads_Sales",
    "FBM_Ads_Orders",
]
STANDARD_REPORT_COLUMNS = [
    "ASIN",
    "Campaign name",
    "Ads Type",
    "ad_spend",
    "ad_sales",
    "ad_orders",
    "impressions",
    "clicks",
]
SNAPSHOT_DIMENSIONS = ["Month", "Store"]
SCHEMA_VERSION = "ads-snapshot-v2"
ENCRYPTED_SCHEMA_VERSION = "encrypted-ads-snapshot-v1"


class AdsDataError(RuntimeError):
    pass


def numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str).str.replace(r"[$,%]", "", regex=True),
        errors="coerce",
    ).fillna(0)


def normalize_person(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def read_advertised_products(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    required = {"Products", "Sales(USD)", "Spend(USD)", "Orders"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise AdsDataError("Advertised Product report thiếu cột: " + ", ".join(missing))
    frame["ASIN"] = (
        frame["Products"].str.extract(PRODUCT_ASIN_PATTERN, expand=False).fillna("").str.upper()
    )
    if frame["ASIN"].eq("").any():
        raise AdsDataError("Advertised Product report có dòng không trích được ASIN.")
    if frame["ASIN"].duplicated().any():
        raise AdsDataError("Advertised Product report có ASIN trùng; cần gộp nguồn trước.")
    return pd.DataFrame(
        {
            "ASIN": frame["ASIN"],
            "product_spend": numeric(frame["Spend(USD)"].rename("Spend")),
            "product_sales": numeric(frame["Sales(USD)"].rename("Sales")),
            "product_orders": numeric(frame["Orders"]),
        }
    )


def read_support_campaigns(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    required = {"Campaign name", "Total cost", "Sales", "Purchases"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise AdsDataError("Support Campaign report thiếu cột: " + ", ".join(missing))
    extracted = frame["Campaign name"].str.findall(ASIN_PATTERN)
    if extracted.str.len().ne(1).any():
        raise AdsDataError("Mỗi support campaign phải chứa đúng một ASIN trong tên campaign.")
    support_marker = frame["Campaign name"].str.contains(SUPPORT_PATTERN)
    if not support_marker.all():
        raise AdsDataError("Support Campaign report có campaign không mang marker Nhi-Support.")
    frame["ASIN"] = extracted.map(lambda values: values[0].upper())
    return pd.DataFrame(
        {
            "ASIN": frame["ASIN"],
            "Campaign name": frame["Campaign name"],
            "support_spend": numeric(frame["Total cost"]),
            "support_sales": numeric(frame["Sales"]),
            "support_orders": numeric(frame["Purchases"]),
        }
    )


def read_ads_workbook(path: Path, ads_type: str) -> pd.DataFrame:
    """Normalize an Amazon Ads workbook without duplicating campaign totals.

    Sponsored Products exposes ASIN directly. Sponsored Brands and Sponsored
    Display expose campaign-level metrics, so the first ASIN in the campaign
    name is used as the primary product for ownership mapping. Additional ASINs
    in collection campaigns are retained only in diagnostics via the campaign
    name; campaign metrics are never expanded across ASINs.
    """
    kind = ads_type.strip().upper()
    if kind not in {"SP", "SB", "SD"}:
        raise AdsDataError(f"Ads Type không hợp lệ: {ads_type}")
    frame = pd.read_excel(path, dtype=object)
    frame.columns = [str(column).strip() for column in frame.columns]
    sales_column = "7 Day Total Sales" if kind == "SP" else "14 Day Total Sales"
    orders_column = (
        "7 Day Total Orders (#)" if kind == "SP" else "14 Day Total Orders (#)"
    )
    required = {
        "Campaign Name",
        "Spend",
        sales_column,
        orders_column,
        "Impressions",
        "Clicks",
    }
    if kind == "SP":
        required.add("Advertised ASIN")
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise AdsDataError(
            f"{kind} workbook thiếu cột: " + ", ".join(missing)
        )

    if kind == "SP":
        asins = frame["Advertised ASIN"].fillna("").astype(str).str.upper().str.strip()
    else:
        asins = (
            frame["Campaign Name"]
            .fillna("")
            .astype(str)
            .str.extract(ASIN_PATTERN, expand=False)
            .fillna("")
            .str.upper()
        )
    normalized = pd.DataFrame(
        {
            "ASIN": asins,
            "Campaign name": frame["Campaign Name"].fillna("").astype(str).str.strip(),
            "Ads Type": kind,
            "ad_spend": numeric(frame["Spend"]),
            "ad_sales": numeric(frame[sales_column]),
            "ad_orders": numeric(frame[orders_column]),
            "impressions": numeric(frame["Impressions"]),
            "clicks": numeric(frame["Clicks"]),
        }
    )
    active = normalized[["ad_spend", "ad_sales", "ad_orders"]].abs().sum(axis=1).gt(0)
    missing_active_asin = active & normalized["ASIN"].eq("")
    if missing_active_asin.any():
        raise AdsDataError(
            f"{kind} workbook có {int(missing_active_asin.sum())} dòng phát sinh số liệu "
            "nhưng không trích được ASIN."
        )
    return normalized[STANDARD_REPORT_COLUMNS]


def build_ads_employee_summary_from_reports(
    reports: list[pd.DataFrame],
    total_asins: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Map complete SP/SB/SD rows to Ads owner, Support, or FBA assignee."""
    required_total = {"asin", "record_id", "ads_by", "custom_by", "fulfill_by"}
    missing = sorted(required_total.difference(total_asins.columns))
    if missing:
        raise AdsDataError("TOTAL ASIN snapshot thiếu cột: " + ", ".join(missing))
    if not reports:
        raise AdsDataError("Chưa cung cấp report SP/SB/SD.")
    for report in reports:
        missing_report = sorted(set(STANDARD_REPORT_COLUMNS).difference(report.columns))
        if missing_report:
            raise AdsDataError("Ads report chuẩn hóa thiếu cột: " + ", ".join(missing_report))

    rows = pd.concat(reports, ignore_index=True)
    active = rows[["ad_spend", "ad_sales", "ad_orders"]].abs().sum(axis=1).gt(0)
    rows = rows.loc[active].copy()
    ownership = apply_fulfillment_overrides(total_asins)
    ownership["ASIN"] = ownership["asin"].fillna("").astype(str).str.upper().str.strip()
    ownership = (
        ownership.sort_values(["ASIN", "record_id"])
        .groupby("ASIN", as_index=False)
        .agg(
            ads_by=("ads_by", first_nonempty),
            custom_by=("custom_by", first_nonempty),
            fulfill_by=("fulfill_by", first_nonempty),
        )
    )
    rows = rows.merge(ownership, on="ASIN", how="left")
    missing_owner = rows["ads_by"].fillna("").str.strip().eq("")
    if missing_owner.any():
        missing_asins = sorted(rows.loc[missing_owner, "ASIN"].unique().tolist())
        raise AdsDataError(
            f"{len(missing_asins)} ASIN phát sinh Ads chưa map được Ads By trong TOTAL ASIN: "
            + ", ".join(missing_asins[:20])
        )

    rows["Nhân sự"] = rows["ads_by"].fillna("").astype(str).str.strip()
    catalog_fba_mask = rows["fulfill_by"].fillna("").str.strip().str.casefold().eq("fba")
    # Fulfillment ownership has priority over campaign execution markers. Every
    # FBA row must reconcile to Nhi-FBA or Linh-FBA and never leak into FBM KPI.
    support_mask = (
        rows["Campaign name"].str.contains(SUPPORT_PATTERN, na=False)
        & ~catalog_fba_mask
    )
    rows.loc[support_mask, "Nhân sự"] = "Nhi-Support"
    execution_masks: dict[str, pd.Series] = {}
    assigned_execution = support_mask.copy()
    for assignee, pattern in EXECUTION_PATTERNS.items():
        marker_mask = (
            rows["Campaign name"].str.contains(pattern, na=False)
            & ~assigned_execution
            & ~catalog_fba_mask
        )
        rows.loc[marker_mask, "Nhân sự"] = assignee
        execution_masks[assignee] = marker_mask
        assigned_execution |= marker_mask

    fba_mask = catalog_fba_mask
    normalized_custom = rows.loc[fba_mask, "custom_by"].fillna("").map(normalize_person)
    rows.loc[fba_mask, "Nhân sự"] = ""
    rows.loc[
        fba_mask
        & normalized_custom.reindex(rows.index, fill_value="").str.contains(
            "truong y nhi", regex=False
        ),
        "Nhân sự",
    ] = "Nhi-FBA"
    rows.loc[
        fba_mask
        & normalized_custom.reindex(rows.index, fill_value="").str.contains(
            "phuong linh", regex=False
        ),
        "Nhân sự",
    ] = "Linh-FBA"
    unknown_fba = fba_mask & rows["Nhân sự"].eq("")
    if unknown_fba.any():
        unknown = rows.loc[unknown_fba, ["ASIN", "custom_by"]].drop_duplicates()
        raise AdsDataError(
            "ASIN FBA chưa xác định được ownership Nhi/Linh từ Custom By: "
            + ", ".join(f"{row.ASIN} ({row.custom_by})" for row in unknown.itertuples())
        )

    summary = (
        rows.groupby("Nhân sự", as_index=False)
        .agg(
            ASINs=("ASIN", "nunique"),
            Ads_Spend=("ad_spend", "sum"),
            Ads_Sales=("ad_sales", "sum"),
            Ads_Orders=("ad_orders", "sum"),
        )
    )
    summary["ACOS"] = summary["Ads_Spend"].div(
        summary["Ads_Sales"].where(summary["Ads_Sales"].ne(0))
    )
    fbm_summary = (
        rows.loc[~catalog_fba_mask]
        .groupby("Nhân sự", as_index=False)
        .agg(
            FBM_ASINs=("ASIN", "nunique"),
            FBM_Ads_Spend=("ad_spend", "sum"),
            FBM_Ads_Sales=("ad_sales", "sum"),
            FBM_Ads_Orders=("ad_orders", "sum"),
        )
    )
    summary = summary.merge(fbm_summary, on="Nhân sự", how="left")
    summary[FBM_METRIC_COLUMNS] = summary[FBM_METRIC_COLUMNS].fillna(0)
    baseline = rows[["ad_spend", "ad_sales", "ad_orders"]].sum()
    final = summary[["Ads_Spend", "Ads_Sales", "Ads_Orders"]].sum()
    final.index = ["ad_spend", "ad_sales", "ad_orders"]
    if not baseline.round(2).equals(final.round(2)):
        raise AdsDataError("Phân bổ SP/SB/SD không bảo toàn tổng Ads Report.")

    by_type: dict[str, dict[str, Any]] = {}
    for kind, group in rows.groupby("Ads Type"):
        by_type[str(kind)] = {
            "rows": int(len(group)),
            "asins": int(group["ASIN"].nunique()),
            "spend": round(float(group["ad_spend"].sum()), 2),
            "sales": round(float(group["ad_sales"].sum()), 2),
            "orders": int(group["ad_orders"].sum()),
            "impressions": int(group["impressions"].sum()),
            "clicks": int(group["clicks"].sum()),
        }
    fba = rows.loc[fba_mask]
    support = rows.loc[support_mask]
    execution_by_assignee = {
        assignee: {
            "campaigns": int(rows.loc[mask, "Campaign name"].nunique()),
            "asins": int(rows.loc[mask, "ASIN"].nunique()),
            "spend": round(float(rows.loc[mask, "ad_spend"].sum()), 2),
            "sales": round(float(rows.loc[mask, "ad_sales"].sum()), 2),
            "orders": int(rows.loc[mask, "ad_orders"].sum()),
        }
        for assignee, mask in execution_masks.items()
    }
    diagnostics = {
        "report_rows": int(len(rows)),
        "report_asins": int(rows["ASIN"].nunique()),
        "by_type": by_type,
        "support_campaigns": int(support["Campaign name"].nunique()),
        "support_asins": int(support["ASIN"].nunique()),
        "support_spend": round(float(support["ad_spend"].sum()), 2),
        "support_sales": round(float(support["ad_sales"].sum()), 2),
        "support_orders": int(support["ad_orders"].sum()),
        "support_asin_list": sorted(support["ASIN"].unique().tolist()),
        "execution_by_assignee": execution_by_assignee,
        "fba_asins": int(fba["ASIN"].nunique()),
        "fba_spend": round(float(fba["ad_spend"].sum()), 2),
        "fba_sales": round(float(fba["ad_sales"].sum()), 2),
        "fba_orders": int(fba["ad_orders"].sum()),
        "fba_by_assignee": {
            assignee: {
                "asins": int(group["ASIN"].nunique()),
                "spend": round(float(group["ad_spend"].sum()), 2),
                "sales": round(float(group["ad_sales"].sum()), 2),
                "orders": int(group["ad_orders"].sum()),
            }
            for assignee, group in fba.groupby("Nhân sự")
        },
        "fba_asins_by_assignee": {
            assignee: sorted(group["ASIN"].unique().tolist())
            for assignee, group in fba.groupby("Nhân sự")
        },
    }
    return summary[SUMMARY_COLUMNS + FBM_METRIC_COLUMNS].sort_values(
        "Ads_Spend", ascending=False
    ), diagnostics


def first_nonempty(series: pd.Series) -> str:
    return next((str(value).strip() for value in series if str(value).strip()), "")


def build_ads_employee_summary(
    products: pd.DataFrame,
    support_campaigns: pd.DataFrame,
    total_asins: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    required_total = {"asin", "record_id", "ads_by", "custom_by", "fulfill_by"}
    missing = sorted(required_total.difference(total_asins.columns))
    if missing:
        raise AdsDataError("TOTAL ASIN snapshot thiếu cột: " + ", ".join(missing))

    ownership = apply_fulfillment_overrides(total_asins)
    ownership["ASIN"] = ownership["asin"].fillna("").astype(str).str.upper().str.strip()
    ownership = (
        ownership.sort_values(["ASIN", "record_id"])
        .groupby("ASIN", as_index=False)
        .agg(
            ads_by=("ads_by", first_nonempty),
            custom_by=("custom_by", first_nonempty),
            fulfill_by=("fulfill_by", first_nonempty),
        )
    )
    base = products.merge(ownership, on="ASIN", how="left")
    if base["ads_by"].fillna("").str.strip().eq("").any():
        missing_asins = base.loc[
            base["ads_by"].fillna("").str.strip().eq(""), "ASIN"
        ].tolist()
        raise AdsDataError(
            f"{len(missing_asins)} Advertised Product ASIN chưa map được Ads By trong TOTAL ASIN."
        )

    if support_campaigns.empty:
        support = pd.DataFrame(
            columns=[
                "ASIN", "support_campaigns", "support_spend", "support_sales",
                "support_orders", "ads_by",
            ]
        )
    else:
        support = (
            support_campaigns.groupby("ASIN", as_index=False)
            .agg(
                support_campaigns=("Campaign name", "nunique"),
                support_spend=("support_spend", "sum"),
                support_sales=("support_sales", "sum"),
                support_orders=("support_orders", "sum"),
            )
            .merge(ownership, on="ASIN", how="left")
        )
    support_missing_products = sorted(set(support["ASIN"]).difference(products["ASIN"]))
    support_missing_owners = support["ads_by"].fillna("").str.strip().eq("")
    if support_missing_products or support_missing_owners.any():
        raise AdsDataError(
            "Support report chưa đối soát đủ với Advertised Product/TOTAL ASIN: "
            f"{len(support_missing_products)} thiếu product, "
            f"{int(support_missing_owners.sum())} thiếu Ads By."
        )

    fba_mask = base["fulfill_by"].fillna("").str.strip().str.casefold().eq("fba")
    fba = base.loc[fba_mask].copy()
    normalized_custom = fba["custom_by"].fillna("").map(normalize_person)
    fba["fba_assignee"] = ""
    fba.loc[normalized_custom.str.contains("truong y nhi", regex=False), "fba_assignee"] = "Nhi-FBA"
    fba.loc[normalized_custom.str.contains("phuong linh", regex=False), "fba_assignee"] = "Linh-FBA"
    if fba["fba_assignee"].eq("").any():
        unknown = fba.loc[fba["fba_assignee"].eq(""), ["ASIN", "custom_by"]]
        raise AdsDataError(
            "ASIN FBA chưa xác định được ownership Nhi/Linh từ Custom By: "
            + ", ".join(f"{row.ASIN} ({row.custom_by})" for row in unknown.itertuples())
        )
    if set(fba["ASIN"]).intersection(support["ASIN"]):
        raise AdsDataError("ASIN FBA trùng report Nhi-Support; cần phân bổ campaign trước.")

    owner_base = base.loc[~fba_mask].copy()
    corrected = (
        owner_base.groupby("ads_by", as_index=False)
        .agg(
            ASINs=("ASIN", "nunique"),
            Ads_Spend=("product_spend", "sum"),
            Ads_Sales=("product_sales", "sum"),
            Ads_Orders=("product_orders", "sum"),
        )
        .rename(columns={"ads_by": "Nhân sự"})
    )
    if not support.empty:
        support_transfers = (
            support.groupby("ads_by", as_index=False)
            .agg(
                Transfer_Spend=("support_spend", "sum"),
                Transfer_Sales=("support_sales", "sum"),
                Transfer_Orders=("support_orders", "sum"),
            )
            .rename(columns={"ads_by": "Nhân sự"})
        )
        corrected = corrected.merge(support_transfers, on="Nhân sự", how="left").fillna(0)
        for metric in ("Spend", "Sales", "Orders"):
            corrected[f"Ads_{metric}"] -= corrected[f"Transfer_{metric}"]
        if corrected[["Ads_Spend", "Ads_Sales", "Ads_Orders"]].min().min() < -0.01:
            raise AdsDataError("Phân bổ support làm tổng nhân sự âm; hãy kiểm tra report period.")

    transfer_rows: list[dict[str, Any]] = []
    if not support.empty:
        transfer_rows.append({
                "Nhân sự": "Nhi-Support",
                "ASINs": int(support["ASIN"].nunique()),
                "Ads_Spend": float(support["support_spend"].sum()),
                "Ads_Sales": float(support["support_sales"].sum()),
                "Ads_Orders": float(support["support_orders"].sum()),
        })
    for assignee, assigned in fba.groupby("fba_assignee"):
        transfer_rows.append({
            "Nhân sự": assignee,
            "ASINs": int(assigned["ASIN"].nunique()),
            "Ads_Spend": float(assigned["product_spend"].sum()),
            "Ads_Sales": float(assigned["product_sales"].sum()),
            "Ads_Orders": float(assigned["product_orders"].sum()),
        })
    transfer_frame = pd.DataFrame(transfer_rows, columns=SUMMARY_COLUMNS[:-1])
    summary = pd.concat(
        [corrected[["Nhân sự", "ASINs", "Ads_Spend", "Ads_Sales", "Ads_Orders"]], transfer_frame],
        ignore_index=True,
    )
    summary["ACOS"] = summary["Ads_Spend"].div(
        summary["Ads_Sales"].where(summary["Ads_Sales"].ne(0))
    )

    baseline_totals = pd.Series({
        "Ads_Spend": base["product_spend"].sum(),
        "Ads_Sales": base["product_sales"].sum(),
        "Ads_Orders": base["product_orders"].sum(),
    })
    final_totals = summary[["Ads_Spend", "Ads_Sales", "Ads_Orders"]].sum()
    if not baseline_totals.round(2).equals(final_totals.round(2)):
        raise AdsDataError("Phân bổ Support/FBA không bảo toàn tổng Ads Report.")

    support_product = support.merge(
        products[["ASIN", "product_spend", "product_sales"]], on="ASIN", how="left"
    )
    diagnostics = {
        "product_rows": len(products),
        "product_asins": int(products["ASIN"].nunique()),
        "support_campaigns": len(support_campaigns),
        "support_asins": int(support["ASIN"].nunique()),
        "support_spend": round(float(support["support_spend"].sum()), 2),
        "support_sales": round(float(support["support_sales"].sum()), 2),
        "support_orders": int(support["support_orders"].sum()),
        "support_asin_list": sorted(support["ASIN"].unique().tolist()),
        "fba_asins": int(fba["ASIN"].nunique()),
        "fba_spend": round(float(fba["product_spend"].sum()), 2),
        "fba_sales": round(float(fba["product_sales"].sum()), 2),
        "fba_orders": int(fba["product_orders"].sum()),
        "fba_by_assignee": {
            assignee: {
                "asins": int(assigned["ASIN"].nunique()),
                "spend": round(float(assigned["product_spend"].sum()), 2),
                "sales": round(float(assigned["product_sales"].sum()), 2),
                "orders": int(assigned["product_orders"].sum()),
            }
            for assignee, assigned in fba.groupby("fba_assignee")
        },
        "fba_asins_by_assignee": {
            assignee: sorted(assigned["ASIN"].unique().tolist())
            for assignee, assigned in fba.groupby("fba_assignee")
        },
        "support_asins_spend_over_product": int(
            support_product["support_spend"].gt(support_product["product_spend"] + 0.005).sum()
        ),
        "support_asins_sales_over_product": int(
            support_product["support_sales"].gt(support_product["product_sales"] + 0.005).sum()
        ),
    }
    return summary[SUMMARY_COLUMNS].sort_values("Ads_Spend", ascending=False), diagnostics


def save_ads_snapshot(
    root: Path,
    summary: pd.DataFrame,
    metadata: dict[str, Any],
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    temporary = root / "employee_ads.csv.tmp"
    stored = summary.copy()
    stored.insert(0, "Store", metadata["store"])
    stored.insert(0, "Month", metadata["month"])
    stored.to_csv(temporary, index=False, encoding="utf-8")
    temporary.replace(root / "employee_ads.csv")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "imports": [metadata],
    }
    temporary_metadata = root / "metadata.json.tmp"
    temporary_metadata.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary_metadata.replace(root / "metadata.json")


def upsert_ads_snapshot(
    root: Path,
    summary: pd.DataFrame,
    metadata: dict[str, Any],
) -> None:
    existing = load_ads_snapshot(root)
    stored = summary.copy()
    stored.insert(0, "Store", metadata["store"])
    stored.insert(0, "Month", metadata["month"])
    imports = [metadata]
    if existing is not None:
        previous = existing["summary"]
        keep = ~(
            previous["Month"].eq(metadata["month"])
            & previous["Store"].eq(metadata["store"])
        )
        stored = pd.concat([previous.loc[keep], stored], ignore_index=True)
        imports = [
            item for item in existing.get("imports", [])
            if not (
                item.get("month") == metadata["month"]
                and item.get("store") == metadata["store"]
            )
        ] + [metadata]
    root.mkdir(parents=True, exist_ok=True)
    temporary = root / "employee_ads.csv.tmp"
    stored.to_csv(temporary, index=False, encoding="utf-8")
    temporary.replace(root / "employee_ads.csv")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "imports": imports,
    }
    temporary_metadata = root / "metadata.json.tmp"
    temporary_metadata.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary_metadata.replace(root / "metadata.json")


def load_ads_snapshot(root: Path) -> dict[str, Any] | None:
    summary_path = root / "employee_ads.csv"
    metadata_path = root / "metadata.json"
    if not summary_path.exists() or not metadata_path.exists():
        return None
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("schema_version") != SCHEMA_VERSION:
        return None
    summary = pd.read_csv(summary_path, keep_default_na=False)
    required = set(SNAPSHOT_DIMENSIONS + SUMMARY_COLUMNS)
    if not required.issubset(summary.columns):
        return None
    numeric_columns = ["ASINs", "Ads_Spend", "Ads_Sales", "Ads_Orders", "ACOS", *FBM_METRIC_COLUMNS]
    for column in numeric_columns:
        if column in summary:
            summary[column] = pd.to_numeric(summary[column], errors="coerce")
    return {"summary": summary, **metadata}


def save_encrypted_ads_snapshot(
    source_root: Path,
    output_path: Path,
    key: str,
) -> None:
    snapshot = load_ads_snapshot(source_root)
    if snapshot is None:
        raise AdsDataError("Chưa có Ads snapshot hợp lệ để mã hóa.")
    try:
        cipher = Fernet(key.strip().encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise AdsDataError("DASHBOARD_DATA_KEY không phải Fernet key hợp lệ.") from exc
    payload = {
        "encrypted_schema_version": ENCRYPTED_SCHEMA_VERSION,
        "metadata": {key: value for key, value in snapshot.items() if key != "summary"},
        "summary_csv": snapshot["summary"].to_csv(index=False),
    }
    encrypted = cipher.encrypt(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_bytes(encrypted)
    temporary.replace(output_path)


def load_encrypted_ads_snapshot(
    path: Path,
    key: str,
) -> dict[str, Any] | None:
    if not path.exists() or not key.strip():
        return None
    try:
        decrypted = Fernet(key.strip().encode("utf-8")).decrypt(path.read_bytes())
        payload = json.loads(decrypted.decode("utf-8"))
    except (OSError, ValueError, InvalidToken, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if payload.get("encrypted_schema_version") != ENCRYPTED_SCHEMA_VERSION:
        return None
    metadata = payload.get("metadata", {})
    if metadata.get("schema_version") != SCHEMA_VERSION:
        return None
    summary = pd.read_csv(StringIO(payload.get("summary_csv", "")), keep_default_na=False)
    required = set(SNAPSHOT_DIMENSIONS + SUMMARY_COLUMNS)
    if not required.issubset(summary.columns):
        return None
    numeric_columns = ["ASINs", "Ads_Spend", "Ads_Sales", "Ads_Orders", "ACOS", *FBM_METRIC_COLUMNS]
    for column in numeric_columns:
        if column in summary:
            summary[column] = pd.to_numeric(summary[column], errors="coerce")
    return {"summary": summary, **metadata}


def load_encrypted_ads_snapshot_with_keys(
    path: Path,
    keys: Iterable[str],
) -> dict[str, Any] | None:
    """Load a published snapshot with any configured shared-key alias.

    Some existing Streamlit deployments still contain both the legacy
    ``PUBLISHED_SNAPSHOT_KEY`` and the newer ``DASHBOARD_DATA_KEY``. Trying all
    distinct values lets a snapshot created by either configured machine be
    read without exposing or rotating the keys.
    """

    attempted: set[str] = set()
    for key in keys:
        normalized = str(key or "").strip()
        if not normalized or normalized in attempted:
            continue
        attempted.add(normalized)
        snapshot = load_encrypted_ads_snapshot(path, normalized)
        if snapshot is not None:
            return snapshot
    return None


def select_ads_summary(
    snapshot: dict[str, Any] | None,
    month: str,
    store: str,
    fbm_only: bool = False,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    if snapshot is None:
        return pd.DataFrame(columns=SUMMARY_COLUMNS), []
    selected = snapshot["summary"].loc[snapshot["summary"]["Month"].eq(month)].copy()
    imports = [item for item in snapshot.get("imports", []) if item.get("month") == month]
    if store != "All Stores":
        selected = selected.loc[selected["Store"].eq(store)]
        imports = [item for item in imports if item.get("store") == store]
    if selected.empty:
        return pd.DataFrame(columns=SUMMARY_COLUMNS), []
    has_complete_fbm_metrics = (
        set(FBM_METRIC_COLUMNS).issubset(selected.columns)
        and selected[FBM_METRIC_COLUMNS].notna().all().all()
    )
    if fbm_only and has_complete_fbm_metrics:
        combined = (
            selected.groupby("Nhân sự", as_index=False)
            .agg(
                ASINs=("FBM_ASINs", "sum"),
                Ads_Spend=("FBM_Ads_Spend", "sum"),
                Ads_Sales=("FBM_Ads_Sales", "sum"),
                Ads_Orders=("FBM_Ads_Orders", "sum"),
            )
        )
        combined = combined.loc[
            combined[["Ads_Spend", "Ads_Sales", "Ads_Orders"]].abs().sum(axis=1).gt(0)
        ]
    else:
        if fbm_only:
            selected = selected.loc[
                ~selected["Nhân sự"].fillna("").astype(str).str.endswith("-FBA")
            ]
        combined = (
            selected.groupby("Nhân sự", as_index=False)
            .agg(
                ASINs=("ASINs", "sum"),
                Ads_Spend=("Ads_Spend", "sum"),
                Ads_Sales=("Ads_Sales", "sum"),
                Ads_Orders=("Ads_Orders", "sum"),
            )
        )
    combined["ACOS"] = combined["Ads_Spend"].div(
        combined["Ads_Sales"].where(combined["Ads_Sales"].ne(0))
    )
    return combined[SUMMARY_COLUMNS].sort_values("Ads_Spend", ascending=False), imports


def ads_fulfillment_summary(
    snapshot: dict[str, Any] | None,
    month: str,
    store: str,
) -> pd.DataFrame:
    """Reconcile published Ads totals into FBM and FBA rows."""

    columns = ["Fulfill By", "Ads_Spend", "Ads_Sales", "Ads_Orders", "ACOS"]
    complete, _ = select_ads_summary(snapshot, month, store)
    fbm, _ = select_ads_summary(snapshot, month, store, fbm_only=True)
    if complete.empty:
        return pd.DataFrame(columns=columns)

    def totals(frame: pd.DataFrame) -> dict[str, float]:
        return {
            metric: float(
                pd.to_numeric(frame[metric], errors="coerce").fillna(0).sum()
            )
            for metric in ("Ads_Spend", "Ads_Sales", "Ads_Orders")
        }

    complete_totals = totals(complete)
    fbm_totals = totals(fbm)
    fba_totals = {
        metric: max(0.0, complete_totals[metric] - fbm_totals[metric])
        for metric in complete_totals
    }
    rows = []
    for fulfillment, metrics in (("FBM", fbm_totals), ("FBA", fba_totals)):
        sales = metrics["Ads_Sales"]
        rows.append(
            {
                "Fulfill By": fulfillment,
                **metrics,
                "ACOS": metrics["Ads_Spend"] / sales if sales else pd.NA,
            }
        )
    return pd.DataFrame(rows, columns=columns)


def ads_fba_employee_summary(
    snapshot: dict[str, Any] | None,
    month: str,
    store: str,
) -> pd.DataFrame:
    """Return FBA Ads metrics split between the two FBA assignees."""

    columns = ["Nhân sự", "ASINs", "Ads_Spend", "Ads_Sales", "Ads_Orders", "ACOS"]
    complete, _ = select_ads_summary(snapshot, month, store)
    owners = pd.DataFrame({"Nhân sự": ["Nhi-FBA", "Linh-FBA"]})
    if complete.empty:
        result = owners.copy()
        for column in ("ASINs", "Ads_Spend", "Ads_Sales", "Ads_Orders"):
            result[column] = 0.0
    else:
        fba = complete.loc[
            complete["Nhân sự"].fillna("").astype(str).isin(owners["Nhân sự"])
        ].copy()
        result = owners.merge(fba.drop(columns=["ACOS"], errors="ignore"), on="Nhân sự", how="left")
        for column in ("ASINs", "Ads_Spend", "Ads_Sales", "Ads_Orders"):
            result[column] = pd.to_numeric(result[column], errors="coerce").fillna(0)
    result["ACOS"] = result["Ads_Spend"].div(
        result["Ads_Sales"].where(result["Ads_Sales"].ne(0))
    )
    return result[columns]
