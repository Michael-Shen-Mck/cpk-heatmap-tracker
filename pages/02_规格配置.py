import sqlite3

import streamlit as st

from auth import require_login
from components import show_dataframe
from database import fetch_specs, init_db, save_spec
from manual import render_user_manual


def normalize_spec_columns(specs):
    normalized = specs.copy()
    if "lower_tolerance_percent" not in normalized.columns:
        normalized["lower_tolerance_percent"] = normalized["lower_tolerance"] / normalized["target_weight"] * 100
    if "lower_tolerance" not in normalized.columns:
        normalized["lower_tolerance"] = normalized["target_weight"] * normalized["lower_tolerance_percent"] / 100
    if "lower_spec_limit" not in normalized.columns:
        normalized["lower_spec_limit"] = normalized["target_weight"] - normalized["lower_tolerance"]
    return normalized


st.set_page_config(page_title="规格配置", layout="wide")
require_login()
init_db()
render_user_manual()

st.title("规格配置")
st.caption("维护每个规格的目标捆重和允许负差百分比。系统会自动计算最低允许捆重。")

specs = normalize_spec_columns(fetch_specs(include_inactive=True))

if specs.empty:
    st.info("还没有规格，请先新增一个规格。")
else:
    display = specs.copy()
    display["状态"] = display["is_active"].map({1: "启用", 0: "停用"})
    display = display.rename(
        columns={
            "spec_name": "规格",
            "target_weight": "目标捆重",
            "lower_tolerance_percent": "允许负差(%)",
            "lower_tolerance": "允许负差重量",
            "lower_spec_limit": "最低允许捆重",
            "unit": "单位",
            "updated_at": "更新时间",
        }
    )
    show_dataframe(display[["规格", "目标捆重", "允许负差(%)", "允许负差重量", "最低允许捆重", "单位", "状态", "更新时间"]])


with st.expander("新增规格", expanded=specs.empty):
    with st.form("add_spec_form", clear_on_submit=True):
        col1, col2, col3, col4 = st.columns(4)
        spec_name = col1.text_input("规格名称", placeholder="例如 12mm / Φ16")
        target_weight = col2.number_input("目标捆重", min_value=0.01, value=1000.0, step=1.0)
        lower_tolerance_percent = col3.number_input("允许负差(%)", min_value=0.0, value=0.4, step=0.01, format="%.3f")
        unit = col4.text_input("单位", value="kg")
        lower_tolerance = target_weight * lower_tolerance_percent / 100
        st.info(f"自动计算：允许负差重量 {lower_tolerance:.3f} {unit}，最低允许捆重 {target_weight - lower_tolerance:.3f} {unit}")
        submitted = st.form_submit_button("保存新规格", type="primary")

    if submitted:
        try:
            save_spec(
                spec_name=spec_name,
                target_weight=target_weight,
                lower_tolerance_percent=lower_tolerance_percent,
                unit=unit,
            )
            st.success("规格已保存。")
            st.rerun()
        except (ValueError, sqlite3.IntegrityError) as exc:
            st.error(f"保存失败：{exc}")


with st.expander("编辑已有规格", expanded=False):
    if specs.empty:
        st.warning("暂无可编辑规格。")
    else:
        selected_id = st.selectbox(
            "选择规格",
            specs["id"].tolist(),
            format_func=lambda spec_id: specs.loc[specs["id"] == spec_id, "spec_name"].iloc[0],
        )
        selected = specs.loc[specs["id"] == selected_id].iloc[0]

        with st.form("edit_spec_form"):
            col1, col2, col3, col4, col5 = st.columns([2, 1, 1, 1, 1])
            edit_name = col1.text_input("规格名称", value=selected["spec_name"])
            edit_target = col2.number_input("目标捆重", min_value=0.01, value=float(selected["target_weight"]), step=1.0)
            edit_tolerance_percent = col3.number_input(
                "允许负差(%)",
                min_value=0.0,
                value=float(selected["lower_tolerance_percent"]),
                step=0.01,
                format="%.3f",
            )
            edit_unit = col4.text_input("单位", value=selected["unit"])
            edit_active = col5.checkbox("启用", value=bool(selected["is_active"]))
            edit_tolerance = edit_target * edit_tolerance_percent / 100
            st.info(f"自动计算：允许负差重量 {edit_tolerance:.3f} {edit_unit}，最低允许捆重 {edit_target - edit_tolerance:.3f} {edit_unit}")
            edit_submitted = st.form_submit_button("保存修改", type="primary")

        if edit_submitted:
            try:
                save_spec(
                    spec_id=int(selected_id),
                    spec_name=edit_name,
                    target_weight=edit_target,
                    lower_tolerance_percent=edit_tolerance_percent,
                    unit=edit_unit,
                    is_active=edit_active,
                )
                st.success("规格已更新。")
                st.rerun()
            except (ValueError, sqlite3.IntegrityError) as exc:
                st.error(f"保存失败：{exc}")
