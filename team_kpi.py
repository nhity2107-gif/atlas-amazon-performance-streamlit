from __future__ import annotations

import pandas as pd


def fbm_asin_rows(attributed_asins: pd.DataFrame) -> pd.DataFrame:
    """Return only explicitly FBM-owned ASIN rows for employee KPI calculations."""
    if "fulfill_by" not in attributed_asins.columns:
        raise ValueError("KPI fulfillment source thiếu cột: fulfill_by")
    fulfillment = (
        attributed_asins["fulfill_by"].fillna("").astype(str).str.strip().str.casefold()
    )
    return attributed_asins.loc[fulfillment.eq("fbm")].copy()


def workflow_kpi_window_end(
    selected_month: str,
    lark_snapshot_updated_at: object,
    fallback: pd.Timestamp,
) -> pd.Timestamp:
    """End Lark workflow KPI at its latest refresh, independent of Order data."""
    updated_at = pd.to_datetime(lark_snapshot_updated_at, errors="coerce", utc=True)
    if pd.isna(updated_at):
        selected_end = pd.Timestamp(fallback).normalize()
    else:
        lark_date = updated_at.tz_convert("Asia/Ho_Chi_Minh").tz_localize(None).normalize()
        lark_month = lark_date.strftime("%Y-%m")
        if selected_month == lark_month:
            selected_end = lark_date
        elif selected_month < lark_month:
            selected_end = pd.Timestamp(f"{selected_month}-01") + pd.offsets.MonthEnd(0)
        else:
            selected_end = pd.Timestamp(fallback).normalize()
    return selected_end + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)


def idea_validation_cohort_end(window_end: pd.Timestamp) -> pd.Timestamp:
    """Cap the Idea validation cohort at day 20 of the selected month."""
    return pd.Timestamp(window_end).normalize().replace(day=20)


def asin_portfolio_revenue(
    attributed_asins: pd.DataFrame,
    owner_column: str,
) -> pd.DataFrame:
    """Return monthly revenue for every ASIN owned by each employee."""
    required = {"asin", owner_column, "Revenue"}
    missing = sorted(required.difference(attributed_asins.columns))
    if missing:
        raise ValueError("ASIN portfolio source thiếu cột: " + ", ".join(missing))

    rows = attributed_asins[
        attributed_asins[owner_column].fillna("").astype(str).str.strip().ne("")
    ].copy()
    if rows.empty:
        return pd.DataFrame(columns=["Nhân sự", "Portfolio_ASINs", "Portfolio_Revenue"])

    return (
        rows.groupby(owner_column, as_index=False)
        .agg(
            Portfolio_ASINs=("asin", "nunique"),
            Portfolio_Revenue=("Revenue", "sum"),
        )
        .rename(columns={owner_column: "Nhân sự"})
    )


def asin_new_revenue_from_custom_cohort(
    attributed_asins: pd.DataFrame,
    owner_column: str,
    cohort_start: pd.Timestamp,
    window_end: pd.Timestamp,
) -> pd.DataFrame:
    """Return revenue only for owned ASINs whose Custom Check Done is in cohort."""
    required = {"asin", owner_column, "custom_check_done_date", "Revenue"}
    missing = sorted(required.difference(attributed_asins.columns))
    if missing:
        raise ValueError("ASIN New Revenue source thiếu cột: " + ", ".join(missing))

    events = attributed_asins[
        attributed_asins[owner_column].fillna("").astype(str).str.strip().ne("")
    ].copy()
    if events.empty:
        return pd.DataFrame(columns=["Nhân sự", "New_Revenue_ASINs", "New_Revenue"])

    custom_dates = pd.to_datetime(events["custom_check_done_date"], errors="coerce")
    events = events[
        custom_dates.dt.normalize().between(
            pd.Timestamp(cohort_start).normalize(),
            pd.Timestamp(window_end).normalize(),
        )
    ].copy()

    return (
        events.groupby(owner_column, as_index=False)
        .agg(
            New_Revenue_ASINs=("asin", "nunique"),
            New_Revenue=("Revenue", "sum"),
        )
        .rename(columns={owner_column: "Nhân sự"})
    )
