from __future__ import annotations

from html import escape
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from services.auth import require_authentication, show_logout_button
from services.supabase_service import (
    cloud_status,
    load_cloud_state_into_session,
)
from services.trading_service import initialize_trading_state

from services.portfolio_engine import (
    UNIVERSE,
    build_default_positions,
    calculate_portfolio,
    exposure_allocation,
    fetch_market_bundle,
    fetch_market_overview,
    load_transactions,
    performance_curve,
    pocket_allocation,
    recommend_orders,
    sector_allocation,
)


st.set_page_config(
    page_title="Alpha Zen Pro — Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

require_authentication()
show_logout_button()
load_cloud_state_into_session()


def load_css() -> None:
    css_path = Path("assets/custom.css")
    if css_path.exists():
        st.markdown(
            f"<style>{css_path.read_text(encoding='utf-8')}</style>",
            unsafe_allow_html=True,
        )


def fr_number(value: float, decimals: int = 2) -> str:
    if value is None or pd.isna(value):
        return "—"
    text = f"{float(value):,.{decimals}f}"
    return text.replace(",", " ").replace(".", ",")


def euro(value: float, decimals: int = 2, signed: bool = False) -> str:
    sign = "+" if signed and pd.notna(value) and float(value) > 0 else ""
    return f"{sign}{fr_number(value, decimals)} €"


def percent(value: float, decimals: int = 2, signed: bool = True) -> str:
    if value is None or pd.isna(value):
        return "—"
    sign = "+" if signed and float(value) > 0 else ""
    return f"{sign}{fr_number(value, decimals)} %"


def kpi_card(
    title: str,
    value: str,
    delta: str,
    note: str,
    icon: str,
    negative: bool = False,
) -> str:
    delta_class = "az-kpi-delta negative" if negative else "az-kpi-delta"
    return f"""
    <div class="az-kpi">
        <div class="az-kpi-head">
            <span>{escape(title)}</span><span class="az-kpi-icon">{icon}</span>
        </div>
        <div class="az-kpi-value">{escape(value)}</div>
        <div class="{delta_class}">{escape(delta)}</div>
        <div class="az-kpi-note">{escape(note)}</div>
    </div>
    """


def progress_rows(data: pd.DataFrame, label_col: str, value_col: str) -> str:
    palette = [
        "#00d7ad",
        "#ff4d5f",
        "#3b82f6",
        "#8b5cf6",
        "#f6a609",
        "#18b98b",
        "#60a5fa",
        "#f97316",
    ]
    rows = []
    for index, (_, row) in enumerate(data.head(8).iterrows()):
        value = max(0.0, min(float(row[value_col]), 100.0))
        color = palette[index % len(palette)]
        rows.append(
            f"""
            <div class="az-progress-row">
                <div class="az-progress-label">
                    <span>{escape(str(row[label_col]))}</span>
                    <strong style="color:{color}">{value:.1f}%</strong>
                </div>
                <div class="az-progress-track">
                    <div class="az-progress-fill"
                         style="width:{value:.1f}%;background:{color};"></div>
                </div>
            </div>
            """
        )
    return "".join(rows)


def alerts_html(frame: pd.DataFrame) -> str:
    priority = frame.copy()
    priority["Alert rank"] = np.select(
        [
            priority["Signal"].str.contains("Sous", na=False),
            priority["Signal"].str.contains("Renforcer", na=False),
            priority["Signal"].str.contains("Surveiller", na=False),
        ],
        [1, 2, 3],
        default=4,
    )
    priority = priority.sort_values(
        ["Alert rank", "Score Alpha Zen"],
        ascending=[True, False],
    ).head(4)

    rows = []
    for _, row in priority.iterrows():
        signal = str(row["Signal"])
        if "Sous" in signal:
            color = "#ff4d5f"
            arrow = "↓"
        elif "Renforcer" in signal:
            color = "#00d7ad"
            arrow = "↑"
        else:
            color = "#f6a609"
            arrow = "•"
        rows.append(
            f"""
            <div class="az-alert">
                <div>
                    <div class="az-alert-name">{escape(str(row["Nom court"]))}</div>
                    <div class="az-alert-signal" style="color:{color}">
                        {escape(signal)}
                    </div>
                </div>
                <div class="az-alert-score" style="color:{color}">
                    {int(row["Score Alpha Zen"])} {arrow}
                </div>
            </div>
            """
        )
    return "".join(rows)


def momentum_ranking_html(frame: pd.DataFrame) -> str:
    ranking = frame.sort_values("Score Alpha Zen", ascending=False).head(7)
    rows = []
    for rank, (_, row) in enumerate(ranking.iterrows(), start=1):
        score = float(row["Score Alpha Zen"])
        color = "#00d7ad" if score >= 70 else "#f6a609" if score >= 50 else "#ff4d5f"
        rows.append(
            f"""
            <div class="az-rank">
                <div class="az-rank-number">{rank}</div>
                <div class="az-rank-name">{escape(str(row["Nom court"]))}</div>
                <div class="az-progress-track">
                    <div class="az-progress-fill"
                         style="width:{score:.0f}%;background:{color};"></div>
                </div>
                <div class="az-rank-score" style="color:{color}">{score:.0f}</div>
            </div>
            """
        )
    return "".join(rows)


@st.cache_data(ttl=1800, show_spinner=False)
def cached_market_bundle(tickers: tuple[str, ...]):
    return fetch_market_bundle(list(tickers))


@st.cache_data(ttl=900, show_spinner=False)
def cached_market_overview():
    return fetch_market_overview()


load_css()

with st.sidebar:
    st.markdown(
        """
        <div class="az-logo">
            <div class="az-logo-box">📈</div>
            <div>
                <div class="az-logo-name">Alpha Zen</div>
                <div class="az-logo-sub">PEA Dashboard</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="az-profile">
            <div class="az-profile-title">Votre profil</div>
            <div class="az-profile-row"><span>Âge</span><strong>49 ans</strong></div>
            <div class="az-profile-row"><span>Profil</span><strong>Dynamique</strong></div>
            <div class="az-profile-row"><span>Horizon</span><strong>10–15 ans</strong></div>
            <div class="az-profile-row"><span>Versement</span><strong>1 000 € / mois</strong></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    capital_reference = st.number_input(
        "Capital de référence",
        min_value=0.0,
        value=float(
            st.session_state.get(
                "cloud_capital_reference",
                10_000.0,
            )
        ),
        step=500.0,
        format="%.2f",
    )
    monthly_contribution = st.number_input(
        "Versement mensuel",
        min_value=0.0,
        value=float(
            st.session_state.get(
                "cloud_monthly_contribution",
                1_000.0,
            )
        ),
        step=100.0,
        format="%.2f",
    )

    if st.button("🔄 Actualiser toutes les données", use_container_width=True):
        cached_market_bundle.clear()
        cached_market_overview.clear()
        st.rerun()

    sync = cloud_status()
    if sync["configured"] and not sync["error"]:
        st.success("☁️ Supabase connecté")
    elif sync["error"]:
        st.warning("☁️ Synchronisation en erreur")
    else:
        st.info("☁️ Supabase non configuré")

    st.markdown('<div class="az-panel-title">Marchés</div>', unsafe_allow_html=True)
    overview = cached_market_overview()
    market_rows = []
    for _, row in overview.iterrows():
        variation = row["Variation (%)"]
        color = "#00d7ad" if pd.notna(variation) and variation >= 0 else "#ff4d5f"
        market_rows.append(
            f"""
            <tr>
                <td>{escape(str(row["Marché"]))}</td>
                <td style="color:{color}">{percent(variation, 2)}</td>
            </tr>
            """
        )
    st.markdown(
        f'<table class="az-mini-table">{"".join(market_rows)}</table>',
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <div class="az-disclaimer">
            Données indicatives pouvant être retardées. Les signaux sont des règles
            mécaniques d’aide au suivi, pas des conseils personnalisés ni des ordres.
        </div>
        """,
        unsafe_allow_html=True,
    )


with st.spinner("Analyse des cours, tendances et allocations…"):
    market_data, price_matrix = cached_market_bundle(
        tuple(UNIVERSE["Ticker"].tolist())
    )

initialize_trading_state(
    UNIVERSE,
    market_data,
    capital_reference,
    monthly_contribution,
)

st.session_state["capital_reference"] = capital_reference
st.session_state["monthly_contribution"] = monthly_contribution

positions = st.session_state.virtual_positions.copy()
frame, summary = calculate_portfolio(
    UNIVERSE,
    market_data,
    positions,
    capital_reference,
)
# Réinjecte la version nettoyée afin que la page Portefeuille retrouve les mêmes lignes.
st.session_state.virtual_positions = frame[["Ticker", "Quantité", "PRU (€)"]].copy()

latest = summary["latest_timestamp"]
latest_text = (
    pd.Timestamp(latest).strftime("%d/%m/%Y %H:%M")
    if pd.notna(latest)
    else "données indisponibles"
)

st.markdown(
    f"""
    <div class="az-header">
        <div>
            <div class="az-title">TABLEAU DE BORD</div>
            <div class="az-subtitle">Vue d’ensemble de votre portefeuille Alpha Zen</div>
        </div>
        <div class="az-update">Dernière cotation : {escape(latest_text)}<br>Devise : EUR</div>
    </div>
    """,
    unsafe_allow_html=True,
)

k1, k2, k3, k4, k5 = st.columns(5)
with k1:
    st.markdown(
        kpi_card(
            "Valeur totale",
            euro(summary["total_value"]),
            percent(summary["performance"]),
            "positions + liquidités",
            "💼",
            summary["performance"] < 0,
        ),
        unsafe_allow_html=True,
    )
with k2:
    st.markdown(
        kpi_card(
            "Investi",
            euro(summary["invested"]),
            f'{int(summary["active_lines"])} lignes actives',
            "capital engagé",
            "🪙",
        ),
        unsafe_allow_html=True,
    )
with k3:
    st.markdown(
        kpi_card(
            "Plus-value",
            euro(summary["gain"], signed=True),
            percent(summary["performance"]),
            "latente",
            "📈",
            summary["gain"] < 0,
        ),
        unsafe_allow_html=True,
    )
with k4:
    cash_pct = (
        summary["cash"] / summary["total_value"] * 100.0
        if summary["total_value"]
        else 0.0
    )
    st.markdown(
        kpi_card(
            "Liquidités",
            euro(summary["cash"]),
            percent(cash_pct, signed=False),
            "du portefeuille",
            "🕘",
        ),
        unsafe_allow_html=True,
    )
with k5:
    st.markdown(
        kpi_card(
            "Performance YTD",
            percent(summary["ytd"]),
            euro(
                summary["invested"] * summary["ytd"] / 100.0,
                signed=True,
            ),
            "estimation pondérée",
            "🏆",
            summary["ytd"] < 0,
        ),
        unsafe_allow_html=True,
    )

st.write("")

pocket = pocket_allocation(frame)
sectors = sector_allocation(frame)
exposure = exposure_allocation(frame)

top1, top2, top3 = st.columns([1.08, 1.25, 1.0])

with top1:
    with st.container(border=True):
        st.markdown(
            '<div class="az-panel-title">RÉPARTITION STRATÉGIQUE</div>',
            unsafe_allow_html=True,
        )
        fig_pocket = px.pie(
            pocket,
            values="Valeur actuelle (€)",
            names="Poche",
            hole=0.63,
            color="Poche",
            color_discrete_map={
                "Socle Zen": "#00d7ad",
                "Momentum": "#3b82f6",
                "Satellite": "#f6a609",
            },
        )
        fig_pocket.update_traces(
            textinfo="percent",
            hovertemplate="<b>%{label}</b><br>%{value:,.0f} €<br>%{percent}<extra></extra>",
        )
        fig_pocket.add_annotation(
            text=f"<b>{fr_number(summary['total_value'], 0)} €</b><br><span style='font-size:11px'>Total</span>",
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(color="#f2f6ff", size=14),
        )
        fig_pocket.update_layout(
            height=300,
            margin=dict(l=0, r=0, t=0, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            legend=dict(
                orientation="v",
                yanchor="middle",
                y=0.5,
                xanchor="left",
                x=0.78,
                font=dict(color="#cbd5e1", size=11),
            ),
        )
        st.plotly_chart(
            fig_pocket,
            use_container_width=True,
            config={"displayModeBar": False},
        )
        st.caption("Objectif de référence : Socle 50 % / Momentum 35 % / Satellite 15 %")

with top2:
    with st.container(border=True):
        st.markdown(
            '<div class="az-panel-title">RÉPARTITION SECTORIELLE</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            progress_rows(sectors, "Secteur", "Poids (%)"),
            unsafe_allow_html=True,
        )

with top3:
    with st.container(border=True):
        st.markdown(
            '<div class="az-panel-title">ALERTES & SIGNAUX</div>',
            unsafe_allow_html=True,
        )
        st.markdown(alerts_html(frame), unsafe_allow_html=True)

st.write("")

with st.container(border=True):
    st.markdown(
        '<div class="az-panel-title">PORTEFEUILLE DÉTAILLÉ</div>',
        unsafe_allow_html=True,
    )
    table = frame[
        [
            "Nom court",
            "Type",
            "Quantité",
            "Cours (€)",
            "Valeur actuelle (€)",
            "Plus-value (€)",
            "Plus-value (%)",
            "Score Alpha Zen",
            "Signal",
            "Poids réel (%)",
        ]
    ].copy()
    table.columns = [
        "Actif",
        "Catégorie",
        "Qté",
        "Cours",
        "Valeur",
        "+/- Value",
        "Perf. %",
        "Momentum",
        "MM200 / Signal",
        "Poids",
    ]
    st.dataframe(
        table,
        hide_index=True,
        use_container_width=True,
        height=500,
        column_config={
            "Actif": st.column_config.TextColumn("Actif", width="medium"),
            "Catégorie": st.column_config.TextColumn("Catégorie", width="small"),
            "Qté": st.column_config.NumberColumn("Qté", format="%.2f"),
            "Cours": st.column_config.NumberColumn("Cours", format="%.2f €"),
            "Valeur": st.column_config.NumberColumn("Valeur", format="%.2f €"),
            "+/- Value": st.column_config.NumberColumn("+/- Value", format="%+.2f €"),
            "Perf. %": st.column_config.NumberColumn("Perf. %", format="%+.2f %%"),
            "Momentum": st.column_config.ProgressColumn(
                "Momentum",
                min_value=0,
                max_value=100,
                format="%.0f",
            ),
            "MM200 / Signal": st.column_config.TextColumn(
                "MM200 / Signal",
                width="medium",
            ),
            "Poids": st.column_config.NumberColumn("Poids", format="%.1f %%"),
        },
    )
    st.caption("Cours indicatifs. Les quantités et PRU sont modifiables dans la page Portefeuille.")

st.write("")

middle1, middle2, middle3 = st.columns([1.35, 0.9, 0.9])

with middle1:
    with st.container(border=True):
        st.markdown(
            '<div class="az-panel-title">PERFORMANCE DU PORTEFEUILLE</div>',
            unsafe_allow_html=True,
        )
        curve = performance_curve(
            price_matrix,
            positions,
            summary["cash"],
            days=365,
        )
        if curve.empty:
            st.info("Historique insuffisant pour afficher la performance.")
        else:
            fig_perf = px.line(
                curve,
                x="Date",
                y="Performance (%)",
                color="Série",
                color_discrete_map={
                    "Portefeuille": "#00d7ad",
                    "MSCI World": "#3b82f6",
                },
            )
            fig_perf.update_traces(line=dict(width=2.2))
            fig_perf.update_layout(
                height=300,
                margin=dict(l=0, r=0, t=10, b=0),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.01,
                    xanchor="left",
                    x=0,
                    font=dict(color="#cbd5e1"),
                ),
                xaxis=dict(
                    title="",
                    gridcolor="rgba(65,85,115,0.2)",
                    color="#8794aa",
                ),
                yaxis=dict(
                    title="",
                    ticksuffix=" %",
                    gridcolor="rgba(65,85,115,0.2)",
                    color="#8794aa",
                ),
                hovermode="x unified",
            )
            st.plotly_chart(
                fig_perf,
                use_container_width=True,
                config={"displayModeBar": False},
            )

with middle2:
    with st.container(border=True):
        st.markdown(
            '<div class="az-panel-title">MOMENTUM RANKING</div>',
            unsafe_allow_html=True,
        )
        st.markdown(momentum_ranking_html(frame), unsafe_allow_html=True)

with middle3:
    with st.container(border=True):
        st.markdown(
            '<div class="az-panel-title">EXPOSITION ESTIMÉE</div>',
            unsafe_allow_html=True,
        )
        fig_expo = go.Figure(
            data=[
                go.Pie(
                    labels=exposure["Exposition"],
                    values=exposure["Valeur (€)"],
                    hole=0.62,
                    marker=dict(colors=["#00d7ad", "#3b82f6", "#f6a609"]),
                    textinfo="none",
                    hovertemplate="<b>%{label}</b><br>%{percent}<extra></extra>",
                )
            ]
        )
        fig_expo.update_layout(
            height=270,
            margin=dict(l=0, r=0, t=0, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            legend=dict(
                orientation="v",
                yanchor="middle",
                y=0.5,
                xanchor="left",
                x=0.76,
                font=dict(color="#cbd5e1", size=11),
            ),
        )
        st.plotly_chart(
            fig_expo,
            use_container_width=True,
            config={"displayModeBar": False},
        )
        st.caption("Estimation simplifiée de l’exposition économique des indices et titres.")

st.write("")

bottom1, bottom2, bottom3 = st.columns(3)

with bottom1:
    with st.container(border=True):
        st.markdown(
            '<div class="az-panel-title">DERNIÈRES TRANSACTIONS</div>',
            unsafe_allow_html=True,
        )
        transactions = st.session_state.get(
            "virtual_transactions",
            load_transactions(),
        ).head(5)
        if transactions.empty:
            st.markdown(
                """
                <table class="az-mini-table">
                    <tr><td>Portefeuille virtuel</td><td>Initialisé</td></tr>
                    <tr><td>Cours automatiques</td><td>Actifs</td></tr>
                    <tr><td>MM200 et momentum</td><td>Calculés</td></tr>
                </table>
                """,
                unsafe_allow_html=True,
            )
            st.caption("Ajoute data/transactions.csv pour afficher tes opérations.")
        else:
            rows = []
            for _, row in transactions.iterrows():
                date_text = (
                    pd.Timestamp(row["Date"]).strftime("%d/%m/%Y")
                    if pd.notna(row["Date"])
                    else "—"
                )
                rows.append(
                    f"<tr><td>{date_text} · {escape(str(row['Type']))}</td>"
                    f"<td>{escape(str(row['Actif']))} · {euro(row['Montant (€)'])}</td></tr>"
                )
            st.markdown(
                f'<table class="az-mini-table">{"".join(rows)}</table>',
                unsafe_allow_html=True,
            )

with bottom2:
    with st.container(border=True):
        st.markdown(
            '<div class="az-panel-title">PROCHAIN VERSEMENT PROGRAMMÉ</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<div class='az-kpi-value' style='font-size:1.65rem'>{euro(monthly_contribution)}</div>",
            unsafe_allow_html=True,
        )
        orders = recommend_orders(
            frame,
            monthly_contribution,
            summary["total_value"] + monthly_contribution,
            max_orders=3,
        )
        if orders.empty:
            st.info("Aucun achat proposé avec les règles actuelles.")
        else:
            rows = []
            for _, row in orders.iterrows():
                rows.append(
                    f"<tr><td>{escape(str(row['Nom court'] if 'Nom court' in row else row['Actif']))}</td>"
                    f"<td>{int(row['Quantité proposée'])} × {fr_number(row['Cours (€)'], 2)} €"
                    f"<br><span style='color:#00d7ad'>{euro(row['Montant proposé (€)'])}</span></td></tr>"
                )
            st.markdown(
                f'<table class="az-mini-table">{"".join(rows)}</table>',
                unsafe_allow_html=True,
            )
        st.caption("Simulation tenant compte des sous-pondérations et de la MM200.")

with bottom3:
    with st.container(border=True):
        st.markdown(
            '<div class="az-panel-title">OBJECTIFS</div>',
            unsafe_allow_html=True,
        )
        goals = [
            ("Objectif 1", 15_000.0, "#00d7ad"),
            ("Objectif 2030", 30_000.0, "#f6a609"),
            ("Objectif 2035", 60_000.0, "#8b5cf6"),
        ]
        goal_rows = []
        for label, target, color in goals:
            progress = min(summary["total_value"] / target * 100.0, 100.0)
            goal_rows.append(
                f"""
                <div class="az-objective">
                    <div class="az-objective-head">
                        <span>{label} · {fr_number(target, 0)} €</span>
                        <strong>{progress:.0f}%</strong>
                    </div>
                    <div class="az-progress-track">
                        <div class="az-progress-fill"
                             style="width:{progress:.1f}%;background:{color};"></div>
                    </div>
                </div>
                """
            )
        st.markdown("".join(goal_rows), unsafe_allow_html=True)

st.markdown(
    """
    <div class="az-disclaimer" style="text-align:center;margin-top:20px">
        Stratégie de suivi : Socle 50 % / Momentum 35 % / Satellite 15 % ·
        Les résultats passés et les scores quantitatifs ne garantissent aucune performance future.
    </div>
    """,
    unsafe_allow_html=True,
)
