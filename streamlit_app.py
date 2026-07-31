from __future__ import annotations

import pandas as pd
import streamlit as st


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


def money(value: float) -> str:
    return f"${value:,.0f}"


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
            {"Revenue": [data["fbm_revenue"], data["fba_revenue"]]},
            index=["FBM", "FBA"],
        )
        st.markdown('<div class="atlas-card"><div class="atlas-eyebrow">FULFILLMENT</div><h3>Revenue split</h3>', unsafe_allow_html=True)
        st.bar_chart(fulfillment, color="#756ee9", horizontal=True, height=230)
        st.caption(f'{data["fbm_orders"]:,} FBM orders · {data["fba_orders"]:,} FBA orders')
        st.markdown("</div>", unsafe_allow_html=True)

    if store == "All Stores":
        store_share = pd.DataFrame(
            {"Revenue": [STORES["Wrappiness"]["revenue"], STORES["Pawsionate"]["revenue"]]},
            index=["Wrappiness", "Pawsionate"],
        )
        st.markdown('<div class="atlas-card"><div class="atlas-eyebrow">REVENUE BY STORE</div><h3>Tỷ trọng Revenue hai store</h3>', unsafe_allow_html=True)
        st.bar_chart(store_share, color="#40b6c8", horizontal=True, height=220)
        st.markdown("</div>", unsafe_allow_html=True)

elif page.startswith("02"):
    products = pd.DataFrame(
        data["products"], columns=["ASIN", "Revenue", "Orders", "Units"]
    )
    products.insert(0, "#", range(1, len(products) + 1))
    products["Share"] = products["Revenue"] / products["Revenue"].sum()
    st.markdown('<div class="atlas-card"><div class="atlas-eyebrow">PRODUCT PERFORMANCE</div><h3>Top ASIN theo Revenue</h3></div>', unsafe_allow_html=True)
    st.dataframe(
        products,
        hide_index=True,
        width="stretch",
        column_config={
            "Revenue": st.column_config.NumberColumn(format="$%.2f"),
            "Share": st.column_config.ProgressColumn(min_value=0, max_value=1, format="%.1%%"),
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
        {"Volume": [ads["impressions"], ads["clicks"], ads["orders"]]},
        index=["Impressions", "Clicks", "Orders"],
    )
    st.markdown('<div class="atlas-card"><div class="atlas-eyebrow">ADS FUNNEL</div><h3>Traffic đến conversion</h3>', unsafe_allow_html=True)
    st.bar_chart(funnel, color="#756ee9", horizontal=True, height=300)
    st.caption(
        f'CTR {ads["clicks"] / ads["impressions"] * 100:.2f}% · '
        f'CVR {ads["orders"] / ads["clicks"] * 100:.2f}% · '
        f'CPC ${ads["spend"] / ads["clicks"]:.2f}'
    )
    st.markdown("</div>", unsafe_allow_html=True)

else:
    st.markdown(
        """
        <div class="kpi-strip">
          <div><span>Qualified Ideas</span><strong>120</strong><small>Unique Record ID</small></div>
          <div><span>Listing Done</span><strong>284</strong><small>Product output</small></div>
          <div><span>Custom Done</span><strong>324</strong><small>Support output</small></div>
          <div><span>EBC Done</span><strong>41</strong><small>Asset delivery</small></div>
          <div><span>Ads Tested</span><strong>18</strong><small>Testing Start recorded</small></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    lead_cols = st.columns(4)
    lead_cols[0].metric("Listing lead time", "2.68 days")
    lead_cols[1].metric("Custom lead time", "3.13 days")
    lead_cols[2].metric("Ads lead time", "1.35 days")
    lead_cols[3].metric("Testing coverage", "6.3%", "Estimate · 18 / 284")

    team_specs = [
        ("Idea", "idea", [("Qualified Ideas", "120"), ("Validated Rate", "Chờ sales ≥10"), ("Revenue", "Chờ Record ID map")]),
        ("Product Development", "product", [("Qualified ASINs", "284"), ("Sold Rate", "Chờ cohort Flow 2"), ("Portfolio Revenue", "Chờ Record ID map")]),
        ("Product Support", "support", [("Qualified Custom ASINs", "324"), ("Asset Points", "Chờ CLIPARTS detail"), ("Lead Time", "3.13 days")]),
        ("Ads Executive", "ads", [("Ads Tested", "18"), ("Portfolio ACOS", "36.9%"), ("Testing Coverage", "6.3% est.")]),
    ]
    for row_start in range(0, 4, 2):
        team_cols = st.columns(2)
        for col, (name, tone, metrics) in zip(team_cols, team_specs[row_start:row_start + 2]):
            with col:
                rows = "".join(f'<div class="team-row"><span>{label}</span><b>{value}</b></div>' for label, value in metrics)
                st.markdown(
                    f'<div class="atlas-card team-card {tone}"><div class="atlas-eyebrow">TEAM KPI</div>'
                    f'<h3>{name}</h3>{rows}</div>',
                    unsafe_allow_html=True,
                )

    st.markdown("### Ownership output theo nhân sự")
    for row_start in range(0, len(EMPLOYEES), 2):
        employee_cols = st.columns(2)
        for col, (title, rows) in zip(employee_cols, list(EMPLOYEES.items())[row_start:row_start + 2]):
            with col:
                frame = pd.DataFrame(rows, columns=["Nhân sự", "Output"]).set_index("Nhân sự")
                st.markdown(f'<div class="atlas-card"><h3>{title}</h3>', unsafe_allow_html=True)
                st.bar_chart(frame, color="#756ee9", horizontal=True, height=max(180, 42 * len(rows)))
                st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(
        """
        <div class="pending"><b>Revenue attribution đang chờ quyền Lark record-level.</b><br>
        Khi có quyền đọc API, hệ thống sẽ nối Record ID → ASIN → Idea By / Managed By /
        Custom By / Ads By để điền Revenue, Sold Rate, Winner và testing coverage từng nhân sự.
        </div>
        """,
        unsafe_allow_html=True,
    )

st.caption("Atlas Performance OS · Internal dashboard · Order data as of 30 Jul 2026")
