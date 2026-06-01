from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from auth import require_login
from components import make_heatmap_figure, metric_cards, show_dataframe
from database import ROLLING_LINES, TEAMS, fetch_measurements, fetch_specs, init_db
from manual import render_user_manual
from metrics import build_heatmap_matrix, format_metric_table, month_bounds, summarize_daily, summarize_monthly


st.set_page_config(page_title="过程能力热力图", layout="wide")
require_login()
init_db()
render_user_manual()

st.title("过程能力热力图")
st.caption("按月查看每个规格每天的负差过程能力。Cpl 越高，越能稳定满足允许负差下限。")

today = date.today()
col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
year = int(col1.number_input("年份", min_value=2020, max_value=2100, value=today.year, step=1))
month = int(col2.selectbox("月份", list(range(1, 13)), index=today.month - 1))
selected_line = col3.selectbox("轧线", ["全部轧线"] + ROLLING_LINES)
selected_team = col4.selectbox("班组", ["全部班组"] + TEAMS)

start_date, end_date = month_bounds(year, month)
measurements = fetch_measurements(
    start_date=start_date,
    end_date=end_date,
    rolling_line=None if selected_line == "全部轧线" else selected_line,
    team=None if selected_team == "全部班组" else selected_team,
)

if measurements.empty:
    st.warning("当前月份还没有捆重数据。请先在“数据录入”页面录入数据。")
    st.stop()

daily_summary = summarize_daily(measurements)
monthly_summary = summarize_monthly(measurements)
matrix = build_heatmap_matrix(daily_summary, year, month)

metric_cards(daily_summary)

st.subheader("月度 Cpl 热力图")
st.markdown("颜色规则：绿色 `Cpl >= 1.33`，黄色 `1.00 <= Cpl < 1.33`，红色 `Cpl < 1.00`，空白表示无数据或样本不足。")
st.plotly_chart(make_heatmap_figure(matrix), use_container_width=True)

st.subheader("规格月度汇总")
monthly_display = format_metric_table(monthly_summary)
show_dataframe(monthly_display.round(3), height=260)

st.subheader("查看某一天的明细")
specs = fetch_specs(include_inactive=True)
available_specs = daily_summary["spec_id"].drop_duplicates().tolist()
filtered_specs = specs.loc[specs["id"].isin(available_specs)]

detail_col1, detail_col2 = st.columns(2)
selected_spec_id = detail_col1.selectbox(
    "规格",
    filtered_specs["id"].tolist(),
    format_func=lambda spec_id: filtered_specs.loc[filtered_specs["id"] == spec_id, "spec_name"].iloc[0],
)

available_dates = (
    daily_summary.loc[daily_summary["spec_id"] == selected_spec_id, "production_date"]
    .drop_duplicates()
    .sort_values()
    .tolist()
)
selected_date = detail_col2.selectbox("日期", available_dates)

selected_summary = daily_summary.loc[
    (daily_summary["spec_id"] == selected_spec_id) & (daily_summary["production_date"] == selected_date)
]
selected_measurements = measurements.loc[
    (measurements["spec_id"] == selected_spec_id) & (measurements["production_date"] == selected_date)
].copy()

if not selected_summary.empty:
    summary_display = format_metric_table(selected_summary)
    show_dataframe(summary_display.round(3), height=120)

if not selected_measurements.empty:
    selected_measurements["负差"] = selected_measurements["deviation"].where(selected_measurements["deviation"] < 0, 0)
    detail_display = selected_measurements[
        [
            "production_date",
            "spec_name",
            "rolling_line",
            "team",
            "batch_no",
            "operator",
            "furnace_no",
            "bundle_index",
            "bundle_no",
            "actual_weight",
            "target_weight",
            "deviation",
            "负差",
            "measurement_remarks",
        ]
    ].rename(
        columns={
            "production_date": "日期",
            "spec_name": "规格",
            "rolling_line": "轧线",
            "team": "班组",
            "batch_no": "批号",
            "operator": "录入人",
            "furnace_no": "炉号",
            "bundle_index": "序号",
            "bundle_no": "捆号",
            "actual_weight": "实际捆重",
            "target_weight": "目标捆重",
            "deviation": "偏差",
            "measurement_remarks": "备注",
        }
    )
    show_dataframe(detail_display.round(3))
