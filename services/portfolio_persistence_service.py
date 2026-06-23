from __future__ import annotations

from datetime import datetime, timezone
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


MARKET_COLUMN_MAP = {
    "price": "Cours (€)",
    "quote_date": "Date du cours",
    "mm50": "MM50 (€)",
    "mm200": "MM200 (€)",
    "distance_mm200": "Distance MM200 (%)",
    "momentum_3m": "Momentum 3M (%)",
    "momentum_6m": "Momentum 6M (%)",
    "momentum_12m": "Momentum 12M (%)",
    "performance_ytd": "Performance YTD (%)",
    "volatility_1y": "Volatilité 1A (%)",
    "alpha_zen_score": "Score Alpha Zen",
    "signal": "Signal",
}


def _number(value: Any, default: float = 0.0) -> float:
    parsed = pd.to_numeric(
        pd.Series([value]),
        errors="coerce",
    ).iloc[0]
    return float(parsed) if pd.notna(parsed) else float(default)


def _nullable_number(value: Any) -> float | None:
    parsed = pd.to_numeric(
        pd.Series([value]),
        errors="coerce",
    ).iloc[0]
    return float(parsed) if pd.notna(parsed) else None


def _date_text(value: Any) -> str | None:
    parsed = pd.to_datetime(
        value,
        errors="coerce",
        utc=True,
    )
    if pd.isna(parsed):
        return None
    return parsed.isoformat()


def fetch_saved_market_state() -> pd.DataFrame:
    if not supabase_is_configured():
        return pd.DataFrame()

    try:
        response = (
            get_supabase_client()
            .table("az_market_prices")
            .select("*")
            .eq("profile_id", get_profile_id())
            .execute()
        )
    except Exception:
        return pd.DataFrame()

    rows = getattr(response, "data", None) or []
    if not rows:
        return pd.DataFrame()

    mapped: list[dict[str, Any]] = []
    for row in rows:
        item: dict[str, Any] = {
            "Ticker": str(row.get("ticker", "")),
        }
        for cloud_name, app_name in MARKET_COLUMN_MAP.items():
            item[app_name] = row.get(cloud_name)
        mapped.append(item)

    saved = pd.DataFrame(mapped)
    if "Date du cours" in saved.columns:
        saved["Date du cours"] = pd.to_datetime(
            saved["Date du cours"],
            errors="coerce",
            utc=True,
        ).dt.tz_convert(None)

    return saved


def hydrate_market_data(
    current_market: pd.DataFrame,
) -> pd.DataFrame:
    """
    Complète les données Yahoo manquantes avec le dernier cours
    sauvegardé dans Supabase. Un cours cloud n'écrase jamais un
    cours Yahoo valide et plus récent.
    """
    if current_market is None:
        current_market = pd.DataFrame()

    current = current_market.copy()
    if "Ticker" not in current.columns:
        return current

    saved = fetch_saved_market_state()
    if saved.empty:
        return current

    merged = current.merge(
        saved,
        on="Ticker",
        how="left",
        suffixes=("", "__cloud"),
    )

    for app_name in MARKET_COLUMN_MAP.values():
        cloud_name = f"{app_name}__cloud"
        if cloud_name not in merged.columns:
            continue

        if app_name == "Date du cours":
            live = pd.to_datetime(
                merged.get(app_name),
                errors="coerce",
            )
            cloud = pd.to_datetime(
                merged[cloud_name],
                errors="coerce",
            )
            merged[app_name] = live.fillna(cloud)
        elif app_name == "Signal":
            live = merged.get(
                app_name,
                pd.Series(index=merged.index, dtype=object),
            )
            missing = live.isna() | live.astype(str).str.contains(
                "indisponible|insuffisante",
                case=False,
                na=True,
            )
            merged.loc[missing, app_name] = merged.loc[
                missing,
                cloud_name,
            ]
        else:
            live = pd.to_numeric(
                merged.get(app_name),
                errors="coerce",
            )
            cloud = pd.to_numeric(
                merged[cloud_name],
                errors="coerce",
            )

            if app_name == "Cours (€)":
                missing = live.isna() | (live <= 0)
            else:
                missing = live.isna()

            live.loc[missing] = cloud.loc[missing]
            merged[app_name] = live

        merged = merged.drop(columns=[cloud_name])

    if "Statut données" in merged.columns:
        price = pd.to_numeric(
            merged.get("Cours (€)"),
            errors="coerce",
        )
        restored = (
            price.notna()
            & (price > 0)
            & (
                merged["Statut données"].astype(str)
                != "OK"
            )
        )
        merged.loc[
            restored,
            "Statut données",
        ] = "Dernier cours sauvegardé"

    return merged


def save_market_state(
    market_data: pd.DataFrame,
) -> int:
    if (
        not supabase_is_configured()
        or market_data is None
        or market_data.empty
        or "Ticker" not in market_data.columns
    ):
        return 0

    now = datetime.now(timezone.utc).isoformat()
    records: list[dict[str, Any]] = []

    for _, row in market_data.iterrows():
        ticker = str(row.get("Ticker", "")).strip()
        price = _nullable_number(row.get("Cours (€)"))

        if not ticker or price is None or price <= 0:
            continue

        record: dict[str, Any] = {
            "profile_id": get_profile_id(),
            "ticker": ticker,
            "price": price,
            "quote_date": _date_text(
                row.get("Date du cours")
            ),
            "mm50": _nullable_number(
                row.get("MM50 (€)")
            ),
            "mm200": _nullable_number(
                row.get("MM200 (€)")
            ),
            "distance_mm200": _nullable_number(
                row.get("Distance MM200 (%)")
            ),
            "momentum_3m": _nullable_number(
                row.get("Momentum 3M (%)")
            ),
            "momentum_6m": _nullable_number(
                row.get("Momentum 6M (%)")
            ),
            "momentum_12m": _nullable_number(
                row.get("Momentum 12M (%)")
            ),
            "performance_ytd": _nullable_number(
                row.get("Performance YTD (%)")
            ),
            "volatility_1y": _nullable_number(
                row.get("Volatilité 1A (%)")
            ),
            "alpha_zen_score": _nullable_number(
                row.get("Score Alpha Zen")
            ),
            "signal": str(
                row.get("Signal", "")
            ),
            "updated_at": now,
        }
        records.append(record)

    if not records:
        return 0

    try:
        (
            get_supabase_client()
            .table("az_market_prices")
            .upsert(
                records,
                on_conflict="profile_id,ticker",
            )
            .execute()
        )
    except Exception as exc:
        raise SupabaseSyncError(
            "Impossible de sauvegarder les derniers cours."
        ) from exc

    st.session_state["az_market_last_sync"] = now
    return len(records)


def save_live_valuation(
    frame: pd.DataFrame,
    summary: dict[str, Any],
) -> None:
    if not supabase_is_configured():
        return

    latest = summary.get("latest_timestamp")
    quote_date = _date_text(latest)
    record = {
        "profile_id": get_profile_id(),
        "capital_reference": _number(
            summary.get("capital_reference")
        ),
        "cash": _number(summary.get("cash")),
        "invested": _number(
            summary.get("invested")
        ),
        "positions_value": _number(
            summary.get("positions_value")
        ),
        "total_value": _number(
            summary.get("total_value")
        ),
        "unrealized_gain": _number(
            summary.get("gain")
        ),
        "performance": _number(
            summary.get("performance")
        ),
        "active_lines": int(
            _number(summary.get("active_lines"))
        ),
        "quote_date": quote_date,
        "updated_at": datetime.now(
            timezone.utc
        ).isoformat(),
    }

    try:
        (
            get_supabase_client()
            .table("az_live_portfolio")
            .upsert(
                record,
                on_conflict="profile_id",
            )
            .execute()
        )
    except Exception as exc:
        raise SupabaseSyncError(
            "Impossible de sauvegarder la valorisation actuelle."
        ) from exc


def fetch_live_valuation() -> dict[str, Any] | None:
    if not supabase_is_configured():
        return None

    try:
        response = (
            get_supabase_client()
            .table("az_live_portfolio")
            .select("*")
            .eq("profile_id", get_profile_id())
            .limit(1)
            .execute()
        )
    except Exception:
        return None

    rows = getattr(response, "data", None) or []
    return rows[0] if rows else None


def rebuild_positions_from_transactions(
    transactions: pd.DataFrame,
) -> pd.DataFrame:
    columns = ["Ticker", "Quantité", "PRU (€)"]

    if transactions is None or transactions.empty:
        return pd.DataFrame(columns=columns)

    work = transactions.copy()
    for column in [
        "Quantité",
        "Prix (€)",
        "Frais (€)",
    ]:
        work[column] = pd.to_numeric(
            work.get(column),
            errors="coerce",
        ).fillna(0.0)

    work["Date__parsed"] = pd.to_datetime(
        work.get("Date"),
        errors="coerce",
        utc=True,
    )
    work = work.sort_values(
        "Date__parsed",
        na_position="first",
    )

    state: dict[str, dict[str, float]] = {}

    for _, row in work.iterrows():
        ticker = str(row.get("Ticker", "")).strip()
        action = str(row.get("Type", "")).strip().upper()
        quantity = float(row.get("Quantité", 0.0))
        price = float(row.get("Prix (€)", 0.0))
        fees = float(row.get("Frais (€)", 0.0))

        if not ticker or quantity <= 0 or price <= 0:
            continue

        position = state.setdefault(
            ticker,
            {"Quantité": 0.0, "PRU (€)": 0.0},
        )
        old_quantity = position["Quantité"]
        old_pru = position["PRU (€)"]

        if action == "ACHAT":
            new_quantity = old_quantity + quantity
            new_pru = (
                old_quantity * old_pru
                + quantity * price
                + fees
            ) / new_quantity
            position["Quantité"] = new_quantity
            position["PRU (€)"] = new_pru

        elif action == "VENTE":
            new_quantity = max(
                old_quantity - quantity,
                0.0,
            )
            position["Quantité"] = new_quantity
            position["PRU (€)"] = (
                old_pru
                if new_quantity > 1e-9
                else 0.0
            )

    return pd.DataFrame(
        [
            {
                "Ticker": ticker,
                "Quantité": values["Quantité"],
                "PRU (€)": values["PRU (€)"],
            }
            for ticker, values in state.items()
        ],
        columns=columns,
    )


def repair_session_pru_from_transactions() -> int:
    """
    Répare seulement les lignes actives dont le PRU vaut zéro.
    Les positions saisies manuellement avec un PRU valide ne sont
    jamais remplacées.
    """
    positions = st.session_state.get(
        "virtual_positions"
    )
    transactions = st.session_state.get(
        "virtual_transactions"
    )

    if (
        positions is None
        or not isinstance(positions, pd.DataFrame)
        or positions.empty
        or transactions is None
        or not isinstance(transactions, pd.DataFrame)
        or transactions.empty
    ):
        return 0

    current = positions.copy()
    current["Quantité"] = pd.to_numeric(
        current.get("Quantité"),
        errors="coerce",
    ).fillna(0.0)
    current["PRU (€)"] = pd.to_numeric(
        current.get("PRU (€)"),
        errors="coerce",
    ).fillna(0.0)

    rebuilt = rebuild_positions_from_transactions(
        transactions
    )
    if rebuilt.empty:
        return 0

    rebuilt = rebuilt.set_index("Ticker")
    repaired = 0

    for index, row in current.iterrows():
        ticker = str(row.get("Ticker", "")).strip()
        quantity = float(row.get("Quantité", 0.0))
        pru = float(row.get("PRU (€)", 0.0))

        if (
            quantity <= 0
            or pru > 0
            or ticker not in rebuilt.index
        ):
            continue

        recovered = rebuilt.loc[ticker]
        recovered_pru = float(
            recovered["PRU (€)"]
        )
        recovered_quantity = float(
            recovered["Quantité"]
        )

        if (
            recovered_pru > 0
            and recovered_quantity > 0
        ):
            current.at[index, "PRU (€)"] = (
                recovered_pru
            )
            repaired += 1

    if repaired:
        st.session_state.virtual_positions = current[
            ["Ticker", "Quantité", "PRU (€)"]
        ].copy()
        st.session_state[
            "az_pru_repaired_count"
        ] = repaired

    return repaired


def persistence_health(
    positions: pd.DataFrame | None,
) -> dict[str, Any]:
    if positions is None or positions.empty:
        return {
            "active_positions": 0,
            "missing_pru": 0,
            "healthy": True,
        }

    work = positions.copy()
    quantity = pd.to_numeric(
        work.get("Quantité"),
        errors="coerce",
    ).fillna(0.0)
    pru = pd.to_numeric(
        work.get("PRU (€)"),
        errors="coerce",
    ).fillna(0.0)

    active = quantity > 0
    missing = active & (pru <= 0)

    return {
        "active_positions": int(active.sum()),
        "missing_pru": int(missing.sum()),
        "healthy": bool(missing.sum() == 0),
    }
