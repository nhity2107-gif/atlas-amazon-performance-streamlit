from __future__ import annotations

from datetime import date, datetime, timezone
import os
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
from lark_data import LarkConfig, fetch_lark_frames
from lark_snapshot_store import load_lark_snapshot, save_lark_snapshot
from scripts.local_data_pipeline import export_snapshot, ingest_order_report, prepare_order_rows


DASHBOARD_ROOT = Path(__file__).resolve().parent
_configured_data_root = os.environ.get("ATLAS_LOCAL_DATA_ROOT", "").strip()
if _configured_data_root:
    ATLAS_ROOT = Path(_configured_data_root).expanduser().resolve()
elif sys.platform == "win32":
    # The PC installation keeps the repository in
    # D:\\Atlas Amazon Performance\\dashboard and data beside it.
    ATLAS_ROOT = DASHBOARD_ROOT.parent
else:
    # Keep Mac/Linux runtime data inside the writable project workspace.
    # This folder is gitignored and never published with the dashboard.
    ATLAS_ROOT = DASHBOARD_ROOT / ".local-data"
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
        return {
            "rows": 0,
            "date_min": None,
            "date_max": None,
            "status": "no-orders",
        }
    start = f"{month}-01"
    end = as_of.isoformat()
    minimum = str(rows["purchase_date_pacific"].min())
    maximum = str(rows["purchase_date_pacific"].max())
    if minimum < start or maximum > end:
        raise ValueError(
            f"Order report {store} có Purchase Date {minimum}–{maximum}, "
            f"nằm ngoài kỳ MTD {start}–{end}."
        )
    return {
        "rows": len(rows),
        "date_min": minimum,
        "date_max": maximum,
        "status": "valid",
    }


def run_git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=DASHBOARD_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def refresh_lark_for_update() -> tuple[dict, str, bool]:
    secret_names = {
        "app_id": "LARK_APP_ID",
        "app_secret": "LARK_APP_SECRET",
        "base_token": "LARK_BASE_TOKEN",
        "total_asin_table_id": "LARK_TOTAL_ASIN_TABLE_ID",
        "mrnd_idea_table_id": "LARK_MRND_IDEA_TABLE_ID",
        "cliparts_table_id": "LARK_CLIPARTS_TABLE_ID",
    }
    values = {
        field: str(st.secrets.get(secret_name, "")).strip()
        for field, secret_name in secret_names.items()
    }
    missing = [secret_names[field] for field, value in values.items() if not value]
    existing = load_lark_snapshot(LARK_SNAPSHOT)
    if missing:
        if existing is None:
            raise ValueError("Thiếu Streamlit Secrets: " + ", ".join(missing))
        return existing, "Không refresh được Lark vì thiếu secrets; đang dùng snapshot cũ.", False
    try:
        live = fetch_lark_frames(LarkConfig(**values))
        save_lark_snapshot(LARK_SNAPSHOT, live)
        counts = live["record_counts"]
        status = (
            f"Lark live: TOTAL ASIN {counts['TOTAL ASIN']:,} · "
            f"MRND IDEA {counts['MRND IDEA']:,} · CLIPARTS {counts['CLIPARTS']:,}"
        )
        return live, status, True
    except Exception as exc:
        if existing is None:
            raise
        return existing, f"Refresh Lark lỗi ({exc}); đang dùng snapshot cũ.", False


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

include_ads = st.checkbox(
    "Import 6 Ads report cuối tháng",
    value=False,
    help="Để tắt khi cập nhật Order MTD hằng ngày. Chỉ bật sau khi đã tải đủ SP/SB/SD của cả hai store.",
)
wr_sp = wr_sb = wr_sd = paw_sp = paw_sb = paw_sd = None
if include_ads:
    st.markdown("### Ads Report cuối tháng · từ ngày 01 đến ngày cuối tháng")
    st.caption("Wrappiness · đủ SP, SB và SD")
    wr_ads_cols = st.columns(3)
    wr_sp = wr_ads_cols[0].file_uploader("Wrappiness SP", type=["xlsx", "csv"], key="wr_sp")
    wr_sb = wr_ads_cols[1].file_uploader("Wrappiness SB", type=["xlsx"], key="wr_sb")
    wr_sd = wr_ads_cols[2].file_uploader("Wrappiness SD", type=["xlsx"], key="wr_sd")
    st.caption("Pawsionate · đủ SP, SB và SD")
    paw_ads_cols = st.columns(3)
    paw_sp = paw_ads_cols[0].file_uploader("Pawsionate SP", type=["xlsx", "csv"], key="paw_sp")
    paw_sb = paw_ads_cols[1].file_uploader("Pawsionate SB", type=["xlsx"], key="paw_sb")
    paw_sd = paw_ads_cols[2].file_uploader("Pawsionate SD", type=["xlsx"], key="paw_sd")
else:
    st.info("Chế độ hằng ngày: chỉ cập nhật 2 Order MTD; Ads snapshot hiện tại được giữ nguyên.")

required_uploads = {
    "Wrappiness Order": wr_order,
    "Pawsionate Order": paw_order,
}
if include_ads:
    required_uploads.update(
        {
            "Wrappiness SP": wr_sp,
            "Wrappiness SB": wr_sb,
            "Wrappiness SD": wr_sd,
            "Pawsionate SP": paw_sp,
            "Pawsionate SB": paw_sb,
            "Pawsionate SD": paw_sd,
        }
    )

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
            }
            if include_ads:
                files.update(
                    {
                        "wr_sp": save_upload(wr_sp, raw_root / "Wrappiness" / "Ads" / f"wrappiness-sp-mtd{Path(wr_sp.name).suffix}"),
                        "wr_sb": save_upload(wr_sb, raw_root / "Wrappiness" / "Ads" / f"wrappiness-sb-mtd{Path(wr_sb.name).suffix}"),
                        "wr_sd": save_upload(wr_sd, raw_root / "Wrappiness" / "Ads" / f"wrappiness-sd-mtd{Path(wr_sd.name).suffix}"),
                        "paw_sp": save_upload(paw_sp, raw_root / "Pawsionate" / "Ads" / f"pawsionate-sp-mtd{Path(paw_sp.name).suffix}"),
                        "paw_sb": save_upload(paw_sb, raw_root / "Pawsionate" / "Ads" / f"pawsionate-sb-mtd{Path(paw_sb.name).suffix}"),
                        "paw_sd": save_upload(paw_sd, raw_root / "Pawsionate" / "Ads" / f"pawsionate-sd-mtd{Path(paw_sd.name).suffix}"),
                    }
                )

            order_checks = {
                "Wrappiness": validate_order_window(files["wr_order"], "Wrappiness", month, as_of),
                "Pawsionate": validate_order_window(files["paw_order"], "Pawsionate", month, as_of),
            }
            with st.spinner("Đang refresh snapshot Lark trước khi sinh KPI…"):
                lark, lark_status, lark_refreshed = refresh_lark_for_update()
            ads_spend = ads_sales = None
            if include_ads:
                wr_reports = [
                    read_ads_workbook(files["wr_sp"], "SP"),
                    read_ads_workbook(files["wr_sb"], "SB"),
                    read_ads_workbook(files["wr_sd"], "SD"),
                ]
                paw_reports = [
                    read_ads_workbook(files["paw_sp"], "SP"),
                    read_ads_workbook(files["paw_sb"], "SB"),
                    read_ads_workbook(files["paw_sd"], "SD"),
                ]
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
            order_snapshot_result = export_snapshot(
                DATABASE,
                ORDER_SNAPSHOT,
                as_of_date=as_of.isoformat(),
            )
            if include_ads:
                common_metadata = {
                    "month": month,
                    "report_scope": "monthly-final",
                    "period_start": f"{month}-01",
                    "period_end": as_of.isoformat(),
                    "imported_at": datetime.now(timezone.utc).isoformat(),
                }
                for store_name, summary, diagnostics in (
                    ("Wrappiness", wr_summary, wr_diagnostics),
                    ("Pawsionate", paw_summary, paw_diagnostics),
                ):
                    upsert_ads_snapshot(
                        ADS_SNAPSHOT,
                        summary,
                        {**common_metadata, "store": store_name, "mapping_mode": "complete-sp-sb-sd", "diagnostics": diagnostics},
                    )
                ads_spend = round(float(wr_summary["Ads_Spend"].sum() + paw_summary["Ads_Spend"].sum()), 2)
                ads_sales = round(float(wr_summary["Ads_Sales"].sum() + paw_summary["Ads_Sales"].sum()), 2)
            st.session_state["last_build"] = {
                "month": month,
                "as_of": as_of.isoformat(),
                "raw_root": str(raw_root),
                "order_checks": order_checks,
                "order_results": order_results,
                "order_snapshot": order_snapshot_result,
                "lark_status": lark_status,
                "lark_refreshed": lark_refreshed,
                "ads_updated": include_ads,
                "ads_spend": ads_spend,
                "ads_sales": ads_sales,
            }
            st.success("Đã kiểm tra và sinh snapshot dashboard thành công.")
            if lark_refreshed:
                st.success(lark_status)
            else:
                st.warning(lark_status)
            zero_order_stores = [
                store for store, check in order_checks.items() if check["rows"] == 0
            ]
            if zero_order_stores:
                st.warning(
                    "Đã chấp nhận report 0 order và xóa dữ liệu MTD cũ: "
                    + ", ".join(zero_order_stores)
                )
        except Exception as exc:
            st.exception(exc)

if "last_build" in st.session_state:
    build = st.session_state["last_build"]
    st.markdown("### Kết quả gần nhất")
    metrics = st.columns(4)
    metrics[0].metric("Order snapshot rows", f"{build['order_snapshot']['rows']:,}")
    metrics[1].metric("Order revenue", f"${build['order_snapshot']['revenue']:,.2f}")
    metrics[2].metric("Ads spend", f"${build['ads_spend']:,.2f}" if build["ads_updated"] else "Không cập nhật")
    metrics[3].metric("Ads sales", f"${build['ads_sales']:,.2f}" if build["ads_updated"] else "Không cập nhật")
    order_status = ", ".join(
        f"{store}: {check['rows']:,} dòng"
        + (" (0 order hợp lệ)" if check["rows"] == 0 else "")
        for store, check in build["order_checks"].items()
    )
    st.caption(f"Order reports · {order_status}")
    st.caption(build.get("lark_status", ""))
    st.caption(f"Raw reports: {build['raw_root']}")

    st.markdown("### Publish lên Streamlit")
    if build["ads_updated"]:
        st.warning(
            "Repository GitHub là public. Ads snapshot sẽ được mã hóa trước khi commit; "
            "không publish raw report, database, Lark snapshot hoặc Ads plaintext."
        )
        publish_label = "2 · Mã hóa Ads, kiểm thử và push"
    else:
        st.info("Lần cập nhật này chỉ publish Order snapshot; Ads snapshot không thay đổi.")
        publish_label = "2 · Kiểm thử và push Order"
    if st.button(publish_label, use_container_width=True):
        try:
            if build["ads_updated"]:
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
            publish_files = [
                "snapshot/dashboard_snapshot.csv",
                "snapshot/dashboard_snapshot.metadata.json",
            ]
            if build["ads_updated"]:
                publish_files.append("snapshot/published_ads_snapshot.enc")
            run_git("add", *publish_files)
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
