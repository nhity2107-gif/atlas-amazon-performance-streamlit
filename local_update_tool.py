from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
import subprocess
import sys

import pandas as pd
import streamlit as st

from ads_data import (
    build_ads_employee_summary_from_reports,
    read_ads_workbook,
    save_encrypted_ads_snapshot,
    upsert_ads_snapshot,
)
from lark_snapshot_store import load_lark_snapshot
from scripts.local_data_pipeline import export_snapshot, ingest_order_report, prepare_order_rows


DASHBOARD_ROOT = Path(__file__).resolve().parent
ATLAS_ROOT = DASHBOARD_ROOT.parent
DATABASE = ATLAS_ROOT / "database" / "atlas.db"
ORDER_SNAPSHOT = DASHBOARD_ROOT / "snapshot" / "dashboard_snapshot.csv"
LARK_SNAPSHOT = DASHBOARD_ROOT / "snapshot" / "lark"
ADS_SNAPSHOT = DASHBOARD_ROOT / "snapshot" / "ads"
PUBLISHED_ADS = DASHBOARD_ROOT / "snapshot" / "published_ads_snapshot.enc"


def save_upload(upload, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(upload.getvalue())
    return path


def validate_order_window(path: Path, store: str, month: str, as_of: date) -> dict:
    rows = prepare_order_rows(path, store, "mtd")
    if rows.empty:
        raise ValueError(f"Order report {store} không có dòng ASIN hợp lệ.")
    start = f"{month}-01"
    end = as_of.isoformat()
    minimum = str(rows["purchase_date_pacific"].min())
    maximum = str(rows["purchase_date_pacific"].max())
    if minimum < start or maximum > end:
        raise ValueError(
            f"Order report {store} có Purchase Date {minimum}–{maximum}, "
            f"nằm ngoài kỳ MTD {start}–{end}."
        )
    return {"rows": len(rows), "date_min": minimum, "date_max": maximum}


def run_git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=DASHBOARD_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


st.set_page_config(page_title="Atlas Local Update Tool", page_icon="🟧", layout="wide")
st.title("Atlas · Local Update Tool")
st.caption(
    "Nạp report month-to-date trên PC → kiểm tra → sinh snapshot → publish GitHub/Streamlit. "
    "Raw report chỉ lưu tại ổ D và không được đưa lên Git."
)

today = date.today()
left, right = st.columns(2)
as_of = left.date_input("Ngày dữ liệu đến hết", value=today, max_value=today)
month = right.text_input("Tháng báo cáo", value=as_of.strftime("%Y-%m"))
if not as_of.isoformat().startswith(month + "-"):
    st.error("Ngày dữ liệu phải nằm trong tháng báo cáo.")
    st.stop()

st.markdown("### Order Report · từ ngày 01 đến ngày input")
order_cols = st.columns(2)
wr_order = order_cols[0].file_uploader(
    "Wrappiness Order", type=["txt", "tsv", "csv"], key="wr_order"
)
paw_order = order_cols[1].file_uploader(
    "Pawsionate Order", type=["txt", "tsv", "csv"], key="paw_order"
)

st.markdown("### Ads Report · từ ngày 01 đến ngày input")
ads_cols = st.columns(4)
wr_sp = ads_cols[0].file_uploader("Wrappiness SP", type=["xlsx", "csv"], key="wr_sp")
wr_sb = ads_cols[1].file_uploader("Wrappiness SB", type=["xlsx"], key="wr_sb")
wr_sd = ads_cols[2].file_uploader("Wrappiness SD", type=["xlsx"], key="wr_sd")
paw_sp = ads_cols[3].file_uploader("Pawsionate SP", type=["xlsx", "csv"], key="paw_sp")

required_uploads = {
    "Wrappiness Order": wr_order,
    "Pawsionate Order": paw_order,
    "Wrappiness SP": wr_sp,
    "Wrappiness SB": wr_sb,
    "Wrappiness SD": wr_sd,
    "Pawsionate SP": paw_sp,
}

if st.button("1 · Kiểm tra và sinh dashboard", type="primary", use_container_width=True):
    missing = [name for name, upload in required_uploads.items() if upload is None]
    if missing:
        st.error("Còn thiếu: " + ", ".join(missing))
    else:
        try:
            raw_root = ATLAS_ROOT / "daily-reports" / month / as_of.isoformat()
            files = {
                "wr_order": save_upload(
                    wr_order,
                    raw_root / "Wrappiness" / "Order" / f"wrappiness-orders-mtd{Path(wr_order.name).suffix}",
                ),
                "paw_order": save_upload(
                    paw_order,
                    raw_root / "Pawsionate" / "Order" / f"pawsionate-orders-mtd{Path(paw_order.name).suffix}",
                ),
                "wr_sp": save_upload(
                    wr_sp, raw_root / "Wrappiness" / "Ads" / f"wrappiness-sp-mtd{Path(wr_sp.name).suffix}"
                ),
                "wr_sb": save_upload(
                    wr_sb, raw_root / "Wrappiness" / "Ads" / f"wrappiness-sb-mtd{Path(wr_sb.name).suffix}"
                ),
                "wr_sd": save_upload(
                    wr_sd, raw_root / "Wrappiness" / "Ads" / f"wrappiness-sd-mtd{Path(wr_sd.name).suffix}"
                ),
                "paw_sp": save_upload(
                    paw_sp, raw_root / "Pawsionate" / "Ads" / f"pawsionate-sp-mtd{Path(paw_sp.name).suffix}"
                ),
            }

            order_checks = {
                "Wrappiness": validate_order_window(files["wr_order"], "Wrappiness", month, as_of),
                "Pawsionate": validate_order_window(files["paw_order"], "Pawsionate", month, as_of),
            }
            lark = load_lark_snapshot(LARK_SNAPSHOT)
            if lark is None:
                raise ValueError("Chưa có Lark snapshot để map Ads ownership.")
            wr_reports = [
                read_ads_workbook(files["wr_sp"], "SP"),
                read_ads_workbook(files["wr_sb"], "SB"),
                read_ads_workbook(files["wr_sd"], "SD"),
            ]
            paw_reports = [read_ads_workbook(files["paw_sp"], "SP")]
            wr_summary, wr_diagnostics = build_ads_employee_summary_from_reports(
                wr_reports, lark["total"]
            )
            paw_summary, paw_diagnostics = build_ads_employee_summary_from_reports(
                paw_reports, lark["total"]
            )

            order_results = [
                ingest_order_report(
                    DATABASE, files["wr_order"], "Wrappiness", "mtd", as_of_date=as_of.isoformat()
                ),
                ingest_order_report(
                    DATABASE, files["paw_order"], "Pawsionate", "mtd", as_of_date=as_of.isoformat()
                ),
            ]
            order_snapshot_result = export_snapshot(DATABASE, ORDER_SNAPSHOT)
            common_metadata = {
                "month": month,
                "report_scope": "mtd",
                "period_start": f"{month}-01",
                "period_end": as_of.isoformat(),
                "imported_at": datetime.now(timezone.utc).isoformat(),
            }
            upsert_ads_snapshot(
                ADS_SNAPSHOT,
                wr_summary,
                {
                    **common_metadata,
                    "store": "Wrappiness",
                    "mapping_mode": "complete-sp-sb-sd",
                    "diagnostics": wr_diagnostics,
                },
            )
            upsert_ads_snapshot(
                ADS_SNAPSHOT,
                paw_summary,
                {
                    **common_metadata,
                    "store": "Pawsionate",
                    "mapping_mode": "complete-sp-only",
                    "diagnostics": paw_diagnostics,
                },
            )
            st.session_state["last_build"] = {
                "month": month,
                "as_of": as_of.isoformat(),
                "raw_root": str(raw_root),
                "order_checks": order_checks,
                "order_results": order_results,
                "order_snapshot": order_snapshot_result,
                "ads_spend": round(float(wr_summary["Ads_Spend"].sum() + paw_summary["Ads_Spend"].sum()), 2),
                "ads_sales": round(float(wr_summary["Ads_Sales"].sum() + paw_summary["Ads_Sales"].sum()), 2),
            }
            st.success("Đã kiểm tra và sinh snapshot dashboard thành công.")
        except Exception as exc:
            st.exception(exc)

if "last_build" in st.session_state:
    build = st.session_state["last_build"]
    st.markdown("### Kết quả gần nhất")
    metrics = st.columns(4)
    metrics[0].metric("Order snapshot rows", f"{build['order_snapshot']['rows']:,}")
    metrics[1].metric("Order revenue", f"${build['order_snapshot']['revenue']:,.2f}")
    metrics[2].metric("Ads spend", f"${build['ads_spend']:,.2f}")
    metrics[3].metric("Ads sales", f"${build['ads_sales']:,.2f}")
    st.caption(f"Raw reports: {build['raw_root']}")

    st.markdown("### Publish lên Streamlit")
    st.warning(
        "Repository GitHub là public. Ads snapshot sẽ được mã hóa trước khi commit; "
        "không publish raw report, database, Lark snapshot hoặc Ads plaintext."
    )
    if st.button("2 · Mã hóa, kiểm thử và push", use_container_width=True):
        try:
            publish_key = str(st.secrets.get("PUBLISHED_SNAPSHOT_KEY", "")).strip()
            if not publish_key:
                raise ValueError(
                    "Thiếu PUBLISHED_SNAPSHOT_KEY. Chạy scripts/setup_publish_key.py và "
                    "thêm cùng key vào Streamlit Cloud Secrets trước khi publish."
                )
            save_encrypted_ads_snapshot(ADS_SNAPSHOT, PUBLISHED_ADS, publish_key)
            tests = subprocess.run(
                [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"],
                cwd=DASHBOARD_ROOT,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            run_git("diff", "--check")
            run_git(
                "add",
                "snapshot/dashboard_snapshot.csv",
                "snapshot/dashboard_snapshot.metadata.json",
                "snapshot/published_ads_snapshot.enc",
            )
            staged = run_git("diff", "--cached", "--name-only").stdout.strip()
            if not staged:
                st.info("Snapshot không thay đổi; không cần push.")
            else:
                run_git("commit", "-m", f"Update live dashboard through {build['as_of']}")
                run_git("push", "origin", "main")
                commit = run_git("rev-parse", "--short", "HEAD").stdout.strip()
                st.success(f"Đã push commit {commit}. Streamlit sẽ tự redeploy từ main.")
                st.caption(tests.stderr.strip() or tests.stdout.strip())
        except subprocess.CalledProcessError as exc:
            st.error(exc.stderr or exc.stdout or str(exc))
        except Exception as exc:
            st.exception(exc)
