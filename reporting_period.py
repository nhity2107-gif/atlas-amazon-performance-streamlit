from __future__ import annotations

import pandas as pd


HALF_YEAR_PERIODS = {
    "H2/2026": ("2026-07", "2026-12"),
}


def period_months(period: str) -> list[str]:
    """Return the calendar months represented by a report-period value."""

    if period not in HALF_YEAR_PERIODS:
        return [period]
    start_month, end_month = HALF_YEAR_PERIODS[period]
    return [stamp.strftime("%Y-%m") for stamp in pd.period_range(start_month, end_month, freq="M")]


def period_bounds(period: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Return inclusive calendar bounds for a month or configured half-year."""

    months = period_months(period)
    start = pd.Timestamp(f"{months[0]}-01")
    end = pd.Timestamp(f"{months[-1]}-01") + pd.offsets.MonthEnd(0)
    return start, end


def period_label(period: str) -> str:
    if period in HALF_YEAR_PERIODS:
        return period
    return pd.Timestamp(f"{period}-01").strftime("Tháng %m/%Y")
