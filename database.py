from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "data" / "agenda.db"


@contextmanager
def _connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                client_name TEXT NOT NULL,
                phone TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                source TEXT NOT NULL DEFAULT 'local',
                google_event_id TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_appointments_start ON appointments(start_time)"
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_google_event_id ON appointments(google_event_id) WHERE google_event_id IS NOT NULL"
        )


def _row_to_dict(row: sqlite3.Row) -> dict:
    item = dict(row)
    item["start"] = datetime.fromisoformat(item.pop("start_time"))
    item["end"] = datetime.fromisoformat(item.pop("end_time"))
    return item


def list_between(start: datetime, end: datetime) -> list[dict]:
    with _connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM appointments
            WHERE start_time < ? AND end_time > ?
            ORDER BY start_time
            """,
            (end.isoformat(), start.isoformat()),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def get_by_id(appointment_id: int) -> dict | None:
    with _connection() as conn:
        row = conn.execute(
            "SELECT * FROM appointments WHERE id = ?", (appointment_id,)
        ).fetchone()
    return _row_to_dict(row) if row else None


def get_by_google_event_id(event_id: str) -> dict | None:
    with _connection() as conn:
        row = conn.execute(
            "SELECT * FROM appointments WHERE google_event_id = ?", (event_id,)
        ).fetchone()
    return _row_to_dict(row) if row else None


def has_conflict(start: datetime, end: datetime) -> bool:
    with _connection() as conn:
        row = conn.execute(
            """
            SELECT 1 FROM appointments
            WHERE start_time < ? AND end_time > ?
            LIMIT 1
            """,
            (end.isoformat(), start.isoformat()),
        ).fetchone()
    return row is not None


def create_appointment(
    start: datetime,
    end: datetime,
    client_name: str,
    phone: str = "",
    notes: str = "",
    source: str = "local",
    google_event_id: str | None = None,
) -> int:
    if has_conflict(start, end):
        raise ValueError("Este horário acabou de ser ocupado. Atualize a agenda e escolha outro horário.")

    with _connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO appointments
                (start_time, end_time, client_name, phone, notes, source, google_event_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                start.isoformat(),
                end.isoformat(),
                client_name.strip(),
                phone.strip(),
                notes.strip(),
                source,
                google_event_id,
            ),
        )
        return int(cursor.lastrowid)


def delete_appointment(appointment_id: int) -> None:
    with _connection() as conn:
        conn.execute("DELETE FROM appointments WHERE id = ?", (appointment_id,))
