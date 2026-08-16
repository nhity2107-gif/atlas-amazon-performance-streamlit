from __future__ import annotations

import argparse
from datetime import datetime
from html import escape
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
import sys

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ads_data import load_ads_snapshot, normalize_person, select_ads_summary
from fulfillment_rules import apply_fulfillment_overrides
from lark_snapshot_store import load_lark_snapshot
from product_data import (
    fulfillment_revenue_frame,
    revenue_milestone_counts,
    top_record_id_frame,
)
from snapshot_store import load_snapshot, load_snapshot_metadata
from target_data import (
    daily_targets_for_month,
    load_fbm_target_snapshot,
    target_for_month,
    target_progress,
)


def first_nonempty(series: pd.Series) -> str:
    return next(
        (str(value).strip() for value in series if pd.notna(value) and str(value).strip()),
        "",
    )


def in_window(series: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce")
    return parsed.dt.normalize().between(start.normalize(), end.normalize())


def prepare_attribution(performance: pd.DataFrame, lark: dict) -> dict:
    total = apply_fulfillment_overrides(lark["total"]).drop_duplicates(
        ["record_id", "asin"]
    )
    asin_performance = (
        performance.groupby("ASIN", as_index=False)
        .agg(
            Revenue=("Revenue", "sum"),
            Orders=("Orders", "sum"),
            Units=("Units", "sum"),
            record_id_hint=("record_id_hint", first_nonempty),
        )
    )
    known_asins = set(total["asin"])
    fallback = asin_performance[
        ~asin_performance["ASIN"].isin(known_asins)
        & asin_performance["record_id_hint"].fillna("").str.strip().ne("")
    ][["ASIN", "record_id_hint"]].drop_duplicates("ASIN")
    if not fallback.empty:
        lookup = total.sort_values(["record_id", "asin"]).drop_duplicates("record_id")
        extra = fallback.merge(
            lookup, left_on="record_id_hint", right_on="record_id", how="left"
        )
        extra["record_id"] = extra["record_id"].fillna(extra["record_id_hint"])
        extra["asin"] = extra["ASIN"]
        for column in total.columns:
            if column not in extra:
                extra[column] = pd.NaT if column.endswith("_date") else ""
        total = pd.concat([total, extra[total.columns]], ignore_index=True)

    owners = total.sort_values(["asin", "record_id"]).drop_duplicates("asin")
    attributed = owners.merge(
        asin_performance, left_on="asin", right_on="ASIN", how="left"
    )
    for column in ("Revenue", "Orders", "Units"):
        attributed[column] = pd.to_numeric(
            attributed[column], errors="coerce"
        ).fillna(0)

    text_columns = [
        "managed_by",
        "custom_by",
        "ads_by",
        "product_name",
        "image_url",
        "image_token",
        "image_record_id",
        "image_field_id",
    ]
    date_columns = [
        "date_pickup",
        "listing_done_date",
        "ps_pickup_date",
        "custom_done_date",
        "custom_check_done_date",
        "testing_start_date",
    ]
    aggregation = {
        **{column: first_nonempty for column in text_columns},
        **{column: "min" for column in date_columns},
        "fulfill_by": first_nonempty,
        "Revenue": "sum",
        "Orders": "sum",
        "Units": "sum",
        "asin": "nunique",
    }
    records = attributed.groupby("record_id", as_index=False).agg(aggregation)
    records = records.rename(columns={"asin": "asin_count"})
    ideas = (
        lark["ideas"]
        .sort_values("handover_date", na_position="last")
        .groupby("record_id", as_index=False)
        .agg(idea_by=("idea_by", first_nonempty), handover_date=("handover_date", "min"))
    )
    records = records.merge(ideas, on="record_id", how="left")
    records["idea_by"] = records["idea_by"].fillna("")
    total_revenue = float(asin_performance["Revenue"].sum())
    mapped_revenue = float(attributed["Revenue"].sum())
    return {
        "total": total,
        "attributed_asins": attributed,
        "records": records,
        "ideas": lark["ideas"].copy(),
        "cliparts": lark["cliparts"].copy(),
        "coverage": mapped_revenue / total_revenue if total_revenue else 0,
    }


def table_html(frame: pd.DataFrame, classes: str = "") -> str:
    if frame.empty:
        return '<div class="empty">Chưa có dữ liệu.</div>'
    return frame.to_html(index=False, border=0, classes=f"data-table {classes}")


def format_money(value: float, decimals: int = 2) -> str:
    return f"${float(value):,.{decimals}f}"


def milestone_table(records: pd.DataFrame, owner: str) -> pd.DataFrame:
    result = revenue_milestone_counts(records, owner)
    return result.rename(
        columns={
            "Portfolio_Records_1000_Revenue": "≥$1K",
            "Portfolio_Records_3000_Revenue": "≥$3K",
            "Portfolio_Records_5000_Revenue": "≥$5K",
            "Portfolio_Records_10000_Revenue": "≥$10K",
            "Portfolio_Records_15000_Revenue": "≥$15K",
            "Portfolio_Records_20000_Revenue": "≥$20K",
        }
    )


def export(month: str, output: Path) -> None:
    order_path = PROJECT_ROOT / "snapshot/dashboard_snapshot.csv"
    performance = load_snapshot(order_path)
    performance["Date"] = pd.to_datetime(performance["Date"], errors="coerce")
    performance = performance[performance["Date"].dt.strftime("%Y-%m").eq(month)].copy()
    if performance.empty:
        raise SystemExit(f"Không có Order snapshot cho {month}.")
    lark = load_lark_snapshot(PROJECT_ROOT / "snapshot/lark")
    if lark is None:
        raise SystemExit("Chưa có Lark snapshot.")
    attribution = prepare_attribution(performance, lark)
    records = attribution["records"]
    attributed = attribution["attributed_asins"]
    start = pd.Timestamp(f"{month}-01")
    end = start + pd.offsets.MonthEnd(1)
    cohort_start = (start - pd.DateOffset(months=1)).replace(day=20)

    revenue = float(performance["Revenue"].sum())
    orders = int(performance["Orders"].sum())
    units = int(performance["Units"].sum())
    asins = int(performance["ASIN"].nunique())
    stores = (
        performance.groupby("Store", as_index=False)
        .agg(Revenue=("Revenue", "sum"), Orders=("Orders", "sum"), Units=("Units", "sum"), ASINs=("ASIN", "nunique"))
        .sort_values(["Revenue", "Orders"], ascending=False, kind="stable")
    )
    stores["Revenue"] = stores["Revenue"].map(format_money)

    fulfillment = fulfillment_revenue_frame(performance, lark["total"])
    fulfillment_display = fulfillment.sort_values(
        ["Revenue", "Orders"], ascending=False, kind="stable"
    ).copy()
    fulfillment_display["Revenue"] = fulfillment_display["Revenue"].map(format_money)

    target_html = ""
    target_frame = load_fbm_target_snapshot(PROJECT_ROOT / "snapshot/fbm_target.csv")
    monthly_fbm_target = target_for_month(target_frame, month)
    order_meta = load_snapshot_metadata(order_path)
    report_as_of = pd.to_datetime(order_meta.get("report_as_of_date"), errors="coerce")
    if monthly_fbm_target is not None and pd.notna(report_as_of):
        fulfillment_index = fulfillment.set_index("Fulfill By")
        fbm_actual = (
            float(fulfillment_index.loc["FBM", "Revenue"])
            if "FBM" in fulfillment_index.index
            else 0.0
        )
        progress = target_progress(target_frame, month, fbm_actual, report_as_of)
        daily_target = daily_targets_for_month(target_frame, month)
        daily_target = daily_target[
            daily_target["Date"].le(report_as_of.normalize())
        ].copy()
        actual_parts = []
        for day, day_orders in performance.groupby("Date", sort=True):
            day_fulfillment = fulfillment_revenue_frame(day_orders, lark["total"])
            day_index = day_fulfillment.set_index("Fulfill By")
            actual_parts.append(
                {
                    "Date": pd.Timestamp(day),
                    "Actual 2026": (
                        float(day_index.loc["FBM", "Revenue"])
                        if "FBM" in day_index.index
                        else 0.0
                    ),
                }
            )
        daily_comparison = daily_target.merge(
            pd.DataFrame(actual_parts), on="Date", how="left"
        )
        daily_comparison["Actual 2026"] = daily_comparison["Actual 2026"].fillna(0)
        daily_comparison["Vs Forecast"] = daily_comparison["Actual 2026"].div(
            daily_comparison["Forecast 2026"].where(daily_comparison["Forecast 2026"].ne(0))
        ).sub(1)
        daily_comparison["YoY"] = daily_comparison["Actual 2026"].div(
            daily_comparison["Revenue 2025"].where(daily_comparison["Revenue 2025"].ne(0))
        ).sub(1)
        daily_comparison["Date"] = daily_comparison["Date"].dt.strftime("%d/%m/%Y")
        for column in ("Actual 2026", "Forecast 2026", "Revenue 2025"):
            daily_comparison[column] = daily_comparison[column].map(format_money)
        for column in ("Vs Forecast", "YoY"):
            daily_comparison[column] = daily_comparison[column].map(
                lambda value: f"{float(value):+.1%}" if pd.notna(value) else "N/A"
            )
        target_html = f"""
        <div class="card"><h2>FBM Actual vs Target · All Stores</h2>
        <div class="desc">Đúng từng ngày từ FORECAST 2026 và DAILY REV 2025 · đang tính {int(progress['elapsed_days'])} ngày theo lần input Order gần nhất.</div>
        <div class="grid target-grid"><div class="metric"><span>Actual MTD 2026</span><strong>{format_money(fbm_actual)}</strong></div><div class="metric"><span>Forecast MTD 2026</span><strong>{format_money(float(progress['forecast_mtd']))}</strong></div><div class="metric"><span>Actual vs Forecast</span><strong>{float(progress['vs_forecast']):+.1%}</strong></div><div class="metric"><span>Revenue 2025 MTD</span><strong>{format_money(float(progress['prior_mtd']))}</strong></div><div class="metric"><span>Actual vs 2025</span><strong>{float(progress['vs_2025']):+.1%}</strong></div></div>
        <div class="desc">Forecast cả tháng: {format_money(float(progress['forecast_full_month']))}</div>
        <div class="table-scroll">{table_html(daily_comparison[["Date", "Actual 2026", "Forecast 2026", "Vs Forecast", "Revenue 2025", "YoY"]])}</div></div>
        """

    daily = performance.groupby("Date", as_index=False).agg(Revenue=("Revenue", "sum"))
    daily_max = max(float(daily["Revenue"].max()), 1)
    daily_bars = "".join(
        f'<div class="bar-wrap" title="{row.Date:%d/%m}: {format_money(row.Revenue)}">'
        f'<div class="bar" style="height:{max(3, row.Revenue / daily_max * 100):.1f}%"></div>'
        f'<span>{row.Date.day}</span></div>'
        for row in daily.itertuples()
    )

    top = top_record_id_frame(records, revenue, 50).drop(
        columns=["Image", "image_token", "image_record_id", "image_field_id"],
        errors="ignore",
    )
    top["Revenue"] = top["Revenue"].map(format_money)
    top["Share"] = top["Share"].map(lambda value: f"{float(value):.2f}%")
    top_html = top.to_html(index=False, border=0, classes="data-table products")

    workflow = lark["workflow"]
    idea_count = int(
        lark["ideas"].loc[
            in_window(lark["ideas"]["handover_date"], start, end), "record_id"
        ].nunique()
    )
    listing_mask = in_window(workflow["listing_done_date"], start, end)
    custom_mask = in_window(workflow["custom_check_done_date"], start, end)
    ads_mask = in_window(workflow["testing_start_date"], start, end)
    listing_lead = pd.to_numeric(
        workflow.loc[listing_mask, "listing_lead_time"], errors="coerce"
    ).mean()
    custom_lead = pd.to_numeric(
        workflow.loc[custom_mask, "custom_lead_time"], errors="coerce"
    ).mean()
    cliparts = attribution["cliparts"]
    asset_points = int(
        cliparts.loc[in_window(cliparts["created_date"], start, end), "asset_points"].sum()
    )

    idea_events = lark["ideas"].copy()
    idea_events["qualified"] = in_window(idea_events["handover_date"], start, end)
    idea_events["in_cohort"] = in_window(
        idea_events["handover_date"], cohort_start, end
    )
    idea_events = (
        idea_events.groupby("record_id", as_index=False)
        .agg(
            idea_by=("idea_by", first_nonempty),
            Qualified_Ideas=("qualified", "any"),
            In_Cohort=("in_cohort", "any"),
        )
        .merge(records[["record_id", "Revenue", "Units"]], on="record_id", how="left")
    )
    idea_events[["Revenue", "Units"]] = idea_events[["Revenue", "Units"]].fillna(0)
    idea_events = idea_events[idea_events["idea_by"].fillna("").str.strip().ne("")]
    idea_events["Validated"] = idea_events["Units"].ge(10)
    idea_events["Cohort_Validated"] = idea_events["In_Cohort"] & idea_events["Validated"]
    idea_summary = (
        idea_events.groupby("idea_by", as_index=False)
        .agg(
            Qualified_Ideas=("Qualified_Ideas", "sum"),
            Portfolio_Record_IDs_10_Units=("Validated", "sum"),
            Pickup_Cohort_Record_IDs=("In_Cohort", "sum"),
            Validated_Record_IDs_10_Units=("Cohort_Validated", "sum"),
            Revenue=("Revenue", "sum"),
        )
        .rename(columns={"idea_by": "Nhân sự"})
    )
    idea_summary["Validated_Rate"] = idea_summary[
        "Validated_Record_IDs_10_Units"
    ].div(idea_summary["Pickup_Cohort_Record_IDs"].where(
        idea_summary["Pickup_Cohort_Record_IDs"].ne(0)
    ))
    idea_summary = idea_summary.merge(
        milestone_table(idea_events, "idea_by"), on="Nhân sự", how="left"
    )
    idea_summary = idea_summary.sort_values(
        ["Qualified_Ideas", "Validated_Record_IDs_10_Units", "Revenue"],
        ascending=False,
        kind="stable",
    )
    idea_summary["Revenue"] = idea_summary["Revenue"].map(format_money)

    product_asins = attributed[attributed["managed_by"].fillna("").str.strip().ne("")].copy()
    product_asins["qualified"] = in_window(product_asins["custom_check_done_date"], start, end)
    product_asins["listing_in_cohort"] = in_window(
        product_asins["listing_done_date"], cohort_start, end
    )
    product_asins["lead"] = pd.to_numeric(product_asins["listing_lead_time"], errors="coerce").where(
        in_window(product_asins["listing_done_date"], start, end)
    )
    product_output = (
        product_asins.groupby("managed_by", as_index=False)
        .agg(Qualified_ASINs=("qualified", "sum"), Listing_Lead_Days=("lead", "mean"))
        .rename(columns={"managed_by": "Nhân sự"})
    )
    product_records = (
        product_asins.groupby("record_id", as_index=False)
        .agg(
            managed_by=("managed_by", first_nonempty),
            In_Cohort=("listing_in_cohort", "any"),
            Revenue=("Revenue", "sum"),
            Units=("Units", "sum"),
        )
    )
    product_records["Sold"] = product_records["Units"].ge(10)
    product_records["Cohort_Sold"] = (
        product_records["In_Cohort"] & product_records["Sold"]
    )
    product_records["New_Revenue"] = product_records["Revenue"].where(
        product_records["In_Cohort"], 0
    )
    product_portfolio = (
        product_records.groupby("managed_by", as_index=False)
        .agg(
            Portfolio_Record_IDs_10_Units=("Sold", "sum"),
            Listing_Cohort_Record_IDs=("In_Cohort", "sum"),
            Sold_Record_IDs_10_Units=("Cohort_Sold", "sum"),
            New_Revenue=("New_Revenue", "sum"),
            Portfolio_Revenue=("Revenue", "sum"),
        )
        .rename(columns={"managed_by": "Nhân sự"})
    )
    product_portfolio["Sold_Rate"] = product_portfolio[
        "Sold_Record_IDs_10_Units"
    ].div(product_portfolio["Listing_Cohort_Record_IDs"].where(
        product_portfolio["Listing_Cohort_Record_IDs"].ne(0)
    ))
    product_summary = product_output.merge(product_portfolio, on="Nhân sự", how="outer")
    product_summary = product_summary.merge(
        milestone_table(product_records, "managed_by"), on="Nhân sự", how="left"
    )
    product_summary = product_summary.fillna(0).sort_values(
        ["Qualified_ASINs", "Sold_Record_IDs_10_Units", "Portfolio_Revenue"],
        ascending=False,
        kind="stable",
    )
    product_summary["Listing_Lead_Days"] = product_summary["Listing_Lead_Days"].map(
        lambda value: f"{value:.2f}" if pd.notna(value) else "N/A"
    )
    product_summary["Portfolio_Revenue"] = product_summary["Portfolio_Revenue"].map(format_money)
    product_summary["New_Revenue"] = product_summary["New_Revenue"].map(format_money)

    support_asins = attributed[attributed["custom_by"].fillna("").str.strip().ne("")].copy()
    support_asins["qualified"] = in_window(support_asins["custom_check_done_date"], start, end)
    support_summary = (
        support_asins.groupby("custom_by", as_index=False)
        .agg(Qualified_Custom_ASINs=("qualified", "sum"))
        .rename(columns={"custom_by": "Nhân sự"})
    )
    points = cliparts[in_window(cliparts["created_date"], start, end)]
    if not points.empty:
        points = (
            points.groupby("employee", as_index=False)
            .agg(Asset_Points=("asset_points", "sum"))
            .rename(columns={"employee": "Nhân sự"})
        )
        support_summary = support_summary.merge(points, on="Nhân sự", how="outer")
    if "Asset_Points" not in support_summary:
        support_summary["Asset_Points"] = 0
    support_summary = support_summary.fillna(0).sort_values(
        ["Qualified_Custom_ASINs", "Asset_Points"],
        ascending=False,
        kind="stable",
    )

    ads_snapshot = load_ads_snapshot(PROJECT_ROOT / "snapshot/ads")
    ads_summary, ads_imports = select_ads_summary(ads_snapshot, month, "All Stores")
    revenue_asins = attributed[attributed["ads_by"].fillna("").str.strip().ne("")].copy()
    revenue_asins["Revenue_Owner"] = revenue_asins["ads_by"]
    fba = revenue_asins["fulfill_by"].fillna("").str.casefold().eq("fba")
    custom = revenue_asins.loc[fba, "custom_by"].map(normalize_person)
    revenue_asins.loc[fba & custom.reindex(revenue_asins.index, fill_value="").str.contains("truong y nhi", regex=False), "Revenue_Owner"] = "Nhi-FBA"
    revenue_asins.loc[fba & custom.reindex(revenue_asins.index, fill_value="").str.contains("phuong linh", regex=False), "Revenue_Owner"] = "Linh-FBA"
    # July does not yet have complete Testing Start Date coverage. Per the KPI
    # convention confirmed for this report, Ads cohort temporarily falls back
    # to Custom Check Done Date. Replace this field when Testing Start is complete.
    revenue_asins["Ads_Cohort"] = in_window(
        revenue_asins["custom_check_done_date"], cohort_start, end
    )
    ads_revenue = (
        revenue_asins.groupby("Revenue_Owner", as_index=False)
        .agg(Portfolio_Revenue=("Revenue", "sum"))
        .rename(columns={"Revenue_Owner": "Nhân sự"})
    )
    ads_records = (
        revenue_asins.groupby(["Revenue_Owner", "record_id"], as_index=False)
        .agg(Revenue=("Revenue", "sum"), In_Cohort=("Ads_Cohort", "any"))
    )
    ads_records["New_Winner_5K"] = (
        ads_records["In_Cohort"] & ads_records["Revenue"].ge(5000)
    )
    ads_cohort = (
        ads_records.groupby("Revenue_Owner", as_index=False)
        .agg(
            Custom_Check_Cohort_Record_IDs=("In_Cohort", "sum"),
            New_Winner_5K=("New_Winner_5K", "sum"),
        )
        .rename(columns={"Revenue_Owner": "Nhân sự"})
    )
    ads_milestones = milestone_table(
        revenue_asins.rename(columns={"Revenue_Owner": "milestone_owner"}),
        "milestone_owner",
    )
    ads_display = ads_summary.merge(ads_revenue, on="Nhân sự", how="outer")
    ads_display = ads_display.merge(ads_cohort, on="Nhân sự", how="outer")
    ads_display = ads_display.merge(ads_milestones, on="Nhân sự", how="outer").fillna(0)
    ads_display["TACOS"] = ads_display["Ads_Spend"].div(
        ads_display["Portfolio_Revenue"].where(ads_display["Portfolio_Revenue"].ne(0))
    )
    ads_display.loc[ads_display["Nhân sự"].eq("Nhi-Support"), "TACOS"] = pd.NA
    total_spend = float(ads_display["Ads_Spend"].sum())
    total_sales = float(ads_display["Ads_Sales"].sum())
    weighted_acos = f"{total_spend / total_sales:.1%}" if total_sales else "N/A"
    ads_display = ads_display.sort_values(
        ["Ads_Spend", "Ads_Sales"], ascending=False, kind="stable"
    )
    ads_display["Ads_Spend"] = ads_display["Ads_Spend"].map(format_money)
    ads_display["Ads_Sales"] = ads_display["Ads_Sales"].map(format_money)
    ads_display["Portfolio_Revenue"] = ads_display["Portfolio_Revenue"].map(format_money)
    ads_display["ACOS"] = ads_display["ACOS"].map(
        lambda value: f"{float(value):.1%}" if pd.notna(value) and float(value) else "N/A"
    )
    ads_display["TACOS"] = ads_display["TACOS"].map(
        lambda value: f"{float(value):.1%}" if pd.notna(value) else "N/A"
    )
    idea_summary["Validated_Rate"] = idea_summary["Validated_Rate"].map(
        lambda value: f"{float(value):.1%}" if pd.notna(value) else "N/A"
    )
    product_summary["Sold_Rate"] = product_summary["Sold_Rate"].map(
        lambda value: f"{float(value):.1%}" if pd.notna(value) else "N/A"
    )

    updated = order_meta.get("source_updated_at") or order_meta.get("updated_at") or ""
    month_label = start.strftime("%m/%Y")
    generated_at = datetime.now().strftime("%d/%m/%Y %H:%M")
    css = """
    :root{--ink:#182033;--muted:#778193;--line:#e3e7ee;--bg:#f3f5f8;--orange:#ef772d;--nav:#151d2e}
    *{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
    .shell{display:grid;grid-template-columns:230px 1fr;min-height:100vh}.side{background:var(--nav);padding:28px 18px;color:#fff;position:sticky;top:0;height:100vh}.brand{font-weight:850;font-size:20px;margin-bottom:8px}.brand-sub{color:#9aa7bc;font-size:12px;margin-bottom:30px}.nav button{display:block;width:100%;border:0;background:transparent;color:#cbd3e2;text-align:left;padding:12px 14px;border-radius:10px;margin:5px 0;font-weight:650;cursor:pointer}.nav button.active,.nav button:hover{background:#ffffff16;color:#fff}.main{padding:38px;max-width:1700px}.page{display:none}.page.active{display:block}.eyebrow{color:#8792a6;font-size:12px;font-weight:850;letter-spacing:.15em}.title{font-size:42px;line-height:1.1;margin:5px 0 8px}.sub{color:var(--muted);margin-bottom:24px}.notice{background:#fff7ef;border:1px solid #f1d5bd;border-radius:14px;padding:15px 18px;margin-bottom:22px}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px;margin:16px 0}.target-grid{grid-template-columns:repeat(5,minmax(0,1fr))}.metric,.card{background:#fff;border:1px solid var(--line);border-radius:16px;padding:20px;box-shadow:0 10px 30px #25324b0a}.card .metric{background:#f8fafc;box-shadow:none}.metric span{color:var(--muted);font-size:13px}.metric strong{display:block;font-size:30px;margin-top:6px}.metric small{color:#94a0b2}.card{margin:18px 0}.card h2{margin:0 0 5px;font-size:20px}.card .desc{color:var(--muted);font-size:13px;margin-bottom:15px}.dark-strip{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;background:linear-gradient(135deg,#151d2e,#283753);padding:16px;border-radius:16px}.dark-strip .metric{background:#ffffff0b;border-color:#ffffff12;color:#fff;box-shadow:none}.dark-strip .metric span,.dark-strip .metric small{color:#9facbf}.chart{height:245px;display:flex;align-items:flex-end;gap:4px;padding:18px 4px 5px;border-bottom:1px solid var(--line)}.bar-wrap{height:100%;flex:1;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;min-width:8px}.bar{width:78%;background:linear-gradient(#ff9a56,#ef772d);border-radius:5px 5px 1px 1px;min-height:3px}.bar-wrap span{font-size:9px;color:#8b95a5;margin-top:5px}.table-scroll{overflow:auto;max-height:760px;border:1px solid var(--line);border-radius:12px}.data-table{width:100%;border-collapse:collapse;background:#fff;font-size:12px}.data-table th{position:sticky;top:0;background:#f7f8fa;color:#687386;text-align:left;padding:11px;white-space:nowrap;border-bottom:1px solid var(--line)}.data-table td{padding:10px 11px;border-bottom:1px solid #edf0f4;white-space:nowrap}.data-table tr:hover td{background:#fff9f3}.products img{width:44px;height:44px;object-fit:cover;border-radius:8px}.split{display:grid;grid-template-columns:1fr 1fr;gap:18px}.footer{color:#8a94a4;font-size:12px;margin:34px 0 10px}.empty{padding:30px;color:var(--muted);text-align:center}.pill{display:inline-block;background:#eaf7ed;color:#268340;padding:5px 9px;border-radius:999px;font-size:12px;font-weight:700}
    @media(max-width:1050px){.shell{display:block}.side{height:auto;position:static}.nav{display:flex;overflow:auto}.nav button{width:auto;white-space:nowrap}.main{padding:22px}.grid{grid-template-columns:repeat(2,1fr)}.dark-strip{grid-template-columns:repeat(2,1fr)}.split{grid-template-columns:1fr}.title{font-size:34px}}
    @media print{.side{display:none}.shell{display:block}.main{padding:10px}.page{display:block!important;page-break-before:always}.page:first-child{page-break-before:auto}.table-scroll{max-height:none;overflow:visible}.data-table th{position:static}}
    """
    html = f"""<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Atlas Performance OS · {month_label}</title><style>{css}</style></head>
    <body><div class="shell"><aside class="side"><div class="brand">ATLAS PERFORMANCE OS</div><div class="brand-sub">Static monthly dashboard · {month_label}</div><nav class="nav">
    <button class="active" data-page="overview">Tổng quan</button><button data-page="products">Sản phẩm</button><button data-page="ads">Ads performance</button><button data-page="team">Team KPI</button></nav></aside><main class="main">
    <section id="overview" class="page active"><div class="eyebrow">PERFORMANCE SNAPSHOT</div><h1 class="title">Tháng {month_label}</h1><div class="sub">Order Report thực tế · Purchase Time theo America/Los_Angeles</div><div class="notice"><b>All Stores</b> · Revenue = Item Price + Shipping Price · Đã loại Cancelled</div>
    <div class="grid"><div class="metric"><span>Net Revenue</span><strong>{format_money(revenue)}</strong></div><div class="metric"><span>Orders</span><strong>{orders:,}</strong></div><div class="metric"><span>Units</span><strong>{units:,}</strong></div><div class="metric"><span>Active ASINs</span><strong>{asins:,}</strong></div></div>
    {target_html}
    <div class="split"><div class="card"><h2>Revenue theo ngày</h2><div class="desc">Tổng hai store theo Purchase Date Los Angeles</div><div class="chart">{daily_bars}</div></div><div class="card"><h2>Revenue theo Fulfillment</h2><div class="desc">TOTAL ASIN Fulfill By, ưu tiên ASIN và fallback Record ID</div><div class="table-scroll">{table_html(fulfillment_display)}</div></div></div>
    <div class="card"><h2>Store breakdown</h2><div class="table-scroll">{table_html(stores)}</div></div></section>

    <section id="products" class="page"><div class="eyebrow">PRODUCT PERFORMANCE</div><h1 class="title">Top 50 Record ID</h1><div class="sub">Gộp Revenue, Orders và Units của toàn bộ ASIN cùng sản phẩm · Revenue mapped <span class="pill">{attribution['coverage']:.1%}</span></div><div class="card"><div class="table-scroll">{top_html}</div></div></section>

    <section id="ads" class="page"><div class="eyebrow">ADVERTISING PERFORMANCE</div><h1 class="title">Ads · Tháng {month_label}</h1><div class="sub">WR: SP/SB/SD · PAW: SP, SB/SD không phát sinh · Mapping ASIN → TOTAL ASIN → ownership</div>
    <div class="grid"><div class="metric"><span>Ads Spend</span><strong>{format_money(total_spend)}</strong></div><div class="metric"><span>Ads Sales</span><strong>{format_money(total_sales)}</strong></div><div class="metric"><span>Ads Orders</span><strong>{int(pd.to_numeric(ads_summary['Ads_Orders'], errors='coerce').fillna(0).sum()):,}</strong></div><div class="metric"><span>Weighted ACOS</span><strong>{weighted_acos}</strong></div></div>
    <div class="card"><h2>Ads theo nhân sự</h2><div class="desc">TACOS chỉ hiển thị khi hàng có ownership Revenue; Nhi-Support không nhận Revenue.</div><div class="table-scroll">{table_html(ads_display)}</div></div></section>

    <section id="team" class="page"><div class="eyebrow">TEAM KPI · RECORD LEVEL</div><h1 class="title">Workflow KPI từ Lark</h1><div class="sub">Lark calendar date không đổi timezone · Revenue/Units theo Purchase Month Los Angeles</div>
    <div class="dark-strip"><div class="metric"><span>Qualified Ideas</span><strong>{idea_count:,}</strong><small>Unique Record ID</small></div><div class="metric"><span>Listing Done</span><strong>{int(listing_mask.sum()):,}</strong><small>TOTAL ASIN record count</small></div><div class="metric"><span>Custom Check Done</span><strong>{int(custom_mask.sum()):,}</strong><small>TOTAL ASIN record count</small></div><div class="metric"><span>Asset Points</span><strong>{asset_points:,}</strong><small>CLIPARTS</small></div><div class="metric"><span>Ads Tested</span><strong>{int(ads_mask.sum()):,}</strong><small>TOTAL ASIN record count</small></div></div>
    <div class="grid"><div class="metric"><span>Listing Lead Time</span><strong>{listing_lead:.2f} days</strong></div><div class="metric"><span>Custom Lead Time</span><strong>{custom_lead:.2f} days</strong></div><div class="metric"><span>Attributed Revenue</span><strong>{format_money(records['Revenue'].sum(),0)}</strong></div><div class="metric"><span>Winner Records</span><strong>{int(records['Revenue'].ge(5000).sum()):,}</strong><small>Revenue ≥ $5,000</small></div></div>
    <div class="card"><h2>Idea · 40% Output / 30% Efficiency / 30% Business</h2><div class="desc">Portfolio ≥10 Units dùng toàn bộ Record ID thuộc ownership; Pickup Cohort từ {cohort_start:%d/%m/%Y} đến {end:%d/%m/%Y}; Validated là Record ID trong cohort có tổng Units ≥10.</div><div class="table-scroll">{table_html(idea_summary)}</div></div>
    <div class="card"><h2>Product · 30% Output / 20% Efficiency / 50% Business</h2><div class="desc">Portfolio ≥10 Units dùng toàn bộ Record ID thuộc ownership; Listing Cohort từ {cohort_start:%d/%m/%Y} đến {end:%d/%m/%Y}; Sold là Record ID trong cohort có tổng Units ≥10.</div><div class="table-scroll">{table_html(product_summary)}</div></div>
    <div class="card"><h2>Product Support · 80% Output / 20% Asset</h2><div class="table-scroll">{table_html(support_summary)}</div></div>
    <div class="card"><h2>Ads · 45% Efficiency / 55% Business</h2><div class="desc">Tháng này Ads cohort tạm dùng Custom Check Done Date từ {cohort_start:%d/%m/%Y} đến {end:%d/%m/%Y}. New Winner là Record ID trong cohort có Revenue tháng ≥$5K. Các mốc Revenue dùng toàn bộ portfolio ownership.</div><div class="table-scroll">{table_html(ads_display)}</div></div></section>
    <div class="footer">Atlas Performance OS · Generated {generated_at} · Order snapshot source {escape(str(updated))}</div></main></div>
    <script>document.querySelectorAll('[data-page]').forEach(b=>b.addEventListener('click',()=>{{document.querySelectorAll('[data-page]').forEach(x=>x.classList.toggle('active',x===b));document.querySelectorAll('.page').forEach(x=>x.classList.toggle('active',x.id===b.dataset.page));window.scrollTo(0,0)}}));</script></body></html>"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    print(output.resolve())


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Atlas dashboard to one static HTML file")
    parser.add_argument("--month", required=True, help="Month in YYYY-MM")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    destination = args.output or PROJECT_ROOT / "exports" / f"atlas-performance-{args.month}.html"
    export(args.month, destination)


if __name__ == "__main__":
    main()
