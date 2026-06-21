"""
dashboard.py - Piolet Market Intelligence dashboard.
Usage: streamlit run dashboard.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv


load_dotenv()

APP_TITLE = "Piolet Market Intelligence"
APP_ICON = Path(r"C:\Users\erick\AppData\Local\Temp\codex-clipboard-9d860758-22dc-4695-ac20-54aacb9faa69.png")
TEST_USER = os.getenv("PIOLET_TEST_USER", "piolet")
TEST_PASSWORD = os.getenv("PIOLET_TEST_PASSWORD", "piolet123")
APIFY_MONTHLY_BUDGET = 5.0
DATA_PATH = Path("datos/videos_latest.csv")
THEME_STATE_KEY = "piolet_theme"
DEFAULT_THEME = "light"


def _page_icon() -> str:
    return str(APP_ICON) if APP_ICON.exists() else "🧊"


st.set_page_config(
    page_title=APP_TITLE,
    page_icon=_page_icon(),
    layout="wide",
    initial_sidebar_state="expanded",
)

if THEME_STATE_KEY not in st.session_state:
    st.session_state[THEME_STATE_KEY] = DEFAULT_THEME


def apply_theme(theme: str) -> None:
    components.html(
        f"""
        <script>
        (function () {{
          try {{
            const theme = {theme!r};
            const parentDoc = window.parent.document;
            parentDoc.documentElement.setAttribute("data-piolet-theme", theme);
            parentDoc.body.setAttribute("data-piolet-theme", theme);
            window.parent.localStorage.setItem("piolet-theme", theme);
          }} catch (e) {{}}
        }})();
        </script>
        """,
        height=0,
        width=0,
    )


apply_theme(st.session_state[THEME_STATE_KEY])

st.markdown(
    """
    <style>
    html, body, [class*="css"] {
        font-family: 'Space Grotesk', 'Segoe UI', 'Aptos', 'Helvetica Neue', Arial, sans-serif !important;
    }

    html[data-piolet-theme="light"],
    body[data-piolet-theme="light"],
    html[data-piolet-theme="light"] .stApp,
    body[data-piolet-theme="light"] .stApp,
    html[data-piolet-theme="light"] [data-testid="stAppViewContainer"],
    html[data-piolet-theme="light"] [data-testid="stHeader"],
    html[data-piolet-theme="light"] [data-testid="stSidebar"],
    html[data-piolet-theme="light"] .main {
        background: #f6f7fb !important;
        color: #111827 !important;
    }

    html[data-piolet-theme="dark"],
    body[data-piolet-theme="dark"],
    html[data-piolet-theme="dark"] .stApp,
    body[data-piolet-theme="dark"] .stApp,
    html[data-piolet-theme="dark"] [data-testid="stAppViewContainer"],
    html[data-piolet-theme="dark"] [data-testid="stHeader"],
    html[data-piolet-theme="dark"] [data-testid="stSidebar"],
    html[data-piolet-theme="dark"] .main {
        background: #0b1020 !important;
        color: #f8fafc !important;
    }

    html[data-piolet-theme="light"] .stApp,
    html[data-piolet-theme="light"] [data-testid="stSidebar"],
    html[data-piolet-theme="light"] [data-testid="stAppViewContainer"] > .main,
    html[data-piolet-theme="dark"] .stApp,
    html[data-piolet-theme="dark"] [data-testid="stSidebar"],
    html[data-piolet-theme="dark"] [data-testid="stAppViewContainer"] > .main {
        transition: background-color 180ms ease, color 180ms ease;
    }

    html[data-piolet-theme="dark"] .stApp *,
    html[data-piolet-theme="dark"] [data-testid="stSidebar"] *,
    html[data-piolet-theme="dark"] [data-testid="stAppViewContainer"] .main * {
        color: #f8fafc;
    }

    html[data-piolet-theme="dark"] [data-testid="stTextInput"] input,
    html[data-piolet-theme="dark"] [data-testid="stNumberInput"] input,
    html[data-piolet-theme="dark"] [data-baseweb="select"] input,
    html[data-piolet-theme="dark"] textarea {
        color: #111827 !important;
        background: #ffffff !important;
    }

    html[data-piolet-theme="dark"] [data-testid="stTextInput"] input::placeholder,
    html[data-piolet-theme="dark"] textarea::placeholder {
        color: #6b7280 !important;
    }

    html[data-piolet-theme="dark"] [data-testid="stDataFrame"],
    html[data-piolet-theme="dark"] [data-testid="stDataFrame"] * {
        color: #111827 !important;
    }

    html[data-piolet-theme="dark"] [data-testid="stDataFrame"] {
        background: #ffffff !important;
        border-radius: 14px !important;
        overflow: hidden !important;
    }

    [data-testid="stToolbar"],
    [data-testid="stDecoration"] {
        display: none !important;
    }

    button[data-testid="collapsedControl"],
    [data-testid="collapsedControl"],
    button[aria-label*="Open sidebar"],
    button[aria-label*="Abrir sidebar"],
    button[aria-label*="Expand sidebar"],
    button[aria-label*="Expandir sidebar"],
    button[aria-label*="Show sidebar"],
    button[aria-label*="Mostrar sidebar"],
    button[aria-label*="Collapse sidebar"],
    button[aria-label*="Colapsar sidebar"],
    button[title*="sidebar"],
    button[kind="headerNoPadding"],
    button[data-testid="stBaseButton-headerNoPadding"],
    button[kind="headerNoPadding"] span,
    button[data-testid="stBaseButton-headerNoPadding"] span {
        display: none !important;
        visibility: hidden !important;
        opacity: 0 !important;
        pointer-events: none !important;
    }

    section[data-testid="stSidebar"] {
        width: 220px !important;
        min-width: 220px !important;
        max-width: 220px !important;
    }

    section[data-testid="stSidebar"] * {
        box-sizing: border-box;
    }

    .piolet-brand {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        margin-bottom: 0.25rem;
    }

    .piolet-brand img {
        width: 52px;
        height: 52px;
        object-fit: contain;
        border-radius: 14px;
    }

    .piolet-brand .title {
        font-size: 1.05rem;
        font-weight: 700;
        letter-spacing: -0.03em;
        line-height: 1.05;
        margin: 0;
    }

    .piolet-brand .subtitle {
        font-size: 0.72rem;
        opacity: 0.72;
        margin-top: 0.12rem;
    }

    .sidebar-summary {
        margin-top: 0.45rem;
        margin-bottom: 0.85rem;
        line-height: 1.15;
    }

    .sidebar-summary .summary-label {
        font-size: 0.82rem;
        margin-top: 0.55rem;
        opacity: 0.88;
    }

    .sidebar-summary .summary-value {
        font-size: 1rem;
        font-weight: 700;
        margin-top: 0.12rem;
    }

    .apify-usage {
        margin-top: 0.8rem;
        margin-bottom: 0.85rem;
    }

    .apify-usage .usage-title {
        font-size: 0.82rem;
        font-weight: 700;
        margin-bottom: 0.3rem;
    }

    .apify-usage .usage-caption {
        font-size: 0.72rem;
        margin-top: 0.16rem;
        opacity: 0.75;
    }

    .apify-usage [data-testid="stProgressBar"] div div,
    .apify-usage [data-testid="stProgressBar"] div[role="progressbar"],
    .apify-usage [data-testid="stProgressBar"] div[role="progressbar"] > div {
        background-color: #d8ff4d !important;
    }

    .stMultiSelect div[data-baseweb="tag"],
    .stMultiSelect span[data-baseweb="tag"],
    .stMultiSelect [data-baseweb="tag"] {
        background-color: #d8ff4d !important;
        color: #111111 !important;
        border: 1px solid rgba(0, 0, 0, 0.06) !important;
    }

    .stMultiSelect div[data-baseweb="tag"] span,
    .stMultiSelect span[data-baseweb="tag"] span,
    .stMultiSelect [data-baseweb="tag"] span {
        color: #111111 !important;
    }

    .stMultiSelect div[data-baseweb="tag"]:hover,
    .stMultiSelect span[data-baseweb="tag"]:hover,
    .stMultiSelect [data-baseweb="tag"]:hover {
        background-color: #ecff8a !important;
    }

    .stMultiSelect div[data-baseweb="tag"] button:hover,
    .stMultiSelect div[data-baseweb="tag"] button:focus,
    .stMultiSelect span[data-baseweb="tag"] button:hover,
    .stMultiSelect span[data-baseweb="tag"] button:focus {
        background-color: #ecff8a !important;
    }

    [data-testid="stNumberInput"] button,
    [data-testid="stNumberInput"] button:hover,
    [data-testid="stNumberInput"] button:focus {
        background-color: #d8ff4d !important;
        color: #111111 !important;
        border-color: rgba(0, 0, 0, 0.06) !important;
    }

    .sidebar-actions .stButton > button,
    .sidebar-actions .stDownloadButton > button {
        width: 100% !important;
        min-height: 38px !important;
        border-radius: 999px !important;
        font-size: 0.85rem !important;
        padding-top: 0.45rem !important;
        padding-bottom: 0.45rem !important;
    }

    [data-testid="stButton"] > button[kind="primary"] {
        position: fixed !important;
        right: 20px;
        bottom: 20px;
        z-index: 1000;
        min-width: 220px;
        min-height: 48px;
        width: auto !important;
        box-shadow: 0 12px 28px rgba(0, 0, 0, 0.12);
        border-radius: 999px !important;
        background: #d8ff4d !important;
        color: #111111 !important;
        border: 1px solid rgba(0, 0, 0, 0.06) !important;
    }

    [data-testid="stDownloadButton"] > button,
    [data-testid="stDownloadButton"] a {
        position: fixed !important;
        right: 252px;
        bottom: 20px;
        z-index: 1000;
        min-width: 220px;
        min-height: 48px;
        width: auto !important;
        box-shadow: 0 12px 28px rgba(0, 0, 0, 0.12);
        border-radius: 999px !important;
    }

    [data-testid="stTextInput"] input {
        min-height: 44px !important;
        height: 44px !important;
        font-size: 0.82rem !important;
        border-radius: 999px !important;
    }

    .login-wrap {
        min-height: calc(100vh - 24px);
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 0.75rem 1rem 1rem;
    }

    .login-shell {
        width: min(560px, 100%);
        text-align: left;
        transform: translateY(-18px);
    }

    .login-head {
        display: flex;
        align-items: center;
        gap: 0.9rem;
        margin-bottom: 1.15rem;
    }

    .login-head img {
        width: 58px;
        height: 58px;
        object-fit: contain;
        border-radius: 16px;
    }

    .login-title {
        font-size: clamp(2rem, 4vw, 3rem);
        line-height: 0.96;
        font-weight: 700;
        letter-spacing: -0.05em;
        text-transform: uppercase;
        margin: 0;
    }

    .login-subtitle {
        font-size: 0.98rem;
        opacity: 0.75;
        margin-top: 1rem;
        margin-bottom: 1.35rem;
    }

    html[data-piolet-theme="dark"] .login-title,
    html[data-piolet-theme="dark"] .login-subtitle,
    html[data-piolet-theme="dark"] .sidebar-summary,
    html[data-piolet-theme="dark"] .sidebar-summary .summary-label,
    html[data-piolet-theme="dark"] .sidebar-summary .summary-value,
    html[data-piolet-theme="dark"] .apify-usage,
    html[data-piolet-theme="dark"] .apify-usage .usage-title,
    html[data-piolet-theme="dark"] .apify-usage .usage-caption {
        color: #ffffff !important;
    }

    html[data-piolet-theme="light"] .login-title,
    html[data-piolet-theme="light"] .login-subtitle,
    html[data-piolet-theme="light"] .sidebar-summary,
    html[data-piolet-theme="light"] .sidebar-summary .summary-label,
    html[data-piolet-theme="light"] .sidebar-summary .summary-value,
    html[data-piolet-theme="light"] .apify-usage,
    html[data-piolet-theme="light"] .apify-usage .usage-title,
    html[data-piolet-theme="light"] .apify-usage .usage-caption {
        color: #111111 !important;
    }

    html[data-piolet-theme="light"] .sidebar-actions .stButton > button,
    html[data-piolet-theme="light"] .sidebar-actions .stDownloadButton > button {
        background: linear-gradient(135deg, #111827 0%, #374151 100%) !important;
        color: #ffffff !important;
        border-color: rgba(17, 24, 39, 0.2) !important;
    }

    html[data-piolet-theme="dark"] .sidebar-actions .stButton > button,
    html[data-piolet-theme="dark"] .sidebar-actions .stDownloadButton > button {
        background: linear-gradient(135deg, #e2e8f0 0%, #ffffff 100%) !important;
        color: #0f172a !important;
        border-color: rgba(226, 232, 240, 0.2) !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def apify_monthly_usage_usd() -> float | None:
    from apify_client import ApifyClient

    token = (
        os.getenv("APIFY_KEY")
        or os.getenv("APIFY_TOKEN")
        or os.getenv("APIFY_API_TOKEN")
    )
    if not token:
        return None
    try:
        client = ApifyClient(token)
        usage = client.user().monthly_usage()
        candidates = [
            "totalUsageCreditsUsdAfterVolumeDiscount",
            "total_usage_credits_usd_after_volume_discount",
            "monthlyUsageUsd",
            "monthly_usage_usd",
            "totalUsageCreditsUsd",
            "total_usage_credits_usd",
            "totalUsageUsdAfterVolumeDiscount",
            "total_usage_usd_after_volume_discount",
        ]
        for key in candidates:
            if isinstance(usage, dict):
                raw_value = usage.get(key)
            else:
                raw_value = getattr(usage, key, None)
            if raw_value is not None:
                return float(raw_value)
        return None
    except Exception:
        return None


def fmt_usd(value: float) -> str:
    return f"${value:,.2f}"


def ensure_sidebar_open() -> None:
    components.html(
        """
        <script>
        (function () {
          try {
            const doc = window.parent.document;
            const sidebarSelectors = [
              'section[data-testid="stSidebar"]',
              'aside[data-testid="stSidebar"]',
              '[data-testid="stSidebar"]'
            ];
            const toggleSelectors = [
              'button[aria-label*="Open sidebar"]',
              'button[aria-label*="Abrir sidebar"]',
              'button[aria-label*="Expand sidebar"]',
              'button[aria-label*="Expandir sidebar"]',
              'button[aria-label*="Show sidebar"]',
              'button[aria-label*="Mostrar sidebar"]',
              'button[aria-label*="Collapse sidebar"]',
              'button[aria-label*="Colapsar sidebar"]',
              'button[data-testid="collapsedControl"]',
              'button[title*="sidebar"]',
              'button[kind="header"]',
              '[data-testid="collapsedControl"] button'
            ];

            const forceSidebarOpen = () => {
              for (const selector of sidebarSelectors) {
                const sidebar = doc.querySelector(selector);
                if (!sidebar) continue;
                sidebar.style.display = "block";
                sidebar.style.visibility = "visible";
                sidebar.style.opacity = "1";
                sidebar.style.transform = "none";
                sidebar.style.willChange = "auto";
                sidebar.style.position = "relative";
                sidebar.style.minWidth = "220px";
                sidebar.style.width = "220px";
                sidebar.style.maxWidth = "220px";
              }
            };

            const clickToggle = () => {
              for (const selector of toggleSelectors) {
                const button = doc.querySelector(selector);
                if (!button) continue;
                const aria = (button.getAttribute("aria-label") || "").toLowerCase();
                const title = (button.getAttribute("title") || "").toLowerCase();
                const expanded = button.getAttribute("aria-expanded");
                const looksLikeSidebarToggle =
                  aria.includes("sidebar") ||
                  title.includes("sidebar") ||
                  aria.includes("expand") ||
                  aria.includes("collapse") ||
                  aria.includes("open") ||
                  aria.includes("show") ||
                  button.textContent.includes("«") ||
                  button.textContent.includes("‹") ||
                  button.textContent.includes("»") ||
                  button.textContent.includes("›");
                if (!looksLikeSidebarToggle) continue;
                if (expanded !== "true") {
                  button.click();
                  return true;
                }
              }
              return false;
            };

            let attempts = 0;
            const tryOpen = () => {
              attempts += 1;
              const clicked = clickToggle();
              forceSidebarOpen();
              if (clicked) {
                return;
              }
              if (attempts < 20) {
                window.setTimeout(tryOpen, 250);
              }
            };
            window.setTimeout(() => {
              forceSidebarOpen();
              tryOpen();
            }, 50);
          } catch (e) {}
        })();
        </script>
        """,
        height=0,
        width=0,
    )


def render_login() -> None:
    c1, c2, c3 = st.columns([1, 1.1, 1], vertical_alignment="center")
    with c2:
        head_cols = st.columns([0.18, 0.82], vertical_alignment="center")
        with head_cols[0]:
            if APP_ICON.exists():
                st.image(str(APP_ICON), width=58)
            else:
                st.markdown("⛏️")
        with head_cols[1]:
            st.markdown(
                "<div class='login-title'>Piolet<br>Market Intelligence</div>"
                "<div class='login-subtitle'>Acceso interno al dashboard. Ingresa con tus credenciales de prueba para continuar.</div>",
                unsafe_allow_html=True,
            )

        with st.form("login_form"):
            user = st.text_input("Usuario", placeholder="Usuario")
            pwd = st.text_input("Contraseña", placeholder="Contraseña", type="password")
            submitted = st.form_submit_button("Entrar", use_container_width=True, type="secondary")

        if submitted:
            if user.strip() == TEST_USER and pwd == TEST_PASSWORD:
                st.session_state.logged_in = True
                st.rerun()
            st.error("Credenciales incorrectas.")

def render_sidebar(df: pd.DataFrame, apify_spent: float | None) -> tuple[list[str], int]:
    with st.sidebar:
        st.markdown(
            "<div style='font-size:1.05rem;font-weight:700;line-height:1.05;letter-spacing:-0.03em;margin-bottom:0.4rem;'>Piolet Market Intelligence</div>",
            unsafe_allow_html=True,
        )

        st.markdown(
            f"""
            <div class="sidebar-summary">
                <div class="summary-label">Videos analizados</div>
                <div class="summary-value">{len(df):,}</div>
                <div class="summary-label">Cuentas</div>
                <div class="summary-value">{df["account"].nunique():,}</div>
                <div class="summary-label">Views promedio</div>
                <div class="summary-value">{df["views"].mean():,.0f}</div>
                <div class="summary-label">Videos virales (>2x)</div>
                <div class="summary-value">{int((df["viral_score"] > 2).sum()):,}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("<div class='apify-usage'>", unsafe_allow_html=True)
        st.markdown("<div class='usage-title'>Consumo Apify</div>", unsafe_allow_html=True)
        if apify_spent is None:
            st.caption("No pude leer el uso mensual de Apify.")
        else:
            progress = min(max(apify_spent / APIFY_MONTHLY_BUDGET, 0.0), 1.0)
            st.progress(progress)
            st.markdown(
                f"<div class='usage-caption'>{fmt_usd(apify_spent)} / {fmt_usd(APIFY_MONTHLY_BUDGET)}</div>",
                unsafe_allow_html=True,
            )
        st.markdown("</div>", unsafe_allow_html=True)

        st.divider()
        plataformas = st.multiselect(
            "Plataforma",
            ["TikTok", "Instagram"],
            default=["TikTok", "Instagram"],
        )
        min_views = st.number_input("Views minimos", min_value=0, value=1000, step=1000)

        st.divider()
        current_theme = st.session_state.get(THEME_STATE_KEY, DEFAULT_THEME)
        theme_choice = st.radio(
            "Tema",
            ["Claro", "Oscuro"],
            index=0 if current_theme == "light" else 1,
            horizontal=True,
            label_visibility="collapsed",
            key="theme_radio",
        )
        selected_theme = "light" if theme_choice == "Claro" else "dark"
        if selected_theme != current_theme:
            st.session_state[THEME_STATE_KEY] = selected_theme
            apply_theme(selected_theme)
            st.rerun()

        with st.container():
            if st.button("Cerrar sesion", type="secondary", use_container_width=True):
                st.session_state.logged_in = False
                st.session_state.historial = []
                st.session_state.reporte_texto = ""
                st.session_state.reporte_pdf = None
                st.rerun()
            if st.session_state.get("logged_in") and st.button(
                "Actualizar datos (scraper)", type="secondary", use_container_width=True
            ):
                with st.spinner("Actualizando datos..."):
                    subprocess.run([sys.executable, "scraper.py"], check=False)
                st.success("Datos actualizados")
                st.rerun()

    return plataformas, min_views


def render_tables(df_filtrado: pd.DataFrame) -> None:
    import pandas as pd

    ranking_cols = [
        "platform",
        "account",
        "views",
        "likes",
        "comments",
        "engagement_rate",
        "viral_score",
        "description",
        "url",
    ]
    ranking_df = (
        df_filtrado[ranking_cols]
        .replace({"": pd.NA})
        .dropna(how="all")
        .head(5)
        .copy()
    )
    if not ranking_df.empty:
        ranking_df["views"] = ranking_df["views"].map(lambda v: f"{int(v):,}")
        ranking_df["likes"] = ranking_df["likes"].map(lambda v: f"{int(v):,}")
        ranking_df["comments"] = ranking_df["comments"].map(lambda v: f"{int(v):,}")
        ranking_df["engagement_rate"] = ranking_df["engagement_rate"].map(lambda v: f"{float(v):.2f}%")
        ranking_df["viral_score"] = ranking_df["viral_score"].map(lambda v: f"{float(v):.2f}")

    perf_df = (
        df_filtrado.groupby(["platform", "account"], as_index=False)
        .agg(
            videos=("views", "count"),
            views_max=("views", "max"),
            views_prom=("views", "mean"),
            eng=("engagement_rate", "mean"),
            vir=("viral_score", lambda x: int((x > 2).sum())),
        )
        .sort_values(["videos", "views_max"], ascending=[False, False])
        .head(5)
    )
    if not perf_df.empty:
        perf_df["views_max"] = perf_df["views_max"].map(lambda v: f"{int(v):,}")
        perf_df["views_prom"] = perf_df["views_prom"].map(lambda v: f"{float(v):,.0f}")
        perf_df["eng"] = perf_df["eng"].map(lambda v: f"{float(v):.2f}%")

    col_left, col_right = st.columns([1.55, 1.0], gap="large")
    with col_left:
        st.subheader("Ranking - Top 5 videos")
        st.dataframe(
            ranking_df,
            use_container_width=True,
            hide_index=True,
            height=320,
            column_config={
                "url": st.column_config.LinkColumn("URL", display_text="Abrir"),
            },
        )
    with col_right:
        st.subheader("Performance por cuenta")
        st.dataframe(
            perf_df,
            use_container_width=True,
            hide_index=True,
            height=320,
        )


def render_agent(context_data: str, df_filtrado: pd.DataFrame) -> None:
    from agent import analisis_automatico, build_report_pdf, stream_respuesta

    st.divider()
    if "historial" not in st.session_state:
        st.session_state.historial = []
    if "reporte_texto" not in st.session_state:
        st.session_state.reporte_texto = ""
    if "reporte_pdf" not in st.session_state:
        st.session_state.reporte_pdf = None

    for msg in st.session_state.historial:
        rol = "user" if msg["role"] == "user" else "assistant"
        with st.chat_message(rol):
            texto = msg["content"]
            if "[DATOS]" in texto:
                texto = texto.split("[DATOS]")[0].strip()
            st.write(texto)

    with st.form("agente_form", clear_on_submit=True):
        c1, c2 = st.columns([12, 1], vertical_alignment="bottom")
        with c1:
            pregunta = st.text_input(
                "Pregunta al agente",
                placeholder="Pregunta al agente... ej: Que videos funcionan mejor en TikTok?",
                label_visibility="collapsed",
            )
        with c2:
            enviar = st.form_submit_button("↗", use_container_width=True, type="secondary")

    if enviar and pregunta.strip():
        with st.chat_message("user"):
            st.write(pregunta)
        with st.chat_message("assistant"):
            respuesta = st.write_stream(
                stream_respuesta(st.session_state.historial, pregunta, context_data)
            )

        user_msg = (
            f"{pregunta}\n\n[DATOS]\n{context_data}"
            if not st.session_state.historial else pregunta
        )
        st.session_state.historial.append({"role": "user", "content": user_msg})
        st.session_state.historial.append({"role": "assistant", "content": respuesta})

    if st.session_state.historial and st.button("Limpiar chat", type="secondary"):
        st.session_state.historial = []
        st.rerun()

    st.write("")
    if st.button("Generar reporte", type="primary", use_container_width=True):
        with st.spinner("El agente esta analizando..."):
            reporte = analisis_automatico(df_filtrado)
            pdf_bytes = build_report_pdf(reporte, output_path="output/pdf/reporte_automatico.pdf")
        st.session_state.reporte_texto = reporte
        st.session_state.reporte_pdf = pdf_bytes
        st.rerun()

    if st.session_state.reporte_pdf:
        st.download_button(
            "Descargar reporte PDF",
            st.session_state.reporte_pdf,
            file_name="reporte_piolet.pdf",
            mime="application/pdf",
            use_container_width=True,
        )

    if st.session_state.reporte_texto:
        st.markdown("### Reporte generado")
        st.markdown(st.session_state.reporte_texto)


def main() -> None:
    if not st.session_state.get("logged_in"):
        render_login()
        return

    from agent import cargar_datos

    if not DATA_PATH.exists():
        st.warning("Sin datos aun. Corre `python scraper.py` en la terminal.")
        st.stop()

    df, context_data = cargar_datos()
    apify_spent = apify_monthly_usage_usd()

    ensure_sidebar_open()
    plataformas, min_views = render_sidebar(df, apify_spent)
    ensure_sidebar_open()

    df_filtrado = df[
        (df["platform"].isin(plataformas)) &
        (df["views"] >= min_views)
    ].copy()

    render_tables(df_filtrado)
    render_agent(context_data, df_filtrado)


if __name__ == "__main__":
    main()
