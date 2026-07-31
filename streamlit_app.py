from __future__ import annotations

import hmac

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from lark_data import LarkConfig, fetch_lark_frames


st.set_page_config(
    page_title="Atlas Performance OS",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    :root { --ink:#172033; --muted:#7b8494; --line:#e7eaf0; --orange:#ff7b2c; }
    .stApp { background:#f4f6f8; color:var(--ink); }
    [data-testid="stSidebar"] { background:#131b2b; }
    [data-testid="stSidebar"] * { color:#e9eef7; }
    [data-testid="stSidebar"] .stRadio label {
        padding:.52rem .7rem; border-radius:.6rem; margin:.12rem 0;
    }
    [data-testid="stMetric"] {
        background:#fff; border:1px solid var(--line); border-radius:14px;
        padding:1rem 1.1rem; min-height:132px; box-shadow:0 8px 25px #1d2a4310;
    }
    [data-testid="stMetricLabel"] { color:var(--muted); font-size:.82rem; }
    [data-testid="stMetricValue"] { color:var(--ink); font-weight:750; }
    .atlas-eyebrow { color:#8791a3; font-size:.72rem; font-weight:800; letter-spacing:.14em; }
    .atlas-title { font-size:2.25rem; line-height:1.1; font-weight:780; margin:.2rem 0 .4rem; }
    .atlas-subtitle { color:var(--muted); font-size:.9rem; margin-bottom:1rem; }
    .atlas-notice {
        display:flex; gap:1rem; align-items:center; padding:.8rem 1rem; margin:.5rem 0 1rem;
        border:1px solid #f3ddca; border-radius:12px; background:#fff7ef; font-size:.8rem;
    }
    .atlas-notice strong { color:#d86721; white-space:nowrap; }
    .atlas-card {
        background:#fff; border:1px solid var(--line); border-radius:14px;
        padding:1rem 1.1rem; margin:.3rem 0 .8rem; box-shadow:0 8px 25px #1d2a430a;
    }
    .atlas-card h3 { margin:.15rem 0 .7rem; font-size:1.05rem; }
    .kpi-strip {
        display:grid; grid-template-columns:repeat(5,1fr); gap:.65rem; padding:1rem;
        background:linear-gradient(135deg,#151d2e,#26334d); border-radius:14px; margin:.5rem 0 1rem;
    }
    .kpi-strip div { background:#ffffff10; border:1px solid #ffffff14; border-radius:10px; padding:.85rem; }
    .kpi-strip span { display:block; color:#b8c3d5; font-size:.7rem; }
    .kpi-strip strong { display:block; color:#fff; font-size:1.7rem; margin:.3rem 0; }
    .kpi-strip small { color:#8291a9; font-size:.62rem; }
    .team-card { border-top:3px solid #756ee9; }
    .team-card.idea { border-top-color:#a881d8; }
    .team-card.product { border-top-color:#f0a45f; }
    .team-card.support { border-top-color:#d581b7; }
    .team-card.ads { border-top-color:#68bd72; }
    .team-row { display:flex; justify-content:space-between; gap:1rem; border-top:1px solid #eef0f3; padding:.6rem 0; font-size:.78rem; }
    .team-row b { text-align:right; }
    .pending {
        border-left:4px solid #f2ad5b; background:#fff; border-radius:12px; padding:1rem;
        color:#667084; font-size:.82rem; margin-top:.6rem;
    }
    @media (max-width:900px) { .kpi-strip { grid-template-columns:repeat(2,1fr); } }
    </style>
    """,
    unsafe_allow_html=True,
)


WR_DAILY = [
    (1, 5095.63, 125), (2, 5274.80, 137), (3, 5311.88, 139), (4, 5595.23, 137),
    (5, 5165.47, 125), (6, 5379.87, 119), (7, 4549.11, 117), (8, 4937.62, 126),
    (9, 4679.64, 123), (10, 5969.97, 145), (11, 5810.55, 144), (12, 5094.08, 123),
    (13, 4988.11, 122), (14, 4701.60, 125), (15, 4657.36, 116), (16, 5735.88, 129),
    (17, 5938.66, 150), (18, 7179.23, 165), (19, 5322.59, 127), (20, 6060.80, 150),
    (21, 4955.93, 118), (22, 4475.10, 111), (23, 6764.84, 164), (24, 5368.02, 134),
    (25, 6890.09, 154), (26, 7385.62, 163), (27, 6210.97, 148), (28, 6574.70, 159),
    (29, 7480.29, 172), (30, 8054.91, 185),
]
PAW_DAILY = [
    (1, 56.96, 1), (3, 33.92, 1), (4, 46.96, 1), (6, 13.99, 1),
    (8, 49.94, 1), (9, 85.93, 2), (12, 49.94, 1), (15, 87.90, 2),
    (16, 54.94, 1), (20, 31.94, 1), (21, 45.96, 1), (22, 49.94, 1),
    (24, 51.97, 1), (25, 56.95, 1), (27, 54.91, 2), (28, 41.97, 1), (30, 127.88, 3),
]
WR_PRODUCTS = [
    ("B0H6ZMZB47", 15323.98, 324, 333), ("B0H2DKV9DX", 8565.76, 212, 228),
    ("B0H74N9R19", 6003.91, 161, 165), ("B0H4F3CH6Z", 4776.77, 105, 105),
    ("B0H6K1BPTT", 3701.35, 110, 117), ("B0H8MM9XTM", 2800.04, 59, 62),
    ("B0H5C6QV2Z", 2706.91, 75, 88), ("B0H4Y8MRCX", 2686.21, 54, 56),
]
PAW_PRODUCTS = [
    ("B0H5HVQF6X", 149.82, 3, 3), ("B0GQG7D7S5", 103.92, 2, 2),
    ("B0H2XGQZJZ", 56.95, 1, 1), ("B0H6J752YY", 54.94, 1, 1),
    ("B0FD2J9HDB", 51.97, 1, 1), ("B0H1LTN61J", 49.95, 1, 1),
    ("B0GS4MMPWX", 45.96, 1, 1), ("B0GQG6RNQB", 45.96, 1, 1),
]

STORES = {
    "Wrappiness": dict(
        raw=4652, cancelled=220, valid=4432, revenue=171608.55, orders=4152, units=4680,
        asins=849, fba_revenue=4731.25, fbm_revenue=166877.30, fba_orders=263,
        fbm_orders=3889, daily=WR_DAILY, products=WR_PRODUCTS,
    ),
    "Pawsionate": dict(
        raw=23, cancelled=1, valid=22, revenue=942.00, orders=22, units=22,
        asins=19, fba_revenue=13.99, fbm_revenue=928.01, fba_orders=1,
        fbm_orders=21, daily=PAW_DAILY, products=PAW_PRODUCTS,
    ),
}

ADS = {
    "Wrappiness": dict(spend=36673.65, sales=99380.14, orders=3028, impressions=3687409, clicks=46441),
    "Pawsionate": dict(spend=152.17, sales=342.68, orders=8, impressions=25919, clicks=224),
}

ADS_BY_TYPE = {
    "Wrappiness": {
        "SP": dict(spend=34041.91, sales=92526.08, orders=2779, impressions=3273038, clicks=41630),
        "SB": dict(spend=2631.74, sales=6854.06, orders=249, impressions=414301, clicks=4811),
        "SD": dict(spend=0.0, sales=0.0, orders=0, impressions=70, clicks=0),
    },
    "Pawsionate": {
        "SP": dict(spend=152.17, sales=342.68, orders=8, impressions=25919, clicks=224),
        "SB": dict(spend=0.0, sales=0.0, orders=0, impressions=0, clicks=0),
        "SD": dict(spend=0.0, sales=0.0, orders=0, impressions=0, clicks=0),
    },
}

EMPLOYEES = {
    "Idea By": [("Gary / Minh Hiếu / MRnD", 120)],
    "Listing By": [
        ("Sammie / Nhật Hạ", 154), ("Phương Linh", 103), ("Ngô Minh Hiếu", 12),
        ("Domi / Quỳnh", 12), ("Katythy / Nhi / Phương", 3),
    ],
    "Custom By": [
        ("Yến / Ny", 146), ("Hazel / Gia Hân", 143), ("Myllie / Thiên Ân", 11),
        ("Phương Linh", 9), ("Thu Trang", 9), ("Ánh Như", 6),
    ],
    "EBC By": [("Sammie / Nhật Hạ", 24), ("Phương Linh", 17)],
    "Ads By": [
        ("Domi / Quỳnh", 120), ("Katythy / Phương", 100),
        ("Trương Ý Nhi", 58), ("Unassigned / khác", 6),
    ],
}

REPORT_START = pd.Timestamp("2026-07-01")
REPORT_END = pd.Timestamp("2026-07-31 23:59:59")
COHORT_START = REPORT_START - pd.DateOffset(months=19)


def money(value: float) -> str:
    return f"${value:,.0f}"


def donut_chart(frame: pd.DataFrame, names: str, values: str, colors: list[str], height: int = 260):
    figure = px.pie(
        frame,
        names=names,
        values=values,
        hole=0.58,
        color_discrete_sequence=colors,
    )
    figure.update_traces(
        textposition="inside",
        texttemplate="%{label}<br>%{percent:.2%}",
        hovertemplate="%{label}<br>$%{value:,.2f}<br>%{percent:.2%}<extra></extra>",
        marker={"line": {"color": "#ffffff", "width": 2}},
    )
    figure.update_layout(
        height=height,
        margin={"l": 8, "r": 8, "t": 8, "b": 8},
        showlegend=True,
        legend={"orientation": "h", "y": -0.08, "x": 0.5, "xanchor": "center"},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return figure


def ads_type_frame(store_name: str) -> pd.DataFrame:
    stores = list(ADS_BY_TYPE) if store_name == "All Stores" else [store_name]
    rows = []
    for ads_type in ("SP", "SB", "SD"):
        row = {
            metric: sum(ADS_BY_TYPE[name][ads_type][metric] for name in stores)
            for metric in ("spend", "sales", "orders", "impressions", "clicks")
        }
        row["Ads Type"] = ads_type
        rows.append(row)
    frame = pd.DataFrame(rows)
    total_spend = float(frame["spend"].sum())
    total_sales = float(frame["sales"].sum())
    frame["Spend Share"] = frame["spend"].div(total_spend if total_spend else 1)
    frame["Sales Share"] = frame["sales"].div(total_sales if total_sales else 1)
    frame["ACOS"] = frame["spend"].div(frame["sales"].where(frame["sales"].ne(0)))
    frame["ROAS"] = frame["sales"].div(frame["spend"].where(frame["spend"].ne(0)))
    frame["CPC"] = frame["spend"].div(frame["clicks"].where(frame["clicks"].ne(0)))
    frame["CVR"] = frame["orders"].div(frame["clicks"].where(frame["clicks"].ne(0)))
    frame["CTR"] = frame["clicks"].div(frame["impressions"].where(frame["impressions"].ne(0)))
    return frame


def daily_frame(store_name: str) -> pd.DataFrame:
    if store_name == "All Stores":
        left = {d: (r, o) for d, r, o in WR_DAILY}
        right = {d: (r, o) for d, r, o in PAW_DAILY}
        rows = [
            (d, left.get(d, (0, 0))[0] + right.get(d, (0, 0))[0],
             left.get(d, (0, 0))[1] + right.get(d, (0, 0))[1])
            for d in range(1, 31)
        ]
    else:
        source = {d: (r, o) for d, r, o in STORES[store_name]["daily"]}
        rows = [(d, *source.get(d, (0, 0))) for d in range(1, 31)]
    return pd.DataFrame(rows, columns=["Day", "Revenue", "Orders"]).set_index("Day")


def active_store(store_name: str) -> dict:
    if store_name != "All Stores":
        return STORES[store_name]
    return {
        key: sum(STORES[name][key] for name in STORES)
        for key in [
            "raw", "cancelled", "valid", "revenue", "orders", "units", "asins",
            "fba_revenue", "fbm_revenue", "fba_orders", "fbm_orders",
        ]
    } | {"products": WR_PRODUCTS}


def aggregate_order_report(uploaded_file, store_name: str) -> pd.DataFrame:
    uploaded_file.seek(0)
    frame = pd.read_csv(uploaded_file, sep="\t", dtype=str)
    required = {
        "purchase-date",
        "order-status",
        "currency",
        "asin",
        "item-price",
        "shipping-price",
        "quantity",
        "amazon-order-id",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Order report {store_name} thiếu cột: {', '.join(missing)}")
    for column in ("item-price", "shipping-price", "quantity"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0)
    frame["purchase_date_pacific"] = (
        pd.to_datetime(frame["purchase-date"], errors="coerce", utc=True)
        .dt.tz_convert("America/Los_Angeles")
    )
    valid = frame[
        frame["order-status"].fillna("").str.casefold().ne("cancelled")
        & frame["currency"].eq("USD")
        & frame["purchase_date_pacific"].dt.date.between(
            REPORT_START.date(),
            pd.Timestamp("2026-07-30").date(),
        )
    ].copy()
    valid["Revenue"] = valid["item-price"] + valid["shipping-price"]
    result = (
        valid.groupby("asin", as_index=False)
        .agg(
            Revenue=("Revenue", "sum"),
            Orders=("amazon-order-id", "nunique"),
            Units=("quantity", "sum"),
        )
        .rename(columns={"asin": "ASIN"})
    )
    result["ASIN"] = result["ASIN"].astype(str).str.upper().str.strip()
    result.insert(0, "Store", store_name)
    return result


def secret_value(name: str) -> str:
    try:
        return str(st.secrets.get(name, "")).strip()
    except Exception:
        return ""


def lark_config() -> tuple[LarkConfig | None, list[str]]:
    names = [
        "LARK_APP_ID",
        "LARK_APP_SECRET",
        "LARK_BASE_TOKEN",
        "LARK_TOTAL_ASIN_TABLE_ID",
        "LARK_MRND_IDEA_TABLE_ID",
        "LARK_CLIPARTS_TABLE_ID",
    ]
    values = {name: secret_value(name) for name in names}
    missing = [name for name, value in values.items() if not value]
    if missing:
        return None, missing
    return (
        LarkConfig(
            app_id=values["LARK_APP_ID"],
            app_secret=values["LARK_APP_SECRET"],
            base_token=values["LARK_BASE_TOKEN"],
            total_asin_table_id=values["LARK_TOTAL_ASIN_TABLE_ID"],
            mrnd_idea_table_id=values["LARK_MRND_IDEA_TABLE_ID"],
            cliparts_table_id=values["LARK_CLIPARTS_TABLE_ID"],
        ),
        [],
    )


@st.cache_data(ttl=600, show_spinner=False)
def cached_lark_frames(config: LarkConfig, schema_version: str = "lark-kpi-v4") -> dict:
    del schema_version
    return fetch_lark_frames(config)


def in_report_month(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce")
    return parsed.between(REPORT_START, REPORT_END)


def workflow_lead_days(start: pd.Series, end: pd.Series) -> pd.Series:
    """Return valid stage lead times completed in the reporting month."""
    start_dates = pd.to_datetime(start, errors="coerce")
    end_dates = pd.to_datetime(end, errors="coerce")
    lead = (end_dates - start_dates).dt.total_seconds().div(86400)
    return lead.where(in_report_month(end_dates) & lead.ge(0))


def first_nonempty(series: pd.Series) -> str:
    for value in series:
        if pd.notna(value) and str(value).strip():
            return str(value).strip()
    return ""


def prepare_attribution(lark: dict, store_name: str, performance: pd.DataFrame) -> dict:
    total = lark["total"].copy()
    ideas = lark["ideas"].copy()
    cliparts = lark["cliparts"].copy()
    performance = performance.copy()
    if store_name != "All Stores":
        performance = performance[performance["Store"].eq(store_name)]
    asin_performance = (
        performance.groupby("ASIN", as_index=False)
        .agg(Revenue=("Revenue", "sum"), Orders=("Orders", "sum"), Units=("Units", "sum"))
    )

    if total.empty:
        return {
            "total": total,
            "records": pd.DataFrame(),
            "cliparts": cliparts,
            "coverage": 0.0,
            "duplicate_asins": 0,
        }

    total = total.drop_duplicates(["record_id", "asin"])
    duplicate_asins = int(total.groupby("asin")["record_id"].nunique().gt(1).sum())
    asin_owner = total.sort_values(["asin", "record_id"]).drop_duplicates("asin", keep="first")
    attributed_asins = asin_owner.merge(
        asin_performance,
        left_on="asin",
        right_on="ASIN",
        how="left",
    )
    for column in ("Revenue", "Orders", "Units"):
        attributed_asins[column] = attributed_asins[column].fillna(0)

    owner_columns = ["managed_by", "custom_by", "ads_by", "ads_status"]
    date_columns = [
        "date_pickup",
        "listing_done_date",
        "ps_pickup_date",
        "custom_done_date",
        "custom_check_done_date",
        "testing_start_date",
    ]
    aggregation = {
        **{column: first_nonempty for column in owner_columns},
        "product_name": first_nonempty,
        "image_url": first_nonempty,
        **{column: "min" for column in date_columns},
        "ads_launched": "max",
        "Revenue": "sum",
        "Orders": "sum",
        "Units": "sum",
        "asin": "nunique",
    }
    records = attributed_asins.groupby("record_id", as_index=False).agg(aggregation)
    records = records.rename(columns={"asin": "asin_count"})

    if not ideas.empty:
        idea_owner = (
            ideas.sort_values("handover_date", na_position="last")
            .groupby("record_id", as_index=False)
            .agg(idea_by=("idea_by", first_nonempty), handover_date=("handover_date", "min"))
        )
        records = records.merge(idea_owner, on="record_id", how="left")
    else:
        records["idea_by"] = ""
        records["handover_date"] = pd.NaT
    records["idea_by"] = records["idea_by"].fillna("")

    total_revenue = float(asin_performance["Revenue"].sum())
    attributed_revenue = float(attributed_asins["Revenue"].sum())
    return {
        "total": total,
        "records": records,
        "attributed_asins": attributed_asins,
        "cliparts": cliparts,
        "coverage": attributed_revenue / total_revenue if total_revenue else 0.0,
        "duplicate_asins": duplicate_asins,
    }


def employee_kpi_tables(attribution: dict, hero_threshold: float) -> dict[str, pd.DataFrame]:
    records = attribution["records"].copy()
    attributed_asins = attribution.get("attributed_asins", pd.DataFrame()).copy()
    cliparts = attribution["cliparts"].copy()
    if records.empty:
        return {}

    records["hero"] = records["Revenue"].ge(hero_threshold)
    records["validated"] = records["Units"].ge(10)
    records["listing_lead_days"] = workflow_lead_days(
        records["date_pickup"], records["listing_done_date"]
    )
    records["custom_lead_days"] = workflow_lead_days(
        records["listing_done_date"], records["custom_done_date"]
    )
    records["pd_check_days"] = workflow_lead_days(
        records["custom_done_date"], records["custom_check_done_date"]
    )
    records["ads_lead_days"] = workflow_lead_days(
        records["custom_check_done_date"], records["testing_start_date"]
    )

    def base_owner_frame(column: str) -> pd.DataFrame:
        return records[records[column].fillna("").str.strip().ne("")].copy()

    idea = base_owner_frame("idea_by")
    idea["qualified"] = in_report_month(idea["handover_date"])
    idea["validated_idea"] = idea["qualified"] & idea["validated"]
    idea_table = (
        idea.groupby("idea_by", as_index=False)
        .agg(
            Qualified_Ideas=("qualified", "sum"),
            Validated_Records=("validated_idea", "sum"),
            Hero_Estimate=("hero", "sum"),
            Revenue=("Revenue", "sum"),
        )
        .rename(columns={"idea_by": "Nhân sự"})
    )
    idea_table["Validated_Rate"] = (
        idea_table["Validated_Records"] / idea_table["Qualified_Ideas"].where(
            idea_table["Qualified_Ideas"].ne(0)
        )
    )

    product_records = base_owner_frame("managed_by")
    product_asins = attributed_asins[
        attributed_asins["managed_by"].fillna("").str.strip().ne("")
    ].copy()
    product_asins["qualified"] = in_report_month(product_asins["custom_check_done_date"])
    product_output = (
        product_asins.groupby("managed_by", as_index=False)
        .agg(Qualified_ASINs=("qualified", "sum"))
        .rename(columns={"managed_by": "Nhân sự"})
    )
    product_table = (
        product_records.groupby("managed_by", as_index=False)
        .agg(
            Portfolio_Records=("record_id", "nunique"),
            Sold_Records=("validated", "sum"),
            Portfolio_Revenue=("Revenue", "sum"),
            Listing_Lead_Days=("listing_lead_days", "mean"),
        )
        .rename(columns={"managed_by": "Nhân sự"})
        .merge(product_output, on="Nhân sự", how="left")
    )
    product_table["Qualified_ASINs"] = product_table["Qualified_ASINs"].fillna(0)
    product_table["Sold_Rate"] = (
        product_table["Sold_Records"]
        / product_table["Portfolio_Records"].where(product_table["Portfolio_Records"].ne(0))
    )

    support_records = base_owner_frame("custom_by")
    support_asins = attributed_asins[
        attributed_asins["custom_by"].fillna("").str.strip().ne("")
    ].copy()
    support_asins["qualified"] = in_report_month(support_asins["custom_check_done_date"])
    support_output = (
        support_asins.groupby("custom_by", as_index=False)
        .agg(Qualified_Custom_ASINs=("qualified", "sum"))
        .rename(columns={"custom_by": "Nhân sự"})
    )
    support_table = (
        support_records.groupby("custom_by", as_index=False)
        .agg(
            Portfolio_Records=("record_id", "nunique"),
            Custom_Lead_Days=("custom_lead_days", "mean"),
            PD_Check_Days=("pd_check_days", "mean"),
        )
        .rename(columns={"custom_by": "Nhân sự"})
        .merge(support_output, on="Nhân sự", how="left")
    )
    support_table["Qualified_Custom_ASINs"] = support_table["Qualified_Custom_ASINs"].fillna(0)
    if not cliparts.empty:
        cliparts_month = cliparts[in_report_month(cliparts["created_date"])]
        points = (
            cliparts_month[cliparts_month["employee"].fillna("").str.strip().ne("")]
            .groupby("employee", as_index=False)
            .agg(Asset_Points=("asset_points", "sum"))
            .rename(columns={"employee": "Nhân sự"})
        )
        support_table = support_table.merge(points, on="Nhân sự", how="left")
    support_table["Asset_Points"] = support_table.get("Asset_Points", 0)
    support_table["Asset_Points"] = support_table["Asset_Points"].fillna(0)

    ads = base_owner_frame("ads_by")
    ads["tested_in_month"] = in_report_month(ads["testing_start_date"])
    ads_table = (
        ads.groupby("ads_by", as_index=False)
        .agg(
            Ownership_Records=("record_id", "nunique"),
            Launched_Records=("ads_launched", "sum"),
            Ads_Tested=("tested_in_month", "sum"),
            Hero_Estimate=("hero", "sum"),
            Portfolio_Revenue=("Revenue", "sum"),
        )
        .rename(columns={"ads_by": "Nhân sự"})
    )
    ads_table["Testing_Coverage"] = (
        ads_table["Launched_Records"]
        / ads_table["Ownership_Records"].where(ads_table["Ownership_Records"].ne(0))
    )
    return {
        "Idea": idea_table.sort_values("Revenue", ascending=False),
        "Product Development": product_table.sort_values("Portfolio_Revenue", ascending=False),
        "Product Support": support_table.sort_values("Qualified_Custom_ASINs", ascending=False),
        "Ads Executive": ads_table.sort_values("Portfolio_Revenue", ascending=False),
    }


def team_access_granted() -> bool:
    expected = secret_value("DASHBOARD_PASSWORD")
    if not expected:
        st.warning(
            "Team KPI chứa dữ liệu nhân sự từ Lark. Hãy thêm DASHBOARD_PASSWORD "
            "trong Streamlit Secrets để bật phần này an toàn trên app public."
        )
        return False
    if st.session_state.get("team_authenticated"):
        return True
    password = st.text_input("Mật khẩu Team KPI", type="password")
    if st.button("Mở Team KPI", type="primary"):
        if hmac.compare_digest(password, expected):
            st.session_state["team_authenticated"] = True
            st.rerun()
        else:
            st.error("Mật khẩu không đúng.")
    return False


with st.sidebar:
    st.markdown("## 🟧 Atlas")
    st.caption("Performance OS")
    page = st.radio(
        "Điều hướng",
        ["01 · Tổng quan", "02 · Sản phẩm", "03 · Ads performance", "04 · Team KPI"],
        label_visibility="collapsed",
    )
    st.divider()
    st.markdown("**July demo**")
    st.caption("Order Report đã xử lý")
    st.caption("Pacific Time · Cancelled excluded\n\nFBA / FBM separated")


top_left, top_right = st.columns([2, 1])
with top_left:
    st.markdown('<div class="atlas-eyebrow">PERFORMANCE SNAPSHOT</div>', unsafe_allow_html=True)
    st.markdown('<div class="atlas-title">Tháng 07/2026</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="atlas-subtitle">Order Report thực tế · 01–30/07 theo Pacific Time</div>',
        unsafe_allow_html=True,
    )
with top_right:
    store = st.selectbox("Store", ["All Stores", "Pawsionate", "Wrappiness"])

data = active_store(store)
st.markdown(
    f'<div class="atlas-notice"><strong>{store}</strong><span>'
    f'{data["raw"]:,} dòng nguồn · loại {data["cancelled"]:,} Cancelled · '
    f'{data["valid"]:,} dòng hợp lệ. Revenue = Item Price + Shipping Price.</span></div>',
    unsafe_allow_html=True,
)


if page.startswith("01"):
    cols = st.columns(4)
    cols[0].metric("Net revenue", money(data["revenue"]), "USD · Item + Shipping")
    cols[1].metric("Orders", f'{data["orders"]:,}', f'{money(data["revenue"] / data["orders"])} / order')
    cols[2].metric("Units", f'{data["units"]:,}', f'{data["units"] / data["orders"]:.2f} units / order')
    cols[3].metric("Active ASINs", f'{data["asins"]:,}', "Có doanh thu USD")

    left, right = st.columns([2, 1])
    with left:
        st.markdown('<div class="atlas-card"><div class="atlas-eyebrow">DAILY REVENUE</div><h3>Revenue theo ngày</h3>', unsafe_allow_html=True)
        st.bar_chart(daily_frame(store)["Revenue"], color="#ff7b2c", height=310)
        st.markdown("</div>", unsafe_allow_html=True)
    with right:
        fulfillment = pd.DataFrame(
            {
                "Fulfillment": ["FBM", "FBA"],
                "Revenue": [data["fbm_revenue"], data["fba_revenue"]],
            }
        )
        st.markdown('<div class="atlas-card"><div class="atlas-eyebrow">FULFILLMENT</div><h3>Revenue split</h3>', unsafe_allow_html=True)
        st.plotly_chart(
            donut_chart(fulfillment, "Fulfillment", "Revenue", ["#756ee9", "#ff9d5c"], 245),
            width="stretch",
            config={"displayModeBar": False},
        )
        st.caption(f'{data["fbm_orders"]:,} FBM orders · {data["fba_orders"]:,} FBA orders')
        st.markdown("</div>", unsafe_allow_html=True)

    if store == "All Stores":
        store_share = pd.DataFrame(
            {
                "Store": ["Wrappiness", "Pawsionate"],
                "Revenue": [STORES["Wrappiness"]["revenue"], STORES["Pawsionate"]["revenue"]],
            }
        )
        st.markdown('<div class="atlas-card"><div class="atlas-eyebrow">REVENUE BY STORE</div><h3>Tỷ trọng Revenue hai store</h3>', unsafe_allow_html=True)
        st.plotly_chart(
            donut_chart(store_share, "Store", "Revenue", ["#40b6c8", "#ff9d5c"], 285),
            width="stretch",
            config={"displayModeBar": False},
        )
        st.markdown("</div>", unsafe_allow_html=True)

elif page.startswith("02"):
    st.markdown('<div class="atlas-card"><div class="atlas-eyebrow">PRODUCT PERFORMANCE</div><h3>Top sản phẩm theo Record ID</h3></div>', unsafe_allow_html=True)
    st.caption(
        "Tải order report để gộp toàn bộ ASIN cùng sản phẩm theo Record ID từ Lark. "
        "Share được tính trên tổng Revenue của store đang chọn."
    )
    product_uploads = {}
    upload_columns = st.columns(2)
    if store in {"All Stores", "Wrappiness"}:
        with upload_columns[0]:
            product_uploads["Wrappiness"] = st.file_uploader(
                "Wrappiness · Order report",
                type=["txt", "tsv", "csv"],
                key="product_wr_order",
            )
    if store in {"All Stores", "Pawsionate"}:
        with upload_columns[1]:
            product_uploads["Pawsionate"] = st.file_uploader(
                "Pawsionate · Order report",
                type=["txt", "tsv", "csv"],
                key="product_paw_order",
            )

    required_product_stores = (
        ["Wrappiness", "Pawsionate"] if store == "All Stores" else [store]
    )
    if all(product_uploads.get(name) is not None for name in required_product_stores):
        product_performance = pd.concat(
            [aggregate_order_report(product_uploads[name], name) for name in required_product_stores],
            ignore_index=True,
        )
        config, missing_secrets = lark_config()
        if missing_secrets:
            st.error("Thiếu Streamlit Secrets: " + ", ".join(missing_secrets))
        else:
            with st.spinner("Đang map Record ID và ảnh từ Lark Base…"):
                lark = cached_lark_frames(config)
            attribution = prepare_attribution(lark, store, product_performance)
            mapped_asins = set(attribution["total"]["asin"])
            selected_asins = set(product_performance["ASIN"])
            unmapped_asins = selected_asins.difference(mapped_asins)
            asin_coverage = 1 - len(unmapped_asins) / len(selected_asins) if selected_asins else 0
            revenue_coverage = attribution["coverage"]

            quality_columns = st.columns(3)
            quality_columns[0].metric("ASIN mapping", f"{asin_coverage:.2%}", f"{len(selected_asins) - len(unmapped_asins):,} / {len(selected_asins):,} ASIN")
            quality_columns[1].metric("Revenue mapping", f"{revenue_coverage:.2%}")
            quality_columns[2].metric("Unmapped ASIN", f"{len(unmapped_asins):,}")

            if unmapped_asins:
                st.error(
                    "Mapping chưa đạt 100%. Các ASIN bên dưới chưa tồn tại trong TOTAL ASIN "
                    "hoặc chưa có Record ID hợp lệ. Cập nhật Lark rồi tải lại để đạt 100%."
                )
                unmapped = (
                    product_performance[product_performance["ASIN"].isin(unmapped_asins)]
                    .groupby(["Store", "ASIN"], as_index=False)
                    .agg(Revenue=("Revenue", "sum"), Orders=("Orders", "sum"), Units=("Units", "sum"))
                    .sort_values("Revenue", ascending=False)
                )
                with st.expander("Danh sách ASIN chưa map", expanded=False):
                    st.dataframe(
                        unmapped,
                        hide_index=True,
                        width="stretch",
                        column_config={"Revenue": st.column_config.NumberColumn(format="$%.2f")},
                    )
                    st.download_button(
                        "Tải CSV ASIN chưa map",
                        unmapped.to_csv(index=False).encode("utf-8-sig"),
                        "unmapped_asins_july_2026.csv",
                        "text/csv",
                    )
            else:
                st.success("Mapping đạt 100%: toàn bộ ASIN có Record ID trong TOTAL ASIN.")

            products = attribution["records"].copy()
            products = products[products["Revenue"].gt(0)].sort_values("Revenue", ascending=False)
            total_revenue = float(product_performance["Revenue"].sum())
            products["Share"] = products["Revenue"].div(total_revenue if total_revenue else 1).mul(100)
            products.insert(0, "#", range(1, len(products) + 1))
            products = products.rename(
                columns={
                    "record_id": "Record ID",
                    "product_name": "Product",
                    "image_url": "Image",
                    "asin_count": "ASIN count",
                }
            )
            st.dataframe(
                products[["#", "Image", "Record ID", "Product", "ASIN count", "Revenue", "Orders", "Units", "Share"]].head(50),
                hide_index=True,
                width="stretch",
                row_height=64,
                column_config={
                    "Image": st.column_config.ImageColumn(width="small"),
                    "Revenue": st.column_config.NumberColumn(format="$%.2f"),
                    "Share": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.2f%%"),
                },
            )
    else:
        products = pd.DataFrame(data["products"], columns=["ASIN", "Revenue", "Orders", "Units"])
        products.insert(0, "#", range(1, len(products) + 1))
        products["Share"] = products["Revenue"].div(data["revenue"] or 1).mul(100)
        st.info("Tải đủ order report để gộp theo Record ID và kiểm tra mapping 100%.")
        st.dataframe(
            products,
            hide_index=True,
            width="stretch",
            column_config={
                "Revenue": st.column_config.NumberColumn(format="$%.2f"),
                "Share": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.2f%%"),
            },
        )

elif page.startswith("03"):
    if store == "All Stores":
        ads = {key: sum(ADS[name][key] for name in ADS) for key in ADS["Wrappiness"]}
    else:
        ads = ADS[store]
    cols = st.columns(4)
    cols[0].metric("Ad spend", money(ads["spend"]), f'{ads["spend"] / data["revenue"] * 100:.1f}% TACOS')
    cols[1].metric("Ad sales", money(ads["sales"]), f'{ads["sales"] / data["revenue"] * 100:.1f}% total revenue')
    cols[2].metric("ACOS", f'{ads["spend"] / ads["sales"] * 100:.1f}%', f'ROAS {ads["sales"] / ads["spend"]:.2f}')
    cols[3].metric("Ad orders", f'{ads["orders"]:,}', f'{ads["orders"] / ads["clicks"] * 100:.1f}% CVR')
    funnel = pd.DataFrame(
        {"Stage": ["Impressions", "Clicks", "PPC Orders"], "Volume": [ads["impressions"], ads["clicks"], ads["orders"]]}
    )
    st.markdown('<div class="atlas-card"><div class="atlas-eyebrow">ADS FUNNEL</div><h3>Traffic đến conversion</h3>', unsafe_allow_html=True)
    funnel_figure = go.Figure(
        go.Funnel(
            y=funnel["Stage"],
            x=funnel["Volume"],
            texttemplate="%{label}<br>%{value:,.0f}<br>%{percentInitial:.2%}",
            marker={"color": ["#756ee9", "#8f88f4", "#ff9d5c"]},
            connector={"line": {"color": "#d8dce5", "width": 1}},
            hovertemplate="%{label}: %{value:,.0f}<extra></extra>",
        )
    )
    funnel_figure.update_layout(
        height=330,
        margin={"l": 16, "r": 16, "t": 12, "b": 12},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(funnel_figure, width="stretch", config={"displayModeBar": False})
    st.caption(
        f'CTR {ads["clicks"] / ads["impressions"] * 100:.2f}% · '
        f'CVR {ads["orders"] / ads["clicks"] * 100:.2f}% · '
        f'CPC ${ads["spend"] / ads["clicks"]:.2f}'
    )
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="atlas-card"><div class="atlas-eyebrow">CAMPAIGN TYPE PERFORMANCE</div><h3>Hiệu quả theo Ads Type · SP / SB / SD</h3></div>', unsafe_allow_html=True)
    type_performance = ads_type_frame(store)
    total_row = pd.DataFrame(
        [
            {
                "Ads Type": "Total",
                "spend": type_performance["spend"].sum(),
                "sales": type_performance["sales"].sum(),
                "orders": type_performance["orders"].sum(),
                "impressions": type_performance["impressions"].sum(),
                "clicks": type_performance["clicks"].sum(),
                "Spend Share": 1.0,
                "Sales Share": 1.0,
            }
        ]
    )
    total_row["ACOS"] = total_row["spend"].div(total_row["sales"].where(total_row["sales"].ne(0)))
    total_row["ROAS"] = total_row["sales"].div(total_row["spend"].where(total_row["spend"].ne(0)))
    total_row["CPC"] = total_row["spend"].div(total_row["clicks"].where(total_row["clicks"].ne(0)))
    total_row["CVR"] = total_row["orders"].div(total_row["clicks"].where(total_row["clicks"].ne(0)))
    total_row["CTR"] = total_row["clicks"].div(total_row["impressions"].where(total_row["impressions"].ne(0)))
    type_display = pd.concat([total_row, type_performance], ignore_index=True).rename(
        columns={
            "spend": "Spend",
            "sales": "Sales",
            "orders": "PPC Orders",
            "impressions": "Impressions",
            "clicks": "Clicks",
            "Spend Share": "Spend %",
            "Sales Share": "Sales %",
        }
    )
    for rate_column in ("Spend %", "Sales %", "ACOS", "CVR", "CTR"):
        type_display[rate_column] = type_display[rate_column].mul(100)
    st.dataframe(
        type_display[
            ["Ads Type", "Spend", "Spend %", "Sales", "Sales %", "ACOS", "ROAS", "Impressions", "Clicks", "CPC", "CVR", "CTR", "PPC Orders"]
        ],
        hide_index=True,
        width="stretch",
        column_config={
            "Spend": st.column_config.NumberColumn(format="$%.2f"),
            "Spend %": st.column_config.NumberColumn(format="%.2f%%"),
            "Sales": st.column_config.NumberColumn(format="$%.2f"),
            "Sales %": st.column_config.NumberColumn(format="%.2f%%"),
            "ACOS": st.column_config.NumberColumn(format="%.2f%%"),
            "ROAS": st.column_config.NumberColumn(format="%.2f"),
            "Impressions": st.column_config.NumberColumn(format="%d"),
            "Clicks": st.column_config.NumberColumn(format="%d"),
            "CPC": st.column_config.NumberColumn(format="$%.2f"),
            "CVR": st.column_config.NumberColumn(format="%.2f%%"),
            "CTR": st.column_config.NumberColumn(format="%.2f%%"),
            "PPC Orders": st.column_config.NumberColumn(format="%d"),
        },
    )

else:
    st.markdown("## Team KPI · Record-level")
    st.caption(
        "Dữ liệu nhân sự lấy trực tiếp từ Lark Base. Revenue tháng 07/2026 được nối "
        "từ ASIN của order report USD, đã loại Cancelled."
    )
    if team_access_granted():
        config, missing_secrets = lark_config()
        if missing_secrets:
            st.error("Thiếu Streamlit Secrets: " + ", ".join(missing_secrets))
        else:
            st.info(
                "Order report được xử lý trong bộ nhớ của phiên đăng nhập và không được "
                "lưu vào repository public."
            )
            upload_cols = st.columns(2)
            with upload_cols[0]:
                wrappiness_report = st.file_uploader(
                    "Wrappiness · Order report tháng 07/2026",
                    type=["txt", "tsv", "csv"],
                    key="wrappiness_order_report",
                )
            with upload_cols[1]:
                pawsionate_report = st.file_uploader(
                    "Pawsionate · Order report tháng 07/2026",
                    type=["txt", "tsv", "csv"],
                    key="pawsionate_order_report",
                )
            required_uploads = {
                "Wrappiness": wrappiness_report,
                "Pawsionate": pawsionate_report,
            }
            selected_stores = (
                ["Wrappiness", "Pawsionate"] if store == "All Stores" else [store]
            )
            missing_reports = [
                name for name in selected_stores if required_uploads[name] is None
            ]
            if missing_reports:
                st.warning(
                    "Hãy tải order report của: " + ", ".join(missing_reports)
                    + ". Không cần tải lại report của store không được chọn."
                )
                st.stop()
            performance = pd.concat(
                [
                    aggregate_order_report(required_uploads[name], name)
                    for name in selected_stores
                ],
                ignore_index=True,
            )
            hero_threshold = st.number_input(
                "Hero revenue threshold / Record ID",
                min_value=0.0,
                value=1000.0,
                step=100.0,
                help="Ngưỡng ước lượng Hero có thể đổi theo tình hình kinh doanh.",
            )
            try:
                with st.spinner("Đang đồng bộ Lark Base…"):
                    lark = cached_lark_frames(config)
                attribution = prepare_attribution(lark, store, performance)
                records = attribution["records"]
                tables = employee_kpi_tables(attribution, hero_threshold)

                counts = lark["record_counts"]
                st.success(
                    "Lark API connected · "
                    f'TOTAL ASIN {counts["TOTAL ASIN"]:,} records · '
                    f'MRND IDEA {counts["MRND IDEA"]:,} records · '
                    f'CLIPARTS {counts["CLIPARTS"]:,} records'
                )

                if records.empty:
                    st.error(
                        "API đã kết nối nhưng chưa tạo được mapping Record ID ↔ ASIN. "
                        "Mở Field diagnostics bên dưới để kiểm tra tên cột."
                    )
                else:
                    ads_tested = int(in_report_month(records["testing_start_date"]).sum())
                    listing_done = int(in_report_month(records["listing_done_date"]).sum())
                    custom_done = int(in_report_month(records["custom_check_done_date"]).sum())
                    idea_done = int(in_report_month(records["handover_date"]).sum())
                    if not idea_done:
                        idea_done = int(records.loc[records["idea_by"].ne(""), "record_id"].nunique())
                    cliparts_month = attribution["cliparts"][
                        in_report_month(attribution["cliparts"]["created_date"])
                    ]
                    asset_total = int(cliparts_month["asset_points"].sum())
                    launched = int(records["ads_launched"].sum())
                    owned_ads = int(records.loc[records["ads_by"].ne(""), "record_id"].nunique())
                    coverage = launched / owned_ads if owned_ads else 0

                    st.markdown(
                        f"""
                        <div class="kpi-strip">
                          <div><span>Qualified Ideas</span><strong>{idea_done:,}</strong><small>Unique Record ID</small></div>
                          <div><span>Listing Done</span><strong>{listing_done:,}</strong><small>Listing Done Date</small></div>
                          <div><span>Custom Check Done</span><strong>{custom_done:,}</strong><small>Qualified Custom ASIN</small></div>
                          <div><span>Asset Points</span><strong>{asset_total:,}</strong><small>CLIPARTS · July</small></div>
                          <div><span>Ads Tested</span><strong>{ads_tested:,}</strong><small>Testing Start Date</small></div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    listing_lead = workflow_lead_days(
                        records["date_pickup"], records["listing_done_date"]
                    ).dropna()
                    custom_lead = workflow_lead_days(
                        records["listing_done_date"], records["custom_done_date"]
                    ).dropna()
                    pd_check_lead = workflow_lead_days(
                        records["custom_done_date"], records["custom_check_done_date"]
                    ).dropna()
                    ads_lead = workflow_lead_days(
                        records["custom_check_done_date"], records["testing_start_date"]
                    ).dropna()
                    lead_cols = st.columns(5)
                    lead_cols[0].metric(
                        "Listing lead time",
                        f"{listing_lead.mean():.2f} days" if not listing_lead.empty else "—",
                    )
                    lead_cols[1].metric(
                        "PS lead time",
                        f"{custom_lead.mean():.2f} days" if not custom_lead.empty else "—",
                    )
                    lead_cols[2].metric(
                        "PD custom check",
                        f"{pd_check_lead.mean():.2f} days" if not pd_check_lead.empty else "—",
                    )
                    lead_cols[3].metric(
                        "Ads lead time",
                        f"{ads_lead.mean():.2f} days" if not ads_lead.empty else "—",
                    )
                    lead_cols[4].metric(
                        "Testing coverage",
                        f"{coverage:.1%}",
                        f"{launched:,} / {owned_ads:,} Record ID",
                    )

                    quality_cols = st.columns(3)
                    quality_cols[0].metric(
                        "Revenue mapped",
                        f'{attribution["coverage"]:.1%}',
                        "ASIN có Record ID trong TOTAL ASIN",
                    )
                    quality_cols[1].metric(
                        "Attributed revenue",
                        money(float(records["Revenue"].sum())),
                        f"{records['record_id'].nunique():,} Record ID",
                    )
                    quality_cols[2].metric(
                        "Hero estimate",
                        f'{int(records["Revenue"].ge(hero_threshold).sum()):,}',
                        f"Revenue ≥ {money(hero_threshold)}",
                    )

                    st.markdown("### KPI theo nhân sự")
                    for title, table in tables.items():
                        with st.expander(title, expanded=True):
                            display = table.copy()
                            integer_columns = [
                                column
                                for column in display.columns
                                if column
                                not in {
                                    "Nhân sự",
                                    "Revenue",
                                    "Portfolio_Revenue",
                                    "Validated_Rate",
                                    "Sold_Rate",
                                    "Testing_Coverage",
                                    "Listing_Lead_Days",
                                    "Custom_Lead_Days",
                                    "PD_Check_Days",
                                }
                            ]
                            for column in integer_columns:
                                display[column] = display[column].fillna(0).round().astype(int)
                            st.dataframe(
                                display,
                                hide_index=True,
                                width="stretch",
                                column_config={
                                    "Revenue": st.column_config.NumberColumn(format="$%.2f"),
                                    "Portfolio_Revenue": st.column_config.NumberColumn(format="$%.2f"),
                                    "Validated_Rate": st.column_config.NumberColumn(format="%.1%%"),
                                    "Sold_Rate": st.column_config.NumberColumn(format="%.1%%"),
                                    "Testing_Coverage": st.column_config.ProgressColumn(
                                        min_value=0, max_value=1, format="%.1%%"
                                    ),
                                    "Listing_Lead_Days": st.column_config.NumberColumn(format="%.2f"),
                                    "Custom_Lead_Days": st.column_config.NumberColumn(format="%.2f"),
                                    "PD_Check_Days": st.column_config.NumberColumn(format="%.2f"),
                                },
                            )

                with st.expander("Field diagnostics"):
                    st.json(
                        {
                            "field_mapping": lark["field_mapping"],
                            "available_fields": lark.get("available_fields", {}),
                        }
                    )
                    if attribution["duplicate_asins"]:
                        st.warning(
                            f'{attribution["duplicate_asins"]} ASIN đang map tới nhiều Record ID; '
                            "dashboard chỉ ghi nhận một Record ID để tránh nhân đôi Revenue."
                        )
            except Exception as exc:
                st.error(f"Không thể đồng bộ Lark API: {exc}")
                st.caption(
                    "Kiểm tra app đã publish, quyền Base đã được cấp và App ID/App Secret "
                    "trong Streamlit Secrets còn hiệu lực."
                )

st.caption("Atlas Performance OS · Internal dashboard · Order data as of 30 Jul 2026")
