from __future__ import annotations

import hmac
import importlib
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from ads_data import (
    load_ads_snapshot,
    load_encrypted_ads_snapshot,
    normalize_person,
    select_ads_summary,
)
from fulfillment_rules import apply_fulfillment_overrides
from lark_data import LarkConfig, fetch_image_data_urls, fetch_lark_frames, probe_image_download
import lark_snapshot_store as _lark_snapshot_store
from product_data import (
    fulfillment_revenue_frame,
    records_from_order_hints,
    revenue_milestone_counts,
    top_record_id_frame,
)
from snapshot_store import (
    SnapshotError,
    empty_snapshot,
    load_snapshot,
    load_snapshot_metadata,
)
import target_data as _target_data
from team_kpi import (
    asin_new_revenue_from_custom_cohort,
    asin_portfolio_revenue,
    fbm_asin_rows,
    workflow_kpi_window_end,
)


# Streamlit Cloud hot-reloads the app file but can retain an older imported
# module in the same process. Reload explicitly so a deployment that changes
# a snapshot schema never imports stale module functions.
_lark_snapshot_store = importlib.reload(_lark_snapshot_store)
LARK_SNAPSHOT_SCHEMA_VERSION = _lark_snapshot_store.SCHEMA_VERSION
load_encrypted_lark_snapshot = _lark_snapshot_store.load_encrypted_lark_snapshot
load_lark_snapshot = _lark_snapshot_store.load_lark_snapshot
save_lark_snapshot = _lark_snapshot_store.save_lark_snapshot
lark_snapshot_version = _lark_snapshot_store.snapshot_version
_target_data = importlib.reload(_target_data)
daily_targets_for_month = _target_data.daily_targets_for_month
load_fbm_target_snapshot = _target_data.load_fbm_target_snapshot
target_for_month = _target_data.target_for_month
target_progress = _target_data.target_progress


PERSISTED_SNAPSHOT_PATH = Path(__file__).with_name("snapshot") / "dashboard_snapshot.csv"
PERSISTED_LARK_SNAPSHOT_DIR = Path(__file__).with_name("snapshot") / "lark"
PUBLISHED_LARK_SNAPSHOT_PATH = (
    Path(__file__).with_name("snapshot") / "published_lark_snapshot.enc"
)
PERSISTED_ADS_SNAPSHOT_DIR = Path(__file__).with_name("snapshot") / "ads"
PUBLISHED_ADS_SNAPSHOT_PATH = (
    Path(__file__).with_name("snapshot") / "published_ads_snapshot.enc"
)
PERSISTED_FBM_TARGET_PATH = Path(__file__).with_name("snapshot") / "fbm_target.csv"


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
REPORT_END = pd.Timestamp("2026-07-30 23:59:59")
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


def daily_frame(store_name: str, month: str | None = None) -> pd.DataFrame:
    stores = list(STORES) if store_name == "All Stores" else [store_name]
    performance = selected_order_performance(stores, month)
    if performance.empty:
        return pd.DataFrame(columns=["Date", "Revenue", "Quantity", "Orders"])
    performance = performance.copy()
    performance["Date"] = pd.to_datetime(performance["Date"], errors="coerce")
    performance = performance.dropna(subset=["Date"])
    return (
        performance.groupby("Date", as_index=False)
        .agg(
            Revenue=("Revenue", "sum"),
            Quantity=("Units", "sum"),
            Orders=("Orders", "sum"),
        )
        .sort_values("Date")
    )


def daily_revenue_quantity_chart(frame: pd.DataFrame) -> go.Figure:
    figure = make_subplots(specs=[[{"secondary_y": True}]])
    figure.add_trace(
        go.Bar(
            x=frame["Date"],
            y=frame["Revenue"],
            name="Revenue",
            marker_color="#ff7b2c",
            hovertemplate="%{x|%d/%m/%Y}<br>Revenue: $%{y:,.2f}<extra></extra>",
        ),
        secondary_y=False,
    )
    figure.add_trace(
        go.Scatter(
            x=frame["Date"],
            y=frame["Quantity"],
            name="Quantity",
            mode="lines+markers",
            line={"color": "#0ea5a8", "width": 3},
            marker={"size": 7},
            hovertemplate="%{x|%d/%m/%Y}<br>Quantity: %{y:,.0f}<extra></extra>",
        ),
        secondary_y=True,
    )
    if "Forecast 2026" in frame and not frame.empty:
        figure.add_trace(
            go.Scatter(
                x=frame["Date"],
                y=frame["Forecast 2026"],
                name="Forecast 2026",
                mode="lines+markers",
                line={"color": "#2563eb", "width": 2, "dash": "dash"},
                marker={"size": 5},
                hovertemplate="%{x|%d/%m/%Y}<br>Forecast 2026: $%{y:,.2f}<extra></extra>",
            ),
            secondary_y=False,
        )
    if "Revenue 2025" in frame and not frame.empty:
        figure.add_trace(
            go.Scatter(
                x=frame["Date"],
                y=frame["Revenue 2025"],
                name="Revenue 2025",
                mode="lines+markers",
                line={"color": "#94a3b8", "width": 2},
                marker={"size": 5},
                hovertemplate="%{x|%d/%m/%Y}<br>Revenue 2025: $%{y:,.2f}<extra></extra>",
            ),
            secondary_y=False,
        )
    figure.update_xaxes(tickformat="%d/%m", title_text="Ngày")
    figure.update_yaxes(title_text="Revenue (USD)", tickprefix="$", secondary_y=False)
    figure.update_yaxes(title_text="Quantity", rangemode="tozero", secondary_y=True)
    figure.update_layout(
        height=340,
        margin={"l": 10, "r": 10, "t": 35, "b": 10},
        hovermode="x unified",
        legend={"orientation": "h", "y": 1.12, "x": 0},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        bargap=0.28,
    )
    return figure


def daily_fulfillment_frames(
    performance: pd.DataFrame,
    total_asins: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """Return aligned daily Revenue/Quantity frames for FBM and FBA."""
    empty = pd.DataFrame(columns=["Date", "Revenue", "Quantity", "Orders"])
    required_order = {"Date", "ASIN", "Revenue", "Orders", "Units"}
    required_total = {"asin", "record_id", "fulfill_by"}
    if (
        performance.empty
        or total_asins.empty
        or not required_order.issubset(performance.columns)
        or not required_total.issubset(total_asins.columns)
    ):
        return {"FBM": empty.copy(), "FBA": empty.copy()}

    dated = performance.copy()
    dated["Date"] = pd.to_datetime(dated["Date"], errors="coerce")
    dated = dated.dropna(subset=["Date"])
    if dated.empty:
        return {"FBM": empty.copy(), "FBA": empty.copy()}

    # Reuse the long-standing fulfillment summary function day by day. This
    # remains compatible with Streamlit Cloud processes that may still have an
    # older product_data module cached while a new commit is hot-reloaded.
    daily_parts: list[pd.DataFrame] = []
    for day, day_orders in dated.groupby("Date", sort=True):
        day_summary = fulfillment_revenue_frame(day_orders, total_asins)
        if day_summary.empty:
            continue
        day_summary = day_summary.copy()
        day_summary["Date"] = day
        daily_parts.append(day_summary)

    calendar = pd.DataFrame({"Date": sorted(dated["Date"].unique())})
    daily_summary = (
        pd.concat(daily_parts, ignore_index=True)
        if daily_parts
        else pd.DataFrame(columns=["Date", "Fulfill By", "Revenue", "Orders", "Units"])
    )
    result: dict[str, pd.DataFrame] = {}
    for fulfillment_type in ("FBM", "FBA"):
        daily = daily_summary[
            daily_summary["Fulfill By"].eq(fulfillment_type)
        ][["Date", "Revenue", "Units", "Orders"]].rename(
            columns={"Units": "Quantity"}
        )
        daily = calendar.merge(daily, on="Date", how="left")
        daily[["Revenue", "Quantity", "Orders"]] = daily[
            ["Revenue", "Quantity", "Orders"]
        ].fillna(0)
        result[fulfillment_type] = daily.sort_values("Date").reset_index(drop=True)
    return result


def active_store(store_name: str, month: str | None = None) -> dict:
    fallback = STORES[store_name] if store_name != "All Stores" else {
        key: sum(STORES[name][key] for name in STORES)
        for key in [
            "raw", "cancelled", "valid", "revenue", "orders", "units", "asins",
            "fba_revenue", "fbm_revenue", "fba_orders", "fbm_orders",
        ]
    } | {"products": WR_PRODUCTS}
    stores = list(STORES) if store_name == "All Stores" else [store_name]
    performance = selected_order_performance(stores, month)
    if performance.empty:
        return fallback | {"snapshot_rows": 0, "snapshot_backed": False}
    return fallback | {
        "revenue": float(performance["Revenue"].sum()),
        "orders": int(performance["Orders"].sum()),
        "units": int(performance["Units"].sum()),
        "asins": int(performance["ASIN"].nunique()),
        "snapshot_rows": len(performance),
        "snapshot_backed": True,
    }


@st.cache_data(show_spinner=False)
def persisted_order_performance(
    snapshot_version: int,
    snapshot_schema_version: int,
) -> pd.DataFrame:
    del snapshot_version, snapshot_schema_version
    try:
        frame = load_snapshot(PERSISTED_SNAPSHOT_PATH)
    except SnapshotError:
        return empty_snapshot()
    return frame


def selected_order_performance(
    stores: list[str],
    month: str | None = None,
) -> pd.DataFrame:
    snapshot_version = (
        PERSISTED_SNAPSHOT_PATH.stat().st_mtime_ns
        if PERSISTED_SNAPSHOT_PATH.exists()
        else 0
    )
    persisted = persisted_order_performance(snapshot_version, 2)
    selected = persisted[persisted["Store"].isin(stores)].copy()
    if month and not selected.empty:
        dates = pd.to_datetime(selected["Date"], errors="coerce")
        selected = selected[dates.dt.strftime("%Y-%m").eq(month)].copy()
    return selected


def available_order_months() -> list[str]:
    persisted = selected_order_performance(list(STORES))
    if persisted.empty:
        return [REPORT_START.strftime("%Y-%m")]
    dates = pd.to_datetime(persisted["Date"], errors="coerce")
    months = sorted(dates.dt.strftime("%Y-%m").dropna().unique(), reverse=True)
    return months or [REPORT_START.strftime("%Y-%m")]


def live_ads_performance(
    month: str,
    store_name: str,
) -> tuple[dict[str, float], pd.DataFrame, list[dict]]:
    snapshot = current_ads_snapshot()
    summary, imports = select_ads_summary(snapshot, month, store_name)
    by_type = {
        kind: {metric: 0.0 for metric in ("spend", "sales", "orders", "impressions", "clicks")}
        for kind in ("SP", "SB", "SD")
    }
    for item in imports:
        for kind, metrics in item.get("diagnostics", {}).get("by_type", {}).items():
            if kind not in by_type:
                continue
            for metric in by_type[kind]:
                by_type[kind][metric] += float(metrics.get(metric, 0))
    frame = pd.DataFrame(
        [{"Ads Type": kind, **metrics} for kind, metrics in by_type.items()]
    )
    total_spend = float(frame["spend"].sum())
    total_sales = float(frame["sales"].sum())
    frame["Spend Share"] = frame["spend"].div(total_spend if total_spend else 1)
    frame["Sales Share"] = frame["sales"].div(total_sales if total_sales else 1)
    frame["ACOS"] = frame["spend"].div(frame["sales"].where(frame["sales"].ne(0)))
    frame["ROAS"] = frame["sales"].div(frame["spend"].where(frame["spend"].ne(0)))
    frame["CPC"] = frame["spend"].div(frame["clicks"].where(frame["clicks"].ne(0)))
    frame["CVR"] = frame["orders"].div(frame["clicks"].where(frame["clicks"].ne(0)))
    frame["CTR"] = frame["clicks"].div(frame["impressions"].where(frame["impressions"].ne(0)))
    totals = {
        "spend": float(summary["Ads_Spend"].sum()) if not summary.empty else 0.0,
        "sales": float(summary["Ads_Sales"].sum()) if not summary.empty else 0.0,
        "orders": float(summary["Ads_Orders"].sum()) if not summary.empty else 0.0,
        "impressions": float(frame["impressions"].sum()),
        "clicks": float(frame["clicks"].sum()),
    }
    return totals, frame, imports


def current_ads_snapshot() -> dict | None:
    local = load_ads_snapshot(PERSISTED_ADS_SNAPSHOT_DIR)
    if local is not None:
        return local
    return load_encrypted_ads_snapshot(
        PUBLISHED_ADS_SNAPSHOT_PATH,
        dashboard_data_key(),
    )


def secret_value(name: str) -> str:
    try:
        return str(st.secrets.get(name, "")).strip()
    except Exception:
        return ""


def dashboard_data_key() -> str:
    """Return the shared snapshot key, preferring the Cloud-facing name."""
    return secret_value("DASHBOARD_DATA_KEY") or secret_value(
        "PUBLISHED_SNAPSHOT_KEY"
    )


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


@st.cache_data(show_spinner=False)
def persisted_lark_frames(snapshot_version: int, schema_version: str) -> dict | None:
    del snapshot_version, schema_version
    return load_lark_snapshot(PERSISTED_LARK_SNAPSHOT_DIR)


@st.cache_data(show_spinner=False)
def published_lark_frames(
    snapshot_version: int,
    schema_version: str,
    publish_key: str,
) -> dict | None:
    del snapshot_version, schema_version
    return load_encrypted_lark_snapshot(PUBLISHED_LARK_SNAPSHOT_PATH, publish_key)


def latest_lark_frames(config: LarkConfig, refresh: bool = False) -> dict:
    version = lark_snapshot_version(PERSISTED_LARK_SNAPSHOT_DIR)
    local_saved = persisted_lark_frames(version, LARK_SNAPSHOT_SCHEMA_VERSION)
    published_version = (
        PUBLISHED_LARK_SNAPSHOT_PATH.stat().st_mtime_ns
        if PUBLISHED_LARK_SNAPSHOT_PATH.exists()
        else 0
    )
    published_saved = published_lark_frames(
        published_version,
        LARK_SNAPSHOT_SCHEMA_VERSION,
        dashboard_data_key(),
    )
    saved = local_saved if local_saved is not None else published_saved
    if saved is not None and not refresh:
        return saved
    try:
        live = fetch_lark_frames(config)
        save_lark_snapshot(PERSISTED_LARK_SNAPSHOT_DIR, live)
        persisted_lark_frames.clear()
        refreshed = persisted_lark_frames(
            lark_snapshot_version(PERSISTED_LARK_SNAPSHOT_DIR),
            LARK_SNAPSHOT_SCHEMA_VERSION,
        )
        return refreshed if refreshed is not None else live
    except Exception as exc:
        if saved is None:
            raise
        fallback = saved.copy()
        fallback["refresh_error"] = str(exc)
        return fallback


@st.cache_data(ttl=3600, show_spinner=False)
def cached_product_images(
    config: LarkConfig,
    references: tuple[tuple[str, str, str], ...],
) -> dict[str, str]:
    return fetch_image_data_urls(config, references)


def render_top_record_table(
    records: pd.DataFrame,
    total_revenue: float,
    config: LarkConfig | None,
) -> None:
    products = top_record_id_frame(records, total_revenue, limit=50)
    if products.empty:
        st.warning("Chưa tìm thấy Record ID hợp lệ để lập bảng xếp hạng.")
        return

    image_data_urls: dict[str, str] = {}
    requested_image_tokens: set[str] = set()
    if config is not None:
        image_references = tuple(
            products[["image_token", "image_field_id", "image_record_id"]]
            .fillna("")
            .itertuples(index=False, name=None)
        )
        requested_image_tokens = {
            token
            for token, field_id, record_id in image_references
            if token and field_id and record_id
        }
        if requested_image_tokens:
            image_data_urls = cached_product_images(config, image_references)
            source_image_urls = products["Image"].copy()
            products["Image"] = products["image_token"].map(image_data_urls).fillna("")
            products["Image"] = products["Image"].where(
                products["Image"].ne(""),
                source_image_urls,
            )
            st.caption(
                f"Ảnh Lark: đã tải {len(image_data_urls)}/{len(requested_image_tokens)} "
                "ảnh của Top Record ID qua API."
            )

    display_products = products[
        [
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
        ]
    ].copy()
    display_products["Revenue"] = display_products["Revenue"].map(
        lambda value: f"${float(value):,.2f}"
    )
    display_products["Share"] = display_products["Share"].map(
        lambda value: f"{float(value):.2f}%"
    )
    product_row_height = 52
    product_table_height = 42 + len(display_products) * product_row_height
    st.dataframe(
        display_products,
        hide_index=True,
        width="stretch",
        height=product_table_height,
        row_height=product_row_height,
        column_config={
            "Image": st.column_config.ImageColumn(width="small"),
            "Record ID": st.column_config.TextColumn(width="medium"),
            "Product": st.column_config.TextColumn(width="large"),
            "Idea By": st.column_config.TextColumn(width="medium"),
            "Managed By": st.column_config.TextColumn(width="medium"),
            "Custom By": st.column_config.TextColumn(width="medium"),
            "Ads By": st.column_config.TextColumn(width="medium"),
            "ASIN count": st.column_config.NumberColumn(width="small"),
            "Revenue": st.column_config.TextColumn(width="medium"),
            "Orders": st.column_config.NumberColumn(width="small"),
            "Units": st.column_config.NumberColumn(width="small"),
            "Share": st.column_config.TextColumn(width="small"),
        },
    )


def in_lark_calendar_window(
    series: pd.Series,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce")
    # Lark date filters operate on calendar dates. Normalizing prevents a
    # timestamp later on the final day (for example 31/07 10:29) from being
    # excluded by an end boundary represented as 31/07 00:00.
    return parsed.dt.normalize().between(
        pd.Timestamp(window_start).normalize(),
        pd.Timestamp(window_end).normalize(),
    )


def in_report_month(series: pd.Series) -> pd.Series:
    return in_lark_calendar_window(series, REPORT_START, REPORT_END)


def workflow_lead_days(
    start: pd.Series,
    end: pd.Series,
    window_start: pd.Timestamp = REPORT_START,
    window_end: pd.Timestamp = REPORT_END,
) -> pd.Series:
    """Return valid stage lead times completed in the reporting month."""
    start_dates = pd.to_datetime(start, errors="coerce")
    end_dates = pd.to_datetime(end, errors="coerce")
    lead = (end_dates - start_dates).dt.total_seconds().div(86400)
    return lead.where(
        in_lark_calendar_window(end_dates, window_start, window_end) & lead.ge(0)
    )


def validation_cohort_start(window_end: pd.Timestamp) -> pd.Timestamp:
    previous_month = window_end.normalize().replace(day=1) - pd.DateOffset(months=1)
    return previous_month.replace(day=20)


def first_nonempty(series: pd.Series) -> str:
    for value in series:
        if pd.notna(value) and str(value).strip():
            return str(value).strip()
    return ""


def prepare_attribution(lark: dict, store_name: str, performance: pd.DataFrame) -> dict:
    total = apply_fulfillment_overrides(lark["total"])
    ideas = lark["ideas"].copy()
    cliparts = lark["cliparts"].copy()
    performance = performance.copy()
    if store_name != "All Stores":
        performance = performance[performance["Store"].eq(store_name)]
    asin_performance = (
        performance.groupby("ASIN", as_index=False)
        .agg(
            Revenue=("Revenue", "sum"),
            Orders=("Orders", "sum"),
            Units=("Units", "sum"),
            record_id_hint=("record_id_hint", first_nonempty),
        )
    )

    if total.empty:
        return {
            "total": total,
            "records": pd.DataFrame(),
            "ideas": ideas,
            "cliparts": cliparts,
            "coverage": 0.0,
            "duplicate_asins": 0,
        }

    total = total.drop_duplicates(["record_id", "asin"])
    known_asins = set(total["asin"])
    sku_hints = asin_performance[
        ~asin_performance["ASIN"].isin(known_asins)
        & asin_performance["record_id_hint"].fillna("").str.strip().ne("")
    ][["ASIN", "record_id_hint"]].drop_duplicates("ASIN")
    sku_fallback_count = len(sku_hints)
    if not sku_hints.empty:
        record_lookup = total.sort_values(["record_id", "asin"]).drop_duplicates("record_id")
        fallback_rows = sku_hints.merge(
            record_lookup,
            left_on="record_id_hint",
            right_on="record_id",
            how="left",
        )
        fallback_rows["record_id"] = fallback_rows["record_id"].fillna(
            fallback_rows["record_id_hint"]
        )
        fallback_rows["asin"] = fallback_rows["ASIN"]
        fallback_date_columns = {
            "date_pickup",
            "listing_done_date",
            "ps_pickup_date",
            "custom_done_date",
            "custom_check_done_date",
            "testing_start_date",
        }
        for column in total.columns:
            if column not in fallback_rows:
                if column in fallback_date_columns:
                    fallback_rows[column] = pd.NaT
                elif column == "ads_launched":
                    fallback_rows[column] = False
                else:
                    fallback_rows[column] = ""
        total = pd.concat([total, fallback_rows[total.columns]], ignore_index=True)
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
        "image_token": first_nonempty,
        "image_record_id": first_nonempty,
        "image_field_id": first_nonempty,
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
        "ideas": ideas,
        "attributed_asins": attributed_asins,
        "cliparts": cliparts,
        "coverage": attributed_revenue / total_revenue if total_revenue else 0.0,
        "duplicate_asins": duplicate_asins,
        "sku_fallback_count": sku_fallback_count,
    }


def employee_kpi_tables(
    attribution: dict,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
    ads_performance: pd.DataFrame | None = None,
    ads_imports: list[dict] | None = None,
) -> dict[str, pd.DataFrame]:
    records = attribution["records"].copy()
    attributed_asins = fbm_asin_rows(
        attribution.get("attributed_asins", pd.DataFrame()).copy()
    )
    cliparts = attribution["cliparts"].copy()
    fbm_record_ids = set(attributed_asins["record_id"].dropna().astype(str))
    records = records.loc[records["record_id"].astype(str).isin(fbm_record_ids)].copy()
    if records.empty:
        return {}

    fbm_record_metrics = (
        attributed_asins.groupby("record_id", as_index=False)
        .agg(Revenue=("Revenue", "sum"), Orders=("Orders", "sum"), Units=("Units", "sum"))
    )
    records = records.drop(columns=["Revenue", "Orders", "Units"], errors="ignore").merge(
        fbm_record_metrics, on="record_id", how="left"
    )
    records[["Revenue", "Orders", "Units"]] = records[
        ["Revenue", "Orders", "Units"]
    ].fillna(0)

    cohort_start = validation_cohort_start(window_end)
    records["validated"] = records["Units"].ge(10)

    def owner_records(column: str) -> pd.DataFrame:
        return records[records[column].fillna("").str.strip().ne("")].copy()

    # Every MRND IDEA record is an FBM idea by business definition. Do not
    # require it to exist in TOTAL ASIN yet: newly qualified ideas often have
    # no ASIN at the time they are handed over. Revenue and Units remain zero
    # until the Record ID can be mapped to FBM ASINs below.
    idea_events = attribution.get("ideas", pd.DataFrame()).copy()
    idea_events["qualified"] = in_lark_calendar_window(
        idea_events["handover_date"], window_start, window_end
    )
    idea_events["in_cohort"] = in_lark_calendar_window(
        idea_events["handover_date"], cohort_start, window_end
    )
    idea = (
        idea_events.groupby("record_id", as_index=False)
        .agg(
            idea_by=("idea_by", first_nonempty),
            qualified=("qualified", "any"),
            in_cohort=("in_cohort", "any"),
        )
        .merge(
            records[["record_id", "Revenue", "Units"]],
            on="record_id",
            how="left",
        )
    )
    idea[["Revenue", "Units"]] = idea[["Revenue", "Units"]].fillna(0)
    idea = idea[idea["idea_by"].fillna("").str.strip().ne("")].copy()
    idea["validated"] = idea["Units"].ge(10)
    idea["cohort_validated"] = idea["in_cohort"] & idea["validated"]
    idea_table = (
        idea.groupby("idea_by", as_index=False)
        .agg(
            Qualified_Ideas=("qualified", "sum"),
            Portfolio_Records_10_Units=("validated", "sum"),
            Cohort_Records=("in_cohort", "sum"),
            Validated_Records=("cohort_validated", "sum"),
        )
        .rename(columns={"idea_by": "Nhân sự"})
    )
    idea_asins = attributed_asins.merge(
        idea[["record_id", "idea_by"]].drop_duplicates("record_id"),
        on="record_id",
        how="left",
    )
    idea_revenue = asin_portfolio_revenue(
        idea_asins,
        "idea_by",
    )[["Nhân sự", "Portfolio_Revenue"]].rename(columns={"Portfolio_Revenue": "Revenue"})
    idea_table = idea_table.merge(idea_revenue, on="Nhân sự", how="outer")
    idea_table = idea_table.merge(
        revenue_milestone_counts(idea, "idea_by"), on="Nhân sự", how="left"
    )
    idea_table["Validated_Rate"] = idea_table["Validated_Records"].div(
        idea_table["Cohort_Records"].where(idea_table["Cohort_Records"].ne(0))
    )

    product_events = attributed_asins.copy()
    product_events["listing_in_cohort"] = in_lark_calendar_window(
        product_events["listing_done_date"], cohort_start, window_end
    )
    product = (
        product_events.groupby("record_id", as_index=False)
        .agg(
            managed_by=("managed_by", first_nonempty),
            in_cohort=("listing_in_cohort", "any"),
            Revenue=("Revenue", "sum"),
            Units=("Units", "sum"),
        )
    )
    product = product[product["managed_by"].fillna("").str.strip().ne("")].copy()
    product["validated"] = product["Units"].ge(10)
    product["cohort_sold"] = product["in_cohort"] & product["validated"]
    product_table = (
        product.groupby("managed_by", as_index=False)
        .agg(
            Portfolio_Records_10_Units=("validated", "sum"),
            Cohort_Records=("in_cohort", "sum"),
            Sold_Records=("cohort_sold", "sum"),
        )
        .rename(columns={"managed_by": "Nhân sự"})
    )
    product_table = product_table.merge(
        revenue_milestone_counts(product, "managed_by"), on="Nhân sự", how="left"
    )
    product_table["Sold_Rate"] = product_table["Sold_Records"].div(
        product_table["Cohort_Records"].where(product_table["Cohort_Records"].ne(0))
    )
    product_asins = attributed_asins[
        attributed_asins["managed_by"].fillna("").str.strip().ne("")
    ].copy()
    product_asins["qualified"] = in_lark_calendar_window(
        product_asins["custom_check_done_date"], window_start, window_end
    )
    listing_lead_source = product_asins.get(
        "listing_lead_time", pd.Series(index=product_asins.index, dtype=float)
    )
    product_asins["listing_lead_selected"] = pd.to_numeric(
        listing_lead_source, errors="coerce"
    ).where(
        in_lark_calendar_window(
            product_asins["listing_done_date"], window_start, window_end
        )
    )
    product_output = (
        product_asins.groupby("managed_by", as_index=False)
        .agg(
            Qualified_ASINs=("qualified", "sum"),
            Listing_Lead_Days=("listing_lead_selected", "mean"),
        )
        .rename(columns={"managed_by": "Nhân sự"})
    )
    product_table = product_table.merge(product_output, on="Nhân sự", how="left")
    product_table["Qualified_ASINs"] = product_table["Qualified_ASINs"].fillna(0)
    product_portfolio = asin_portfolio_revenue(attributed_asins, "managed_by")
    product_new_revenue = asin_new_revenue_from_custom_cohort(
        attributed_asins,
        "managed_by",
        cohort_start,
        window_end,
    )
    product_table = product_table.merge(product_portfolio, on="Nhân sự", how="outer")
    product_table = product_table.merge(product_new_revenue, on="Nhân sự", how="outer")

    support_asins = attributed_asins[
        attributed_asins["custom_by"].fillna("").str.strip().ne("")
    ].copy()
    support_asins["qualified"] = in_lark_calendar_window(
        support_asins["custom_check_done_date"], window_start, window_end
    )
    support_table = (
        support_asins.groupby("custom_by", as_index=False)
        .agg(Qualified_Custom_ASINs=("qualified", "sum"))
        .rename(columns={"custom_by": "Nhân sự"})
    )
    points = pd.DataFrame(columns=["Nhân sự", "Asset_Points"])
    if not cliparts.empty:
        cliparts_window = cliparts[
            in_lark_calendar_window(
                cliparts["created_date"], window_start, window_end
            )
            & cliparts["employee"].fillna("").str.strip().ne("")
        ]
        points = (
            cliparts_window.groupby("employee", as_index=False)
            .agg(Asset_Points=("asset_points", "sum"))
            .rename(columns={"employee": "Nhân sự"})
        )
    support_table = support_table.merge(points, on="Nhân sự", how="outer")
    for column in ("Qualified_Custom_ASINs", "Asset_Points"):
        support_table[column] = support_table[column].fillna(0)

    ads = owner_records("ads_by")
    ads["winner"] = ads["Revenue"].ge(5000)
    ads_table = (
        ads.groupby("ads_by", as_index=False)
        .agg(
            New_Winner_Created=("winner", "sum"),
            Portfolio_Revenue=("Revenue", "sum"),
        )
        .rename(columns={"ads_by": "Nhân sự"})
    )
    # Employee KPI revenue is FBM-only. Campaign execution rows have no owned
    # Order Revenue; they arrive only from the FBM Ads allocation.
    revenue_asins = attributed_asins.copy()
    revenue_asins = revenue_asins[
        revenue_asins["ads_by"].fillna("").str.strip().ne("")
    ]
    revenue_asins["Revenue_Owner"] = revenue_asins["ads_by"]
    ads_revenue_milestones = revenue_milestone_counts(
        revenue_asins.rename(columns={"Revenue_Owner": "milestone_owner"}),
        "milestone_owner",
    )
    allocated_revenue = (
        revenue_asins.groupby("Revenue_Owner", as_index=False)
        .agg(Allocated_Portfolio_Revenue=("Revenue", "sum"))
        .rename(columns={"Revenue_Owner": "Nhân sự"})
    )
    ads_new_revenue = asin_new_revenue_from_custom_cohort(
        revenue_asins,
        "Revenue_Owner",
        cohort_start,
        window_end,
    )
    ads_table = ads_table.merge(allocated_revenue, on="Nhân sự", how="outer")
    ads_table = ads_table.merge(ads_new_revenue, on="Nhân sự", how="outer")
    ads_table = ads_table.merge(ads_revenue_milestones, on="Nhân sự", how="outer")
    ads_table["Portfolio_Revenue"] = ads_table["Allocated_Portfolio_Revenue"].combine_first(
        ads_table["Portfolio_Revenue"]
    )
    ads_table = ads_table.drop(columns=["Allocated_Portfolio_Revenue"])
    if ads_performance is not None and not ads_performance.empty:
        ads_metrics = ads_performance[
            ["Nhân sự", "Ads_Spend", "Ads_Sales", "Ads_Orders", "ACOS"]
        ].copy()
        ads_table = ads_table.merge(ads_metrics, on="Nhân sự", how="outer")
        for column in (
            "New_Winner_Created",
            "New_Revenue_ASINs",
            "New_Revenue",
            "Portfolio_Revenue",
            "Ads_Spend",
            "Ads_Sales",
            "Ads_Orders",
        ):
            ads_table[column] = pd.to_numeric(ads_table[column], errors="coerce").fillna(0)
    else:
        ads_table["Ads_Spend"] = pd.NA
        ads_table["Ads_Sales"] = pd.NA
        ads_table["Ads_Orders"] = pd.NA
        ads_table["ACOS"] = pd.NA
    ads_table["TACOS"] = pd.to_numeric(ads_table["Ads_Spend"], errors="coerce").div(
        pd.to_numeric(ads_table["Portfolio_Revenue"], errors="coerce").where(
            pd.to_numeric(ads_table["Portfolio_Revenue"], errors="coerce").ne(0)
        )
    )

    milestone_columns = [
        "Portfolio_Records_1000_Revenue",
        "Portfolio_Records_3000_Revenue",
        "Portfolio_Records_5000_Revenue",
        "Portfolio_Records_10000_Revenue",
        "Portfolio_Records_15000_Revenue",
        "Portfolio_Records_20000_Revenue",
    ]
    for table in (idea_table, product_table, ads_table):
        for column in milestone_columns:
            table[column] = pd.to_numeric(table[column], errors="coerce").fillna(0)

    idea_table = idea_table[
        [
            "Nhân sự",
            "Qualified_Ideas",
            "Portfolio_Records_10_Units",
            *milestone_columns,
            "Cohort_Records",
            "Validated_Records",
            "Validated_Rate",
            "Revenue",
        ]
    ]
    product_table = product_table[
        [
            "Nhân sự",
            "Qualified_ASINs",
            "Portfolio_Records_10_Units",
            *milestone_columns,
            "Cohort_Records",
            "Sold_Records",
            "Sold_Rate",
            "New_Revenue_ASINs",
            "New_Revenue",
            "Portfolio_Revenue",
            "Listing_Lead_Days",
        ]
    ]
    ads_table = ads_table[
        [
            "Nhân sự",
            "New_Winner_Created",
            *milestone_columns,
            "Ads_Spend",
            "Ads_Sales",
            "Ads_Orders",
            "ACOS",
            "TACOS",
            "Portfolio_Revenue",
            "New_Revenue_ASINs",
            "New_Revenue",
        ]
    ]

    return {
        "Idea · 40% Output / 30% Efficiency / 30% Business": idea_table.sort_values(
            "Revenue", ascending=False
        ),
        "Product · 30% Output / 20% Efficiency / 50% Business": product_table.sort_values(
            "Portfolio_Revenue", ascending=False
        ),
        "Product Support · 80% Output / 20% Asset": support_table.sort_values(
            "Qualified_Custom_ASINs", ascending=False
        ),
        "Ads · 45% Efficiency / 55% Business": ads_table.sort_values(
            "Portfolio_Revenue", ascending=False
        ),
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
    month_options = available_order_months()
    selected_month = st.selectbox(
        "Tháng báo cáo",
        month_options,
        format_func=lambda value: pd.Timestamp(f"{value}-01").strftime("Tháng %m/%Y"),
    )
    st.markdown("**Live month-to-date**")
    st.caption("Order + Ads snapshot đã xử lý")
    st.caption("Pacific Time · Cancelled excluded\n\nFBA / FBM separated")


top_left, top_right = st.columns([2, 1])
with top_left:
    st.markdown('<div class="atlas-eyebrow">PERFORMANCE SNAPSHOT</div>', unsafe_allow_html=True)
    report_month_label = pd.Timestamp(f"{selected_month}-01").strftime("Tháng %m/%Y")
    st.markdown(f'<div class="atlas-title">{report_month_label}</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="atlas-subtitle">Order Report thực tế · Purchase Time theo America/Los_Angeles</div>',
        unsafe_allow_html=True,
    )
with top_right:
    store = st.selectbox("Store", ["All Stores", "Pawsionate", "Wrappiness"])

data = active_store(store, selected_month)
selected_order_rows = selected_order_performance(
    list(STORES) if store == "All Stores" else [store],
    selected_month,
)
order_snapshot_metadata = load_snapshot_metadata(PERSISTED_SNAPSHOT_PATH)
report_as_of_date = pd.to_datetime(
    order_snapshot_metadata.get("report_as_of_date"), errors="coerce"
)
if not selected_order_rows.empty:
    live_through = pd.to_datetime(selected_order_rows["Date"], errors="coerce").max()
    if pd.notna(live_through):
        if pd.notna(report_as_of_date) and report_as_of_date.normalize() > live_through.normalize():
            st.caption(
                f"Order Report MTD đã input đến {report_as_of_date:%d/%m/%Y}; "
                f"Purchase Date mới nhất có order là {live_through:%d/%m/%Y}."
            )
        else:
            st.caption(f"Order snapshot đang cập nhật đến hết ngày {live_through:%d/%m/%Y}.")
if data["snapshot_backed"]:
    notice_text = (
        f'{data["snapshot_rows"]:,} dòng tổng hợp theo ngày/ASIN · Cancelled đã loại tại pipeline · '
        "Revenue = Item Price + Shipping Price."
    )
else:
    notice_text = (
        f'{data["raw"]:,} dòng nguồn · loại {data["cancelled"]:,} Cancelled · '
        f'{data["valid"]:,} dòng hợp lệ. Revenue = Item Price + Shipping Price.'
    )
st.markdown(
    f'<div class="atlas-notice"><strong>{store}</strong><span>{notice_text}</span></div>',
    unsafe_allow_html=True,
)


if page.startswith("01"):
    cols = st.columns(4)
    cols[0].metric("Net revenue", money(data["revenue"]), "USD · Item + Shipping")
    cols[1].metric("Orders", f'{data["orders"]:,}', f'{money(data["revenue"] / data["orders"])} / order')
    cols[2].metric("Units", f'{data["units"]:,}', f'{data["units"] / data["orders"]:.2f} units / order')
    cols[3].metric("Active ASINs", f'{data["asins"]:,}', "Có doanh thu USD")

    overview_stores = list(STORES) if store == "All Stores" else [store]
    overview_performance = selected_order_performance(overview_stores, selected_month)
    overview_lark = persisted_lark_frames(
        lark_snapshot_version(PERSISTED_LARK_SNAPSHOT_DIR),
        LARK_SNAPSHOT_SCHEMA_VERSION,
    )
    fulfillment = fulfillment_revenue_frame(
        overview_performance,
        overview_lark["total"] if overview_lark else pd.DataFrame(),
    )
    fbm_actual_revenue = 0.0
    if not fulfillment.empty:
        fulfillment_index = fulfillment.set_index("Fulfill By")
        fulfillment_cols = st.columns(2)
        for column, fulfillment_type in zip(fulfillment_cols, ("FBA", "FBM")):
            row = (
                fulfillment_index.loc[fulfillment_type]
                if fulfillment_type in fulfillment_index.index
                else pd.Series({"Revenue": 0, "Orders": 0, "ASINs": 0})
            )
            revenue = float(row["Revenue"])
            if fulfillment_type == "FBM":
                fbm_actual_revenue = revenue
            column.metric(
                f"{fulfillment_type} revenue",
                money(revenue),
                f'{revenue / data["revenue"]:.1%} · {int(row["Orders"]):,} orders · {int(row["ASINs"]):,} ASINs',
            )
        unmapped = (
            fulfillment_index.loc["Unmapped"]
            if "Unmapped" in fulfillment_index.index
            else None
        )
        if unmapped is not None and float(unmapped["Revenue"]):
            st.warning(
                f'Có {int(unmapped["ASINs"]):,} ASIN chưa map Fulfill By, '
                f'tương ứng {money(float(unmapped["Revenue"]))} Revenue.'
            )

    fbm_target_progress = None
    fbm_daily_targets = pd.DataFrame()
    target_as_of = pd.NaT
    fbm_targets = load_fbm_target_snapshot(PERSISTED_FBM_TARGET_PATH)
    monthly_fbm_target = target_for_month(fbm_targets, selected_month)
    if monthly_fbm_target is not None and store == "All Stores":
        target_as_of = report_as_of_date
        if pd.isna(target_as_of):
            target_as_of = pd.to_datetime(
                overview_performance.get("Date", pd.Series(dtype="datetime64[ns]")),
                errors="coerce",
            ).max()
        if pd.notna(target_as_of):
            fbm_target_progress = target_progress(
                fbm_targets,
                selected_month,
                fbm_actual_revenue,
                target_as_of,
            )
            fbm_daily_targets = daily_targets_for_month(fbm_targets, selected_month)
            fbm_daily_targets = fbm_daily_targets[
                fbm_daily_targets["Date"].le(pd.Timestamp(target_as_of).normalize())
            ].copy()
            st.markdown(
                '<div class="atlas-card"><div class="atlas-eyebrow">FBM ACTUAL VS TARGET · ALL STORES</div><h3>Tiến độ Revenue FBM</h3></div>',
                unsafe_allow_html=True,
            )
            target_cols = st.columns(5)
            target_cols[0].metric("Actual MTD", money(fbm_actual_revenue))
            target_cols[1].metric(
                "Forecast MTD 2026", money(float(fbm_target_progress["forecast_mtd"]))
            )
            target_cols[2].metric(
                "Actual vs Forecast", f'{float(fbm_target_progress["vs_forecast"]):+.1%}'
            )
            target_cols[3].metric(
                "Revenue 2025 MTD", money(float(fbm_target_progress["prior_mtd"]))
            )
            target_cols[4].metric(
                "Actual vs 2025", f'{float(fbm_target_progress["vs_2025"]):+.1%}'
            )
            st.caption(
                "So sánh theo từng ngày từ sheet `Revenue Forecast Q1&2 - 2026`: "
                "`FORECAST 2026` và `DAILY REV 2025`. "
                f"Đang tính {int(fbm_target_progress['elapsed_days'])} ngày theo lần input Order gần nhất; "
                f"Forecast cả tháng = {money(float(fbm_target_progress['forecast_full_month']))}."
            )
    elif monthly_fbm_target is not None and store != "All Stores":
        st.info(
            "Target FBM hiện được cung cấp ở cấp All Stores, chưa có phân bổ theo từng store. "
            "Chọn All Stores để xem Actual vs Target."
        )

    left, right = st.columns([2, 1])
    with left:
        st.markdown('<div class="atlas-card"><div class="atlas-eyebrow">DAILY PERFORMANCE</div><h3>Revenue & Quantity theo ngày · FBM / FBA</h3>', unsafe_allow_html=True)
        daily_by_fulfillment = daily_fulfillment_frames(
            overview_performance,
            overview_lark["total"] if overview_lark else pd.DataFrame(),
        )
        if all(frame.empty for frame in daily_by_fulfillment.values()):
            st.warning("Chưa có dữ liệu Fulfill By để tách Daily Performance thành FBM và FBA.")
        else:
            for fulfillment_type in ("FBM", "FBA"):
                daily_performance = daily_by_fulfillment[fulfillment_type]
                if fulfillment_type == "FBM" and not fbm_daily_targets.empty:
                    daily_performance = fbm_daily_targets.merge(
                        daily_performance,
                        on="Date",
                        how="left",
                    )
                    daily_performance[["Revenue", "Quantity", "Orders"]] = (
                        daily_performance[["Revenue", "Quantity", "Orders"]].fillna(0)
                    )
                    daily_performance["Vs Forecast"] = (
                        daily_performance["Revenue"]
                        .div(daily_performance["Forecast 2026"].where(
                            daily_performance["Forecast 2026"].ne(0)
                        ))
                        .sub(1)
                    )
                    daily_performance["YoY"] = (
                        daily_performance["Revenue"]
                        .div(daily_performance["Revenue 2025"].where(
                            daily_performance["Revenue 2025"].ne(0)
                        ))
                        .sub(1)
                    )
                st.markdown(f"#### {fulfillment_type}")
                chart_tab, table_tab = st.tabs(
                    [f"{fulfillment_type} · Chart", f"{fulfillment_type} · Bảng dữ liệu"]
                )
                with chart_tab:
                    st.plotly_chart(
                        daily_revenue_quantity_chart(daily_performance),
                        width="stretch",
                        config={"displayModeBar": False},
                    )
                with table_tab:
                    daily_columns = ["Date", "Revenue", "Quantity"]
                    if fulfillment_type == "FBM" and not fbm_daily_targets.empty:
                        daily_columns = [
                            "Date", "Revenue", "Forecast 2026", "Vs Forecast",
                            "Revenue 2025", "YoY", "Quantity",
                        ]
                    daily_table = daily_performance[daily_columns].copy()
                    st.dataframe(
                        daily_table,
                        width="stretch",
                        hide_index=True,
                        column_config={
                            "Date": st.column_config.DateColumn("Ngày", format="DD/MM/YYYY"),
                            "Revenue": st.column_config.NumberColumn(
                                "Actual 2026", format="dollar", help="Item Price + Shipping Price"
                            ),
                            "Quantity": st.column_config.NumberColumn(
                                "Quantity", format="%d", help="Tổng Units theo Purchase Date"
                            ),
                            "Forecast 2026": st.column_config.NumberColumn(
                                "Forecast 2026", format="dollar"
                            ),
                            "Vs Forecast": st.column_config.NumberColumn(
                                "Vs Forecast", format="percent"
                            ),
                            "Revenue 2025": st.column_config.NumberColumn(
                                "Revenue 2025", format="dollar"
                            ),
                            "YoY": st.column_config.NumberColumn(
                                "YoY", format="percent"
                            ),
                        },
                    )
                    st.caption(
                        (
                            "FBM · Actual 2026 theo Purchase Date Los Angeles; Forecast 2026 "
                            "và Revenue 2025 lấy đúng từng ngày trong file forecast."
                            if fulfillment_type == "FBM" and not fbm_daily_targets.empty
                            else f"{fulfillment_type} · Quantity = tổng Units theo Purchase Date."
                        )
                    )
        st.markdown("</div>", unsafe_allow_html=True)
    with right:
        store_share = (
            overview_performance.groupby("Store", as_index=False)["Revenue"].sum()
            if not overview_performance.empty
            else pd.DataFrame({"Store": [store], "Revenue": [data["revenue"]]})
        )
        st.markdown('<div class="atlas-card"><div class="atlas-eyebrow">SNAPSHOT ORDER</div><h3>Revenue theo store</h3>', unsafe_allow_html=True)
        st.plotly_chart(
            donut_chart(store_share, "Store", "Revenue", ["#40b6c8", "#ff9d5c"], 285),
            width="stretch",
            config={"displayModeBar": False},
        )
        st.caption("Purchase Time · America/Los_Angeles · Cancelled excluded")
        st.markdown("</div>", unsafe_allow_html=True)

elif page.startswith("02"):
    st.markdown('<div class="atlas-card"><div class="atlas-eyebrow">PRODUCT PERFORMANCE</div><h3>Top sản phẩm theo Record ID</h3></div>', unsafe_allow_html=True)
    st.caption(
        "Dữ liệu Order được nạp tự động từ snapshot đã lưu và gộp toàn bộ ASIN "
        "cùng sản phẩm theo Record ID từ Lark. "
        "Share được tính trên tổng Revenue của store đang chọn."
    )
    config, missing_secrets = lark_config()
    lark = None
    if not missing_secrets:
        with st.spinner("Đang nạp snapshot Lark gần nhất…"):
            lark = latest_lark_frames(config)
        if lark.get("snapshot_updated_at"):
            product_lark_updated_at = pd.to_datetime(
                lark["snapshot_updated_at"], errors="coerce", utc=True
            )
            if pd.notna(product_lark_updated_at):
                product_lark_updated_at = product_lark_updated_at.tz_convert(
                    "Asia/Ho_Chi_Minh"
                )
                st.caption(
                    "Mapping lấy từ snapshot đồng bộ tất cả bảng Lark lúc "
                    f"{product_lark_updated_at:%d/%m/%Y %H:%M}."
                )
        image_candidates = (
            lark["total"][["image_token", "image_field_id", "image_record_id"]]
            .fillna("")
            .drop_duplicates()
        )
        image_candidates = image_candidates[
            image_candidates.astype(bool).all(axis=1)
        ].head(3)
        sample_image_references = tuple(
            image_candidates.itertuples(index=False, name=None)
        )
        direct_image_count = int(
            lark["total"]["image_url"].fillna("").astype(str).str.startswith("http").sum()
        )
        if sample_image_references:
            sample_images = cached_product_images(config, sample_image_references)
            st.caption(
                f"Ảnh Lark: {direct_image_count:,} dòng có URL trực tiếp · "
                f"{len(sample_images)}/{len(sample_image_references)} ảnh mẫu tải qua Media API."
            )
            if not sample_images and not direct_image_count:
                st.warning(
                    "API ảnh Lark chưa sẵn sàng: "
                    + probe_image_download(config, sample_image_references[0])
                )
    required_product_stores = (
        ["Wrappiness", "Pawsionate"] if store == "All Stores" else [store]
    )
    product_performance = selected_order_performance(required_product_stores, selected_month)
    if not product_performance.empty:
        if missing_secrets:
            st.warning(
                "Chưa kết nối Lark nên dashboard đang gộp theo Record ID lấy từ SKU. "
                "Các cột Idea By, Managed By, Custom By và Ads By được để trống "
                "cho đến khi map được dữ liệu từ Lark."
            )
            hint_records = records_from_order_hints(product_performance)
            render_top_record_table(
                hint_records,
                float(product_performance["Revenue"].sum()),
                None,
            )
        else:
            assert lark is not None
            attribution = prepare_attribution(lark, store, product_performance)
            mapped_asins = set(attribution["total"]["asin"])
            selected_asins = set(product_performance["ASIN"])
            unmapped_asins = selected_asins.difference(mapped_asins)
            asin_coverage = 1 - len(unmapped_asins) / len(selected_asins) if selected_asins else 0
            revenue_coverage = attribution["coverage"]

            quality_columns = st.columns(3)
            quality_columns[0].metric("ASIN mapping", f"{asin_coverage:.2%}", f"{len(selected_asins) - len(unmapped_asins):,} / {len(selected_asins):,} ASIN")
            quality_columns[1].metric(
                "Revenue mapping",
                f"{revenue_coverage:.2%}",
                f'{attribution.get("sku_fallback_count", 0):,} ASIN fallback từ SKU',
            )
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
                        f"unmapped_asins_{selected_month}.csv",
                        "text/csv",
                    )
            else:
                st.success("Mapping đạt 100%: toàn bộ ASIN có Record ID trong TOTAL ASIN.")

            records = attribution["records"].copy()
            records = records[records["Revenue"].gt(0)]
            render_top_record_table(
                records,
                float(product_performance["Revenue"].sum()),
                config,
            )
    else:
        st.warning(
            "Chưa đồng bộ dữ liệu Order để lập Top 50 Record ID. Hãy chạy pipeline cập nhật "
            "snapshot/dashboard_snapshot.csv."
        )

elif page.startswith("03"):
    ads, type_performance, live_ads_imports = live_ads_performance(selected_month, store)
    if not live_ads_imports:
        st.warning(
            "Chưa có Ads snapshot month-to-date khớp tháng/store đang chọn. "
            "Hãy chạy scripts/update_month_to_date.ps1 với Ads report mới nhất."
        )
    else:
        ads_period_ends = [item.get("period_end", "") for item in live_ads_imports]
        ads_period_ends = [value for value in ads_period_ends if value]
        if ads_period_ends:
            st.caption(
                "Ads snapshot đang cập nhật đến hết ngày "
                + pd.Timestamp(max(ads_period_ends)).strftime("%d/%m/%Y")
                + "."
            )
    tacos = ads["spend"] / data["revenue"] if data["revenue"] else pd.NA
    acos = ads["spend"] / ads["sales"] if ads["sales"] else pd.NA
    roas = ads["sales"] / ads["spend"] if ads["spend"] else pd.NA
    cvr = ads["orders"] / ads["clicks"] if ads["clicks"] else pd.NA
    cols = st.columns(4)
    cols[0].metric(
        "Ad spend", money(ads["spend"]),
        f"{tacos:.1%} TACOS" if pd.notna(tacos) else "TACOS N/A",
    )
    sales_share = ads["sales"] / data["revenue"] if data["revenue"] else pd.NA
    cols[1].metric(
        "Ad sales", money(ads["sales"]),
        f"{sales_share:.1%} total revenue" if pd.notna(sales_share) else "N/A",
    )
    cols[2].metric(
        "ACOS", f"{acos:.1%}" if pd.notna(acos) else "N/A",
        f"ROAS {roas:.2f}" if pd.notna(roas) else "ROAS N/A",
    )
    cols[3].metric(
        "Ad orders", f'{int(ads["orders"]):,}',
        f"{cvr:.1%} CVR" if pd.notna(cvr) else "CVR N/A",
    )
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
    ctr = ads["clicks"] / ads["impressions"] if ads["impressions"] else pd.NA
    cpc = ads["spend"] / ads["clicks"] if ads["clicks"] else pd.NA
    st.caption(
        (f"CTR {ctr:.2%} · " if pd.notna(ctr) else "CTR N/A · ")
        + (f"CVR {cvr:.2%} · " if pd.notna(cvr) else "CVR N/A · ")
        + (f"CPC ${cpc:.2f}" if pd.notna(cpc) else "CPC N/A")
    )
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="atlas-card"><div class="atlas-eyebrow">CAMPAIGN TYPE PERFORMANCE</div><h3>Hiệu quả theo Ads Type · SP / SB / SD</h3></div>', unsafe_allow_html=True)
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
    st.markdown("## Team KPI · ASIN revenue / Record workflow")
    st.caption(
        "Record ID, ASIN và workflow dùng ngày lịch gốc của Lark, không đổi timezone. "
        "Orders, Units và Revenue dùng Purchase Time của Order Report đã đổi sang "
        "America/Los_Angeles, đã loại Cancelled và chỉ giữ Fulfill By = FBM cho KPI nhân sự."
    )
    if team_access_granted():
        config, missing_secrets = lark_config()
        if missing_secrets:
            st.error("Thiếu Streamlit Secrets: " + ", ".join(missing_secrets))
        else:
            st.info(
                "Quy ước thời gian: KPI workflow lọc theo ngày trên bảng Lark; KPI bán hàng "
                "lọc theo Purchase Month Los Angeles. Hai nguồn không chuyển timezone qua lại."
            )
            order_snapshot_metadata = load_snapshot_metadata(PERSISTED_SNAPSHOT_PATH)
            selected_stores = (
                ["Wrappiness", "Pawsionate"] if store == "All Stores" else [store]
            )
            performance = selected_order_performance(selected_stores, selected_month)
            if performance.empty:
                st.error(
                    "Chưa đồng bộ dữ liệu Order. Hãy chạy pipeline cập nhật "
                    "snapshot/dashboard_snapshot.csv."
                )
                st.stop()
            if "Date" not in performance.columns:
                persisted_order_performance.clear()
                performance = selected_order_performance(selected_stores, selected_month)
            if "Date" not in performance.columns:
                # Streamlit may retain the previously imported snapshot_store module
                # after a hot reload. Read the persisted CSV once to refresh its schema.
                fresh_snapshot = pd.read_csv(
                    PERSISTED_SNAPSHOT_PATH,
                    dtype={"Store": str, "Date": str, "ASIN": str, "record_id_hint": str},
                )
                performance = fresh_snapshot[
                    fresh_snapshot["Store"].isin(selected_stores)
                ].copy()
                performance = performance[
                    pd.to_datetime(performance["Date"], errors="coerce")
                    .dt.strftime("%Y-%m")
                    .eq(selected_month)
                ].copy()
            if "Date" not in performance.columns:
                # A legacy single-month snapshot can still be used for its report month.
                performance["Date"] = REPORT_START
                st.warning(
                    "Snapshot cũ không có Purchase Date; dashboard đang gán toàn bộ dữ liệu "
                    f"vào tháng {REPORT_START:%m/%Y}. Hãy cập nhật snapshot trước khi thêm tháng khác."
                )
            performance["Date"] = pd.to_datetime(performance["Date"], errors="coerce")
            available_dates = performance["Date"].dropna()
            if available_dates.empty:
                st.error("Snapshot Order chưa có Purchase Date hợp lệ để lọc KPI theo tháng.")
                st.stop()
            report_start = performance["Date"].min().normalize()
            report_end = performance["Date"].max().normalize()
            window_start = pd.Timestamp(f"{selected_month}-01")
            st.success(
                f"Đã nạp Purchase Month {window_start:%m/%Y} từ snapshot · "
                f"Order/Revenue Los Angeles hiện có {report_start:%d/%m/%Y}–"
                f"{report_end:%d/%m/%Y}."
            )
            refresh_lark = st.button(
                "Cập nhật snapshot Lark · tất cả bảng",
                help=(
                    "Đồng bộ TOTAL ASIN, MRND IDEA và CLIPARTS trong cùng một lần cập nhật; "
                    "các lần mở sau chỉ đọc snapshot đã lưu."
                ),
            )
            try:
                spinner_text = (
                    "Đang cập nhật dữ liệu từ Lark Base…"
                    if refresh_lark
                    else "Đang nạp snapshot Lark gần nhất…"
                )
                with st.spinner(spinner_text):
                    lark = latest_lark_frames(config, refresh=refresh_lark)
                window_end = workflow_kpi_window_end(
                    selected_month,
                    lark.get("snapshot_updated_at", ""),
                    report_end,
                )
                if lark.get("refresh_error"):
                    st.warning(
                        "Không cập nhật được Lark API; dashboard tiếp tục dùng snapshot gần nhất."
                    )
                if lark.get("snapshot_updated_at"):
                    updated_at = pd.to_datetime(
                        lark["snapshot_updated_at"], errors="coerce", utc=True
                    )
                    if pd.notna(updated_at):
                        updated_at = updated_at.tz_convert("Asia/Ho_Chi_Minh")
                        st.caption(
                            f"Snapshot Lark cập nhật lần cuối: {updated_at:%d/%m/%Y %H:%M}"
                        )
                st.caption(
                    "KPI output Lark dùng ngày lịch Lark đến lần cập nhật mới nhất: "
                    f"{window_start:%d/%m/%Y}–{window_end:%d/%m/%Y}."
                )
                order_updated_at = pd.to_datetime(
                    order_snapshot_metadata.get("source_updated_at")
                    or order_snapshot_metadata.get("updated_at"),
                    errors="coerce",
                    utc=True,
                )
                if pd.notna(order_updated_at):
                    order_updated_at = order_updated_at.tz_convert("Asia/Ho_Chi_Minh")
                    st.caption(
                        "Snapshot Order cập nhật từ report gần nhất: "
                        f"{order_updated_at:%d/%m/%Y %H:%M} · "
                        "Purchase Time đã chuẩn hóa America/Los_Angeles"
                    )
                attribution = prepare_attribution(lark, store, performance)
                ads_snapshot = current_ads_snapshot()
                ads_summary, ads_imports = select_ads_summary(
                    ads_snapshot, selected_month, store, fbm_only=True
                )
                ads_snapshot_matches = not ads_summary.empty
                records = attribution["records"]
                tables = employee_kpi_tables(
                    attribution,
                    window_start,
                    window_end,
                    ads_summary,
                    ads_imports,
                )

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
                    # Qualified Ideas is a unique Record ID metric. TOTAL ASIN workflow
                    # outputs follow Lark's source-row Record count after date filters.
                    workflow_records = lark["workflow"]
                    ads_tested_mask = in_lark_calendar_window(
                        workflow_records["testing_start_date"], window_start, window_end
                    )
                    ads_tested = int(ads_tested_mask.sum())
                    listing_done = int(
                        in_lark_calendar_window(
                            workflow_records["listing_done_date"], window_start, window_end
                        ).sum()
                    )
                    custom_done = int(
                        in_lark_calendar_window(
                            workflow_records["custom_check_done_date"], window_start, window_end
                        ).sum()
                    )
                    idea_done = int(
                        lark["ideas"].loc[
                            in_lark_calendar_window(
                                lark["ideas"]["handover_date"], window_start, window_end
                            ),
                            "record_id",
                        ].nunique()
                    )
                    cliparts_month = attribution["cliparts"][
                        in_lark_calendar_window(
                            attribution["cliparts"]["created_date"], window_start, window_end
                        )
                    ]
                    asset_total = int(cliparts_month["asset_points"].sum())

                    st.markdown("### Workflow KPI từ Lark · toàn portfolio")
                    st.caption(
                        "Ngày KPI lấy nguyên từ Lark (không đổi timezone). "
                        f"Chỉ đếm output hoàn thành trong {window_start:%d/%m/%Y}–"
                        f"{window_end:%d/%m/%Y}. Qualified Ideas đếm unique Record ID; "
                        "Listing/Custom/Ads dùng Record count của TOTAL ASIN; lead time "
                        "là Average trực tiếp trên các record sau khi lọc."
                    )
                    st.markdown(
                        f"""
                        <div class="kpi-strip">
                          <div><span>Qualified Ideas</span><strong>{idea_done:,}</strong><small>MRND IDEA · Unique Record ID</small></div>
                          <div><span>Listing Done</span><strong>{listing_done:,}</strong><small>TOTAL ASIN · Record count</small></div>
                          <div><span>Custom Check Done</span><strong>{custom_done:,}</strong><small>TOTAL ASIN · Record count</small></div>
                          <div><span>Asset Points</span><strong>{asset_total:,}</strong><small>CLIPARTS · selected window</small></div>
                          <div><span>Ads Tested</span><strong>{ads_tested:,}</strong><small>TOTAL ASIN · Record count</small></div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    listing_lead_source = workflow_records.get(
                        "listing_lead_time",
                        pd.Series(index=workflow_records.index, dtype=float),
                    )
                    custom_lead_source = workflow_records.get(
                        "custom_lead_time",
                        pd.Series(index=workflow_records.index, dtype=float),
                    )
                    listing_lead = pd.to_numeric(
                        listing_lead_source, errors="coerce"
                    ).where(
                        in_lark_calendar_window(
                            workflow_records["listing_done_date"], window_start, window_end
                        )
                    ).dropna()
                    custom_lead = pd.to_numeric(
                        custom_lead_source, errors="coerce"
                    ).where(
                        in_lark_calendar_window(
                            workflow_records["custom_check_done_date"], window_start, window_end
                        )
                    ).dropna()
                    lead_cols = st.columns(2)
                    lead_cols[0].metric(
                        "Listing lead time",
                        f"{listing_lead.mean():.2f} days" if not listing_lead.empty else "—",
                    )
                    lead_cols[1].metric(
                        "Custom lead time",
                        f"{custom_lead.mean():.2f} days" if not custom_lead.empty else "—",
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
                        f"{records.loc[records['Revenue'].gt(0), 'record_id'].nunique():,} sold Record ID",
                    )
                    winner_count = int(records["Revenue"].ge(5000).sum())
                    quality_cols[2].metric(
                        "Winner Records",
                        f"{winner_count:,}",
                        "Revenue ≥ $5,000 / Record ID",
                    )

                    employee_asins = fbm_asin_rows(attribution["attributed_asins"])
                    new_asin_mask = in_lark_calendar_window(
                        employee_asins["custom_check_done_date"],
                        validation_cohort_start(window_end),
                        window_end,
                    )
                    product_new_asins = employee_asins.loc[
                        new_asin_mask
                        & employee_asins["managed_by"]
                        .fillna("")
                        .str.strip()
                        .ne(""),
                        "asin",
                    ].nunique()
                    ads_new_asins = employee_asins.loc[
                        new_asin_mask
                        & employee_asins["ads_by"]
                        .fillna("")
                        .str.strip()
                        .ne(""),
                        "asin",
                    ].nunique()
                    ownership_cols = st.columns(2)
                    cohort_label = (
                        f"Custom Check Done {validation_cohort_start(window_end):%d/%m}–"
                        f"{window_end:%d/%m}"
                    )
                    ownership_cols[0].metric(
                        "Product New ASINs",
                        f"{product_new_asins:,}",
                        cohort_label,
                    )
                    ownership_cols[1].metric(
                        "Ads New ASINs",
                        f"{ads_new_asins:,}",
                        cohort_label,
                    )

                    st.markdown("### KPI theo nhân sự · Lark calendar + Purchase Month LA")
                    st.caption(
                        "Idea theo MRND IDEA Pickup Date; Product output và Product Support theo "
                        "Custom Check Done Date; cohort Sold/Validated vẫn theo Record ID, còn "
                        "Product/Ads New Revenue theo từng ASIN có Custom Check Done từ ngày 20 "
                        "tháng trước đến cuối time window. Toàn bộ Order và Ads FBA bị loại khỏi "
                        "các bảng KPI nhân sự."
                    )
                    if ads_snapshot_matches:
                        diagnostics = [item.get("diagnostics", {}) for item in ads_imports]
                        support_asins = sum(int(item.get("support_asins", 0)) for item in diagnostics)
                        support_spend = sum(float(item.get("support_spend", 0)) for item in diagnostics)
                        support_sales = sum(float(item.get("support_sales", 0)) for item in diagnostics)
                        execution_totals: dict[str, float] = {}
                        for item in diagnostics:
                            for assignee, metrics in item.get("execution_by_assignee", {}).items():
                                execution_totals[assignee] = execution_totals.get(assignee, 0) + float(
                                    metrics.get("spend", 0)
                                )
                        execution_summary = ", ".join(
                            f"{assignee} ${spend:,.2f}"
                            for assignee, spend in execution_totals.items()
                            if spend > 0
                        )
                        execution_clause = (
                            f"tách campaign thực thi {execution_summary}; "
                            if execution_summary
                            else ""
                        )
                        fba_asins = sum(int(item.get("fba_asins", 0)) for item in diagnostics)
                        imported_stores = ", ".join(item.get("store", "") for item in ads_imports)
                        st.success(
                            "Ads snapshot đã map 100% SP/SB/SD ASIN → TOTAL ASIN → "
                            f"Ads By cho {imported_stores}. Đã chuyển {support_asins} ASIN / "
                            f"${support_spend:,.2f} Spend / ${support_sales:,.2f} Sales sang "
                            f"Nhi-Support; {execution_clause}đồng thời nhận diện và loại "
                            f"{fba_asins} ASIN FBA khỏi KPI nhân sự."
                        )
                        catalog_fba_asins = set(
                            attribution["total"].loc[
                                attribution["total"]["fulfill_by"]
                                .fillna("")
                                .str.strip()
                                .str.casefold()
                                .eq("fba"),
                                "asin",
                            ]
                        )
                        reported_fba_asins = {
                            asin
                            for item in diagnostics
                            for values in item.get("fba_asins_by_assignee", {}).values()
                            for asin in values
                        }
                        missing_fba_asins = sorted(catalog_fba_asins - reported_fba_asins)
                        if missing_fba_asins:
                            st.warning(
                                f"Advertised Product hiện chỉ có {len(reported_fba_asins):,}/"
                                f"{len(catalog_fba_asins):,} ASIN FBA trong TOTAL ASIN. "
                                f"{len(missing_fba_asins):,} ASIN không có trong Ads report nên "
                                "không phát sinh Spend/Sales trong bảng này: "
                                + ", ".join(missing_fba_asins)
                            )
                    else:
                        st.warning(
                            "Chưa có Ads snapshot khớp Store/Purchase Month nên ACOS theo "
                            "nhân sự đang N/A."
                        )
                    with st.expander("Quy định KPI đang áp dụng", expanded=False):
                        st.markdown(
                            """
- **Phạm vi fulfillment:** toàn bộ bảng KPI nhân sự chỉ dùng ASIN có `Fulfill By = FBM`; Order, Revenue, Units, ASIN count và Ads Spend/Sales/Orders của FBA đều bị loại. Overview và Ads Performance tổng vẫn giữ FBA + FBM để đối soát store.
- **Idea:** Qualified Ideas theo Pickup Date; `Pickup Cohort` là unique Record ID FBM có Pickup Date từ ngày 20 tháng trước đến cuối kỳ. Validated Rate chỉ dùng cohort này và ngưỡng tổng Units FBM ≥10. `Revenue` là tổng doanh thu tháng của toàn bộ ASIN FBM thuộc Idea ownership.
- **Product:** Qualified ASINs là unique ASIN FBM theo Custom Check Done Date; `Listing Cohort` là unique Record ID FBM có Listing Done Date từ ngày 20 tháng trước đến cuối kỳ. Sold Records là Record ID trong cohort có tổng Units FBM ≥10. `Portfolio Revenue` là doanh thu của toàn bộ ASIN FBM thuộc Managed By; `New Revenue` chỉ gồm các ASIN FBM có chính `Custom Check Done Date` nằm trong cohort 20 tháng trước–cuối kỳ.
- **Product Support:** Qualified Custom ASINs theo Custom Check Done Date; Asset Points theo ngày tạo/cập nhật asset và ma trận 10/5/10/5 điểm, không tính reuse/duplicate.
- **Ads:** `Portfolio Revenue` là doanh thu tháng của toàn bộ ASIN FBM thuộc Ads ownership. `New Revenue` chỉ gồm các ASIN FBM có chính `Custom Check Done Date` nằm trong cohort ngày 20 tháng trước đến cuối kỳ. Winner vẫn là Record ID FBM có Revenue ≥ $5,000. Spend/Sales lấy từ ba report SP/SB/SD rồi loại mọi dòng map tới ASIN FBA trước khi gộp KPI, kể cả campaign `Support` hoặc marker `LINH`/`HIEU`/`HA`. `ACOS = Spend / Ads Sales`; `TACOS = Spend / Portfolio Revenue` chỉ áp dụng cho hàng có ownership Revenue.
- **Revenue milestones:** các cột `Record IDs ≥$1K/≥$3K/≥$5K/≥$10K/≥$15K/≥$20K` đếm unique Record ID thuộc toàn bộ ownership của nhân sự có Revenue trong Purchase Month đang chọn đạt ngưỡng tương ứng; không giới hạn theo workflow cohort.
                            """
                        )
                    for title, table in tables.items():
                        with st.expander(title, expanded=True):
                            display = table.copy()
                            display = display.rename(
                                columns={
                                    "Qualified_Ideas": "Qualified_Ideas (Pickup Date)",
                                    "Portfolio_Records_10_Units": "Portfolio_Record_IDs (≥10 Units)",
                                    "Portfolio_Records_1000_Revenue": "Record_IDs (≥$1K Revenue)",
                                    "Portfolio_Records_3000_Revenue": "Record_IDs (≥$3K Revenue)",
                                    "Portfolio_Records_5000_Revenue": "Record_IDs (≥$5K Revenue)",
                                    "Portfolio_Records_10000_Revenue": "Record_IDs (≥$10K Revenue)",
                                    "Portfolio_Records_15000_Revenue": "Record_IDs (≥$15K Revenue)",
                                    "Portfolio_Records_20000_Revenue": "Record_IDs (≥$20K Revenue)",
                                    "Cohort_Records": (
                                        f"Pickup_Cohort_Record_IDs ({validation_cohort_start(window_end):%d/%m}–{window_end:%d/%m})"
                                        if title.startswith("Idea")
                                        else f"Listing_Cohort_Record_IDs ({validation_cohort_start(window_end):%d/%m}–{window_end:%d/%m})"
                                        if title.startswith("Product ·")
                                        else f"Custom_Check_Cohort_Record_IDs ({validation_cohort_start(window_end):%d/%m}–{window_end:%d/%m})"
                                    ),
                                    "Validated_Records": "Validated_Records (≥10 Units)",
                                    "Sold_Records": "Sold_Records (≥10 Units)",
                                    "Qualified_ASINs": "Qualified_ASINs (unique)",
                                    "New_Revenue_ASINs": f"New_Revenue_ASINs ({validation_cohort_start(window_end):%d/%m}–{window_end:%d/%m})",
                                }
                            )
                            integer_columns = [
                                column
                                for column in display.columns
                                if column
                                not in {
                                    "Nhân sự",
                                    "Revenue",
                                    "New_Revenue",
                                    "Portfolio_Revenue",
                                    "Ads_Spend",
                                    "Ads_Sales",
                                    "Validated_Rate",
                                    "Sold_Rate",
                                    "ACOS",
                                    "TACOS",
                                    "Listing_Lead_Days",
                                    "Custom_Lead_Days",
                                    "PD_Check_Days",
                                }
                            ]
                            for column in integer_columns:
                                display[column] = display[column].fillna(0).round().astype(int)
                            for money_column in (
                                "Revenue",
                                "New_Revenue",
                                "Portfolio_Revenue",
                                "Ads_Spend",
                                "Ads_Sales",
                            ):
                                if money_column in display:
                                    display[money_column] = display[money_column].fillna(0).map(
                                        lambda value: f"${float(value):,.2f}"
                                    )
                            for rate_column in (
                                "Validated_Rate",
                                "Sold_Rate",
                                "ACOS",
                                "TACOS",
                            ):
                                if rate_column in display:
                                    display[rate_column] = display[rate_column].map(
                                        lambda value: (
                                            "N/A"
                                            if pd.isna(value)
                                            else f"{float(value):.1%}"
                                        )
                                    )
                            st.dataframe(
                                display,
                                hide_index=True,
                                width="stretch",
                                column_config={
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

footer_as_of = report_as_of_date
if pd.isna(footer_as_of) and not selected_order_rows.empty:
    footer_as_of = pd.to_datetime(selected_order_rows["Date"], errors="coerce").max()
footer_label = (
    footer_as_of.strftime("%d %b %Y") if pd.notna(footer_as_of) else "chưa xác định"
)
st.caption(f"Atlas Performance OS · Internal dashboard · Report input as of {footer_label}")
