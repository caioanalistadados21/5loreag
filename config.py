from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from zoneinfo import ZoneInfo

APP_NAME = "Agenda Mobile"
TIMEZONE_NAME = "America/Sao_Paulo"
TIMEZONE = ZoneInfo(TIMEZONE_NAME)

# Cada atendimento dura 1h30.
SLOT_DURATION_MINUTES = 90

# A lista de horarios de inicio vai das 07:00 ate 19:00.
# O ultimo atendimento termina as 20:30.
DAY_START = time(7, 0)
DAY_END = time(20, 30)
LAST_START = time(19, 0)
TIME_STEP_MINUTES = 30


@dataclass(frozen=True)
class AppColors:
    background: str = "#F6F8FB"
    card: str = "#FFFFFF"
    text: str = "#172033"
    muted: str = "#667085"
    primary: str = "#3157D5"
    primary_dark: str = "#2443AA"
    available: str = "#16A34A"
    available_bg: str = "#ECFDF3"
    busy: str = "#DC2626"
    busy_bg: str = "#FEF2F2"
    border: str = "#E4E7EC"


COLORS = AppColors()
