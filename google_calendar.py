from __future__ import annotations

import json
import os
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from config import TIMEZONE, TIMEZONE_NAME

SCOPES = ["https://www.googleapis.com/auth/calendar"]
ROOT = Path(__file__).resolve().parent


class GoogleCalendarConfigError(RuntimeError):
    """Raised when Google Calendar credentials/configuration are incomplete."""


def _read_toml_sections(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read Google sections from a TOML file without depending on Streamlit."""
    if not path.exists() or not path.is_file():
        return {}, {}

    try:
        import tomllib

        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except Exception as exc:
        raise GoogleCalendarConfigError(
            f"Arquivo TOML inválido em {path}: {exc}"
        ) from exc

    cal = data.get("google_calendar", {})
    svc = data.get("google_service_account", {})
    return (
        dict(cal) if isinstance(cal, dict) else {},
        dict(svc) if isinstance(svc, dict) else {},
    )


def _load_streamlit_secrets() -> tuple[dict[str, Any], dict[str, Any]]:
    """Load secrets from Streamlit, .streamlit/secrets.toml or root secrets.toml."""
    cal: dict[str, Any] = {}
    svc: dict[str, Any] = {}

    # Standard Streamlit mechanism.
    try:
        import streamlit as st

        cal = dict(st.secrets.get("google_calendar", {}))
        svc = dict(st.secrets.get("google_service_account", {}))
    except Exception:
        pass

    # Explicit fallbacks make local execution more forgiving, including the
    # common case where the user leaves secrets.toml in the project root.
    for candidate in (ROOT / ".streamlit" / "secrets.toml", ROOT / "secrets.toml"):
        file_cal, file_svc = _read_toml_sections(candidate)
        if not cal and file_cal:
            cal = file_cal
        if not svc and file_svc:
            svc = file_svc
        if cal and svc:
            break

    return cal, svc


def _normalize_service_account_info(info: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(info)
    private_key = normalized.get("private_key")
    if isinstance(private_key, str) and "\\n" in private_key:
        normalized["private_key"] = private_key.replace("\\n", "\n")
    return normalized


def _load_service_account_from_env() -> dict[str, Any] | None:
    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        return None

    try:
        info = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GoogleCalendarConfigError(
            "GOOGLE_SERVICE_ACCOUNT_JSON não contém um JSON válido. "
            "Cole o conteúdo completo do arquivo JSON da Service Account."
        ) from exc

    if not isinstance(info, dict):
        raise GoogleCalendarConfigError(
            "GOOGLE_SERVICE_ACCOUNT_JSON precisa conter um objeto JSON."
        )
    return _normalize_service_account_info(info)


def _load_service_account_from_individual_env() -> dict[str, Any] | None:
    """Optional fallback for hosts where a large JSON env var is inconvenient."""
    client_email = os.getenv("GOOGLE_CLIENT_EMAIL", "").strip()
    private_key = os.getenv("GOOGLE_PRIVATE_KEY", "").strip()
    project_id = os.getenv("GOOGLE_PROJECT_ID", "").strip()

    if not any((client_email, private_key, project_id)):
        return None
    if not all((client_email, private_key, project_id)):
        raise GoogleCalendarConfigError(
            "Para usar credenciais separadas por variável de ambiente, defina "
            "GOOGLE_PROJECT_ID, GOOGLE_CLIENT_EMAIL e GOOGLE_PRIVATE_KEY."
        )

    if "\\n" in private_key:
        private_key = private_key.replace("\\n", "\n")

    return {
        "type": "service_account",
        "project_id": project_id,
        "private_key_id": os.getenv("GOOGLE_PRIVATE_KEY_ID", ""),
        "private_key": private_key,
        "client_email": client_email,
        "client_id": os.getenv("GOOGLE_CLIENT_ID", ""),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": os.getenv("GOOGLE_CLIENT_X509_CERT_URL", ""),
        "universe_domain": "googleapis.com",
    }


def get_google_config() -> dict[str, Any] | None:
    cal_secrets, service_secrets = _load_streamlit_secrets()
    calendar_id = (
        str(cal_secrets.get("calendar_id", "")).strip()
        or os.getenv("GOOGLE_CALENDAR_ID", "").strip()
    )

    if not calendar_id:
        return None

    if service_secrets:
        return {
            "calendar_id": calendar_id,
            "service_account_info": _normalize_service_account_info(service_secrets),
            "auth_source": "streamlit_secrets",
        }

    env_info = _load_service_account_from_env()
    if env_info:
        return {
            "calendar_id": calendar_id,
            "service_account_info": env_info,
            "auth_source": "environment_json",
        }

    individual_env_info = _load_service_account_from_individual_env()
    if individual_env_info:
        return {
            "calendar_id": calendar_id,
            "service_account_info": individual_env_info,
            "auth_source": "individual_environment_variables",
        }

    file_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
    candidates: list[Path] = []
    if file_path:
        candidates.append(Path(file_path))
    candidates.append(ROOT / "service_account.json")

    for candidate in candidates:
        if candidate.exists():
            return {
                "calendar_id": calendar_id,
                "service_account_file": str(candidate),
                "auth_source": "service_account_file",
            }
    return None


def get_google_diagnostics() -> list[str]:
    """Return human-readable hints about missing configuration without exposing secrets."""
    problems: list[str] = []
    try:
        cal_secrets, service_secrets = _load_streamlit_secrets()
    except GoogleCalendarConfigError as exc:
        return [str(exc)]
    calendar_id = (
        str(cal_secrets.get("calendar_id", "")).strip()
        or os.getenv("GOOGLE_CALENDAR_ID", "").strip()
    )
    if not calendar_id:
        problems.append(
            "Falta o calendar_id. Defina [google_calendar].calendar_id em .streamlit/secrets.toml "
            "ou secrets.toml na raiz, ou use GOOGLE_CALENDAR_ID."
        )

    has_credentials = bool(service_secrets)
    if not has_credentials:
        try:
            has_credentials = _load_service_account_from_env() is not None
            has_credentials = has_credentials or _load_service_account_from_individual_env() is not None
        except GoogleCalendarConfigError as exc:
            problems.append(str(exc))
            has_credentials = True

    if not has_credentials:
        file_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
        candidates = [Path(file_path)] if file_path else []
        candidates.append(ROOT / "service_account.json")
        has_credentials = any(path.exists() for path in candidates)

    if not has_credentials:
        problems.append(
            "Faltam as credenciais da Service Account. Configure GOOGLE_SERVICE_ACCOUNT_JSON, "
            "as variáveis GOOGLE_PROJECT_ID/GOOGLE_CLIENT_EMAIL/GOOGLE_PRIVATE_KEY, "
            "ou use .streamlit/secrets.toml, secrets.toml na raiz ou service_account.json."
        )
    return problems


def is_google_configured() -> bool:
    try:
        return get_google_config() is not None
    except GoogleCalendarConfigError:
        return False


class GoogleCalendarService:
    def __init__(self) -> None:
        config = get_google_config()
        if not config:
            detail = " ".join(get_google_diagnostics()) or "Google Calendar não está configurado."
            raise GoogleCalendarConfigError(detail)

        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        try:
            if "service_account_info" in config:
                credentials = service_account.Credentials.from_service_account_info(
                    config["service_account_info"], scopes=SCOPES
                )
            else:
                credentials = service_account.Credentials.from_service_account_file(
                    config["service_account_file"], scopes=SCOPES
                )
        except Exception as exc:
            raise GoogleCalendarConfigError(
                f"Não foi possível carregar a credencial da Service Account: {exc}"
            ) from exc

        self.calendar_id = config["calendar_id"]
        self.auth_source = config.get("auth_source", "unknown")
        self.service_account_email = getattr(credentials, "service_account_email", "")
        self.service = build("calendar", "v3", credentials=credentials, cache_discovery=False)

    @staticmethod
    def _extract_google_detail(exc: Exception) -> str:
        detail = str(exc)
        content = getattr(exc, "content", None)
        if isinstance(content, bytes):
            try:
                payload = json.loads(content.decode("utf-8"))
                errors = payload.get("error", {}).get("errors", [])
                message = payload.get("error", {}).get("message")
                reason = errors[0].get("reason") if errors else None
                parts = [x for x in (reason, message) if x]
                if parts:
                    return " - ".join(parts)
            except Exception:
                pass
        return detail

    @classmethod
    def _format_google_error(cls, exc: Exception) -> str:
        status = getattr(getattr(exc, "resp", None), "status", None)
        detail = cls._extract_google_detail(exc)
        if status == 403:
            return (
                "Google respondeu 403 (sem permissão de gravação). Compartilhe o calendário "
                "com o e-mail da Service Account e use a permissão 'Fazer alterações nos eventos'. "
                f"Detalhe: {detail}"
            )
        if status == 404:
            return (
                "Google respondeu 404 (calendário não encontrado para esta credencial). "
                "Confira GOOGLE_CALENDAR_ID e confirme que o calendário foi compartilhado "
                f"com a Service Account. Detalhe: {detail}"
            )
        if status == 401:
            return (
                "Google respondeu 401 (credencial inválida). Gere/baixe uma chave válida da "
                f"Service Account e atualize a configuração. Detalhe: {detail}"
            )
        if status == 400:
            return f"Google respondeu 400 (requisição inválida). Detalhe: {detail}"
        return detail

    def _execute(self, request):
        try:
            return request.execute(num_retries=5)
        except Exception as exc:
            raise RuntimeError(self._format_google_error(exc)) from exc

    def test_connection(self) -> dict[str, str]:
        calendar = self._execute(
            self.service.calendars().get(calendarId=self.calendar_id)
        )
        self._execute(
            self.service.events().list(
                calendarId=self.calendar_id,
                maxResults=1,
                singleEvents=True,
            )
        )
        return {
            "calendar_id": self.calendar_id,
            "calendar_summary": calendar.get("summary", ""),
            "service_account_email": self.service_account_email,
            "auth_source": self.auth_source,
        }

    def test_write_access(self) -> dict[str, str]:
        """Create and immediately delete a temporary event to prove write permission."""
        now = datetime.now(TIMEZONE)
        start = now + timedelta(minutes=5)
        end = start + timedelta(minutes=5)
        body = {
            "summary": "[TESTE] Agenda Mobile - integração Google",
            "description": "Evento temporário criado para validar permissão de gravação. Será removido automaticamente.",
            "start": {"dateTime": start.isoformat(), "timeZone": TIMEZONE_NAME},
            "end": {"dateTime": end.isoformat(), "timeZone": TIMEZONE_NAME},
            "visibility": "private",
            "transparency": "transparent",
        }
        event = self._execute(
            self.service.events().insert(calendarId=self.calendar_id, body=body)
        )
        event_id = event.get("id", "")
        try:
            if event_id:
                self._execute(
                    self.service.events().delete(
                        calendarId=self.calendar_id,
                        eventId=event_id,
                    )
                )
        except Exception as exc:
            raise RuntimeError(
                "A gravação funcionou, mas o evento temporário não pôde ser apagado. "
                f"ID do evento: {event_id}. Erro: {exc}"
            ) from exc

        return {
            "calendar_id": self.calendar_id,
            "event_id": event_id,
            "service_account_email": self.service_account_email,
        }

    def list_events(self, start: datetime, end: datetime) -> list[dict]:
        response = (
            self.service.events()
            .list(
                calendarId=self.calendar_id,
                timeMin=start.isoformat(),
                timeMax=end.isoformat(),
                singleEvents=True,
                orderBy="startTime",
                timeZone=TIMEZONE_NAME,
            ).execute(num_retries=5)
        )

        parsed = []

        for event in response.get("items", []):
            start_data = event.get("start", {})
            end_data = event.get("end", {})

            if "dateTime" in start_data:
                ev_start = datetime.fromisoformat(
                    start_data["dateTime"].replace("Z", "+00:00")
                ).astimezone(TIMEZONE)

                ev_end = datetime.fromisoformat(
                    end_data["dateTime"].replace("Z", "+00:00")
                ).astimezone(TIMEZONE)

            else:
                start_date = date.fromisoformat(
                    start_data["date"]
                )

                end_date = date.fromisoformat(
                    end_data["date"]
                )

                ev_start = datetime.combine(
                    start_date,
                    time.min,
                    tzinfo=TIMEZONE,
                )

                ev_end = datetime.combine(
                    end_date,
                    time.min,
                    tzinfo=TIMEZONE,
                )

            parsed.append(
                {
                    "id": event.get("id"),
                    "title": event.get("summary") or "Ocupado",
                    "start": ev_start,
                    "end": ev_end,
                    "source": "google",
                    "html_link": event.get("htmlLink"),
                }
            )

        return parsed

    def create_event(
        self,
        start: datetime,
        end: datetime,
        client_name: str,
        phone: str = "",
        notes: str = "",
    ) -> dict:
        description_lines = ["Agendamento criado pelo Agenda Mobile."]
        if phone:
            description_lines.append(f"Telefone: {phone}")
        if notes:
            description_lines.append(f"Observações: {notes}")

        body = {
            "summary": f"{client_name}",
            "description": "\n".join(description_lines),
            "start": {"dateTime": start.isoformat(), "timeZone": TIMEZONE_NAME},
            "end": {"dateTime": end.isoformat(), "timeZone": TIMEZONE_NAME},
        }
        return (
            self.service.events().insert(calendarId=self.calendar_id,body=body,).execute(num_retries=5)
        )

    def delete_event(self, event_id: str) -> None:
        try:
            self.service.events().delete(
                calendarId=self.calendar_id,
                eventId=event_id,
            ).execute(num_retries=5)
        except Exception as exc:
            status = getattr(getattr(exc, "resp", None), "status", None)
            # Delete is idempotent for the app: if the user already removed the event
            # manually in Google Calendar, the local record can still be cancelled.
            if status == 404:
                return
            raise RuntimeError(self._format_google_error(exc)) from exc
