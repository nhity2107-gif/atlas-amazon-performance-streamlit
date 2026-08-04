from __future__ import annotations

import pandas as pd


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
