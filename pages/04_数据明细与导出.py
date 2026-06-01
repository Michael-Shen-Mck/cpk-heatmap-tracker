from __future__ import annotations

from datetime import date

import streamlit as st

from auth import require_login
from components import download_csv, show_dataframe
from database import ROLLING_LINES, TEAMS, delete_batch, fetch_batches, fetch_measurements, fetch_specs, init_db
from manual import render_user_manual
from metrics import add_metric_columns, format_metric_table, summarize_daily, summarize_monthly


st.set_page_config(page_title="数据明细与导出", layout="wide")
require_login()
init_db()
render_user_manual()

st.title("数据明细与导出")
st.caption("筛选原始捆重、批次汇总和过程能力指标，并导出 CSV。")

today = date.today()
default_start = today.replace(day=1)

specs = fetch_specs(include_inactive=True)
col1, col2, col3, col4, col5 = st.columns([1, 1, 2, 1, 1])
start_date = col1.date_input("开始日期", value=default_start)
end_date = col2.date_input("结束日期", value=today)

spec_options = [0] + specs["id"].tolist() if not specs.empty else [0]
selected_spec_id = col3.selectbox(
    "规格",
    spec_options,
    format_func=lambda spec_id: "全部规格"
    if spec_id == 0
    else specs.loc[specs["id"] == spec_id, "spec_name"].iloc[0],
)
selected_line = col4.selectbox("轧线", ["全部轧线"] + ROLLING_LINES)
selected_team = col5.selectbox("班组", ["全部班组"] + TEAMS)

if start_date > end_date:
    st.error("开始日期不能晚于结束日期。")
    st.stop()

spec_id = None if selected_spec_id == 0 else int(selected_spec_id)
rolling_line = None if selected_line == "全部轧线" else selected_line
team = None if selected_team == "全部班组" else selected_team
measurements = fetch_measurements(
    start_date=start_date.isoformat(),
    end_date=end_date.isoformat(),
    spec_id=spec_id,
    rolling_line=rolling_line,
    team=team,
)
batches = fetch_batches(
    start_date=start_date.isoformat(),
    end_date=end_date.isoformat(),
    spec_id=spec_id,
    rolling_line=rolling_line,
    team=team,
)

if measurements.empty:
    st.warning("筛选条件下没有数据。")
    st.stop()

measurements = add_metric_columns(measurements)
daily_summary = summarize_daily(measurements)
monthly_summary = summarize_monthly(measurements)

tab_raw, tab_batch, tab_daily, tab_month = st.tabs(["捆重明细", "批次汇总", "每日指标", "区间汇总"])

with tab_raw:
    raw_display = measurements[
        [
            "production_date",
            "spec_name",
            "rolling_line",
            "team",
            "batch_no",
            "operator",
            "bundle_index",
            "actual_weight",
            "target_weight",
            "lower_spec_limit",
            "deviation",
            "negative_deviation",
            "remarks",
        ]
    ].rename(
        columns={
            "production_date": "日期",
            "spec_name": "规格",
            "rolling_line": "轧线",
            "team": "班组",
            "batch_no": "批号",
            "operator": "录入人",
            "bundle_index": "序号",
            "actual_weight": "实际捆重",
            "target_weight": "目标捆重",
            "lower_spec_limit": "最低允许捆重",
            "deviation": "偏差",
            "negative_deviation": "负差",
            "remarks": "备注",
        }
    )
    show_dataframe(raw_display.round(3))
    download_csv("导出捆重明细 CSV", raw_display, "measurements.csv")

with tab_batch:
    batch_display = batches[
        [
            "batch_id",
            "spec_name",
            "production_date",
            "rolling_line",
            "team",
            "batch_no",
            "operator",
            "sample_count",
            "avg_weight",
            "min_weight",
            "max_weight",
            "remarks",
            "created_at",
        ]
    ].rename(
        columns={
            "batch_id": "批次 ID",
            "spec_name": "规格",
            "production_date": "日期",
            "rolling_line": "轧线",
            "team": "班组",
            "batch_no": "批号",
            "operator": "录入人",
            "sample_count": "样本数",
            "avg_weight": "平均捆重",
            "min_weight": "最小捆重",
            "max_weight": "最大捆重",
            "remarks": "备注",
            "created_at": "录入时间",
        }
    )
    show_dataframe(batch_display.round(3))
    download_csv("导出批次汇总 CSV", batch_display, "batches.csv")

    with st.expander("删除错误批次"):
        st.warning("删除批次会同时删除该批次下的所有捆重明细，请谨慎操作。")
        batch_ids = batches["batch_id"].tolist()
        batch_to_delete = st.selectbox(
            "选择要删除的批次",
            batch_ids,
            format_func=lambda batch_id: batches.loc[batches["batch_id"] == batch_id, "batch_no"].iloc[0],
        )
        confirm_delete = st.checkbox("我确认要删除这个批次")
        if st.button("删除批次", disabled=not confirm_delete):
            delete_batch(int(batch_to_delete))
            st.success("批次已删除。")
            st.rerun()

with tab_daily:
    daily_display = format_metric_table(daily_summary)
    show_dataframe(daily_display.round(3))
    download_csv("导出每日指标 CSV", daily_display, "daily_metrics.csv")

with tab_month:
    month_display = format_metric_table(monthly_summary)
    show_dataframe(month_display.round(3))
    download_csv("导出区间汇总 CSV", month_display, "period_metrics.csv")
