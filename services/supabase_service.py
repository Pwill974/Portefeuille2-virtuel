from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import pandas as pd
import streamlit as st
from supabase import Client, create_client


LOCAL_TRANSACTION_COLUMNS = [
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


class SupabaseConfigurationError(RuntimeError):
    """Les paramètres Supabase sont absents des Secrets Streamlit."""


class SupabaseSyncError(RuntimeError):
    """La lecture ou l'écriture dans Supabase a échoué."""


def supabase_is_configured() -> bool:
    try:
        section = st.secrets["supabase"]
        url = str(section.get("url", "")).strip()
        key = str(
            section.get(
                "secret_key",
                section.get("service_role_key", section.get("key", "")),
            )
        ).strip()
        return bool(url and key)
    except (KeyError, FileNotFoundError, TypeError):
        return False


def get_profile_id() -> str:
    try:
        profile_id = str(
            st.secrets["supabase"].get("profile_id", "alpha_zen_main")
        ).strip()
    except (KeyError, FileNotFoundError, TypeError):
        profile_id = "alpha_zen_main"

    return profile_id or "alpha_zen_main"


@st.cache_resource(show_spinner=False)
def get_supabase_client() -> Client:
    if not supabase_is_configured():
        raise SupabaseConfigurationError(
            "Supabase n'est pas configuré dans les Secrets Streamlit."
        )

    section = st.secrets["supabase"]
    url = str(section["url"]).strip()
    key = str(
        section.get(
            "secret_key",
            section.get("service_role_key", section.get("key", "")),
        )
    ).strip()

    return create_client(url, key)


def _response_data(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    return data if isinstance(data, list) else []


def _clean_positions(positions: pd.DataFrame) -> pd.DataFrame:
    columns = ["Ticker", "Quantité", "PRU (€)"]

    if positions is None or positions.empty:
        return pd.DataFrame(columns=columns)

    result = positions.copy()

    for column in columns:
        if column not in result.columns:
            result[column] = "" if column == "Ticker" else 0.0

    result["Ticker"] = (
        result["Ticker"]
        .astype(str)
        .str.strip()
        .replace({"STM.PA": "STMPA.PA"})
    )
    result["Quantité"] = pd.to_numeric(
        result["Quantité"], errors="coerce"
    ).fillna(0.0)
    result["PRU (€)"] = pd.to_numeric(
        result["PRU (€)"], errors="coerce"
    ).fillna(0.0)

    return result[columns].drop_duplicates("Ticker", keep="last")


def _cloud_transactions_to_dataframe(
    rows: list[dict[str, Any]],
) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=LOCAL_TRANSACTION_COLUMNS)

    mapped = []

    for row in rows:
        executed_at = pd.to_datetime(
            row.get("executed_at"),
            errors="coerce",
            utc=True,
        )
        date_text = (
            executed_at.strftime("%Y-%m-%d %H:%M:%S UTC")
            if pd.notna(executed_at)
            else str(row.get("executed_at", ""))
        )

        mapped.append(
            {
                "Date": date_text,
                "Type": row.get("trade_type", ""),
                "Actif": row.get("asset_name", ""),
                "Ticker": row.get("ticker", ""),
                "Quantité": float(row.get("quantity", 0) or 0),
                "Prix (€)": float(row.get("price", 0) or 0),
                "Frais (€)": float(row.get("fees", 0) or 0),
                "Montant brut (€)": float(
                    row.get("gross_amount", 0) or 0
                ),
                "Montant net (€)": float(
                    row.get("net_amount", 0) or 0
                ),
                "Plus-value réalisée (€)": float(
                    row.get("realized_gain", 0) or 0
                ),
                "Liquidités après (€)": float(
                    row.get("cash_after", 0) or 0
                ),
            }
        )

    return pd.DataFrame(mapped, columns=LOCAL_TRANSACTION_COLUMNS)


def test_supabase_connection() -> dict[str, Any]:
    client = get_supabase_client()
    profile_id = get_profile_id()

    try:
        response = (
            client.table("az_settings")
            .select("profile_id")
            .eq("profile_id", profile_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise SupabaseSyncError(
            "Connexion impossible. Vérifie l'URL, la clé secrète "
            "et l'exécution du fichier SQL."
        ) from exc

    return {
        "connected": True,
        "profile_id": profile_id,
        "settings_rows": len(_response_data(response)),
    }


def fetch_cloud_state() -> dict[str, Any]:
    client = get_supabase_client()
    profile_id = get_profile_id()

    try:
        settings_response = (
            client.table("az_settings")
            .select("*")
            .eq("profile_id", profile_id)
            .limit(1)
            .execute()
        )
        positions_response = (
            client.table("az_positions")
            .select("ticker,quantity,pru,updated_at")
            .eq("profile_id", profile_id)
            .order("ticker")
            .execute()
        )
        transactions_response = (
            client.table("az_transactions")
            .select("*")
            .eq("profile_id", profile_id)
            .order("executed_at", desc=True)
            .limit(1000)
            .execute()
        )
    except Exception as exc:
        raise SupabaseSyncError(
            "Impossible de lire les données Supabase."
        ) from exc

    settings_rows = _response_data(settings_response)
    position_rows = _response_data(positions_response)
    transaction_rows = _response_data(transactions_response)

    positions = pd.DataFrame(
        [
            {
                "Ticker": row.get("ticker", ""),
                "Quantité": float(row.get("quantity", 0) or 0),
                "PRU (€)": float(row.get("pru", 0) or 0),
            }
            for row in position_rows
        ],
        columns=["Ticker", "Quantité", "PRU (€)"],
    )

    settings = settings_rows[0] if settings_rows else {}

    return {
        "settings": settings,
        "positions": _clean_positions(positions),
        "transactions": _cloud_transactions_to_dataframe(
            transaction_rows
        ),
        "has_data": bool(settings_rows or position_rows or transaction_rows),
    }


def load_cloud_state_into_session(force: bool = False) -> bool:
    """
    Charge Supabase dans st.session_state.
    Retourne True lorsqu'une sauvegarde existante a été trouvée.
    """
    if not supabase_is_configured():
        st.session_state["az_cloud_configured"] = False
        return False

    if (
        st.session_state.get("az_cloud_checked", False)
        and not force
    ):
        return bool(st.session_state.get("az_cloud_has_data", False))

    try:
        state = fetch_cloud_state()
    except (SupabaseConfigurationError, SupabaseSyncError) as exc:
        st.session_state["az_cloud_configured"] = True
        st.session_state["az_cloud_error"] = str(exc)
        st.session_state["az_cloud_checked"] = True
        return False

    settings = state["settings"]
    positions = state["positions"]
    transactions = state["transactions"]

    if not positions.empty:
        st.session_state.virtual_positions = positions.copy()

    if settings:
        st.session_state.virtual_cash = float(
            settings.get("cash", 0) or 0
        )
        st.session_state.cloud_capital_reference = float(
            settings.get("capital_reference", 10000) or 10000
        )
        st.session_state.cloud_monthly_contribution = float(
            settings.get("monthly_contribution", 1000) or 1000
        )

    if not transactions.empty:
        st.session_state.virtual_transactions = transactions.copy()
    elif state["has_data"]:
        st.session_state.virtual_transactions = pd.DataFrame(
            columns=LOCAL_TRANSACTION_COLUMNS
        )

    st.session_state["az_cloud_configured"] = True
    st.session_state["az_cloud_checked"] = True
    st.session_state["az_cloud_has_data"] = bool(state["has_data"])
    st.session_state["az_cloud_last_load"] = datetime.now(
        timezone.utc
    ).isoformat()
    st.session_state.pop("az_cloud_error", None)

    return bool(state["has_data"])


def save_portfolio_state(
    positions: pd.DataFrame,
    cash: float,
    capital_reference: float,
    monthly_contribution: float = 1000.0,
) -> None:
    client = get_supabase_client()
    profile_id = get_profile_id()
    now = datetime.now(timezone.utc).isoformat()
    positions = _clean_positions(positions)

    settings_record = {
        "profile_id": profile_id,
        "capital_reference": float(capital_reference),
        "monthly_contribution": float(monthly_contribution),
        "cash": float(cash),
        "updated_at": now,
    }

    position_records = [
        {
            "profile_id": profile_id,
            "ticker": str(row["Ticker"]),
            "quantity": float(row["Quantité"]),
            "pru": float(row["PRU (€)"]),
            "updated_at": now,
        }
        for _, row in positions.iterrows()
    ]

    try:
        (
            client.table("az_settings")
            .upsert(
                settings_record,
                on_conflict="profile_id",
            )
            .execute()
        )

        if position_records:
            (
                client.table("az_positions")
                .upsert(
                    position_records,
                    on_conflict="profile_id,ticker",
                )
                .execute()
            )
    except Exception as exc:
        raise SupabaseSyncError(
            "Impossible de sauvegarder les positions ou les liquidités."
        ) from exc

    st.session_state["az_cloud_has_data"] = True
    st.session_state["az_cloud_last_sync"] = now
    st.session_state.pop("az_cloud_error", None)


def save_transaction(transaction: dict[str, Any]) -> str:
    client = get_supabase_client()
    profile_id = get_profile_id()
    transaction_id = str(
        transaction.get("Transaction ID") or uuid4()
    )

    executed_at = transaction.get("Date")
    if not executed_at:
        executed_at = datetime.now(timezone.utc).isoformat()

    record = {
        "transaction_id": transaction_id,
        "profile_id": profile_id,
        "executed_at": str(executed_at),
        "trade_type": str(transaction.get("Type", "")),
        "asset_name": str(transaction.get("Actif", "")),
        "ticker": str(transaction.get("Ticker", "")),
        "quantity": float(transaction.get("Quantité", 0) or 0),
        "price": float(transaction.get("Prix (€)", 0) or 0),
        "fees": float(transaction.get("Frais (€)", 0) or 0),
        "gross_amount": float(
            transaction.get("Montant brut (€)", 0) or 0
        ),
        "net_amount": float(
            transaction.get("Montant net (€)", 0) or 0
        ),
        "realized_gain": float(
            transaction.get("Plus-value réalisée (€)", 0) or 0
        ),
        "cash_after": float(
            transaction.get("Liquidités après (€)", 0) or 0
        ),
    }

    try:
        (
            client.table("az_transactions")
            .upsert(
                record,
                on_conflict="transaction_id",
            )
            .execute()
        )
    except Exception as exc:
        raise SupabaseSyncError(
            "La transaction n'a pas pu être sauvegardée dans Supabase."
        ) from exc

    st.session_state["az_cloud_last_sync"] = datetime.now(
        timezone.utc
    ).isoformat()
    return transaction_id


def delete_cloud_transactions() -> None:
    client = get_supabase_client()
    profile_id = get_profile_id()

    try:
        (
            client.table("az_transactions")
            .delete()
            .eq("profile_id", profile_id)
            .execute()
        )
    except Exception as exc:
        raise SupabaseSyncError(
            "Impossible de supprimer l'historique Supabase."
        ) from exc


def cloud_status() -> dict[str, Any]:
    return {
        "configured": supabase_is_configured(),
        "checked": bool(
            st.session_state.get("az_cloud_checked", False)
        ),
        "has_data": bool(
            st.session_state.get("az_cloud_has_data", False)
        ),
        "last_load": st.session_state.get("az_cloud_last_load"),
        "last_sync": st.session_state.get("az_cloud_last_sync"),
        "error": st.session_state.get("az_cloud_error"),
        "profile_id": get_profile_id(),
    }
