from __future__ import annotations

import hashlib
import hmac
import time as time_module
from pathlib import Path
from datetime import date, datetime, time, timedelta
from html import escape
from textwrap import dedent

import streamlit as st
import streamlit.components.v1 as components
import extra_streamlit_components as stx

import database as db

from config import (
        APP_NAME,
        COLORS,
        DAY_END,
        DAY_START,
        TIMEZONE,
    )

from google_calendar import (
        GoogleCalendarService,
        get_google_diagnostics,
        is_google_configured,
    )

from scheduling import (
    find_overlap,
    generate_timeline_marks,
    list_available_start_times,
    slot_from_start,
)
st.set_page_config(
    page_title=APP_NAME,
    page_icon="📅",
    layout="centered",
    initial_sidebar_state="collapsed",
)

cookie_manager = stx.CookieManager(
    key="agenda_cookie_manager"
)

COOKIE_NAME = "agenda_login"
COOKIE_DAYS = 120
COOKIE_MAX_AGE = COOKIE_DAYS * 24 * 60 * 60


def _get_cookie_secret() -> str:
    try:
        secret = str(st.secrets["auth"]["cookie_secret"]).strip()
    except Exception as exc:
        raise RuntimeError(
            "Configure auth.cookie_secret nos Secrets do Streamlit Cloud."
        ) from exc

    if not secret:
        raise RuntimeError(
            "auth.cookie_secret nao pode ficar vazio nos Secrets do Streamlit Cloud."
        )

    return secret


def create_login_token(username: str, expires: int | None = None) -> str:
    if expires is None:
        expires = int(time_module.time() + COOKIE_MAX_AGE)
    payload = f"{username}|{expires}"

    signature = hmac.new(
        _get_cookie_secret().encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()

    return f"{username}|{expires}|{signature}"


def validate_login_token(token: str):
    try:
        username, expires, signature = token.split("|", 2)
        expires = int(expires)

        if time_module.time() > expires:
            return None

        payload = f"{username}|{expires}"
        expected_signature = hmac.new(
            _get_cookie_secret().encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(signature, expected_signature):
            return None

        users = _load_auth_users()
        if username not in users:
            return None

        return username, expires120

    except Exception:
        return None


def _normalize_auth_users(raw_users) -> dict[str, dict]:
    users: dict[str, dict] = {}
    try:
        items = raw_users.items()
    except AttributeError:
        return users

    for username, raw_data in items:
        try:
            user_data = dict(raw_data)
        except Exception:
            continue
        key = str(username).strip().lower()
        if key:
            users[key] = user_data
    return users


def _load_auth_users() -> dict[str, dict]:
    # 1) Forma padrao do Streamlit / Streamlit Cloud.
    try:
        auth = st.secrets.get("auth", {})
        users = _normalize_auth_users(auth.get("users", {}))
        if users:
            return users
    except Exception:
        pass

    # 2) Compatibilidade com execucao local.
    try:
        import tomllib
    except ImportError:
        return {}

    root = Path(__file__).resolve().parent
    for candidate in (root / ".streamlit" / "secrets.toml", root / "secrets.toml"):
        if not candidate.exists():
            continue
        try:
            with candidate.open("rb") as handle:
                data = tomllib.load(handle)
            auth = data.get("auth", {})
            users = _normalize_auth_users(auth.get("users", {}))
            if users:
                return users
        except Exception:
            continue

    return {}


def _read_persistent_login_cookie() -> str | None:
    # st.context.cookies vem junto com a requisicao inicial da sessao e nao
    # depende do retorno assincrono do componente CookieManager.
    try:
        cookies = st.context.cookies
        if COOKIE_NAME in cookies:
            value = cookies[COOKIE_NAME]
            if value:
                return str(value)
    except Exception:
        pass

    # Fallback para versoes/ambientes em que st.context nao esteja disponivel.
    try:
        value = cookie_manager.get(COOKIE_NAME)
        return str(value) if value else None
    except Exception:
        return None


def _set_logged_user(
    username: str,
    user_data: dict,
    expires_at: int | None = None,
) -> None:
    st.session_state.authenticated = True
    st.session_state.logged_user = username
    st.session_state.logged_name = str(user_data.get("name", username))
    st.session_state.auth_expires_at = expires_at


def login_required() -> None:
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        expires_at = st.session_state.get("auth_expires_at")

        # Mesmo com a aba aberta por muito tempo, exige nova senha ao completar
        # 120 dias quando existe uma autenticacao persistente com validade.
        if expires_at is None or time_module.time() <= expires_at:
            return

        st.session_state.authenticated = False
        st.session_state.logged_user = None
        st.session_state.logged_name = None
        st.session_state.auth_expires_at = None

    # Depois de clicar em Sair, nao rele o cookie antigo desta mesma conexao.
    # st.context.cookies representa os cookies recebidos no inicio da sessao.
    skip_cookie = st.session_state.get("logout_in_progress", False)

    if not skip_cookie:
        saved_token = _read_persistent_login_cookie()

        if saved_token:
            validated = validate_login_token(saved_token)

            if validated:
                username, expires_at = validated
                users = _load_auth_users()
                user_data = users.get(username)

                if user_data:
                    _set_logged_user(username, user_data, expires_at)
                    return

    login_area = st.empty()

    with login_area.container():
        st.markdown(
            """
            <div style="
                max-width:420px;
                margin:60px auto 25px auto;
                text-align:center;
            ">
                <h2>🔐 Agenda</h2>
                <p style="color:#667085;">
                    Informe seu usuario e senha
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.form("login_form"):
            username = st.text_input(
                "Usuario",
                placeholder="Digite seu usuario",
            )

            password = st.text_input(
                "Senha",
                type="password",
                placeholder="Digite sua senha",
            )

            remember = st.checkbox(
                "Lembrar-me",
                value=True,
            )

            entrar = st.form_submit_button(
                "Entrar",
                type="primary",
                use_container_width=True,
            )

    if entrar:
        username = username.strip().lower()

        try:
            users = _load_auth_users()

            if username not in users:
                st.error("Usuario ou senha invalidos.")
                st.stop()

            user_data = users[username]
            senha_correta = str(user_data["password"])

            if not hmac.compare_digest(password, senha_correta):
                st.error("Usuario ou senha invalidos.")
                st.stop()

            login_expires_at = int(time_module.time() + COOKIE_MAX_AGE)
            _set_logged_user(username, user_data, login_expires_at)
            st.session_state.logout_in_progress = False

            if remember:
                token = create_login_token(username, login_expires_at)

                # Nao chame st.rerun() imediatamente depois deste set.
                # O componente precisa chegar ao navegador para gravar o cookie.
                cookie_manager.set(
                    COOKIE_NAME,
                    token,
                    key=f"set_{COOKIE_NAME}",
                    path="/",
                    expires_at=datetime.now() + timedelta(days=COOKIE_DAYS),
                    max_age=COOKIE_MAX_AGE,
                    same_site="lax",
                )
            else:
                # Se havia um cookie antigo e o usuario desmarcou Lembrar-me, remove-o.
                try:
                    cookie_manager.delete(
                        COOKIE_NAME,
                        key=f"delete_{COOKIE_NAME}_login",
                    )
                except Exception:
                    pass

            # Remove a tela de login desta execucao e deixa a pagina continuar.
            # O CookieManager fara o rerun necessario quando concluir no navegador.
            login_area.empty()
            return

        except Exception as exc:
            st.error(f"Erro no login: {exc}")

    st.stop()


login_required()

db.init_db()

if "selected_date" not in st.session_state:
    st.session_state.selected_date = date.today()
if "booking_slot" not in st.session_state:
    st.session_state.booking_slot = None
if "direct_date" not in st.session_state:
    st.session_state.direct_date = st.session_state.selected_date
if "scroll_to_slots" not in st.session_state:
    st.session_state.scroll_to_slots = False
if "flash" not in st.session_state:
    st.session_state.flash = None
if "last_google_event_link" not in st.session_state:
    st.session_state.last_google_event_link = None


def inject_css() -> None:
    st.markdown(
        f"""
        <style>
        :root {{
            --bg: {COLORS.background};
            --card: {COLORS.card};
            --text: {COLORS.text};
            --muted: {COLORS.muted};
            --primary: {COLORS.primary};
            --available: {COLORS.available};
            --available-bg: {COLORS.available_bg};
            --busy: {COLORS.busy};
            --busy-bg: {COLORS.busy_bg};
            --border: {COLORS.border};
            --timeline-left: #8C73F6;
            --timeline-left-dark: #7A60F0;
            --timeline-right: #EDE5FF;
            --timeline-row: #F4EEFF;
        }}
        .stApp {{ background: var(--bg); }}
        .block-container {{
            max-width: 760px;
            padding-top: 1rem;
            padding-bottom: 3rem;
        }}
        #MainMenu, footer {{ visibility: hidden; }}
        header[data-testid="stHeader"] {{ background: transparent; }}
        .hero {{
            background: linear-gradient(135deg, #203A8F 0%, #3157D5 58%, #5878E8 100%);
            color: white;
            border-radius: 24px;
            padding: 22px 20px;
            box-shadow: 0 14px 32px rgba(49, 87, 213, .18);
            margin: .25rem 0 1rem 0;
        }}
        .hero .eyebrow {{ font-size: .78rem; opacity: .78; letter-spacing: .08em; text-transform: uppercase; }}
        .hero h1 {{ margin: 5px 0 4px 0; font-size: 1.85rem; line-height: 1.1; }}
        .hero p {{ margin: 0; opacity: .86; font-size: .94rem; }}
        .section-title {{
            font-size: 1.05rem;
            font-weight: 760;
            color: var(--text);
            margin: 1rem 0 .5rem 0;
        }}
        .legend {{ display:flex; gap:14px; align-items:center; flex-wrap:wrap; margin: .25rem 0 .9rem 0; }}
        .legend-item {{ color: var(--muted); font-size: .83rem; }}
        .dot {{ display:inline-block; width:9px; height:9px; border-radius:999px; margin-right:6px; }}

        .timeline-wrap {{ margin-top: .5rem; }}
        .time-gap {{
            position: relative;
            display:flex;
            align-items:center;
            justify-content:center;
            color:#667085;
            font-weight:800;
            font-size:1.05rem;
            min-height:46px;
            margin: 0 0 6px 0;
            border-radius: 12px;
            background: #FFFFFF;
            border: 1px solid #E4E7EC;
        }}
        .time-gap .gap-label {{ position:relative; z-index:2; }}
        .time-gap::before, .time-gap::after {{
            content:"";
            position:absolute;
            top:50%;
            width:27%;
            height:1px;
            background: #D0D5DD;
        }}
        .time-gap::before {{ left: 14px; }}
        .time-gap::after {{ right: 14px; }}
        .time-gap.bookable {{ background: #F0FDF4; color:#166534; border-color:#BBF7D0; }}
        .time-gap.bookable::before, .time-gap.bookable::after {{ background: #86EFAC; }}
        .time-gap.blocked-end {{
            color:#FFFFFF;
            border-color: rgba(126, 94, 249, .16);
            background: linear-gradient(90deg, rgba(124, 91, 238, .86), rgba(156, 129, 248, .80));
        }}
        .time-gap.blocked-end::before, .time-gap.blocked-end::after {{ background: rgba(255,255,255,.45); }}

        .event-card {{
            display:grid;
            grid-template-columns: 78px minmax(0, 1fr);
            border-radius: 16px;
            overflow:hidden;
            margin: 0 0 8px 0;
            border: 1px solid rgba(126, 94, 249, .16);
            box-shadow: 0 5px 16px rgba(88, 76, 160, .08);
        }}
        .event-left {{
            background: linear-gradient(180deg, var(--timeline-left) 0%, var(--timeline-left-dark) 100%);
            color: #FFFFFF;
            padding: 12px 8px;
            display:flex;
            flex-direction:column;
            justify-content:flex-start;
            align-items:center;
            text-align:center;
            min-height: 176px;
        }}
        .event-start {{ font-size: .98rem; font-weight: 900; line-height: 1.15; margin-top: 4px; }}
        .event-end {{ font-size: .72rem; opacity: .95; margin-top: 2px; }}
        .event-right {{
            background: linear-gradient(180deg, #F0E9FF 0%, #E8DEFF 100%);
            color: var(--text);
            min-height: 176px;
        }}
        .event-main {{ padding: 14px 14px 10px 14px; }}
        .event-header {{ display:flex; justify-content:space-between; align-items:flex-start; gap:10px; }}
        .event-client {{ font-size: 1.02rem; font-weight:900; line-height: 1.18; }}
        .event-meta {{ margin-top: 8px; color: #564A83; font-size: .8rem; }}
        .event-observation {{ margin-top: 10px; }}
        .event-observation-label {{ color:#6F57DB; font-size:.74rem; font-weight:900; text-transform:uppercase; letter-spacing:.04em; }}
        .event-observation-text {{ margin-top:3px; color:#43386B; font-size:.85rem; line-height:1.35; overflow-wrap:anywhere; }}
        .event-menu {{
            flex: 0 0 auto;
            width: 28px;
            height: 28px;
            border-radius: 8px;
            background: rgba(124, 99, 236, .12);
            color: #6F57DB;
            display:flex;
            align-items:center;
            justify-content:center;
            font-size: 16px;
            font-weight: 700;
        }}
        .event-mid-row {{
            height: 38px;
            display:flex;
            align-items:center;
            justify-content:center;
            color: #FFFFFF;
            font-weight: 800;
            font-size: .98rem;
            border-top: 1px solid rgba(255,255,255,.35);
            background: linear-gradient(90deg, rgba(124, 91, 238, .86), rgba(156, 129, 248, .80));
        }}
        .event-actions-caption {{ color: var(--muted); font-size: .78rem; margin: 0 0 .45rem .1rem; }}

        .booking-card {{
            background: #FFFFFF;
            border: 1px solid var(--border);
            border-radius: 18px;
            padding: 14px;
            box-shadow: 0 4px 14px rgba(16, 24, 40, .035);
        }}
        div[data-testid="stButton"] > button {{
            width: 100%;
            border-radius: 12px;
            min-height: 42px;
            font-weight: 720;
        }}
        div[data-testid="stForm"] {{
            background: #fff;
            border: 1px solid var(--border);
            border-radius: 18px;
            padding: 12px;
        }}
        [data-testid="stSidebar"] {{ background: #F8FAFC; }}
        @media (max-width: 640px) {{
            .block-container {{ padding-left: .85rem; padding-right: .85rem; padding-top: .45rem; }}
            .hero {{ border-radius: 20px; padding: 19px 16px; }}
            .hero h1 {{ font-size: 1.55rem; }}
            .event-card {{ grid-template-columns: 72px minmax(0, 1fr); }}
            .event-left {{ min-height: 168px; padding: 10px 6px; }}
            .event-right {{ min-height: 168px; }}
            .event-main {{ padding: 12px 12px 9px 12px; }}
            .event-client {{ font-size: .98rem; }}
            .event-mid-row {{ height: 36px; font-size: .94rem; }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=TIMEZONE)
    return start, start + timedelta(days=1)

def week_bounds(day: date) -> tuple[datetime, datetime]:
    monday = day - timedelta(days=day.weekday())

    start = datetime.combine(
        monday,
        time.min,
        tzinfo=TIMEZONE,
    )

    end = start + timedelta(days=7)

    return start, end


def month_bounds(day: date) -> tuple[datetime, datetime]:
    first_day = day.replace(day=1)

    if first_day.month == 12:
        next_month = date(
            first_day.year + 1,
            1,
            1,
        )
    else:
        next_month = date(
            first_day.year,
            first_day.month + 1,
            1,
        )

    start = datetime.combine(
        first_day,
        time.min,
        tzinfo=TIMEZONE,
    )

    end = datetime.combine(
        next_month,
        time.min,
        tzinfo=TIMEZONE,
    )

    return start, end

def get_google_counters(day: date) -> tuple[int, int]:
    if not is_google_configured():
        return 0, 0

    try:
        # ----------------------------
        # MÊS
        # ----------------------------

        month_start, month_end = month_bounds(day)

        events = google_service().list_events(
            month_start,
            month_end,
        )

        monthly_count = len(events)

        # ----------------------------
        # SEMANA
        # ----------------------------

        week_start, week_end = week_bounds(day)

        weekly_count = sum(
            1
            for event in events
            if week_start <= event["start"] < week_end
        )

        return weekly_count, monthly_count

    except Exception as exc:

       st.warning(
        "Não foi possível atualizar os contadores agora. "
        "Tente novamente em alguns segundos."
       )

       return 0, 0


@st.cache_resource(show_spinner=False)
def google_service() -> GoogleCalendarService:
    return GoogleCalendarService()


def get_google_events(start: datetime, end: datetime) -> list[dict]:
    if not is_google_configured():
        return []
    try:
        return google_service().list_events(start, end)
    except Exception as exc:
        st.warning(f"Não foi possível consultar o Google Calendar agora: {exc}")
        return []


def get_busy_items(day: date, use_google: bool) -> list[dict]:
    start, end = day_bounds(day)
    local_items = db.list_between(start, end)
    for item in local_items:
        item["source"] = item.get("source", "local")
        item["title"] = item.get("client_name", "Atendimento")
        item["is_local_record"] = True

    if not use_google:
        return local_items

    google_items = get_google_events(start, end)
    local_google_ids = {x.get("google_event_id") for x in local_items if x.get("google_event_id")}
    external_google = [x for x in google_items if x.get("id") not in local_google_ids]
    for item in external_google:
        item["is_local_record"] = False
    return local_items + external_google


def format_range(start: datetime, end: datetime) -> str:
    return f"{start:%H:%M} – {end:%H:%M}"


def render_time_gap(label: datetime, is_bookable: bool, is_blocked_end: bool = False) -> None:
    if is_blocked_end:
        css_class = "time-gap blocked-end"
    elif is_bookable:
        css_class = "time-gap bookable"
    else:
        css_class = "time-gap"
    st.html(
        dedent(
            f"""
            <div class="{css_class}">
                <span class="gap-label">{label:%H:%M}</span>
            </div>
            """
        )
    )


def render_event_card(busy: dict) -> None:
    start = busy["start"]
    end = busy["end"]
    client = escape(str(busy.get("client_name") or busy.get("title") or "Cliente"))
    phone = escape(str(busy.get("phone") or "").strip())
    notes = escape(str(busy.get("notes") or "").strip()) or "Sem observação."
    mid_1 = (start + timedelta(minutes=30)).strftime("%H:%M")
    mid_2 = (start + timedelta(minutes=60)).strftime("%H:%M")
    end_label = end.strftime("%H:%M")
    phone_html = f'<div class="event-meta">📞 {phone}</div>' if phone else ""

    st.html(
        dedent(
            f"""
            <div class="event-card">
                <div class="event-left">
                    <div class="event-start">{start:%H:%M}</div>
                    <div class="event-end">até {end:%H:%M}</div>
                </div>
                <div class="event-right">
                    <div class="event-main">
                        <div class="event-header">
                            <div>
                                <div class="event-client">{client}</div>
                                <div class="event-observation">
                                    <div class="event-observation-label">Observação</div>
                                    <div class="event-observation-text">{notes}</div>
                                </div>
                                {phone_html}
                            </div>
                        </div>
                    </div>
                    <div class="event-mid-row">{mid_1}</div>
                    <div class="event-mid-row">{mid_2}</div>
                    <div class="event-mid-row">{end_label}</div>
                </div>
            </div>
            """
        )
    )


def render_busy_actions(busy: dict, key_prefix: str, google_ready: bool) -> None:
    appointment_id = busy.get("id") if busy.get("is_local_record") else None

    if "delete_confirm" not in st.session_state:
        st.session_state.delete_confirm = None

    # ---------------------------------------------------------
    # AGENDAMENTO CRIADO PELO APLICATIVO
    # ---------------------------------------------------------
    if appointment_id and str(appointment_id).isdigit():

        confirm_key = f"local_{appointment_id}"

        with st.expander("Ver detalhes / excluir"):
            st.write(f"**Cliente:** {busy.get('client_name', '-')}")
            st.write(
                f"**Horário:** "
                f"{busy['start']:%H:%M} – {busy['end']:%H:%M}"
            )

            if busy.get("phone"):
                st.write(f"**Telefone:** {busy['phone']}")

            if busy.get("notes"):
                st.write(f"**Observações:** {busy['notes']}")

            # Primeiro clique
            if st.session_state.delete_confirm != confirm_key:

                if st.button(
                    "Excluir horário",
                    key=f"delete_{key_prefix}_{appointment_id}",
                    use_container_width=True,
                ):
                    st.session_state.delete_confirm = confirm_key
                    st.rerun()

            # Confirmação
            else:
                st.warning(
                    "Tem certeza que deseja excluir este horário?"
                )

                col1, col2 = st.columns(2)

                with col1:
                    if st.button(
                        "Sim, excluir",
                        key=f"confirm_delete_{key_prefix}_{appointment_id}",
                        type="primary",
                        use_container_width=True,
                    ):
                        try:

                            # Exclui do Google Calendar
                            if busy.get("google_event_id") and google_ready:
                                google_service().delete_event(
                                    busy["google_event_id"]
                                )

                            # Exclui do banco local
                            db.delete_appointment(
                                int(appointment_id)
                            )

                            st.session_state.delete_confirm = None
                            st.session_state.booking_slot = None

                            st.session_state.flash = (
                                "Horário excluído com sucesso."
                            )

                            st.rerun()

                        except Exception as exc:
                            st.error(
                                f"Não foi possível excluir o horário: {exc}"
                            )

                with col2:
                    if st.button(
                        "Cancelar",
                        key=f"cancel_delete_{key_prefix}_{appointment_id}",
                        use_container_width=True,
                    ):
                        st.session_state.delete_confirm = None
                        st.rerun()

    # ---------------------------------------------------------
    # EVENTO QUE EXISTE SOMENTE NO GOOGLE CALENDAR
    # ---------------------------------------------------------
    elif busy.get("source") == "google":

        google_event_id = busy.get("id")

        confirm_key = f"google_{google_event_id}"

        with st.expander("Ver detalhes / excluir"):

            st.write(
                f"**Evento:** "
                f"{busy.get('title') or 'Compromisso'}"
            )

            st.write(
                f"**Horário:** "
                f"{busy['start']:%H:%M} – {busy['end']:%H:%M}"
            )

            if google_event_id and google_ready:

                # Primeiro clique
                if st.session_state.delete_confirm != confirm_key:

                    if st.button(
                        "Excluir horário",
                        key=f"delete_google_{key_prefix}_{google_event_id}",
                        use_container_width=True,
                    ):
                        st.session_state.delete_confirm = confirm_key
                        st.rerun()

                # Confirmação
                else:

                    st.warning(
                        "Tem certeza que deseja excluir este horário "
                        "do Google Calendar?"
                    )

                    col1, col2 = st.columns(2)

                    with col1:
                        if st.button(
                            "Sim, excluir",
                            key=f"confirm_google_{key_prefix}_{google_event_id}",
                            type="primary",
                            use_container_width=True,
                        ):
                            try:

                                google_service().delete_event(
                                    google_event_id
                                )

                                st.session_state.delete_confirm = None
                                st.session_state.booking_slot = None

                                st.session_state.flash = (
                                    "Horário excluído com sucesso."
                                )

                                st.rerun()

                            except Exception as exc:
                                st.error(
                                    f"Não foi possível excluir o horário: {exc}"
                                )

                    with col2:
                        if st.button(
                            "Cancelar",
                            key=f"cancel_google_{key_prefix}_{google_event_id}",
                            use_container_width=True,
                        ):
                            st.session_state.delete_confirm = None
                            st.rerun()

            else:
                st.warning(
                    "Não foi possível identificar o evento "
                    "no Google Calendar."
                )

def render_booking_form(start: datetime, end: datetime, use_google: bool) -> None:
    st.markdown(f"#### Novo atendimento · {format_range(start, end)}")
    with st.form("booking_form", clear_on_submit=True):
        name = st.text_input("Nome do cliente *", placeholder="Ex.: João da Silva")
        phone = st.text_input("Telefone / WhatsApp", placeholder="(62) 99999-9999")
        notes = st.text_area("Observações", placeholder="Informações importantes do atendimento", height=90)
        submitted = st.form_submit_button("Confirmar agendamento", type="primary", use_container_width=True)

    if submitted:
        if not name.strip():
            st.error("Informe o nome do cliente.")
            return

        fresh_busy = get_busy_items(start.date(), use_google)
        if find_overlap(start, end, fresh_busy):
            st.error("Este horário foi ocupado. Escolha outro horário.")
            return

        google_event_id = None
        try:
            if use_google:
                event = google_service().create_event(start, end, name, phone, notes)
                google_event_id = event.get("id")
                st.session_state.last_google_event_link = event.get("htmlLink")

            try:
                db.create_appointment(
                    start=start,
                    end=end,
                    client_name=name,
                    phone=phone,
                    notes=notes,
                    source="google" if use_google else "local",
                    google_event_id=google_event_id,
                )
            except Exception:
                if use_google and google_event_id:
                    try:
                        google_service().delete_event(google_event_id)
                    except Exception:
                        pass
                raise

            st.session_state.booking_slot = None
            if use_google:
                st.session_state.flash = (
                    f"Agendamento confirmado para {start:%d/%m/%Y às %H:%M} e salvo no Google Calendar."
                )
            else:
                st.session_state.flash = f"Agendamento confirmado para {start:%d/%m/%Y às %H:%M}."
            st.rerun()
        except Exception as exc:
            st.error(f"Não foi possível criar o agendamento: {exc}")


inject_css()

#st.markdown(
#    """
#    <div class="hero">
#      <div class="eyebrow">agenda de atendimentos</div>
#      <h1>Escolha um dia e visualize a grade de horários</h1>
 #     <p>Ao escolher um horário, o sistema reserva 1h30 para frente. O horário final máximo do dia é 20:30.</p>
#    </div>
#    """,
#    unsafe_allow_html=True,
#)

google_ready = is_google_configured()
with st.sidebar:
    logged_name = st.session_state.get("logged_name", "")
    if logged_name:
        st.caption(f"Conectado como: {logged_name}")
    if st.button("🚪 Sair", key="logout_button", use_container_width=True):
        st.session_state.logout_in_progress = True
        st.session_state.authenticated = False
        st.session_state.logged_user = None
        st.session_state.logged_name = None
        st.session_state.auth_expires_at = None

        cookie_manager.delete(
            COOKIE_NAME,
            key=f"delete_{COOKIE_NAME}_logout",
        )

        # Nao use st.rerun() aqui: primeiro deixe o componente apagar o cookie
        # no navegador. A resposta do componente provocara a proxima execucao.
        st.stop()

    st.divider()
    st.markdown("### Configurações")
    if google_ready:
        use_google = st.toggle("Sincronizar com Google Calendar", value=True)
        st.success("Google Calendar configurado")

        if st.button("1. Testar leitura do Google", use_container_width=True):
            try:
                info = google_service().test_connection()
                st.success(
                    f"Leitura OK · Agenda: {info.get('calendar_summary') or info['calendar_id']}"
                )
                if info.get("service_account_email"):
                    st.caption(f"Service Account: {info['service_account_email']}")
            except Exception as exc:
                st.error(f"Falha na leitura do Google Calendar: {exc}")

        if st.button("2. Testar gravação no Google", use_container_width=True):
            try:
                info = google_service().test_write_access()
                st.success("Gravação OK. Evento temporário criado e removido com sucesso.")
                if info.get("service_account_email"):
                    st.caption(f"Service Account: {info['service_account_email']}")
            except Exception as exc:
                st.error(f"Falha na gravação do Google Calendar: {exc}")
    else:
        use_google = False
        st.warning("Google Calendar ainda não está configurado")
        for diagnostic in get_google_diagnostics():
            st.caption(f"• {diagnostic}")
        st.caption("Veja o README e .streamlit/secrets.example.toml.")
    st.caption("Fuso horário: America/Sao_Paulo")

if st.session_state.flash:
    st.success(st.session_state.flash)
    #if st.session_state.last_google_event_link:
    #    st.link_button(
    #        "Abrir evento no Google Calendar",
    #        st.session_state.last_google_event_link,
    #        use_container_width=True,
    #    )
    st.session_state.flash = None
    st.session_state.last_google_event_link = None

st.markdown('<div class="section-title">1. Selecione a data</div>', unsafe_allow_html=True)
with st.expander("Ir diretamente para uma data", expanded=True):
    direct_date = st.date_input(
        "Data",
        key="direct_date",
        format="DD/MM/YYYY",
        label_visibility="collapsed",
    )
    if direct_date != st.session_state.selected_date:
        st.session_state.selected_date = direct_date
        st.session_state.booking_slot = None
        st.session_state.scroll_to_slots = True
        st.rerun()

selected = st.session_state.selected_date
st.markdown('<div id="appointments-list"></div>', unsafe_allow_html=True)

# ---------------------------------------------------------
# CONTADORES GOOGLE CALENDAR
# ---------------------------------------------------------

weekly_count, monthly_count = get_google_counters(selected)

col_week, col_month = st.columns(2)

with st.expander("Total Agendamentos", expanded=False):
    st.metric(
            label="Agendamentos da semana",
            value=weekly_count,
        )
    
    st.metric(
            label="Agendamentos do mês",
            value=monthly_count,
        )

if st.session_state.scroll_to_slots:
    components.html(
        """
        <script>
        const goToAppointments = () => {
            const target = window.parent.document.getElementById('appointments-list');
            if (target) {
                target.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        };
        setTimeout(goToAppointments, 120);
        </script>
        """,
        height=0,
        width=0,
    )
    st.session_state.scroll_to_slots = False

weekday = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"][selected.weekday()]
st.markdown(
    f'<div class="section-title">2. Grade do dia · {weekday}, {selected:%d/%m/%Y}</div>',
    unsafe_allow_html=True,
)
st.markdown(
    f"""
    <div class="legend">
      <span class="legend-item"><span class="dot" style="background:{COLORS.available}"></span>Horário livre para início</span>
      <span class="legend-item"><span class="dot" style="background:{COLORS.busy}"></span>Atendimento já marcado</span>
    </div>
    """,
    unsafe_allow_html=True,
)

busy_items = sorted(get_busy_items(selected, use_google), key=lambda item: item["start"])
available_starts = list_available_start_times(selected, busy_items)
bookable_starts = {datetime.combine(selected, t, tzinfo=TIMEZONE) for t in available_starts}
blocked_end_starts = {item["end"] for item in busy_items}
closing_dt = datetime.combine(selected, DAY_END, tzinfo=TIMEZONE)

st.markdown('<div class="timeline-wrap">', unsafe_allow_html=True)
current = datetime.combine(selected, DAY_START, tzinfo=TIMEZONE)
for index, busy in enumerate(busy_items):
    while current < busy["start"]:
        render_time_gap(current, current in bookable_starts, current in blocked_end_starts)
        current += timedelta(minutes=30)
    render_event_card(busy)
    # The ending time is rendered inside the purple appointment card, directly
    # after the intermediate half-hour marks. Details/cancel comes after it.
    current = max(current, busy["end"] + timedelta(minutes=30))
    render_busy_actions(busy, f"busy_{index}", google_ready)

while current <= closing_dt:
    render_time_gap(current, current in bookable_starts, current in blocked_end_starts)
    current += timedelta(minutes=30)

st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div class="section-title">3. Novo agendamento</div>', unsafe_allow_html=True)
if not available_starts:
    st.info("Não há horários disponíveis neste dia.")
else:
    options = [(t, slot_from_start(selected, t)) for t in available_starts]
    selected_option = st.selectbox(
        "Escolha o horário de início",
        options=options,
        format_func=lambda item: f"{item[1][0]:%H:%M} – {item[1][1]:%H:%M}",
        index=0,
        key="slot_selector",
    )
    start_dt, end_dt = selected_option[1]
    st.caption(
        f"Ao confirmar, o sistema reservará automaticamente o período de **{start_dt:%H:%M} até {end_dt:%H:%M}**."
    )

    if st.button(f"Agendar {start_dt:%H:%M} – {end_dt:%H:%M}", type="primary", use_container_width=True):
        st.session_state.booking_slot = start_dt.isoformat()
        st.rerun()

    if st.session_state.booking_slot == start_dt.isoformat():
        render_booking_form(start_dt, end_dt, use_google)
        if st.button("Fechar formulário", key="close_booking_form", use_container_width=True):
            st.session_state.booking_slot = None
            st.rerun()

st.caption(
    "Agenda Mobile · Início do dia: 07:00 · Cada atendimento ocupa 1h30 para frente · Encerramento máximo: 20:30"
)
