from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
import streamlit as st

from services.portfolio_engine import build_default_positions


TRANSACTION_COLUMNS = [
    "Date",
    "Type",
    "Actif",
    "Ticker",
    "Quantité",
    "Prix (€)",
    "Frais (€)",
    "Montant brut (€)",
    "Montant net (€)",
    "Plus-value réalisée (€)",
    "Liquidités après (€)",
]


def _empty_transactions() -> pd.DataFrame:
    return pd.DataFrame(columns=TRANSACTION_COLUMNS)


def _clean_positions(positions: pd.DataFrame) -> pd.DataFrame:
    columns = ["Ticker", "Quantité", "PRU (€)"]

    if positions is None or positions.empty:
        return pd.DataFrame(columns=columns)

    result = positions.copy()

    for column in columns:
        if column not in result.columns:
            result[column] = "" if column == "Ticker" else 0.0

    result["Ticker"] = result["Ticker"].astype(str).replace(
        {"STM.PA": "STMPA.PA"}
    )
    result["Quantité"] = pd.to_numeric(
        result["Quantité"], errors="coerce"
    ).fillna(0.0)
    result["PRU (€)"] = pd.to_numeric(
        result["PRU (€)"], errors="coerce"
    ).fillna(0.0)

    return result[columns].drop_duplicates("Ticker", keep="last")


def initialize_trading_state(
    universe: pd.DataFrame,
    market_data: pd.DataFrame,
    capital_reference: float,
) -> None:
    """Initialise positions, liquidités et historique dans Session State."""
    if (
        "virtual_positions" not in st.session_state
        or st.session_state.virtual_positions is None
        or st.session_state.virtual_positions.empty
    ):
        st.session_state.virtual_positions = build_default_positions(
            universe,
            market_data,
            capital_reference,
        )

    st.session_state.virtual_positions = _clean_positions(
        st.session_state.virtual_positions
    )

    if "virtual_cash" not in st.session_state:
        invested_at_cost = float(
            (
                st.session_state.virtual_positions["Quantité"]
                * st.session_state.virtual_positions["PRU (€)"]
            ).sum()
        )
        st.session_state.virtual_cash = max(
            float(capital_reference) - invested_at_cost,
            0.0,
        )

    if "virtual_transactions" not in st.session_state:
        st.session_state.virtual_transactions = _empty_transactions()


def reset_trading_state(
    universe: pd.DataFrame,
    market_data: pd.DataFrame,
    capital_reference: float,
) -> None:
    positions = build_default_positions(
        universe,
        market_data,
        capital_reference,
    )
    invested_at_cost = float(
        (positions["Quantité"] * positions["PRU (€)"]).sum()
    )

    st.session_state.virtual_positions = _clean_positions(positions)
    st.session_state.virtual_cash = max(
        float(capital_reference) - invested_at_cost,
        0.0,
    )
    st.session_state.virtual_transactions = _empty_transactions()


def market_value(
    positions: pd.DataFrame,
    market_data: pd.DataFrame,
) -> float:
    positions = _clean_positions(positions)
    prices = market_data[["Ticker", "Cours (€)"]].copy()
    prices["Cours (€)"] = pd.to_numeric(
        prices["Cours (€)"], errors="coerce"
    ).fillna(0.0)

    merged = positions.merge(prices, on="Ticker", how="left")
    return float((merged["Quantité"] * merged["Cours (€)"]).sum())


def current_position(
    ticker: str,
) -> dict[str, float]:
    positions = _clean_positions(st.session_state.virtual_positions)
    match = positions.loc[positions["Ticker"] == ticker]

    if match.empty:
        return {"Quantité": 0.0, "PRU (€)": 0.0}

    return {
        "Quantité": float(match.iloc[0]["Quantité"]),
        "PRU (€)": float(match.iloc[0]["PRU (€)"]),
    }


def execute_trade(
    *,
    trade_type: str,
    asset_name: str,
    ticker: str,
    quantity: float,
    price: float,
    fees: float = 0.0,
) -> dict[str, Any]:
    """Exécute un achat ou une vente virtuelle."""
    action = trade_type.strip().upper()
    quantity = float(quantity)
    price = float(price)
    fees = float(fees)

    if action not in {"ACHAT", "VENTE"}:
        raise ValueError("Le type doit être ACHAT ou VENTE.")
    if quantity <= 0:
        raise ValueError("La quantité doit être supérieure à zéro.")
    if price <= 0:
        raise ValueError("Le prix doit être supérieur à zéro.")
    if fees < 0:
        raise ValueError("Les frais ne peuvent pas être négatifs.")

    positions = _clean_positions(st.session_state.virtual_positions)
    cash = float(st.session_state.get("virtual_cash", 0.0))

    row_index = positions.index[positions["Ticker"] == ticker].tolist()

    if row_index:
        index = row_index[0]
        old_quantity = float(positions.at[index, "Quantité"])
        old_pru = float(positions.at[index, "PRU (€)"])
    else:
        index = len(positions)
        old_quantity = 0.0
        old_pru = 0.0
        positions.loc[index, ["Ticker", "Quantité", "PRU (€)"]] = [
            ticker,
            0.0,
            0.0,
        ]

    gross_amount = quantity * price
    realized_gain = 0.0

    if action == "ACHAT":
        total_cost = gross_amount + fees

        if total_cost > cash + 1e-9:
            raise ValueError(
                "Liquidités insuffisantes pour cet achat. "
                f"Besoin : {total_cost:.2f} €, disponibles : {cash:.2f} €."
            )

        new_quantity = old_quantity + quantity
        new_pru = (
            (old_quantity * old_pru + gross_amount + fees)
            / new_quantity
        )

        positions.at[index, "Quantité"] = new_quantity
        positions.at[index, "PRU (€)"] = new_pru
        cash -= total_cost
        net_amount = -total_cost

    else:
        if quantity > old_quantity + 1e-9:
            raise ValueError(
                "Quantité insuffisante pour cette vente. "
                f"Détenu : {old_quantity:.4f}."
            )

        proceeds = gross_amount - fees

        if proceeds < 0:
            raise ValueError("Les frais dépassent le montant de la vente.")

        new_quantity = old_quantity - quantity
        realized_gain = quantity * (price - old_pru) - fees

        positions.at[index, "Quantité"] = max(new_quantity, 0.0)
        positions.at[index, "PRU (€)"] = (
            old_pru if new_quantity > 1e-9 else 0.0
        )
        cash += proceeds
        net_amount = proceeds

    positions["Quantité"] = pd.to_numeric(
        positions["Quantité"], errors="coerce"
    ).fillna(0.0)
    positions["PRU (€)"] = pd.to_numeric(
        positions["PRU (€)"], errors="coerce"
    ).fillna(0.0)

    transaction = {
        "Date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Type": "Achat" if action == "ACHAT" else "Vente",
        "Actif": asset_name,
        "Ticker": ticker,
        "Quantité": quantity,
        "Prix (€)": price,
        "Frais (€)": fees,
        "Montant brut (€)": gross_amount,
        "Montant net (€)": net_amount,
        "Plus-value réalisée (€)": realized_gain,
        "Liquidités après (€)": cash,
    }

    history = st.session_state.get(
        "virtual_transactions",
        _empty_transactions(),
    )
    history = pd.concat(
        [pd.DataFrame([transaction]), history],
        ignore_index=True,
    )

    st.session_state.virtual_positions = positions[
        ["Ticker", "Quantité", "PRU (€)"]
    ].copy()
    st.session_state.virtual_cash = cash
    st.session_state.virtual_transactions = history[
        TRANSACTION_COLUMNS
    ].copy()

    return transaction
