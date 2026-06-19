from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd


FORTUNEO_PLANS = ("Starter", "Progress", "Trader Pro")


@dataclass(frozen=True)
class FeeQuote:
    plan: str
    gross_amount: float
    fee: float
    fee_rate_percent: float
    explanation: str
    free_order_used: bool = False


def _monthly_order_count(
    transactions: pd.DataFrame | None,
    when: datetime | None = None,
) -> int:
    if transactions is None or transactions.empty:
        return 0

    when = when or datetime.now(timezone.utc)
    dates = pd.to_datetime(
        transactions.get("Date"),
        errors="coerce",
        utc=True,
    )
    valid = dates.notna()

    return int(
        (
            valid
            & (dates.dt.year == when.year)
            & (dates.dt.month == when.month)
        ).sum()
    )


def calculate_fortuneo_fee(
    plan: str,
    gross_amount: float,
    transactions: pd.DataFrame | None = None,
    when: datetime | None = None,
) -> FeeQuote:
    """
    Estimation des frais de courtage Fortuneo pour un ordre PEA en ligne
    sur Euronext. Le plafond réglementaire PEA de 0,50 % est appliqué.
    """
    amount = max(float(gross_amount), 0.0)
    selected_plan = (
        plan if plan in FORTUNEO_PLANS else "Starter"
    )

    if amount <= 0:
        return FeeQuote(
            plan=selected_plan,
            gross_amount=amount,
            fee=0.0,
            fee_rate_percent=0.0,
            explanation="Montant nul.",
        )

    pea_cap = amount * 0.005
    free_order_used = False

    if selected_plan == "Starter":
        order_count = _monthly_order_count(
            transactions,
            when,
        )

        if order_count == 0 and amount <= 500.0:
            raw_fee = 0.0
            free_order_used = True
            explanation = (
                "Starter : premier ordre du mois inférieur "
                "ou égal à 500 €, frais estimés à 0 €."
            )
        else:
            raw_fee = amount * 0.0035
            explanation = (
                "Starter : 0,35 % du montant de l'ordre."
            )

    elif selected_plan == "Progress":
        if amount <= 3000.0:
            raw_fee = 4.90
            explanation = (
                "Progress : 4,90 € pour un ordre "
                "inférieur ou égal à 3 000 €."
            )
        else:
            raw_fee = amount * 0.0015
            explanation = (
                "Progress : 0,15 % pour un ordre "
                "supérieur à 3 000 €."
            )

    else:
        if amount <= 10000.0:
            raw_fee = 9.50
            explanation = (
                "Trader Pro : 9,50 € pour un ordre "
                "inférieur ou égal à 10 000 €."
            )
        else:
            raw_fee = amount * 0.0010
            explanation = (
                "Trader Pro : 0,10 % pour un ordre "
                "supérieur à 10 000 €."
            )

    fee = round(min(raw_fee, pea_cap), 2)
    rate = fee / amount * 100.0 if amount else 0.0

    if raw_fee > pea_cap:
        explanation += (
            " Le plafond PEA de 0,50 % du montant "
            "de l'ordre a été appliqué."
        )

    return FeeQuote(
        plan=selected_plan,
        gross_amount=amount,
        fee=fee,
        fee_rate_percent=rate,
        explanation=explanation,
        free_order_used=free_order_used,
    )


def plan_summary(plan: str) -> str:
    summaries = {
        "Starter": (
            "Premier ordre mensuel ≤ 500 € : 0 € ; "
            "sinon 0,35 % par ordre."
        ),
        "Progress": (
            "4,90 € jusqu'à 3 000 € ; "
            "0,15 % au-delà."
        ),
        "Trader Pro": (
            "9,50 € jusqu'à 10 000 € ; "
            "0,10 % au-delà."
        ),
    }
    return summaries.get(plan, summaries["Starter"])
