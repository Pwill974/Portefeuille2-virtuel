from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import streamlit as st

from services.fortuneo_fees import calculate_fortuneo_fee
from services.supabase_service import (
    SupabaseSyncError,
    get_profile_id,
    get_supabase_client,
    save_portfolio_state,
    supabase_is_configured,
)


REUNION_TZ = ZoneInfo("Indian/Reunion")
STRATEGIES = ("Rééquilibrage", "Mixte", "Momentum")


@dataclass(frozen=True)
class MonthlyStatus:
    month_key: str
    contribution_recorded: bool
    plan_executed: bool
    amount: float
    invested_amount: float
    fees: float


def reunion_now() -> datetime:
    return datetime.now(REUNION_TZ)


def month_key(when: datetime | None = None) -> str:
    current = when or reunion_now()
    return current.strftime("%Y-%m-01")


def default_settings() -> dict[str, object]:
    return {
        "monthly_plan_enabled": True,
        "monthly_purchase_day": 5,
        "monthly_max_orders": 3,
        "monthly_strategy": "Mixte",
        "monthly_respect_mm200": True,
        "monthly_min_score": 0.0,
    }


def load_monthly_settings() -> dict[str, object]:
    defaults = default_settings()

    if not supabase_is_configured():
        saved = st.session_state.get("monthly_plan_settings", {})
        return {**defaults, **saved}

    try:
        response = (
            get_supabase_client()
            .table("az_settings")
            .select(
                "monthly_plan_enabled,"
                "monthly_purchase_day,"
                "monthly_max_orders,"
                "monthly_strategy,"
                "monthly_respect_mm200,"
                "monthly_min_score"
            )
            .eq("profile_id", get_profile_id())
            .limit(1)
            .execute()
        )
        rows = getattr(response, "data", None) or []
        return {**defaults, **(rows[0] if rows else {})}
    except Exception:
        return defaults


def save_monthly_settings(settings: dict[str, object]) -> None:
    clean = {
        "monthly_plan_enabled": bool(
            settings.get("monthly_plan_enabled", True)
        ),
        "monthly_purchase_day": int(
            np.clip(
                int(settings.get("monthly_purchase_day", 5)),
                1,
                28,
            )
        ),
        "monthly_max_orders": int(
            np.clip(
                int(settings.get("monthly_max_orders", 3)),
                1,
                8,
            )
        ),
        "monthly_strategy": str(
            settings.get("monthly_strategy", "Mixte")
        ),
        "monthly_respect_mm200": bool(
            settings.get("monthly_respect_mm200", True)
        ),
        "monthly_min_score": float(
            settings.get("monthly_min_score", 0.0)
        ),
    }
    st.session_state["monthly_plan_settings"] = clean

    if not supabase_is_configured():
        return

    record = {
        "profile_id": get_profile_id(),
        **clean,
        "updated_at": reunion_now().isoformat(),
    }

    try:
        (
            get_supabase_client()
            .table("az_settings")
            .upsert(record, on_conflict="profile_id")
            .execute()
        )
    except Exception as exc:
        raise SupabaseSyncError(
            "Impossible d'enregistrer les paramètres du plan mensuel. "
            "Vérifie que la migration SQL a été exécutée."
        ) from exc


def get_monthly_status(
    when: datetime | None = None,
) -> MonthlyStatus:
    key = month_key(when)

    if not supabase_is_configured():
        local = st.session_state.get("monthly_contributions", {})
        record = local.get(key, {})
        return MonthlyStatus(
            month_key=key,
            contribution_recorded=bool(record),
            plan_executed=record.get("status") == "executed",
            amount=float(record.get("amount", 0.0) or 0.0),
            invested_amount=float(
                record.get("invested_amount", 0.0) or 0.0
            ),
            fees=float(record.get("fees", 0.0) or 0.0),
        )

    try:
        response = (
            get_supabase_client()
            .table("az_contributions")
            .select(
                "amount,status,invested_amount,fees"
            )
            .eq("profile_id", get_profile_id())
            .eq("contribution_month", key)
            .limit(1)
            .execute()
        )
        rows = getattr(response, "data", None) or []
    except Exception as exc:
        raise SupabaseSyncError(
            "Impossible de lire le versement mensuel."
        ) from exc

    if not rows:
        return MonthlyStatus(
            key,
            False,
            False,
            0.0,
            0.0,
            0.0,
        )

    row = rows[0]
    return MonthlyStatus(
        month_key=key,
        contribution_recorded=True,
        plan_executed=row.get("status") == "executed",
        amount=float(row.get("amount", 0.0) or 0.0),
        invested_amount=float(
            row.get("invested_amount", 0.0) or 0.0
        ),
        fees=float(row.get("fees", 0.0) or 0.0),
    )


def record_monthly_contribution(
    amount: float,
    monthly_contribution: float,
) -> MonthlyStatus:
    amount = float(amount)

    if amount <= 0:
        raise ValueError(
            "Le versement mensuel doit être supérieur à zéro."
        )

    current_status = get_monthly_status()
    if current_status.contribution_recorded:
        raise ValueError(
            "Le versement de ce mois a déjà été enregistré."
        )

    current_cash = float(
        st.session_state.get("virtual_cash", 0.0)
    )
    current_capital = float(
        st.session_state.get(
            "capital_reference",
            st.session_state.get(
                "cloud_capital_reference",
                0.0,
            ),
        )
    )

    new_cash = current_cash + amount
    new_capital = current_capital + amount

    record = {
        "profile_id": get_profile_id(),
        "contribution_month": month_key(),
        "amount": amount,
        "status": "deposited",
        "invested_amount": 0.0,
        "fees": 0.0,
        "created_at": reunion_now().isoformat(),
    }

    if supabase_is_configured():
        try:
            (
                get_supabase_client()
                .table("az_contributions")
                .insert(record)
                .execute()
            )
        except Exception as exc:
            raise SupabaseSyncError(
                "Le versement n'a pas pu être enregistré. "
                "Vérifie la table az_contributions."
            ) from exc
    else:
        local = st.session_state.setdefault(
            "monthly_contributions",
            {},
        )
        local[month_key()] = record

    st.session_state.virtual_cash = new_cash
    st.session_state.capital_reference = new_capital
    st.session_state.cloud_capital_reference = new_capital
    st.session_state.monthly_contribution = float(
        monthly_contribution
    )

    if supabase_is_configured():
        save_portfolio_state(
            st.session_state.virtual_positions,
            new_cash,
            new_capital,
            monthly_contribution,
        )

    return get_monthly_status()


def mark_plan_executed(
    invested_amount: float,
    fees: float,
) -> None:
    key = month_key()

    if supabase_is_configured():
        try:
            (
                get_supabase_client()
                .table("az_contributions")
                .update(
                    {
                        "status": "executed",
                        "invested_amount": float(
                            invested_amount
                        ),
                        "fees": float(fees),
                        "executed_at": reunion_now().isoformat(),
                    }
                )
                .eq("profile_id", get_profile_id())
                .eq("contribution_month", key)
                .execute()
            )
        except Exception as exc:
            raise SupabaseSyncError(
                "Impossible de marquer le plan mensuel comme exécuté."
            ) from exc
    else:
        local = st.session_state.setdefault(
            "monthly_contributions",
            {},
        )
        record = local.setdefault(key, {})
        record.update(
            {
                "status": "executed",
                "invested_amount": float(invested_amount),
                "fees": float(fees),
            }
        )


def _synthetic_transactions(
    actual_transactions: pd.DataFrame | None,
    prior_planned_orders: int,
) -> pd.DataFrame:
    if actual_transactions is None:
        result = pd.DataFrame()
    else:
        result = actual_transactions.copy()

    if prior_planned_orders <= 0:
        return result

    dummy = pd.DataFrame(
        {
            "Date": [
                reunion_now().isoformat()
            ] * prior_planned_orders
        }
    )
    return pd.concat(
        [result, dummy],
        ignore_index=True,
        sort=False,
    )


def _strategy_factor(
    strategy: str,
    score: float,
) -> float:
    normalized = float(
        np.clip(score / 100.0, 0.0, 1.0)
    )

    if strategy == "Momentum":
        return 0.40 + 1.40 * normalized
    if strategy == "Mixte":
        return 0.75 + 0.65 * normalized
    return 1.0


def calculate_monthly_plan(
    frame: pd.DataFrame,
    budget: float,
    current_total_value: float,
    brokerage_plan: str,
    transactions: pd.DataFrame | None,
    max_orders: int = 3,
    strategy: str = "Mixte",
    respect_mm200: bool = True,
    minimum_score: float = 0.0,
    always_allow_core: bool = True,
    max_overshoot_percent: float = 1.0,
) -> tuple[pd.DataFrame, dict[str, float]]:
    """
    Calcule des quantités entières en tenant compte :
    - des allocations cibles ;
    - du momentum ;
    - de la MM200 ;
    - des frais Fortuneo ;
    - du nombre maximal d'ordres ;
    - du budget réellement disponible.
    """
    budget = max(float(budget), 0.0)
    max_orders = max(int(max_orders), 1)

    if budget <= 0 or frame is None or frame.empty:
        return pd.DataFrame(), {
            "budget": budget,
            "invested": 0.0,
            "fees": 0.0,
            "remaining": budget,
            "orders": 0.0,
        }

    required = [
        "Actif",
        "Ticker",
        "Poche",
        "Allocation cible (%)",
        "Cours (€)",
        "Valeur actuelle (€)",
        "Score Alpha Zen",
        "Distance MM200 (%)",
        "Signal",
    ]
    missing = [
        column for column in required
        if column not in frame.columns
    ]
    if missing:
        raise ValueError(
            "Colonnes manquantes pour le calcul mensuel : "
            + ", ".join(missing)
        )

    work = frame[required].copy()
    numeric_columns = [
        "Allocation cible (%)",
        "Cours (€)",
        "Valeur actuelle (€)",
        "Score Alpha Zen",
        "Distance MM200 (%)",
    ]
    for column in numeric_columns:
        work[column] = pd.to_numeric(
            work[column],
            errors="coerce",
        )

    total_after = float(current_total_value) + budget
    work["Cible après versement (€)"] = (
        total_after
        * work["Allocation cible (%)"]
        / 100.0
    )
    work["Manque cible (€)"] = (
        work["Cible après versement (€)"]
        - work["Valeur actuelle (€)"]
    )
    work["Facteur stratégie"] = work[
        "Score Alpha Zen"
    ].fillna(0.0).apply(
        lambda score: _strategy_factor(
            strategy,
            float(score),
        )
    )

    mm200_ok = (
        work["Distance MM200 (%)"].fillna(-999.0) >= 0.0
    )
    if always_allow_core:
        mm200_ok = mm200_ok | (
            work["Poche"] == "Socle Zen"
        )

    work["Éligible"] = (
        (work["Cours (€)"].fillna(0.0) > 0.0)
        & (
            work["Score Alpha Zen"].fillna(0.0)
            >= float(minimum_score)
        )
        & (
            mm200_ok
            if respect_mm200
            else True
        )
    )

    candidates = work[work["Éligible"]].copy()
    if candidates.empty:
        return pd.DataFrame(), {
            "budget": budget,
            "invested": 0.0,
            "fees": 0.0,
            "remaining": budget,
            "orders": 0.0,
        }

    quantities = {
        ticker: 0
        for ticker in candidates["Ticker"]
    }
    order_sequence: list[str] = []
    remaining = budget
    max_iterations = 10000

    indexed = candidates.set_index("Ticker")

    def fee_for(
        ticker: str,
        quantity: int,
        proposed_sequence: list[str],
    ) -> float:
        if quantity <= 0:
            return 0.0

        order_index = proposed_sequence.index(ticker)
        tx = _synthetic_transactions(
            transactions,
            order_index,
        )
        gross = (
            quantity
            * float(indexed.at[ticker, "Cours (€)"])
        )
        return calculate_fortuneo_fee(
            brokerage_plan,
            gross,
            tx,
        ).fee

    for _ in range(max_iterations):
        best_ticker = None
        best_ratio = -1.0
        best_incremental_cost = 0.0
        best_sequence: list[str] = []

        for ticker, row in indexed.iterrows():
            current_quantity = quantities[ticker]

            if (
                current_quantity == 0
                and ticker not in order_sequence
                and len(order_sequence) >= max_orders
            ):
                continue

            trial_sequence = list(order_sequence)
            if ticker not in trial_sequence:
                trial_sequence.append(ticker)

            price = float(row["Cours (€)"])
            old_fee = fee_for(
                ticker,
                current_quantity,
                trial_sequence,
            )
            new_fee = fee_for(
                ticker,
                current_quantity + 1,
                trial_sequence,
            )
            incremental_cost = (
                price + new_fee - old_fee
            )

            if incremental_cost <= 0:
                continue
            if incremental_cost > remaining + 1e-9:
                continue

            projected_value = (
                float(row["Valeur actuelle (€)"])
                + current_quantity * price
            )
            target_value = float(
                row["Cible après versement (€)"]
            )
            overshoot_limit = (
                target_value
                + total_after
                * float(max_overshoot_percent)
                / 100.0
            )

            if projected_value + price > overshoot_limit:
                continue

            gap_before = max(
                target_value - projected_value,
                0.0,
            )
            gap_after = max(
                target_value
                - projected_value
                - price,
                0.0,
            )
            improvement = gap_before - gap_after

            if improvement <= 0:
                continue

            weighted_improvement = (
                improvement
                * float(row["Facteur stratégie"])
            )
            ratio = (
                weighted_improvement
                / incremental_cost
            )

            if ratio > best_ratio:
                best_ratio = ratio
                best_ticker = ticker
                best_incremental_cost = (
                    incremental_cost
                )
                best_sequence = trial_sequence

        if best_ticker is None:
            break

        quantities[best_ticker] += 1
        order_sequence = best_sequence
        remaining -= best_incremental_cost

    rows = []
    total_fees = 0.0
    total_gross = 0.0

    for ticker in order_sequence:
        quantity = quantities[ticker]
        if quantity <= 0:
            continue

        row = indexed.loc[ticker]
        price = float(row["Cours (€)"])
        gross = quantity * price
        fee = fee_for(
            ticker,
            quantity,
            order_sequence,
        )
        total = gross + fee
        total_fees += fee
        total_gross += gross
        post_value = (
            float(row["Valeur actuelle (€)"])
            + gross
        )
        post_weight = (
            post_value / total_after * 100.0
            if total_after > 0
            else 0.0
        )

        rows.append(
            {
                "Actif": row["Actif"],
                "Ticker": ticker,
                "Poche": row["Poche"],
                "Quantité à acheter": int(quantity),
                "Cours (€)": price,
                "Montant brut (€)": gross,
                "Frais (€)": fee,
                "Coût total (€)": total,
                "Score Alpha Zen": float(
                    row["Score Alpha Zen"]
                ),
                "Signal": row["Signal"],
                "Cible après versement (€)": float(
                    row["Cible après versement (€)"]
                ),
                "Valeur après achat (€)": post_value,
                "Poids après achat (%)": post_weight,
            }
        )

    plan = pd.DataFrame(rows)
    total_cost = total_gross + total_fees

    summary = {
        "budget": budget,
        "invested": total_gross,
        "fees": total_fees,
        "total_cost": total_cost,
        "remaining": max(budget - total_cost, 0.0),
        "orders": float(len(plan)),
    }
    return plan, summary
