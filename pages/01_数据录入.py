from __future__ import annotations

from io import BytesIO
import re
from datetime import date

import pandas as pd
import streamlit as st

from auth import require_login
from components import show_dataframe
from database import ROLLING_LINES, TEAMS, create_batch_with_measurements, fetch_specs, init_db
from manual import render_user_manual


TEMPLATE_COLUMNS = ["生产日期", "规格", "轧线", "班组", "批号", "炉号", "捆号", "捆重", "备注", "录入人"]


def parse_weights(raw_text: str) -> tuple[list[float], list[str]]:
    tokens = re.split(r"[\s,，;；]+", raw_text.strip())
    weights: list[float] = []
    invalid: list[str] = []

    for token in tokens:
        if not token:
            continue
        try:
            value = float(token)
        except ValueError:
            invalid.append(token)
            continue
        if value <= 0:
            invalid.append(token)
        else:
            weights.append(value)

    return weights, invalid


def build_excel_template(specs: pd.DataFrame) -> bytes:
    sample_spec = specs["spec_name"].iloc[0] if not specs.empty else "φ16"
    template = pd.DataFrame(
        [
            {
                "生产日期": date.today().isoformat(),
                "规格": sample_spec,
                "轧线": "三轧",
                "班组": "甲班",
                "批号": "20260601-A",
                "炉号": "1092",
                "捆号": "1",
                "捆重": 1998.5,
                "备注": "示例：一行代表一捆",
                "录入人": "张三",
            },
            {
                "生产日期": date.today().isoformat(),
                "规格": sample_spec,
                "轧线": "三轧",
                "班组": "甲班",
                "批号": "20260601-A",
                "炉号": "1092",
                "捆号": "2",
                "捆重": 2001.2,
                "备注": "同一批号可填写多行捆重",
                "录入人": "张三",
            },
        ],
        columns=TEMPLATE_COLUMNS,
    )
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        template.to_excel(writer, index=False, sheet_name="捆重导入模板")
        pd.DataFrame({"可选规格": specs["spec_name"].tolist()}).to_excel(writer, index=False, sheet_name="规格清单")
        pd.DataFrame({"可选轧线": ROLLING_LINES}).to_excel(writer, index=False, sheet_name="轧线")
        pd.DataFrame({"可选班组": TEAMS}).to_excel(writer, index=False, sheet_name="班组")
    return buffer.getvalue()


def read_import_file(uploaded_file, specs: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    try:
        imported = pd.read_excel(uploaded_file, sheet_name=0)
    except Exception as exc:
        return pd.DataFrame(), [f"无法读取 Excel 文件：{exc}"]

    imported.columns = [str(column).strip() for column in imported.columns]
    missing_columns = [column for column in TEMPLATE_COLUMNS if column not in imported.columns]
    if missing_columns:
        return imported, ["模板缺少必填列：" + "、".join(missing_columns)]

    df = imported[TEMPLATE_COLUMNS].dropna(how="all").copy()
    if df.empty:
        return df, ["Excel 中没有可导入的数据。"]

    errors: list[str] = []
    spec_names = set(specs["spec_name"].tolist())

    for column in ["规格", "轧线", "班组", "批号", "炉号", "捆号", "备注", "录入人"]:
        df[column] = df[column].fillna("").astype(str).str.strip()

    df["生产日期"] = pd.to_datetime(df["生产日期"], errors="coerce").dt.date
    df["捆重"] = pd.to_numeric(df["捆重"], errors="coerce")

    invalid_dates = df["生产日期"].isna()
    invalid_weights = df["捆重"].isna() | (df["捆重"] <= 0)
    invalid_specs = ~df["规格"].isin(spec_names)
    invalid_lines = ~df["轧线"].isin(ROLLING_LINES)
    invalid_teams = ~df["班组"].isin(TEAMS)
    empty_batches = df["批号"] == ""

    if invalid_dates.any():
        errors.append(f"有 {int(invalid_dates.sum())} 行生产日期无效。")
    if invalid_weights.any():
        errors.append(f"有 {int(invalid_weights.sum())} 行捆重为空或不是正数。")
    if invalid_specs.any():
        bad_specs = sorted(df.loc[invalid_specs, "规格"].dropna().unique().tolist())
        errors.append("存在未启用或不存在的规格：" + "、".join(bad_specs[:10]))
    if invalid_lines.any():
        errors.append("轧线只能填写：三轧、四轧。")
    if invalid_teams.any():
        errors.append("班组只能填写：甲班、乙班。")
    if empty_batches.any():
        errors.append(f"有 {int(empty_batches.sum())} 行批号为空。")

    return df, errors


def import_excel_rows(df: pd.DataFrame, specs: pd.DataFrame) -> tuple[int, int]:
    spec_ids = {row["spec_name"]: int(row["id"]) for _, row in specs.iterrows()}
    group_columns = ["生产日期", "规格", "轧线", "班组", "批号", "录入人"]

    created_batches = 0
    created_measurements = 0
    for keys, group in df.groupby(group_columns, dropna=False):
        production_date, spec_name, rolling_line, team, batch_no, operator = keys
        measurement_rows = [
            {
                "furnace_no": row["炉号"],
                "bundle_no": row["捆号"],
                "actual_weight": row["捆重"],
                "measurement_remarks": row["备注"],
            }
            for _, row in group.iterrows()
        ]
        create_batch_with_measurements(
            spec_id=spec_ids[spec_name],
            production_date=production_date.isoformat(),
            rolling_line=rolling_line,
            team=team,
            batch_no=batch_no,
            operator=operator,
            remarks="Excel模板导入",
            weights=[],
            measurement_rows=measurement_rows,
        )
        created_batches += 1
        created_measurements += len(measurement_rows)

    return created_batches, created_measurements


st.set_page_config(page_title="数据录入", layout="wide")
require_login()
init_db()
render_user_manual()

st.title("数据录入")
st.caption("选择规格、轧线、班组和批次信息后，可手工录入，也可按 Excel 模板批量导入。")

specs = fetch_specs(include_inactive=False)

if specs.empty:
    st.warning("请先到“规格配置”页面新增并启用至少一个规格。")
    st.stop()

selected_spec_id = st.selectbox(
    "规格",
    specs["id"].tolist(),
    format_func=lambda spec_id: specs.loc[specs["id"] == spec_id, "spec_name"].iloc[0],
)
selected_spec = specs.loc[specs["id"] == selected_spec_id].iloc[0]

manual_tab, import_tab = st.tabs(["手工录入", "Excel 模板导入"])

with manual_tab:
    col1, col2, col3, col4, col5 = st.columns(5)
    production_date = col1.date_input("生产日期", value=date.today())
    rolling_line = col2.selectbox("轧线", ROLLING_LINES)
    team = col3.selectbox("班组", TEAMS)
    batch_no = col4.text_input("批号", placeholder="例如 20260601-A")
    operator = col5.text_input("录入人", placeholder="姓名")

    remarks = st.text_input("备注", placeholder="可选")
    raw_weights = st.text_area(
        "捆重数据",
        height=180,
        placeholder="每行一个捆重，也可以用空格、逗号或从 Excel 直接粘贴。\n例如：\n998.2\n1001.5\n996.8",
    )

    weights, invalid_tokens = parse_weights(raw_weights)

    st.subheader("录入预览")
    if invalid_tokens:
        st.error("以下内容无法识别为有效正数：" + "、".join(invalid_tokens[:20]))

    if weights:
        preview = pd.DataFrame(
            {
                "炉号": "",
                "捆号": [str(index) for index in range(1, len(weights) + 1)],
                "实际捆重": weights,
                "备注": "",
            }
        )
        preview["轧线"] = rolling_line
        preview["班组"] = team
        preview["目标捆重"] = float(selected_spec["target_weight"])
        preview["偏差"] = preview["实际捆重"] - preview["目标捆重"]
        preview["是否负差"] = preview["偏差"] < 0
        edited_preview = st.data_editor(
            preview,
            use_container_width=True,
            hide_index=True,
            height=300,
            column_config={
                "炉号": st.column_config.TextColumn("炉号", help="来自纸表的炉号，可按每捆填写"),
                "捆号": st.column_config.TextColumn("捆号", help="来自纸表的捆号"),
                "实际捆重": st.column_config.NumberColumn("实际捆重", min_value=0.01, step=0.01),
                "备注": st.column_config.TextColumn("备注", help="单捆备注或复查说明"),
            },
            disabled=["轧线", "班组", "目标捆重", "偏差", "是否负差"],
        )
        edited_preview["实际捆重"] = pd.to_numeric(edited_preview["实际捆重"], errors="coerce")
        edited_preview["偏差"] = edited_preview["实际捆重"] - float(selected_spec["target_weight"])
        edited_preview["是否负差"] = edited_preview["偏差"] < 0

        col_a, col_b, col_c, col_d = st.columns(4)
        col_a.metric("本次样本数", len(edited_preview))
        col_b.metric("平均捆重", f"{edited_preview['实际捆重'].mean():.2f} {selected_spec['unit']}")
        col_c.metric("平均偏差", f"{edited_preview['偏差'].mean():.2f} {selected_spec['unit']}")
        col_d.metric("负差数", int(edited_preview["是否负差"].sum()))
    else:
        st.info("粘贴捆重后，这里会显示录入预览。")

    submitted = st.button("提交本批数据", type="primary", disabled=not weights or bool(invalid_tokens))

    if submitted:
        try:
            batch_id = create_batch_with_measurements(
                spec_id=int(selected_spec_id),
                production_date=production_date.isoformat(),
                rolling_line=rolling_line,
                team=team,
                batch_no=batch_no,
                operator=operator,
                remarks=remarks,
                weights=[],
                measurement_rows=[
                    {
                        "furnace_no": row["炉号"],
                        "bundle_no": row["捆号"],
                        "actual_weight": row["实际捆重"],
                        "measurement_remarks": row["备注"],
                    }
                    for _, row in edited_preview.iterrows()
                    if pd.notna(row["实际捆重"]) and float(row["实际捆重"]) > 0
                ],
            )
            st.success(f"已保存批次 {batch_no}，批次 ID：{batch_id}。")
        except ValueError as exc:
            st.error(f"提交失败：{exc}")

with import_tab:
    st.markdown("模板要求：一行代表一捆重量；同一批号填写多行，导入时会自动合并成一个批次。")
    st.download_button(
        "下载 Excel 导入模板",
        data=build_excel_template(specs),
        file_name="cpk_bundle_import_template.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    uploaded_file = st.file_uploader("上传填写好的 Excel 模板", type=["xlsx"])
    if uploaded_file is not None:
        import_df, import_errors = read_import_file(uploaded_file, specs)
        st.subheader("导入预览")
        if not import_df.empty:
            show_dataframe(import_df, height=320)

        if import_errors:
            for error in import_errors:
                st.error(error)
        else:
            batch_count = import_df.groupby(["生产日期", "规格", "轧线", "班组", "批号", "录入人"], dropna=False).ngroups
            st.success(f"校验通过：将导入 {batch_count} 个批次、{len(import_df)} 条捆重。")
            if st.button("确认导入 Excel 数据", type="primary"):
                created_batches, created_measurements = import_excel_rows(import_df, specs)
                st.success(f"导入完成：新增 {created_batches} 个批次、{created_measurements} 条捆重。")
