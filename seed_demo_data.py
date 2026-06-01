from __future__ import annotations

import random
from datetime import date, timedelta

from database import create_batch_with_measurements, fetch_measurements, fetch_specs, get_connection, init_db, save_spec


DEMO_SPECS = [
    ("φ14", 2000.0, 8.0),
    ("φ16", 2000.0, 8.0),
    ("φ18", 2500.0, 10.0),
    ("φ20", 2500.0, 10.0),
    ("φ22", 2500.0, 10.0),
    ("φ25", 3000.0, 12.0),
    ("φ28", 3000.0, 12.0),
    ("φ32", 3000.0, 12.0),
]
SPEC_LINE = {
    "φ14": "三轧",
    "φ16": "三轧",
    "φ18": "三轧",
    "φ20": "三轧",
    "φ22": "四轧",
    "φ25": "四轧",
    "φ28": "四轧",
    "φ32": "四轧",
}
TEAM_BY_BATCH_INDEX = {1: "甲班", 2: "乙班"}


def ensure_specs() -> dict[str, int]:
    specs = fetch_specs(include_inactive=True)
    existing = {row["spec_name"]: int(row["id"]) for _, row in specs.iterrows()} if not specs.empty else {}
    spec_ids: dict[str, int] = {}

    for spec_name, target_weight, lower_tolerance in DEMO_SPECS:
        if spec_name in existing:
            spec_id = existing[spec_name]
            save_spec(
                spec_id=spec_id,
                spec_name=spec_name,
                target_weight=target_weight,
                lower_tolerance=lower_tolerance,
                unit="kg",
                is_active=True,
            )
        else:
            spec_id = save_spec(
                spec_name=spec_name,
                target_weight=target_weight,
                lower_tolerance=lower_tolerance,
                unit="kg",
                is_active=True,
            )
        spec_ids[spec_name] = spec_id

    return spec_ids


def batch_exists(batch_no: str) -> bool:
    with get_connection() as conn:
        row = conn.execute("SELECT 1 FROM batches WHERE batch_no = ? LIMIT 1", (batch_no,)).fetchone()
    return row is not None


def backfill_demo_line_team() -> None:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT b.id, b.batch_no, s.spec_name
            FROM batches b
            JOIN specs s ON s.id = b.spec_id
            WHERE b.batch_no LIKE 'DEMO-%'
              AND (b.rolling_line IS NULL OR b.rolling_line = '' OR b.team IS NULL OR b.team = '')
            """
        ).fetchall()

        for row in rows:
            batch_index = int(str(row["batch_no"]).rsplit("-", 1)[-1])
            rolling_line = SPEC_LINE.get(row["spec_name"], "三轧")
            team = TEAM_BY_BATCH_INDEX.get(batch_index, "甲班")
            conn.execute(
                """
                UPDATE batches
                SET rolling_line = ?,
                    team = ?,
                    shift = ?
                WHERE id = ?
                """,
                (rolling_line, team, f"{rolling_line} / {team}", row["id"]),
            )


def build_weights(
    *,
    rng: random.Random,
    target_weight: float,
    lower_tolerance: float,
    day_index: int,
    spec_index: int,
    batch_index: int,
) -> list[float]:
    pattern = (day_index + spec_index) % 6
    if pattern in (0, 1):
        bias = lower_tolerance * 0.70
        sigma = lower_tolerance * 0.22
    elif pattern in (2, 3):
        bias = lower_tolerance * 0.35
        sigma = lower_tolerance * 0.34
    else:
        bias = -lower_tolerance * 0.15
        sigma = lower_tolerance * 0.48

    batch_shift = (batch_index - 0.5) * lower_tolerance * 0.12
    return [
        round(target_weight + bias + batch_shift + rng.gauss(0, sigma), 2)
        for _ in range(10)
    ]


def seed_demo_data() -> tuple[int, int]:
    init_db()
    rng = random.Random(20260601)
    spec_ids = ensure_specs()

    start_date = date(2026, 6, 1)
    days = 30
    created_batches = 0
    created_measurements = 0

    spec_lookup = {spec_name: (target, tolerance) for spec_name, target, tolerance in DEMO_SPECS}
    for spec_index, spec_name in enumerate(spec_ids):
        target_weight, lower_tolerance = spec_lookup[spec_name]
        for day_index in range(days):
            production_date = start_date + timedelta(days=day_index)
            for batch_index, team in TEAM_BY_BATCH_INDEX.items():
                batch_no = f"DEMO-{production_date:%Y%m%d}-{spec_name}-{batch_index}"
                if batch_exists(batch_no):
                    continue

                weights = build_weights(
                    rng=rng,
                    target_weight=target_weight,
                    lower_tolerance=lower_tolerance,
                    day_index=day_index,
                    spec_index=spec_index,
                    batch_index=batch_index,
                )
                create_batch_with_measurements(
                    spec_id=spec_ids[spec_name],
                    production_date=production_date.isoformat(),
                    rolling_line=SPEC_LINE.get(spec_name, "三轧"),
                    team=team,
                    batch_no=batch_no,
                    operator="演示数据",
                    remarks="系统生成的演示数据，可在明细页删除批次",
                    weights=weights,
                )
                created_batches += 1
                created_measurements += len(weights)

    backfill_demo_line_team()
    return created_batches, created_measurements


def seed_demo_data_if_empty() -> tuple[int, int]:
    init_db()
    measurements = fetch_measurements()
    if not measurements.empty:
        backfill_demo_line_team()
        return 0, 0
    return seed_demo_data()


if __name__ == "__main__":
    batches, measurements = seed_demo_data()
    print(f"Demo seed complete. batches={batches}, measurements={measurements}")
