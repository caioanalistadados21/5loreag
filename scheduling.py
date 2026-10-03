from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Iterable

from config import (
    DAY_END,
    DAY_START,
    LAST_START,
    SLOT_DURATION_MINUTES,
    TIME_STEP_MINUTES,
    TIMEZONE,
)


def slot_from_start(selected_date: date, start_time: time) -> tuple[datetime, datetime]:
    """Build one 90-minute appointment from the selected start time."""
    start = datetime.combine(selected_date, start_time, tzinfo=TIMEZONE)
    end = start + timedelta(minutes=SLOT_DURATION_MINUTES)
    return start, end


def start_is_allowed(start_time: time) -> bool:
    """A start is valid when it is inside the list and its end is at most 20:30."""
    if not (DAY_START <= start_time <= LAST_START):
        return False
    dummy_day = date(2000, 1, 1)
    _, end = slot_from_start(dummy_day, start_time)
    closing = datetime.combine(dummy_day, DAY_END, tzinfo=TIMEZONE)
    return end <= closing


def generate_start_times() -> list[time]:
    """Generate selectable starts every 30 minutes from 07:00 through 19:00."""
    dummy_day = date(2000, 1, 1)
    current = datetime.combine(dummy_day, DAY_START)
    last = datetime.combine(dummy_day, LAST_START)
    values: list[time] = []
    while current <= last:
        values.append(current.time())
        current += timedelta(minutes=TIME_STEP_MINUTES)
    return values


def generate_timeline_marks() -> list[time]:
    """Generate visible half-hour marks from 07:00 through 20:30."""
    dummy_day = date(2000, 1, 1)
    current = datetime.combine(dummy_day, DAY_START)
    closing = datetime.combine(dummy_day, DAY_END)
    values: list[time] = []
    while current <= closing:
        values.append(current.time())
        current += timedelta(minutes=TIME_STEP_MINUTES)
    return values


def overlaps(start: datetime, end: datetime, busy_start: datetime, busy_end: datetime) -> bool:
    return start < busy_end and end > busy_start


def find_overlap(
    start: datetime,
    end: datetime,
    busy_items: Iterable[dict],
) -> dict | None:
    for item in busy_items:
        if overlaps(start, end, item["start"], item["end"]):
            return item
    return None


def list_available_start_times(selected_date: date, busy_items: Iterable[dict]) -> list[time]:
    """Return allowed start times.

    Besides normal overlap validation, the label at the exact end of an existing
    appointment stays blocked as well, matching the visual timeline rule.
    Example: 08:00–09:30 also blocks the 09:30 card; the next start becomes 10:00.
    """
    values: list[time] = []
    busy_list = list(busy_items)
    blocked_exact_starts = {item["end"] for item in busy_list}
    for start_time in generate_start_times():
        start, end = slot_from_start(selected_date, start_time)
        if start in blocked_exact_starts:
            continue
        if find_overlap(start, end, busy_list) is None:
            values.append(start_time)
    return values
