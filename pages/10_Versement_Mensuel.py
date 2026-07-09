from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Alpha Zen Pro — Versement mensuel",
    page_icon="💶",
    layout="wide",
)

from services.auth import require_authentication, show_logout_button
from services.supabase_service import (
    SupabaseSyncError,
    get_profile_id,
    get_supabase_client,
    load_cloud_state_into_session,
    save_portfolio_state,
    supabase_is_configured,
)
from services.trading_service import save_current_state_to_cloud


REUNION_TZ = ZoneInfo("Indian/Reunion")


require_authentication()
show_logout_button()


def euro(value: float) -> str:
    return f"{float(value):,.2f} €".replace(",", " ").replace(".", ",")


def now_reunion() -> datetime:
    return datetime.now(REUNION_TZ)


def month_key() -> str:
    return now_reunion().strftime("%Y-%m-01")


def ensure_numeric_session() -> None:
    st.session_state["virtual_cash"] = float(
        st.session_state.get("virtual_cash", 0.0) or 0.0
    )
    st.session_state["capital_reference"] = float(
        st.session_state.get(
            "capital_reference",
            st.session_state.get("cloud_capital_reference", 10_000.0),
        )
        or 10_000.0
    )
    st.session_state["monthly_contribution"] = float(
        st.session_state.get(
            "monthly_contribution",
            st.session_state.get("cloud_monthly_contribution", 1_000.0),
        )
        or 1_000.0
    )
    if "virtual_positions" not in st.session_state:
        st.session_state["virtual_positions"] = pd.DataFrame(
            columns=["Ticker", "Quantité", "PRU (€)"]
        )


def get_current_contribution() -> dict | None:
    if not supabase_is_configured():
        return None

    try:
        response = (
            get_supabase_client()
            .table("az_contributions")
            .select("*")
            .eq("profile_id", get_profile_id())
            .eq("contribution_month", month_key())
            .limit(1)
            .execute()
        )
        rows = getattr(response, "data", None) or []
        return rows[0] if rows else None
    except Exception as error:
        raise SupabaseSyncError(
            "Impossible de lire la table az_contributions. "
            "Si elle n'existe pas, exécute le SQL fourni."
        ) from error


def load_contribution_history(limit: int = 24) -> pd.DataFrame:
    if not supabase_is_configured():
        return pd.DataFrame()

    try:
        response = (
            get_supabase_client()
            .table("az_contributions")
            .select("*")
            .eq("profile_id", get_profile_id())
            .order("contribution_month", desc=True)
            .limit(limit)
            .execute()
        )
        rows = getattr(response, "data", None) or []
    except Exception:
        return pd.DataFrame()

    return pd.DataFrame(rows)


def upsert_contribution_record(
    amount: float,
    status: str = "deposited",
    invested_amount: float = 0.0,
    fees: float = 0.0,
) -> None:
    if not supabase_is_configured():
        return

    record = {
        "profile_id": get_profile_id(),
        "contribution_month": month_key(),
        "amount": float(amount),
        "status": status,
        "invested_amount": float(invested_amount),
        "fees": float(fees),
        "created_at": now_reunion().isoformat(),
    }

    try:
        (
            get_supabase_client()
            .table("az_contributions")
            .upsert(record, on_conflict="profile_id,contribution_month")
            .execute()
        )
    except Exception as error:
        raise SupabaseSyncError(
            "Le portefeuille a été mis à jour, mais le journal "
            "az_contributions n'a pas pu être enregistré."
        ) from error


def add_cash_contribution(
    amount: float,
    *,
    exceptional: bool = False,
) -> None:
    amount = float(amount)

    if amount <= 0:
        raise ValueError("Le montant doit être supérieur à zéro.")

    existing = get_current_contribution()

    if existing and not exceptional:
        raise ValueError(
            "Le versement normal de ce mois est déjà enregistré. "
            "Utilise le versement exceptionnel si tu veux ajouter une somme en plus."
        )

    old_cash = float(st.session_state.virtual_cash)
    old_capital = float(st.session_state.capital_reference)

    new_cash = old_cash + amount
    new_capital = old_capital + amount

    if existing and exceptional:
        total_month_amount = float(existing.get("amount", 0.0) or 0.0) + amount
        status = str(existing.get("status", "deposited") or "deposited")
        invested_amount = float(existing.get("invested_amount", 0.0) or 0.0)
        fees = float(existing.get("fees", 0.0) or 0.0)
    else:
        total_month_amount = amount
        status = "deposited"
        invested_amount = 0.0
        fees = 0.0

    st.session_state.virtual_cash = new_cash
    st.session_state.capital_reference = new_capital
    st.session_state.cloud_capital_reference = new_capital
    st.session_state.monthly_contribution = float(
        st.session_state.get("monthly_contribution", amount)
    )

    save_portfolio_state(
        st.session_state.virtual_positions,
        new_cash,
        new_capital,
        float(st.session_state.monthly_contribution),
    )

    upsert_contribution_record(
        total_month_amount,
        status=status,
        invested_amount=invested_amount,
        fees=fees,
    )


st.title("💶 Versement mensuel")
st.caption(
    "Ajoute ton apport mensuel au portefeuille virtuel. "
    "Les liquidités et le capital versé sont sauvegardés dans Supabase."
)

if not supabase_is_configured():
    st.error(
        "Supabase n'est pas configuré. Ajoute d'abord les secrets Supabase dans Streamlit."
    )
    st.stop()

loaded = load_cloud_state_into_session(force=True)
ensure_numeric_session()

current_month = month_key()
current_contribution = None

try:
    current_contribution = get_current_contribution()
except Exception as error:
    st.error(str(error))
    st.info(
        "Si la table manque, exécute le fichier SQL : "
        "database/az_contributions_migration.sql"
    )
    st.stop()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Mois", current_month[:7])
col2.metric("Liquidités actuelles", euro(st.session_state.virtual_cash))
col3.metric("Capital versé", euro(st.session_state.capital_reference))
col4.metric(
    "Versement du mois",
    euro(float(current_contribution.get("amount", 0.0)))
    if current_contribution
    else "Non enregistré",
)

st.divider()

left, right = st.columns([1, 1])

with left:
    st.subheader("1️⃣ Ajouter le versement normal")

    monthly_default = float(
        st.session_state.get("monthly_contribution", 1_000.0) or 1_000.0
    )

    monthly_amount = st.number_input(
        "Montant du versement mensuel",
        min_value=0.0,
        value=monthly_default,
        step=50.0,
        format="%.2f",
    )

    if current_contribution:
        st.warning(
            "Le versement normal de ce mois est déjà enregistré. "
            "Tu ne peux pas le rajouter une deuxième fois par erreur."
        )
    else:
        st.success("Aucun versement normal enregistré pour ce mois.")

    confirm_monthly = st.checkbox(
        "Je confirme l'ajout du versement mensuel aux liquidités.",
        key="confirm_monthly_contribution",
        disabled=bool(current_contribution),
    )

    if st.button(
        "➕ Ajouter le versement mensuel",
        type="primary",
        use_container_width=True,
        disabled=bool(current_contribution) or not confirm_monthly,
    ):
        try:
            add_cash_contribution(monthly_amount, exceptional=False)
            st.success(
                f"Versement ajouté : {euro(monthly_amount)}. "
                f"Nouvelles liquidités : {euro(st.session_state.virtual_cash)}."
            )
            st.rerun()
        except Exception as error:
            st.error(str(error))

with right:
    st.subheader("2️⃣ Versement exceptionnel")

    st.info(
        "À utiliser seulement si tu veux ajouter une somme en plus du versement normal."
    )

    exceptional_amount = st.number_input(
        "Montant exceptionnel",
        min_value=0.0,
        value=0.0,
        step=50.0,
        format="%.2f",
    )

    confirm_exceptional = st.checkbox(
        "Je confirme l'ajout d'un versement exceptionnel.",
        key="confirm_exceptional_contribution",
    )

    if st.button(
        "➕ Ajouter un versement exceptionnel",
        use_container_width=True,
        disabled=not confirm_exceptional,
    ):
        try:
            add_cash_contribution(exceptional_amount, exceptional=True)
            st.success(
                f"Versement exceptionnel ajouté : {euro(exceptional_amount)}. "
                f"Nouvelles liquidités : {euro(st.session_state.virtual_cash)}."
            )
            st.rerun()
        except Exception as error:
            st.error(str(error))

st.divider()
st.subheader("Historique des versements")

history = load_contribution_history()

if history.empty:
    st.info("Aucun historique de versement disponible.")
else:
    display = history.copy()
    for col in ["amount", "invested_amount", "fees"]:
        if col in display.columns:
            display[col] = pd.to_numeric(display[col], errors="coerce").fillna(0.0)

    columns = [
        col
        for col in [
            "contribution_month",
            "amount",
            "status",
            "invested_amount",
            "fees",
            "created_at",
            "executed_at",
        ]
        if col in display.columns
    ]

    st.dataframe(
        display[columns],
        hide_index=True,
        use_container_width=True,
        column_config={
            "contribution_month": "Mois",
            "amount": st.column_config.NumberColumn(
                "Montant versé",
                format="%.2f €",
            ),
            "status": "Statut",
            "invested_amount": st.column_config.NumberColumn(
                "Montant investi",
                format="%.2f €",
            ),
            "fees": st.column_config.NumberColumn(
                "Frais",
                format="%.2f €",
            ),
            "created_at": "Créé le",
            "executed_at": "Exécuté le",
        },
    )

st.caption(
    "Après le versement, va dans la page Actifs & Ordres ou Achat Mensuel "
    "pour choisir les achats à réaliser manuellement."
)
