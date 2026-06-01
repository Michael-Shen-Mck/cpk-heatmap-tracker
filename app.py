import streamlit as st

from auth import require_login
from database import init_db
from manual import render_user_manual
from seed_demo_data import seed_demo_data_if_empty


st.set_page_config(
    page_title="CPK Heatmap 平台",
    page_icon="📊",
    layout="wide",
)

require_login()
init_db()
seed_demo_data_if_empty()
render_user_manual()

st.title("CPK Heatmap 平台")
st.caption("录入不同规格、批次的捆重数据，并按负差规则查看过程能力热力图。")

st.markdown(
    """
    ### 使用流程

    1. 先在 **规格配置** 中维护规格、目标捆重和允许负差。
    2. 员工在 **数据录入** 中选择规格、轧线、班组、批号并录入每捆重量。
    3. 在 **过程能力热力图** 中选择月份、轧线、班组，查看各规格每天的 Cpl 表现。
    4. 在 **数据明细与导出** 中筛选、核对并导出原始数据和月度指标。
    """
)

st.info("左侧菜单可以切换页面。首次使用建议先进入“规格配置”。")
