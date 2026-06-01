from __future__ import annotations

import calendar
from datetime import date

import numpy as np
import pandas as pd


MIN_CPK_SAMPLES = 5

SUMMARY_COLUMNS = [
    "spec_id",
    "spec_name",
    "production_date",
    "sample_count",
    "target_weight",
    "lower_tolerance_percent",
    "lower_tolerance",
    "lsl_deviation",
    "mean_weight",
    "mean_deviation",
    "std_deviation",
    "negative_count",
    "negative_rate",
    "avg_negative_deviation",
    "max_negative_deviation",
    "cpl",
    "status",
    "status_label",
]


def month_bounds(year: int, month: int) -> tuple[str, str]:
    last_day = calendar.monthrange(year, month)[1]
    return f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{last_day:02d}"


def add_metric_columns(measurements: pd.DataFrame) -> pd.DataFrame:
    if measurements.empty:
        return measurements.copy()

    df = measurements.copy()
    if "production_date" in df.columns:
        df["production_date"] = pd.to_datetime(df["production_date"]).dt.date.astype(str)
    df["deviation"] = df["actual_weight"] - df["target_weight"]
    df["lsl_deviation"] = -df["lower_tolerance"].abs()
    df["negative_deviation"] = np.where(df["deviation"] < 0, df["deviation"], 0.0)
    df["is_negative"] = df["deviation"] < 0
    return df


def classify_cpl(cpl: float | None, sample_count: int, std_deviation: float | None) -> tuple[str, str]:
    if sample_count < MIN_CPK_SAMPLES:
        return "insufficient", "样本不足"
    if std_deviation is None or pd.isna(std_deviation) or np.isclose(std_deviation, 0):
        return "no_variation", "无波动"
    if cpl is None or pd.isna(cpl):
        return "unknown", "无法计算"
    if cpl >= 1.33:
        return "good", "良好"
    if cpl >= 1.0:
        return "watch", "关注"
    return "risk", "不足"


def calculate_group_metrics(group: pd.DataFrame) -> pd.Series:
    df = add_metric_columns(group)
    sample_count = int(len(df))
    target_weight = float(df["target_weight"].iloc[0])
    lower_tolerance_percent = (
        float(df["lower_tolerance_percent"].iloc[0])
        if "lower_tolerance_percent" in df.columns
        else float(df["lower_tolerance"].iloc[0]) / target_weight * 100
    )
    lower_tolerance = float(df["lower_tolerance"].iloc[0])
    lsl_deviation = -abs(lower_tolerance)

    mean_weight = float(df["actual_weight"].mean())
    mean_deviation = float(df["deviation"].mean())
    std_deviation = float(df["deviation"].std(ddof=1)) if sample_count > 1 else np.nan
    negative = df.loc[df["deviation"] < 0, "deviation"]
    negative_count = int(negative.count())
    negative_rate = negative_count / sample_count if sample_count else np.nan
    avg_negative_deviation = float(negative.mean()) if negative_count else 0.0
    max_negative_deviation = float(negative.min()) if negative_count else 0.0

    cpl = np.nan
    if sample_count >= MIN_CPK_SAMPLES and not pd.isna(std_deviation) and not np.isclose(std_deviation, 0):
        cpl = (mean_deviation - lsl_deviation) / (3 * std_deviation)

    status, status_label = classify_cpl(cpl, sample_count, std_deviation)

    return pd.Series(
        {
            "sample_count": sample_count,
            "target_weight": target_weight,
            "lower_tolerance_percent": lower_tolerance_percent,
            "lower_tolerance": lower_tolerance,
            "lsl_deviation": lsl_deviation,
            "mean_weight": mean_weight,
            "mean_deviation": mean_deviation,
            "std_deviation": std_deviation,
            "negative_count": negative_count,
            "negative_rate": negative_rate,
            "avg_negative_deviation": avg_negative_deviation,
            "max_negative_deviation": max_negative_deviation,
            "cpl": cpl,
            "status": status,
            "status_label": status_label,
        }
    )


def summarize_daily(measurements: pd.DataFrame) -> pd.DataFrame:
    if measurements.empty:
        return pd.DataFrame(columns=SUMMARY_COLUMNS)

    df = add_metric_columns(measurements)
    summary = (
        df.groupby(["spec_id", "spec_name", "production_date"])
        .apply(calculate_group_metrics)
        .reset_index()
    )
    return summary[SUMMARY_COLUMNS].sort_values(["spec_name", "production_date"])


def summarize_monthly(measurements: pd.DataFrame) -> pd.DataFrame:
    if measurements.empty:
        return pd.DataFrame(columns=[col for col in SUMMARY_COLUMNS if col != "production_date"])

    df = add_metric_columns(measurements)
    summary = df.groupby(["spec_id", "spec_name"]).apply(calculate_group_metrics).reset_index()
    columns = [col for col in SUMMARY_COLUMNS if col != "production_date"]
    return summary[columns].sort_values("spec_name")


def build_heatmap_matrix(daily_summary: pd.DataFrame, year: int, month: int) -> pd.DataFrame:
    if daily_summary.empty:
        return pd.DataFrame()

    start, end = month_bounds(year, month)
    days = pd.date_range(start=start, end=end, freq="D").strftime("%Y-%m-%d").tolist()
    matrix = (
        daily_summary.pivot(index="spec_name", columns="production_date", values="cpl")
        .reindex(columns=days)
        .sort_index()
    )
    return matrix


def format_metric_table(summary: pd.DataFrame) -> pd.DataFrame:
    if summary.empty:
        return summary

    table = summary.copy()
    rename_map = {
        "spec_name": "规格",
        "production_date": "日期",
        "sample_count": "样本数",
        "target_weight": "目标捆重",
        "lower_tolerance_percent": "允许负差(%)",
        "lower_tolerance": "允许负差重量",
        "mean_weight": "平均捆重",
        "mean_deviation": "平均偏差",
        "std_deviation": "偏差标准差",
        "negative_count": "负差数",
        "negative_rate": "负差率",
        "avg_negative_deviation": "平均负差",
        "max_negative_deviation": "最大负差",
        "cpl": "Cpl",
        "status_label": "状态",
    }
    table = table.rename(columns=rename_map)
    display_columns = [column for column in rename_map.values() if column in table.columns]
    return table[display_columns]
