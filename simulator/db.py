"""
Database layer for vehicle telemetry.

Design decisions:
- SQLite is enough at this stage: single-writer (the ingest service),
  and reads (for the API/UI) are simple range queries on an indexed
  timestamp column. No need for a dedicated time-series DB yet.
- WAL (write-ahead log) mode is enabled so the API can read the DB
  concurrently while the ingest service is still writing to it --
  without WAL, SQLite would block readers during writes.
- fault_flags is stored as a JSON string (SQLite has no array type).
  Fine at this scale; if you outgrow this, a separate `faults` table
  keyed by timestamp would let you query/filter by fault type directly.
"""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent / "telemetry.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS telemetry (
    ts REAL PRIMARY KEY,
    soc_pct REAL NOT NULL,
    pack_voltage REAL NOT NULL,
    pack_current REAL NOT NULL,
    motor_temp_c REAL NOT NULL,
    speed_kph REAL NOT NULL,
    odometer_km REAL NOT NULL,
    range_km REAL NOT NULL,
    power_kw REAL NOT NULL,
    consumption_kwh_per_100km REAL NOT NULL,
    power_mode TEXT NOT NULL,
    fault_flags TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_telemetry_ts ON telemetry(ts);
"""


@contextmanager
def get_connection(db_path: Path = DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db(db_path: Path = DB_PATH) -> None:
    with get_connection(db_path) as conn:
        conn.executescript(SCHEMA)
        conn.commit()


def insert_telemetry(state: dict, db_path: Path = DB_PATH) -> None:
    """
    Insert one VehicleState tick (as a dict, e.g. from json.loads on the
    MQTT payload) into the telemetry table. Uses INSERT OR IGNORE so a
    duplicate/replayed message with the same timestamp doesn't crash
    the ingest loop.
    """
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO telemetry (
                ts, soc_pct, pack_voltage, pack_current, motor_temp_c,
                speed_kph, odometer_km, range_km, power_kw,
                consumption_kwh_per_100km, power_mode, fault_flags
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                state["timestamp"],
                state["soc_pct"],
                state["pack_voltage"],
                state["pack_current"],
                state["motor_temp_c"],
                state["speed_kph"],
                state["odometer_km"],
                state["range_km"],
                state["power_kw"],
                state["consumption_kwh_per_100km"],
                state["power_mode"],
                json.dumps(state.get("fault_flags", [])),
            ),
        )
        conn.commit()


def get_latest(db_path: Path = DB_PATH) -> dict | None:
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM telemetry ORDER BY ts DESC LIMIT 1"
        ).fetchone()
        return _row_to_dict(row) if row else None


def get_history(since_ts: float, db_path: Path = DB_PATH) -> list[dict]:
    """Return all rows with ts >= since_ts, oldest first."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM telemetry WHERE ts >= ? ORDER BY ts ASC", (since_ts,)
        ).fetchall()
        return [_row_to_dict(r) for r in rows]


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["fault_flags"] = json.loads(d["fault_flags"])
    return d


if __name__ == "__main__":
    init_db()
    print(f"Initialized database at {DB_PATH}")
