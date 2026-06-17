from __future__ import annotations

import pandas as pd
import streamlit as st

from services.auth import require_authentication, show_logout_button
from services.portfolio_engine import UNIVERSE, fetch_market_bundle
from services.trading_service import (
    current_position,
    execute_trade,
    initialize_trading_state,
    market_value,
    reset_trading_state,
)


st.set_page_config(
    page_title="Alpha Zen Pro — Acheter / Vendre",
    page_icon="💱",
    layout="wide",
)

require_authentication()
show_logout_button()


@st.cache_data(ttl=900, show_spinner=False)
def load_market_data(tickers: tuple[str, ...]):
    market, _ = fetch_market_bundle(list(tickers))
    return market


def euro(value: float) -> str:
    return (
        f"{float(value):,.2f} €"
        .replace(",", " ")
        .replace(".", ",")
    )


st.title("💱 Acheter ou vendre")
st.caption(
    "Simulation d’ordres sur le portefeuille virtuel. "
    "Aucun ordre réel n’est envoyé à Fortuneo."
)

capital_reference = st.number_input(
    "Capital virtuel de référence",
    min_value=0.0,
    value=10_000.0,
    step=500.0,
    format="%.2f",
    key="trading_capital_reference",
)

with st.spinner("Chargement des cours…"):
    market_data = load_market_data(
        tuple(UNIVERSE["Ticker"].tolist())
    )

initialize_trading_state(
    UNIVERSE,
    market_data,
    capital_reference,
)

positions = st.session_state.virtual_positions.copy()
cash = float(st.session_state.virtual_cash)
positions_value = market_value(positions, market_data)
total_value = cash + positions_value

k1, k2, k3 = st.columns(3)
k1.metric("Liquidités", euro(cash))
k2.metric("Valeur des positions", euro(positions_value))
k3.metric("Valeur totale", euro(total_value))

st.divider()

asset_options = UNIVERSE["Actif"].tolist()
selected_asset = st.selectbox(
    "Actif",
    asset_options,
)

asset_row = UNIVERSE.loc[
    UNIVERSE["Actif"] == selected_asset
].iloc[0]
ticker = str(asset_row["Ticker"])

market_row = market_data.loc[
    market_data["Ticker"] == ticker
]
current_price = (
    float(market_row.iloc[0]["Cours (€)"])
    if not market_row.empty
    and pd.notna(market_row.iloc[0]["Cours (€)"])
    else 0.0
)

holding = current_position(ticker)

info1, info2, info3 = st.columns(3)
info1.metric("Cours automatique", euro(current_price))
info2.metric("Quantité détenue", f"{holding['Quantité']:.4f}")
info3.metric("PRU actuel", euro(holding["PRU (€)"]))

with st.form("virtual_trade_form", clear_on_submit=False):
    action = st.radio(
        "Opération",
        ["Achat", "Vente"],
        horizontal=True,
    )

    quantity = st.number_input(
        "Quantité",
        min_value=0.0,
        value=1.0,
        step=1.0,
        format="%.4f",
    )

    execution_price = st.number_input(
        "Prix d’exécution simulé",
        min_value=0.0,
        value=float(current_price),
        step=0.01,
        format="%.4f",
    )

    fees = st.number_input(
        "Frais estimés",
        min_value=0.0,
        value=0.0,
        step=0.10,
        format="%.2f",
    )

    gross = quantity * execution_price
    estimated = (
        gross + fees
        if action == "Achat"
        else gross - fees
    )

    st.info(
        f"Montant estimé : {euro(estimated)}"
    )

    submitted = st.form_submit_button(
        f"Confirmer la {action.lower()} virtuelle",
        use_container_width=True,
        type="primary",
    )

if submitted:
    try:
        transaction = execute_trade(
            trade_type=action,
            asset_name=selected_asset,
            ticker=ticker,
            quantity=quantity,
            price=execution_price,
            fees=fees,
        )

        if action == "Achat":
            st.success(
                f"Achat enregistré : {quantity:.4f} × "
                f"{euro(execution_price)}."
            )
        else:
            st.success(
                f"Vente enregistrée : {quantity:.4f} × "
                f"{euro(execution_price)}. "
                f"Plus-value réalisée : "
                f"{euro(transaction['Plus-value réalisée (€)'])}."
            )

        st.rerun()

    except ValueError as error:
        st.error(str(error))

st.divider()
st.subheader("Positions après opérations")

positions_table = (
    UNIVERSE[
        [
            "Actif",
            "Ticker",
            "Poche",
            "Allocation cible (%)",
        ]
    ]
    .merge(
        st.session_state.virtual_positions,
        on="Ticker",
        how="left",
    )
    .merge(
        market_data[["Ticker", "Cours (€)"]],
        on="Ticker",
        how="left",
    )
)

positions_table["Quantité"] = pd.to_numeric(
    positions_table["Quantité"], errors="coerce"
).fillna(0.0)
positions_table["PRU (€)"] = pd.to_numeric(
    positions_table["PRU (€)"], errors="coerce"
).fillna(0.0)
positions_table["Cours (€)"] = pd.to_numeric(
    positions_table["Cours (€)"], errors="coerce"
).fillna(0.0)
positions_table["Valeur (€)"] = (
    positions_table["Quantité"]
    * positions_table["Cours (€)"]
)
positions_table["Plus-value (€)"] = (
    positions_table["Quantité"]
    * (positions_table["Cours (€)"] - positions_table["PRU (€)"])
)

st.dataframe(
    positions_table[
        [
            "Actif",
            "Ticker",
            "Poche",
            "Quantité",
            "PRU (€)",
            "Cours (€)",
            "Valeur (€)",
            "Plus-value (€)",
        ]
    ],
    hide_index=True,
    use_container_width=True,
    column_config={
        "Quantité": st.column_config.NumberColumn(
            "Quantité",
            format="%.4f",
        ),
        "PRU (€)": st.column_config.NumberColumn(
            "PRU",
            format="%.2f €",
        ),
        "Cours (€)": st.column_config.NumberColumn(
            "Cours",
            format="%.2f €",
        ),
        "Valeur (€)": st.column_config.NumberColumn(
            "Valeur",
            format="%.2f €",
        ),
        "Plus-value (€)": st.column_config.NumberColumn(
            "Plus-value",
            format="%+.2f €",
        ),
    },
)

st.divider()
st.subheader("Historique des transactions virtuelles")

history = st.session_state.virtual_transactions.copy()

if history.empty:
    st.info("Aucune transaction virtuelle enregistrée.")
else:
    st.dataframe(
        history,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Quantité": st.column_config.NumberColumn(
                "Quantité",
                format="%.4f",
            ),
            "Prix (€)": st.column_config.NumberColumn(
                "Prix",
                format="%.2f €",
            ),
            "Frais (€)": st.column_config.NumberColumn(
                "Frais",
                format="%.2f €",
            ),
            "Montant brut (€)": st.column_config.NumberColumn(
                "Montant brut",
                format="%.2f €",
            ),
            "Montant net (€)": st.column_config.NumberColumn(
                "Montant net",
                format="%+.2f €",
            ),
            "Plus-value réalisée (€)": st.column_config.NumberColumn(
                "Plus-value réalisée",
                format="%+.2f €",
            ),
            "Liquidités après (€)": st.column_config.NumberColumn(
                "Liquidités après",
                format="%.2f €",
            ),
        },
    )

    st.download_button(
        "⬇️ Télécharger l’historique CSV",
        data=history.to_csv(
            index=False,
            sep=";",
        ).encode("utf-8-sig"),
        file_name="transactions_virtuelles_alpha_zen.csv",
        mime="text/csv",
    )

st.download_button(
    "⬇️ Sauvegarder les positions CSV",
    data=st.session_state.virtual_positions.to_csv(
        index=False,
        sep=";",
    ).encode("utf-8-sig"),
    file_name="positions_virtuelles_alpha_zen.csv",
    mime="text/csv",
)

st.divider()

confirm_reset = st.checkbox(
    "Je confirme vouloir réinitialiser le portefeuille virtuel."
)

if st.button(
    "♻️ Réinitialiser le portefeuille",
    disabled=not confirm_reset,
):
    reset_trading_state(
        UNIVERSE,
        market_data,
        capital_reference,
    )
    st.success("Portefeuille virtuel réinitialisé.")
    st.rerun()

st.caption(
    "Les achats et ventes sont uniquement simulés. "
    "Les données restent en mémoire pendant la session Streamlit ; "
    "utilise les exports CSV pour les sauvegarder."
)
