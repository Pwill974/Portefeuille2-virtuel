from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st

from services.supabase_service import (
    SupabaseSyncError,
    get_profile_id,
    get_supabase_client,
    supabase_is_configured,
)


SNAPSHOT_COLUMNS = [
    "Date",
    "Valeur totale (€)",
    "Valeur positions (€)",
    "Liquidités (€)",
    "Investi (€)",
    "Capital de référence (€)",
    "Plus-value latente (€)",
    "Plus-value réalisée (€)",
    "Frais cumulés (€)",
    "Performance nette (%)",
]


def cumulative_fees(
    transactions: pd.DataFrame | None,
) -> float:
    if transactions is None or transactions.empty:
        return 0.0

    return float(
        pd.to_numeric(
            transactions.get("Frais (€)"),
            errors="coerce",
        ).fillna(0.0).sum()
    )


def realized_gain(
    transactions: pd.DataFrame | None,
) -> float:
    if transactions is None or transactions.empty:
        return 0.0

    return float(
        pd.to_numeric(
            transactions.get("Plus-value réalisée (€)"),
            errors="coerce",
        ).fillna(0.0).sum()
    )


def _local_snapshot_frame() -> pd.DataFrame:
    frame = st.session_state.get(
        "az_local_snapshots",
        pd.DataFrame(columns=SNAPSHOT_COLUMNS),
    )
    return frame.copy()


def build_snapshot(
    *,
    total_value: float,
    positions_value: float,
    cash: float,
    invested: float,
    capital_reference: float,
    unrealized_gain: float,
    transactions: pd.DataFrame | None,
) -> dict[str, Any]:
    capital = float(capital_reference)
    net_performance = (
        (float(total_value) / capital - 1.0) * 100.0
        if capital > 0
        else 0.0
    )

    return {
        "Date": date.today().isoformat(),
        "Valeur totale (€)": float(total_value),
        "Valeur positions (€)": float(positions_value),
        "Liquidités (€)": float(cash),
        "Investi (€)": float(invested),
        "Capital de référence (€)": capital,
        "Plus-value latente (€)": float(unrealized_gain),
        "Plus-value réalisée (€)": realized_gain(transactions),
        "Frais cumulés (€)": cumulative_fees(transactions),
        "Performance nette (%)": net_performance,
    }


def save_daily_snapshot(snapshot: dict[str, Any]) -> None:
    local = _local_snapshot_frame()
    row = pd.DataFrame([snapshot], columns=SNAPSHOT_COLUMNS)

    if not local.empty:
        local = local[
            local["Date"].astype(str) != str(snapshot["Date"])
        ]

    st.session_state.az_local_snapshots = pd.concat(
        [local, row],
        ignore_index=True,
    ).sort_values("Date")

    if not supabase_is_configured():
        return

    client = get_supabase_client()
    profile_id = get_profile_id()
    record = {
        "profile_id": profile_id,
        "snapshot_date": str(snapshot["Date"]),
        "total_value": float(snapshot["Valeur totale (€)"]),
        "positions_value": float(
            snapshot["Valeur positions (€)"]
        ),
        "cash": float(snapshot["Liquidités (€)"]),
        "invested": float(snapshot["Investi (€)"]),
        "capital_reference": float(
            snapshot["Capital de référence (€)"]
        ),
        "unrealized_gain": float(
            snapshot["Plus-value latente (€)"]
        ),
        "realized_gain": float(
            snapshot["Plus-value réalisée (€)"]
        ),
        "cumulative_fees": float(
            snapshot["Frais cumulés (€)"]
        ),
        "net_performance": float(
            snapshot["Performance nette (%)"]
        ),
        "updated_at": datetime.now(
            timezone.utc
        ).isoformat(),
    }

    try:
        (
            client.table("az_snapshots")
            .upsert(
                record,
                on_conflict="profile_id,snapshot_date",
            )
            .execute()
        )
    except Exception as exc:
        raise SupabaseSyncError(
            "Impossible d'enregistrer l'historique de performance. "
            "Vérifie que la migration SQL a été exécutée."
        ) from exc


def fetch_performance_history() -> pd.DataFrame:
    if not supabase_is_configured():
        return _local_snapshot_frame()

    client = get_supabase_client()
    profile_id = get_profile_id()

    try:
        response = (
            client.table("az_snapshots")
            .select("*")
            .eq("profile_id", profile_id)
            .order("snapshot_date")
            .execute()
        )
    except Exception:
        return _local_snapshot_frame()

    rows = getattr(response, "data", None) or []
    if not rows:
        return _local_snapshot_frame()

    mapped = [
        {
            "Date": row.get("snapshot_date"),
            "Valeur totale (€)": float(
                row.get("total_value", 0) or 0
            ),
            "Valeur positions (€)": float(
                row.get("positions_value", 0) or 0
            ),
            "Liquidités (€)": float(
                row.get("cash", 0) or 0
            ),
            "Investi (€)": float(
                row.get("invested", 0) or 0
            ),
            "Capital de référence (€)": float(
                row.get("capital_reference", 0) or 0
            ),
            "Plus-value latente (€)": float(
                row.get("unrealized_gain", 0) or 0
            ),
            "Plus-value réalisée (€)": float(
                row.get("realized_gain", 0) or 0
            ),
            "Frais cumulés (€)": float(
                row.get("cumulative_fees", 0) or 0
            ),
            "Performance nette (%)": float(
                row.get("net_performance", 0) or 0
            ),
        }
        for row in rows
    ]

    history = pd.DataFrame(
        mapped,
        columns=SNAPSHOT_COLUMNS,
    )
    history["Date"] = pd.to_datetime(
        history["Date"],
        errors="coerce",
    )
    return history.sort_values("Date")


def save_brokerage_plan(plan: str) -> None:
    st.session_state["brokerage_plan"] = plan

    if not supabase_is_configured():
        return

    client = get_supabase_client()
    profile_id = get_profile_id()

    try:
        (
            client.table("az_settings")
            .upsert(
                {
                    "profile_id": profile_id,
                    "brokerage_plan": plan,
                    "updated_at": datetime.now(
                        timezone.utc
                    ).isoformat(),
                },
                on_conflict="profile_id",
            )
            .execute()
        )
    except Exception as exc:
        raise SupabaseSyncError(
            "Impossible d'enregistrer le tarif Fortuneo."
        ) from exc


def load_brokerage_plan(default: str = "Starter") -> str:
    if "brokerage_plan" in st.session_state:
        return str(st.session_state["brokerage_plan"])

    if not supabase_is_configured():
        st.session_state["brokerage_plan"] = default
        return default

    client = get_supabase_client()
    profile_id = get_profile_id()

    try:
        response = (
            client.table("az_settings")
            .select("brokerage_plan")
            .eq("profile_id", profile_id)
            .limit(1)
            .execute()
        )
        rows = getattr(response, "data", None) or []
        plan = (
            str(rows[0].get("brokerage_plan", default))
            if rows
            else default
        )
    except Exception:
        plan = default

    st.session_state["brokerage_plan"] = plan
    return plan


def performance_statistics(
    history: pd.DataFrame,
) -> dict[str, float]:
    if history is None or history.empty:
        return {
            "return": 0.0,
            "max_drawdown": 0.0,
            "volatility": 0.0,
            "fees": 0.0,
        }

    ordered = history.sort_values("Date").copy()
    values = pd.to_numeric(
        ordered["Valeur totale (€)"],
        errors="coerce",
    ).dropna()

    returns = values.pct_change().dropna()
    running_max = values.cummax()
    drawdown = (
        values / running_max - 1.0
        if not values.empty
        else pd.Series(dtype=float)
    )

    total_return = (
        (values.iloc[-1] / values.iloc[0] - 1.0) * 100.0
        if len(values) >= 2 and values.iloc[0] != 0
        else 0.0
    )
    volatility = (
        float(returns.std() * np.sqrt(252) * 100.0)
        if len(returns) >= 2
        else 0.0
    )
    max_drawdown = (
        float(drawdown.min() * 100.0)
        if not drawdown.empty
        else 0.0
    )
    fees = float(
        pd.to_numeric(
            ordered["Frais cumulés (€)"],
            errors="coerce",
        ).fillna(0.0).iloc[-1]
    )

    return {
        "return": total_return,
        "max_drawdown": max_drawdown,
        "volatility": volatility,
        "fees": fees,
    }
