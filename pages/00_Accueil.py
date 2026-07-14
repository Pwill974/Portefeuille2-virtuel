from __future__ import annotations

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Alpha Zen Pro — Accueil", page_icon="📊", layout="wide")

from services.auth import require_authentication, show_logout_button
from services.benchmark_comparison_service import build_portfolio_vs_sp500
from services.supabase_service import (
    get_profile_id,
    get_supabase_client,
    load_cloud_state_into_session,
    supabase_is_configured,
)

require_authentication()
show_logout_button()


def euro(value: float) -> str:
    return f"{float(value):,.2f} €".replace(",", " ").replace(".", ",")


def pct(value: float) -> str:
    return f"{float(value) * 100:.2f} %".replace(".", ",")


def safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


@st.cache_data(ttl=60 * 20, show_spinner=False)
def load_snapshot_rows(profile_id: str) -> list[dict]:
    response = (
        get_supabase_client()
        .table("az_snapshots")
        .select("*")
        .eq("profile_id", profile_id)
        .order("snapshot_date", desc=False)
        .execute()
    )
    return getattr(response, "data", None) or []


st.title("📊 Alpha Zen Pro")
st.caption("Suivi de la valeur du portefeuille et comparaison avec le S&P 500.")

if not supabase_is_configured():
    st.error("Supabase n'est pas configuré.")
    st.stop()

try:
    load_cloud_state_into_session(force=True)
except Exception as error:
    st.warning(f"Chargement du portefeuille incomplet : {error}")

cash = safe_float(st.session_state.get("virtual_cash", 0.0), 0.0)
capital_reference = safe_float(
    st.session_state.get("capital_reference", st.session_state.get("cloud_capital_reference", 0.0)),
    0.0,
)

try:
    rows = load_snapshot_rows(get_profile_id())
except Exception as error:
    st.error(f"Impossible de lire la table az_snapshots : {error}")
    st.stop()

chart = build_portfolio_vs_sp500(rows)

if chart.empty or len(chart) < 2:
    st.warning("Pas encore assez d'historique pour afficher le graphique comparatif.")
    st.info("Il faut au minimum 2 lignes dans Supabase > Table Editor > az_snapshots.")
    st.stop()

latest = chart.iloc[-1]
first = chart.iloc[0]

portfolio_now = safe_float(latest["Portefeuille"])
portfolio_start = safe_float(first["Portefeuille"])
sp_now = safe_float(latest.get("S&P 500 normalisé", 0.0))
sp_start = safe_float(first.get("S&P 500 normalisé", portfolio_start))

portfolio_perf = (portfolio_now / portfolio_start - 1) if portfolio_start > 0 else 0.0
sp_perf = (sp_now / sp_start - 1) if sp_start > 0 else 0.0
ecart = portfolio_perf - sp_perf

c1, c2, c3, c4 = st.columns(4)
c1.metric("Portefeuille actuel", euro(portfolio_now))
c2.metric("Performance portefeuille", pct(portfolio_perf))
c3.metric("Performance S&P 500", pct(sp_perf))
c4.metric("Écart vs S&P 500", pct(ecart))

st.divider()
st.subheader("Valeur du portefeuille vs S&P 500")
st.caption("Le S&P 500 est normalisé sur la même valeur de départ que ton portefeuille.")

chart_display = chart.copy()
chart_display["Date"] = pd.to_datetime(chart_display["Date"])
chart_display = chart_display.set_index("Date")
chart_display = chart_display[["Portefeuille", "S&P 500 normalisé"]]
st.line_chart(chart_display, use_container_width=True)

st.divider()
left, right = st.columns(2)

with left:
    st.subheader("Lecture rapide")
    if ecart > 0:
        st.success(f"Ton portefeuille fait mieux que le S&P 500 : +{pct(ecart)} d'écart.")
    elif ecart < 0:
        st.warning(f"Ton portefeuille fait moins bien que le S&P 500 : {pct(ecart)} d'écart.")
    else:
        st.info("Ton portefeuille est au même niveau que le S&P 500 sur la période.")

with right:
    st.subheader("Liquidités et capital")
    st.metric("Liquidités", euro(cash))
    if capital_reference > 0:
        st.metric("Capital versé", euro(capital_reference))

st.caption("Comparaison indicative : le S&P 500 est en USD, ton portefeuille PEA est en euros.")
