from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

import pandas as pd


DB_PATH = Path(__file__).resolve().parent / "data" / "cpk_tracker.db"
ROLLING_LINES = ["三轧", "四轧"]
TEAMS = ["甲班", "乙班"]


def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Return a SQLite connection with foreign keys enabled."""
    db_path = Path(db_path or DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS specs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                spec_name TEXT NOT NULL UNIQUE,
                target_weight REAL NOT NULL CHECK (target_weight > 0),
                lower_tolerance REAL NOT NULL CHECK (lower_tolerance >= 0),
                unit TEXT NOT NULL DEFAULT 'kg',
                is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TRIGGER IF NOT EXISTS specs_updated_at
            AFTER UPDATE ON specs
            FOR EACH ROW
            BEGIN
                UPDATE specs SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
            END;

            CREATE TABLE IF NOT EXISTS batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                spec_id INTEGER NOT NULL,
                production_date TEXT NOT NULL,
                rolling_line TEXT,
                team TEXT,
                shift TEXT,
                batch_no TEXT NOT NULL,
                operator TEXT,
                remarks TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (spec_id) REFERENCES specs (id)
            );

            CREATE TABLE IF NOT EXISTS measurements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id INTEGER NOT NULL,
                bundle_index INTEGER NOT NULL,
                actual_weight REAL NOT NULL CHECK (actual_weight > 0),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (batch_id) REFERENCES batches (id) ON DELETE CASCADE,
                UNIQUE (batch_id, bundle_index)
            );
            """
        )
        ensure_column(conn, "batches", "rolling_line", "TEXT")
        ensure_column(conn, "batches", "team", "TEXT")


def ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, column_type: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}
    if column_name not in columns:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")


def fetch_specs(include_inactive: bool = False) -> pd.DataFrame:
    where = "" if include_inactive else "WHERE is_active = 1"
    with get_connection() as conn:
        return pd.read_sql_query(
            f"""
            SELECT
                id,
                spec_name,
                target_weight,
                lower_tolerance,
                target_weight - lower_tolerance AS lower_spec_limit,
                unit,
                is_active,
                created_at,
                updated_at
            FROM specs
            {where}
            ORDER BY spec_name
            """,
            conn,
        )


def get_spec(spec_id: int) -> pd.Series | None:
    specs = fetch_specs(include_inactive=True)
    match = specs.loc[specs["id"] == spec_id]
    if match.empty:
        return None
    return match.iloc[0]


def save_spec(
    *,
    spec_name: str,
    target_weight: float,
    lower_tolerance: float,
    unit: str = "kg",
    is_active: bool = True,
    spec_id: int | None = None,
) -> int:
    spec_name = spec_name.strip()
    unit = unit.strip() or "kg"
    if not spec_name:
        raise ValueError("规格名称不能为空")
    if target_weight <= 0:
        raise ValueError("目标捆重必须大于 0")
    if lower_tolerance < 0:
        raise ValueError("允许负差不能小于 0")

    with get_connection() as conn:
        if spec_id is None:
            cursor = conn.execute(
                """
                INSERT INTO specs (spec_name, target_weight, lower_tolerance, unit, is_active)
                VALUES (?, ?, ?, ?, ?)
                """,
                (spec_name, target_weight, lower_tolerance, unit, int(is_active)),
            )
            return int(cursor.lastrowid)

        conn.execute(
            """
            UPDATE specs
            SET spec_name = ?,
                target_weight = ?,
                lower_tolerance = ?,
                unit = ?,
                is_active = ?
            WHERE id = ?
            """,
            (spec_name, target_weight, lower_tolerance, unit, int(is_active), spec_id),
        )
        return spec_id


def create_batch_with_measurements(
    *,
    spec_id: int,
    production_date: str,
    batch_no: str,
    operator: str,
    remarks: str,
    weights: Iterable[float],
    rolling_line: str = "",
    team: str = "",
    shift: str = "",
) -> int:
    clean_weights = [float(weight) for weight in weights if float(weight) > 0]
    if not clean_weights:
        raise ValueError("至少需要录入一条有效捆重")

    batch_no = batch_no.strip()
    if not batch_no:
        raise ValueError("批号不能为空")

    rolling_line = rolling_line.strip()
    team = team.strip()
    shift = shift.strip() or " / ".join(part for part in [rolling_line, team] if part)

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO batches (spec_id, production_date, rolling_line, team, shift, batch_no, operator, remarks)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                spec_id,
                production_date,
                rolling_line,
                team,
                shift,
                batch_no,
                operator.strip(),
                remarks.strip(),
            ),
        )
        batch_id = int(cursor.lastrowid)
        conn.executemany(
            """
            INSERT INTO measurements (batch_id, bundle_index, actual_weight)
            VALUES (?, ?, ?)
            """,
            [(batch_id, index, weight) for index, weight in enumerate(clean_weights, start=1)],
        )
        return batch_id


def fetch_measurements(
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    spec_id: int | None = None,
    rolling_line: str | None = None,
    team: str | None = None,
) -> pd.DataFrame:
    conditions: list[str] = []
    params: list[object] = []

    if start_date:
        conditions.append("b.production_date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("b.production_date <= ?")
        params.append(end_date)
    if spec_id:
        conditions.append("s.id = ?")
        params.append(spec_id)
    if rolling_line:
        conditions.append("b.rolling_line = ?")
        params.append(rolling_line)
    if team:
        conditions.append("b.team = ?")
        params.append(team)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    with get_connection() as conn:
        return pd.read_sql_query(
            f"""
            SELECT
                m.id AS measurement_id,
                b.id AS batch_id,
                s.id AS spec_id,
                s.spec_name,
                s.target_weight,
                s.lower_tolerance,
                s.target_weight - s.lower_tolerance AS lower_spec_limit,
                s.unit,
                b.production_date,
                COALESCE(NULLIF(b.rolling_line, ''), '未填写') AS rolling_line,
                COALESCE(NULLIF(b.team, ''), '未填写') AS team,
                b.shift,
                b.batch_no,
                b.operator,
                b.remarks,
                m.bundle_index,
                m.actual_weight,
                m.actual_weight - s.target_weight AS deviation,
                CASE WHEN m.actual_weight < s.target_weight THEN 1 ELSE 0 END AS is_negative
            FROM measurements m
            JOIN batches b ON b.id = m.batch_id
            JOIN specs s ON s.id = b.spec_id
            {where}
            ORDER BY b.production_date DESC, s.spec_name, b.batch_no, m.bundle_index
            """,
            conn,
            params=params,
        )


def fetch_batches(
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    spec_id: int | None = None,
    rolling_line: str | None = None,
    team: str | None = None,
) -> pd.DataFrame:
    conditions: list[str] = []
    params: list[object] = []

    if start_date:
        conditions.append("b.production_date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("b.production_date <= ?")
        params.append(end_date)
    if spec_id:
        conditions.append("s.id = ?")
        params.append(spec_id)
    if rolling_line:
        conditions.append("b.rolling_line = ?")
        params.append(rolling_line)
    if team:
        conditions.append("b.team = ?")
        params.append(team)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    with get_connection() as conn:
        return pd.read_sql_query(
            f"""
            SELECT
                b.id AS batch_id,
                s.spec_name,
                b.production_date,
                COALESCE(NULLIF(b.rolling_line, ''), '未填写') AS rolling_line,
                COALESCE(NULLIF(b.team, ''), '未填写') AS team,
                b.shift,
                b.batch_no,
                b.operator,
                COUNT(m.id) AS sample_count,
                ROUND(AVG(m.actual_weight), 3) AS avg_weight,
                ROUND(MIN(m.actual_weight), 3) AS min_weight,
                ROUND(MAX(m.actual_weight), 3) AS max_weight,
                b.remarks,
                b.created_at
            FROM batches b
            JOIN specs s ON s.id = b.spec_id
            LEFT JOIN measurements m ON m.batch_id = b.id
            {where}
            GROUP BY b.id
            ORDER BY b.production_date DESC, b.created_at DESC
            """,
            conn,
            params=params,
        )


def delete_batch(batch_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM batches WHERE id = ?", (batch_id,))


def count_demo_batches() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS count FROM batches WHERE batch_no LIKE 'DEMO-%'").fetchone()
    return int(row["count"])


def delete_demo_batches() -> int:
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM batches WHERE batch_no LIKE 'DEMO-%'")
        return int(cursor.rowcount)


def delete_all_batches() -> int:
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM batches")
        return int(cursor.rowcount)
