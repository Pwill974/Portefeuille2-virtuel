from __future__ import annotations

from html import escape

import numpy as np
import pandas as pd
import streamlit as st

from services.auth import (
    require_authentication,
    show_logout_button,
)
from services.fortuneo_fees import (
    FORTUNEO_PLANS,
    calculate_fortuneo_fee,
    plan_summary,
)
from services.performance_history_service import (
    build_snapshot,
    load_brokerage_plan,
    save_brokerage_plan,
    save_daily_snapshot,
)
from services.portfolio_engine import (
    UNIVERSE,
    calculate_portfolio,
    fetch_market_bundle,
)
from services.portfolio_persistence_service import (
    hydrate_market_data,
    repair_session_pru_from_transactions,
    save_live_valuation,
    save_market_state,
)
from services.supabase_service import (
    cloud_status,
    load_cloud_state_into_session,
)
from services.trading_service import (
    current_position,
    execute_trade,
    initialize_trading_state,
    market_value,
)


st.set_page_config(
    page_title="Alpha Zen Pro — Actifs & Ordres",
    page_icon="📊",
    layout="wide",
)

require_authentication()
show_logout_button()
load_cloud_state_into_session()


@st.cache_data(ttl=900, show_spinner=False)
def load_market_bundle(
    tickers: tuple[str, ...],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    return fetch_market_bundle(list(tickers))


def euro(value: float) -> str:
    return (
        f"{float(value):,.2f} €"
        .replace(",", " ")
        .replace(".", ",")
    )


def signed_euro(value: float) -> str:
    sign = "+" if float(value) > 0 else ""
    return (
        f"{sign}{float(value):,.2f} €"
        .replace(",", " ")
        .replace(".", ",")
    )


def signed_percent(value: float) -> str:
    sign = "+" if float(value) > 0 else ""
    return (
        f"{sign}{float(value):.2f} %"
        .replace(".", ",")
    )


def number(value: object, default: float = 0.0) -> float:
    parsed = pd.to_numeric(
        pd.Series([value]),
        errors="coerce",
    ).iloc[0]
    return (
        float(parsed)
        if pd.notna(parsed)
        else float(default)
    )


def pocket_class(pocket: str) -> str:
    normalized = pocket.lower()
    if "socle" in normalized:
        return "badge-zen"
    if "satellite" in normalized:
        return "badge-satellite"
    return "badge-momentum"


def score_label(score: float) -> str:
    if score >= 75:
        return "Fort"
    if score >= 55:
        return "Moyen"
    return "Faible"


def score_icon(score: float) -> str:
    if score >= 75:
        return "🚀"
    if score >= 55:
        return "⚡"
    return "⚠️"


def recommendation(row: pd.Series) -> tuple[str, str]:
    quantity = number(row.get("Quantité"))
    distance = number(
        row.get("Distance MM200 (%)"),
        default=np.nan,
    )
    score = number(row.get("Score Alpha Zen"))
    target = number(row.get("Allocation cible (%)"))
    real_weight = number(row.get("Poids portefeuille (%)"))

    if pd.notna(distance) and distance < 0 and quantity > 0:
        return (
            "🔴 Vendre / alléger",
            "Position détenue sous la MM200.",
        )
    if (
        pd.notna(distance)
        and distance >= 0
        and score >= 75
        and real_weight < target
    ):
        return (
            "🟢 Renforcer",
            "Momentum fort et allocation encore sous la cible.",
        )
    if pd.notna(distance) and distance >= 0 and score >= 55:
        return (
            "🟠 Conserver",
            "Tendance positive, mais signal moins puissant.",
        )
    if quantity <= 0:
        return (
            "⚪ Attendre",
            "Aucun signal d'achat suffisamment fort actuellement.",
        )
    return (
        "🟠 Surveiller",
        "La position ne réunit pas encore tous les critères.",
    )


def set_focus(ticker: str) -> None:
    st.session_state["asset_focus_ticker"] = ticker
    try:
        st.query_params["ticker"] = ticker
    except Exception:
        pass


def selected_ticker_from_state() -> str | None:
    ticker = st.session_state.get("asset_focus_ticker")

    try:
        query_ticker = st.query_params.get("ticker")
        if isinstance(query_ticker, list):
            query_ticker = (
                query_ticker[0]
                if query_ticker
                else None
            )
        if query_ticker:
            ticker = str(query_ticker)
    except Exception:
        pass

    valid = set(UNIVERSE["Ticker"].astype(str))
    return ticker if ticker in valid else None


st.markdown(
    """
<style>
    .block-container {
        padding-top: 1.2rem;
        padding-bottom: 4rem;
        max-width: 1120px;
    }

    .az-title {
        font-size: 2rem;
        font-weight: 800;
        letter-spacing: -0.02em;
        margin-bottom: 0.15rem;
    }

    .az-subtitle {
        color: #94a3b8;
        margin-bottom: 1rem;
    }

    .pocket-heading {
        display: flex;
        align-items: center;
        gap: 0.7rem;
        margin: 1.7rem 0 0.75rem 0;
        font-size: 1.15rem;
        font-weight: 800;
        letter-spacing: 0.08em;
        text-transform: uppercase;
    }

    .pocket-line {
        width: 5px;
        height: 30px;
        border-radius: 4px;
        background: #14b8a6;
    }

    .asset-header {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 0.45rem;
        margin-bottom: 0.25rem;
    }

    .asset-ticker {
        font-size: 1.35rem;
        font-weight: 900;
        color: #22d3b6;
    }

    .asset-name {
        color: #94a3b8;
        font-size: 1rem;
        margin-top: 0.2rem;
    }

    .asset-isin {
        color: #64748b;
        font-size: 0.85rem;
        margin-top: 0.15rem;
    }

    .badge {
        display: inline-flex;
        border-radius: 0.5rem;
        padding: 0.18rem 0.55rem;
        font-size: 0.78rem;
        font-weight: 700;
        border: 1px solid;
    }

    .badge-type {
        color: #60a5fa;
        border-color: rgba(59, 130, 246, 0.55);
        background: rgba(37, 99, 235, 0.12);
    }

    .badge-sector {
        color: #2dd4bf;
        border-color: rgba(20, 184, 166, 0.5);
        background: rgba(13, 148, 136, 0.12);
    }

    .badge-zen {
        color: #2dd4bf;
        border-color: rgba(20, 184, 166, 0.5);
        background: rgba(13, 148, 136, 0.12);
    }

    .badge-momentum {
        color: #60a5fa;
        border-color: rgba(59, 130, 246, 0.55);
        background: rgba(37, 99, 235, 0.12);
    }

    .badge-satellite {
        color: #fbbf24;
        border-color: rgba(245, 158, 11, 0.55);
        background: rgba(217, 119, 6, 0.12);
    }

    .metric-label {
        color: #64748b;
        font-size: 0.8rem;
        text-transform: uppercase;
        margin-bottom: 0.1rem;
    }

    .metric-main {
        font-size: 1.35rem;
        font-weight: 800;
    }

    .metric-secondary {
        color: #94a3b8;
        font-size: 0.95rem;
    }

    .positive {
        color: #10b981;
    }

    .negative {
        color: #fb7185;
    }

    .neutral {
        color: #cbd5e1;
    }

    .detail-box {
        border: 1px solid rgba(148, 163, 184, 0.25);
        background: rgba(15, 23, 42, 0.45);
        border-radius: 1rem;
        padding: 1rem;
        margin-bottom: 0.75rem;
    }

    .signal-box {
        border-left: 5px solid #14b8a6;
        border-radius: 0.7rem;
        background: rgba(15, 23, 42, 0.45);
        padding: 0.85rem 1rem;
        margin: 0.75rem 0;
    }

    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 1rem;
        border-color: rgba(100, 116, 139, 0.28);
        background: rgba(15, 23, 42, 0.48);
        box-shadow: 0 8px 24px rgba(2, 6, 23, 0.12);
    }

    div[data-testid="stProgress"] > div > div > div {
        background-color: #14b8a6;
    }

    .stButton > button {
        border-radius: 0.7rem;
        font-weight: 700;
    }
</style>
""",
    unsafe_allow_html=True,
)


st.markdown(
    '<div class="az-title">📊 Actifs & Ordres</div>'
    '<div class="az-subtitle">'
    "Une fiche complète par actif, avec Momentum, allocation, "
    "plus-value et passage d'ordre sur la même page."
    "</div>",
    unsafe_allow_html=True,
)

status = cloud_status()
if status["configured"] and not status["error"]:
    st.success("☁️ Portefeuille Supabase connecté")
elif status["error"]:
    st.warning(
        f"☁️ Synchronisation Supabase : {status['error']}"
    )
else:
    st.info(
        "☁️ Mode local : configure Supabase pour conserver "
        "durablement les opérations."
    )

capital_reference = float(
    st.session_state.get(
        "cloud_capital_reference",
        st.session_state.get(
            "capital_reference",
            10_000.0,
        ),
    )
)
monthly_contribution = float(
    st.session_state.get(
        "cloud_monthly_contribution",
        st.session_state.get(
            "monthly_contribution",
            1_000.0,
        ),
    )
)

refresh_col, plan_col = st.columns([1, 2])
with refresh_col:
    if st.button(
        "🔄 Actualiser les cours",
        use_container_width=True,
    ):
        load_market_bundle.clear()
        st.rerun()

with plan_col:
    current_plan = load_brokerage_plan()
    selected_plan = st.selectbox(
        "Tarif Fortuneo",
        FORTUNEO_PLANS,
        index=(
            FORTUNEO_PLANS.index(current_plan)
            if current_plan in FORTUNEO_PLANS
            else 0
        ),
        label_visibility="collapsed",
    )
    if selected_plan != current_plan:
        save_brokerage_plan(selected_plan)

with st.spinner("Chargement des cours et des indicateurs…"):
    market_data, price_matrix = load_market_bundle(
        tuple(UNIVERSE["Ticker"].tolist())
    )
    market_data = hydrate_market_data(market_data)
    try:
        save_market_state(market_data)
    except Exception as error:
        st.session_state["az_market_error"] = str(error)

initialize_trading_state(
    UNIVERSE,
    market_data,
    capital_reference,
    monthly_contribution,
)
repair_session_pru_from_transactions()

positions = st.session_state.virtual_positions.copy()
frame, _ = calculate_portfolio(
    UNIVERSE,
    market_data,
    positions,
    capital_reference,
)

cash = float(
    st.session_state.get(
        "virtual_cash",
        0.0,
    )
)
positions_value = market_value(
    positions,
    market_data,
)
total_value = cash + positions_value

frame["Poids portefeuille (%)"] = (
    frame["Valeur actuelle (€)"] / total_value * 100.0
    if total_value > 0
    else 0.0
)
frame["Écart cible portefeuille (%)"] = (
    frame["Poids portefeuille (%)"]
    - frame["Allocation cible (%)"]
)

summary_cols = st.columns(4)
summary_cols[0].metric(
    "Valeur totale",
    euro(total_value),
)
summary_cols[1].metric(
    "Positions",
    euro(positions_value),
)
summary_cols[2].metric(
    "Liquidités",
    euro(cash),
)
summary_cols[3].metric(
    "Lignes détenues",
    int((frame["Quantité"] > 0).sum()),
)

focus_ticker = selected_ticker_from_state()

if focus_ticker:
    detail_match = frame.loc[
        frame["Ticker"] == focus_ticker
    ]

    if not detail_match.empty:
        row = detail_match.iloc[0]
        price = number(row.get("Cours (€)"))
        quantity_held = number(row.get("Quantité"))
        pru = number(row.get("PRU (€)"))
        invested = number(row.get("Investi (€)"))
        current_value = number(
            row.get("Valeur actuelle (€)")
        )
        gain = number(row.get("Plus-value (€)"))
        gain_pct = number(row.get("Plus-value (%)"))
        score = number(row.get("Score Alpha Zen"))
        target = number(
            row.get("Allocation cible (%)")
        )
        real_weight = number(
            row.get("Poids portefeuille (%)")
        )
        signal_title, signal_text = recommendation(row)

        st.divider()

        close_col, title_col = st.columns([1, 8])
        with close_col:
            if st.button(
                "← Retour",
                use_container_width=True,
            ):
                st.session_state.pop(
                    "asset_focus_ticker",
                    None,
                )
                try:
                    st.query_params.clear()
                except Exception:
                    pass
                st.rerun()

        with title_col:
            st.markdown(
                f"""
<div class="asset-header">
    <span class="asset-ticker">
        {escape(str(row["Ticker"]).replace(".PA", ""))}
    </span>
    <span class="badge badge-type">
        {escape(str(row["Type"]))}
    </span>
    <span class="badge badge-sector">
        {escape(str(row["Secteur"]))}
    </span>
    <span class="badge {pocket_class(str(row["Poche"]))}">
        {escape(str(row["Poche"]))}
    </span>
</div>
<div class="asset-name">{escape(str(row["Actif"]))}</div>
<div class="asset-isin">{escape(str(row["ISIN"]))}</div>
""",
                unsafe_allow_html=True,
            )

        left, right = st.columns([1.45, 1])

        with left:
            top_metrics = st.columns(4)
            top_metrics[0].metric(
                "Cours",
                euro(price),
            )
            top_metrics[1].metric(
                "Quantité",
                f"{quantity_held:.4f}",
            )
            top_metrics[2].metric(
                "Valeur",
                euro(current_value),
            )
            top_metrics[3].metric(
                "Plus-value",
                signed_euro(gain),
                signed_percent(gain_pct),
            )

            st.markdown(
                f"""
<div class="signal-box">
    <strong>{escape(signal_title)}</strong><br>
    <span style="color:#94a3b8">{escape(signal_text)}</span>
</div>
""",
                unsafe_allow_html=True,
            )

            momentum_cols = st.columns(4)
            momentum_cols[0].metric(
                "Score Momentum",
                f"{score:.0f}/100",
            )
            momentum_cols[1].metric(
                "MM200",
                euro(number(row.get("MM200 (€)"))),
                signed_percent(
                    number(
                        row.get("Distance MM200 (%)")
                    )
                ),
            )
            momentum_cols[2].metric(
                "Momentum 6 mois",
                signed_percent(
                    number(
                        row.get("Momentum 6M (%)")
                    )
                ),
            )
            momentum_cols[3].metric(
                "Volatilité 1 an",
                f"{number(row.get('Volatilité 1A (%)')):.2f} %",
            )

            st.progress(
                min(max(score / 100.0, 0.0), 1.0),
                text=(
                    f"{score_icon(score)} Momentum "
                    f"{score_label(score)} — {score:.0f}/100"
                ),
            )

            allocation_cols = st.columns(3)
            allocation_cols[0].metric(
                "Allocation cible",
                f"{target:.1f} %",
            )
            allocation_cols[1].metric(
                "Poids réel",
                f"{real_weight:.1f} %",
            )
            allocation_cols[2].metric(
                "Écart à la cible",
                signed_percent(real_weight - target),
            )

            tab_chart, tab_info = st.tabs(
                ["📈 Historique", "ℹ️ Toutes les informations"]
            )

            with tab_chart:
                if (
                    focus_ticker in price_matrix.columns
                    and not price_matrix[
                        focus_ticker
                    ].dropna().empty
                ):
                    close = (
                        price_matrix[focus_ticker]
                        .dropna()
                        .tail(365)
                        .rename("Cours")
                    )
                    chart = pd.DataFrame(
                        {
                            "Cours": close,
                            "MM50": close.rolling(50).mean(),
                            "MM200": close.rolling(200).mean(),
                        }
                    )
                    st.line_chart(
                        chart,
                        use_container_width=True,
                        height=330,
                    )
                else:
                    st.info(
                        "Historique indisponible pour cet actif."
                    )

            with tab_info:
                info_table = pd.DataFrame(
                    [
                        ("Nom", row["Actif"]),
                        ("Ticker Yahoo", row["Ticker"]),
                        ("ISIN", row["ISIN"]),
                        ("Type", row["Type"]),
                        ("Poche", row["Poche"]),
                        ("Secteur", row["Secteur"]),
                        ("PRU", euro(pru)),
                        ("Montant investi", euro(invested)),
                        ("Cours actuel", euro(price)),
                        ("Valeur actuelle", euro(current_value)),
                        ("Plus-value", signed_euro(gain)),
                        ("Plus-value %", signed_percent(gain_pct)),
                        (
                            "MM50",
                            euro(number(row.get("MM50 (€)"))),
                        ),
                        (
                            "MM200",
                            euro(number(row.get("MM200 (€)"))),
                        ),
                        (
                            "Distance MM200",
                            signed_percent(
                                number(
                                    row.get(
                                        "Distance MM200 (%)"
                                    )
                                )
                            ),
                        ),
                        (
                            "Momentum 3 mois",
                            signed_percent(
                                number(
                                    row.get("Momentum 3M (%)")
                                )
                            ),
                        ),
                        (
                            "Momentum 6 mois",
                            signed_percent(
                                number(
                                    row.get("Momentum 6M (%)")
                                )
                            ),
                        ),
                        (
                            "Momentum 12 mois",
                            signed_percent(
                                number(
                                    row.get("Momentum 12M (%)")
                                )
                            ),
                        ),
                        (
                            "Performance YTD",
                            signed_percent(
                                number(
                                    row.get(
                                        "Performance YTD (%)"
                                    )
                                )
                            ),
                        ),
                        (
                            "Score Alpha Zen",
                            f"{score:.0f}/100",
                        ),
                        ("Signal", row.get("Signal", "—")),
                        (
                            "Allocation cible",
                            f"{target:.2f} %",
                        ),
                        (
                            "Poids réel",
                            f"{real_weight:.2f} %",
                        ),
                    ],
                    columns=["Information", "Valeur"],
                )
                st.dataframe(
                    info_table,
                    hide_index=True,
                    use_container_width=True,
                )

        with right:
            st.subheader("💱 Passer un ordre virtuel")
            st.caption(
                "Le portefeuille et Supabase sont mis à jour "
                "après confirmation."
            )
            st.info(
                plan_summary(selected_plan)
            )

            with st.form(
                f"asset_trade_{focus_ticker}",
                clear_on_submit=False,
            ):
                action = st.radio(
                    "Opération",
                    ["Achat", "Vente"],
                    horizontal=True,
                )

                default_quantity = 1.0
                if (
                    action == "Vente"
                    and quantity_held > 0
                ):
                    default_quantity = quantity_held

                quantity = st.number_input(
                    "Quantité",
                    min_value=0.0,
                    value=float(default_quantity),
                    step=1.0,
                    format="%.4f",
                )

                execution_price = st.number_input(
                    "Prix d'exécution",
                    min_value=0.0,
                    value=float(price),
                    step=0.01,
                    format="%.4f",
                )

                gross = quantity * execution_price
                fee_quote = calculate_fortuneo_fee(
                    selected_plan,
                    gross,
                    st.session_state.get(
                        "virtual_transactions",
                        pd.DataFrame(),
                    ),
                )
                fees = float(fee_quote.fee)

                if action == "Achat":
                    estimated = gross + fees
                    available = cash
                    max_quantity = (
                        int(
                            max(
                                (available - fees)
                                // execution_price,
                                0,
                            )
                        )
                        if execution_price > 0
                        else 0
                    )
                    st.write(
                        f"**Coût estimé :** {euro(estimated)}"
                    )
                    st.write(
                        f"**Liquidités disponibles :** "
                        f"{euro(available)}"
                    )
                    st.write(
                        f"**Quantité maximale indicative :** "
                        f"{max_quantity}"
                    )
                else:
                    estimated = gross - fees
                    st.write(
                        f"**Produit net estimé :** "
                        f"{euro(estimated)}"
                    )
                    st.write(
                        f"**Quantité détenue :** "
                        f"{quantity_held:.4f}"
                    )
                    estimated_gain = (
                        quantity
                        * (execution_price - pru)
                        - fees
                    )
                    st.write(
                        f"**Plus-value réalisée estimée :** "
                        f"{signed_euro(estimated_gain)}"
                    )

                st.write(
                    f"**Frais estimés :** {euro(fees)}"
                )
                st.caption(fee_quote.explanation)

                confirm = st.checkbox(
                    "Je vérifie le cours, la quantité et les frais."
                )

                submitted = st.form_submit_button(
                    f"Confirmer la {action.lower()} virtuelle",
                    use_container_width=True,
                    type="primary",
                    disabled=not confirm,
                )

            if submitted:
                try:
                    transaction = execute_trade(
                        trade_type=action,
                        asset_name=str(row["Actif"]),
                        ticker=focus_ticker,
                        quantity=quantity,
                        price=execution_price,
                        fees=fees,
                        brokerage_plan=selected_plan,
                    )

                    updated_positions = (
                        st.session_state.virtual_positions.copy()
                    )
                    updated_positions_value = market_value(
                        updated_positions,
                        market_data,
                    )
                    updated_cash = float(
                        st.session_state.virtual_cash
                    )
                    invested_cost = float(
                        (
                            updated_positions["Quantité"]
                            * updated_positions["PRU (€)"]
                        ).sum()
                    )

                    snapshot = build_snapshot(
                        total_value=(
                            updated_positions_value
                            + updated_cash
                        ),
                        positions_value=(
                            updated_positions_value
                        ),
                        cash=updated_cash,
                        invested=invested_cost,
                        capital_reference=capital_reference,
                        unrealized_gain=(
                            updated_positions_value
                            - invested_cost
                        ),
                        transactions=st.session_state.get(
                            "virtual_transactions",
                            pd.DataFrame(),
                        ),
                    )
                    save_daily_snapshot(snapshot)

                    updated_frame, updated_summary = (
                        calculate_portfolio(
                            UNIVERSE,
                            market_data,
                            updated_positions,
                            capital_reference,
                        )
                    )
                    updated_summary["cash"] = updated_cash
                    updated_summary["total_value"] = (
                        updated_positions_value + updated_cash
                    )
                    updated_summary["positions_value"] = (
                        updated_positions_value
                    )
                    updated_summary["invested"] = invested_cost
                    updated_summary["gain"] = (
                        updated_positions_value
                        - invested_cost
                    )
                    updated_summary["performance"] = (
                        updated_summary["gain"]
                        / invested_cost
                        * 100.0
                        if invested_cost > 0
                        else 0.0
                    )
                    save_live_valuation(
                        updated_frame,
                        updated_summary,
                    )

                    if action == "Achat":
                        st.success(
                            f"Achat enregistré : "
                            f"{quantity:.4f} × "
                            f"{euro(execution_price)}."
                        )
                    else:
                        st.success(
                            f"Vente enregistrée. "
                            f"Plus-value réalisée : "
                            f"{signed_euro(transaction['Plus-value réalisée (€)'])}."
                        )
                    st.rerun()

                except ValueError as error:
                    st.error(str(error))
                except Exception as error:
                    st.error(
                        "L'ordre a rencontré une erreur : "
                        f"{error}"
                    )

        st.divider()
        st.subheader("Autres actifs du portefeuille")

pocket_order = ["Socle Zen", "Momentum", "Satellite"]
pocket_icons = {
    "Socle Zen": "🟢",
    "Momentum": "🔵",
    "Satellite": "🟠",
}

for pocket in pocket_order:
    pocket_frame = frame.loc[
        frame["Poche"] == pocket
    ].copy()

    if focus_ticker:
        pocket_frame = pocket_frame.loc[
            pocket_frame["Ticker"] != focus_ticker
        ]

    if pocket_frame.empty:
        continue

    st.markdown(
        f"""
<div class="pocket-heading">
    <span class="pocket-line"></span>
    <span>{pocket_icons.get(pocket, "•")} {escape(pocket)}</span>
</div>
""",
        unsafe_allow_html=True,
    )

    for _, row in pocket_frame.iterrows():
        ticker = str(row["Ticker"])
        display_ticker = ticker.replace(".PA", "")
        price = number(row.get("Cours (€)"))
        quantity = number(row.get("Quantité"))
        current_value = number(
            row.get("Valeur actuelle (€)")
        )
        gain = number(row.get("Plus-value (€)"))
        gain_pct = number(row.get("Plus-value (%)"))
        score = number(row.get("Score Alpha Zen"))
        target = number(
            row.get("Allocation cible (%)")
        )
        real_weight = number(
            row.get("Poids portefeuille (%)")
        )
        gain_class = (
            "positive"
            if gain > 0
            else "negative"
            if gain < 0
            else "neutral"
        )
        recommendation_title, _ = recommendation(row)

        with st.container(border=True):
            top_left, top_middle, top_button = st.columns(
                [3.2, 1.25, 1.05],
                vertical_alignment="center",
            )

            with top_left:
                st.markdown(
                    f"""
<div class="asset-header">
    <span class="asset-ticker">
        {escape(display_ticker)}
    </span>
    <span class="badge badge-type">
        {escape(str(row["Type"]))}
    </span>
    <span class="badge badge-sector">
        {escape(str(row["Secteur"]))}
    </span>
</div>
<div class="asset-name">
    {escape(str(row["Actif"]))}
</div>
<div class="asset-isin">
    {escape(str(row["ISIN"]))}
</div>
""",
                    unsafe_allow_html=True,
                )

            with top_middle:
                st.markdown(
                    f"""
<div class="metric-label">Cours</div>
<div class="metric-main">{escape(euro(price))}</div>
""",
                    unsafe_allow_html=True,
                )

            with top_button:
                if st.button(
                    "💱 Ordre",
                    key=f"open_asset_{ticker}",
                    use_container_width=True,
                    type="primary",
                ):
                    set_focus(ticker)
                    st.rerun()

            qty_col, gain_col, momentum_col, target_col = (
                st.columns([1, 1.15, 1.25, 1])
            )

            with qty_col:
                st.markdown(
                    f"""
<div class="metric-label">Qté / valeur</div>
<div class="metric-main">{quantity:.4f}</div>
<div class="metric-secondary">
    {escape(euro(current_value))}
</div>
""",
                    unsafe_allow_html=True,
                )

            with gain_col:
                st.markdown(
                    f"""
<div class="metric-label">+/- value</div>
<div class="metric-main {gain_class}">
    {escape(signed_euro(gain))}
</div>
<div class="metric-secondary {gain_class}">
    {escape(signed_percent(gain_pct))}
</div>
""",
                    unsafe_allow_html=True,
                )

            with momentum_col:
                st.markdown(
                    f"""
<div class="metric-label">Momentum</div>
<div class="metric-main">
    {score_icon(score)} {score:.0f}
</div>
<div class="metric-secondary">
    {escape(score_label(score))}
</div>
""",
                    unsafe_allow_html=True,
                )
                st.progress(
                    min(max(score / 100.0, 0.0), 1.0),
                    text=None,
                )

            with target_col:
                st.markdown(
                    f"""
<div class="metric-label">Cible / réel</div>
<div class="metric-main">{target:.1f} %</div>
<div class="metric-secondary">
    Réel {real_weight:.1f} %
</div>
""",
                    unsafe_allow_html=True,
                )

            st.caption(
                f"{recommendation_title} · "
                f"Signal : {row.get('Signal', '—')}"
            )

st.caption(
    "Cette page simule les opérations et sauvegarde le portefeuille "
    "dans Supabase. Aucun ordre réel n'est transmis à Fortuneo."
)
