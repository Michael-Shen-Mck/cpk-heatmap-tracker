from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def render_user_manual() -> None:
    _, manual_col = st.columns([0.78, 0.22])
    with manual_col:
        with st.popover("打开使用说明书", use_container_width=True):
            st.markdown(
                """
                ### 1. 规格配置

                - 先维护规格、目标捆重和允许负差。
                - 允许负差填写正数，例如目标 2000kg、最低允许 1992kg，则允许负差填 8。
                - 停用规格不会出现在录入页面，但历史数据仍可查询。

                ### 2. 数据录入

                - 选择规格、生产日期、班次、批号和录入人。
                - 捆重可以一行一个，也可以从 Excel 复制一列直接粘贴。
                - 提交前先看预览，确认样本数、平均捆重、平均偏差和负差数。

                ### 3. 热力图查看

                - 选择年份和月份后，系统按“规格 x 日期”展示 Cpl。
                - 绿色表示 `Cpl >= 1.33`，黄色表示 `1.00 <= Cpl < 1.33`，红色表示 `Cpl < 1.00`。
                - 样本不足 5 条时不计算 Cpl。

                ### 4. 数据导出和纠错

                - 在“数据明细与导出”中可以导出捆重明细、批次汇总、每日指标和区间汇总。
                - 如果录错批次，可以在“批次汇总”页签中勾选确认后删除整个批次。

                ### 5. 计算口径

                - 偏差 = 实际捆重 - 目标捆重
                - 允许负差下限 = -允许负差
                - Cpl = (平均偏差 - 允许负差下限) / (3 x 偏差标准差)
                """
            )


def show_dataframe(df: pd.DataFrame, *, height: int = 420) -> None:
    st.dataframe(df, use_container_width=True, hide_index=True, height=height)


def metric_cards(summary: pd.DataFrame) -> None:
    if summary.empty:
        return

    sample_count = int(summary["sample_count"].sum())
    weighted_cpl = summary.dropna(subset=["cpl"])
    avg_cpl = weighted_cpl["cpl"].mean() if not weighted_cpl.empty else None
    risk_days = int((summary["status"] == "risk").sum())
    watch_days = int((summary["status"] == "watch").sum())

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("样本数", f"{sample_count:,}")
    col2.metric("平均 Cpl", "-" if avg_cpl is None else f"{avg_cpl:.2f}")
    col3.metric("能力不足格数", risk_days)
    col4.metric("需关注格数", watch_days)


def make_heatmap_figure(matrix: pd.DataFrame) -> go.Figure:
    x_labels = [str(col)[-2:] for col in matrix.columns]
    y_labels = matrix.index.tolist()
    z = matrix.to_numpy(dtype=float)
    text = matrix.map(lambda value: "" if pd.isna(value) else f"{value:.2f}").to_numpy()

    fig = go.Figure(
        data=go.Heatmap(
            z=z,
            text=text,
            texttemplate="%{text}",
            textfont={"size": 11, "color": "#111111"},
            x=x_labels,
            y=y_labels,
            zmin=0,
            zmax=1.67,
            colorscale=[
                [0.0, "#c0392b"],
                [0.60, "#c0392b"],
                [0.60, "#f1c40f"],
                [0.80, "#f1c40f"],
                [0.80, "#27ae60"],
                [1.0, "#27ae60"],
            ],
            colorbar={"title": "Cpl"},
            hovertemplate="规格：%{y}<br>日期：%{x}日<br>Cpl：%{z:.2f}<extra></extra>",
        )
    )
    fig.update_layout(
        height=max(360, 70 + 34 * max(len(y_labels), 1)),
        margin=dict(l=20, r=20, t=30, b=20),
        xaxis_title="日期",
        yaxis_title="规格",
        plot_bgcolor="#f0f2f6",
    )
    return fig


def download_csv(label: str, df: pd.DataFrame, file_name: str) -> None:
    csv = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(label, data=csv, file_name=file_name, mime="text/csv")
