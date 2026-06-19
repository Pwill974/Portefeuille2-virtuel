from __future__ import annotations

import pandas as pd
import streamlit as st

from services.auth import (
    require_authentication,
    show_logout_button,
)
from services.fortuneo_fees import (
    FORTUNEO_PLANS,
    plan_summary,
)
from services.monthly_investment_service import (
    STRATEGIES,
    calculate_monthly_plan,
    get_monthly_status,
    load_monthly_settings,
    mark_plan_executed,
    record_monthly_contribution,
    reunion_now,
    save_monthly_settings,
)
from services.performance_history_service import (
    build_snapshot,
    load_brokerage_plan,
    save_daily_snapshot,
)
from services.portfolio_engine import (
    UNIVERSE,
    calculate_portfolio,
    fetch_market_bundle,
)
from services.supabase_service import (
    cloud_status,
    load_cloud_state_into_session,
)
from services.trading_service import (
    execute_trade,
    initialize_trading_state,
    market_value,
)


st.set_page_config(
    page_title="Alpha Zen Pro — Achat mensuel",
    page_icon="📅",
    layout="wide",
)

require_authentication()
show_logout_button()
load_cloud_state_into_session()


@st.cache_data(ttl=900, show_spinner=False)
def load_market_data(
    tickers: tuple[str, ...],
):
    market, _ = fetch_market_bundle(
        list(tickers)
    )
    return market


def euro(value: float) -> str:
    return (
        f"{float(value):,.2f} €"
        .replace(",", " ")
        .replace(".", ",")
    )


st.title("📅 Achat mensuel guidé")
st.caption(
    "Le module ajoute le versement, calcule les quantités "
    "entières à acheter et prépare les ordres virtuels."
)

cloud = cloud_status()
if cloud["configured"] and not cloud["error"]:
    st.success("☁️ Sauvegarde Supabase active")
elif cloud["error"]:
    st.warning(
        f"☁️ Erreur de synchronisation : {cloud['error']}"
    )
else:
    st.info(
        "☁️ Mode local : le plan fonctionne, mais le suivi "
        "mensuel ne sera pas permanent."
    )

with st.spinner("Chargement des cours et des signaux…"):
    market_data = load_market_data(
        tuple(UNIVERSE["Ticker"].tolist())
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

initialize_trading_state(
    UNIVERSE,
    market_data,
    capital_reference,
    monthly_contribution,
)

settings = load_monthly_settings()
brokerage_plan = load_brokerage_plan()
status = get_monthly_status()
now = reunion_now()

with st.expander(
    "⚙️ Paramètres du plan mensuel",
    expanded=not settings["monthly_plan_enabled"],
):
    enabled = st.toggle(
        "Activer le plan d’achat mensuel",
        value=bool(
            settings["monthly_plan_enabled"]
        ),
    )

    p1, p2, p3 = st.columns(3)
    with p1:
        contribution = st.number_input(
            "Versement mensuel",
            min_value=0.0,
            value=monthly_contribution,
            step=50.0,
            format="%.2f",
        )
    with p2:
        purchase_day = st.number_input(
            "Jour prévu du mois",
            min_value=1,
            max_value=28,
            value=int(
                settings["monthly_purchase_day"]
            ),
            step=1,
        )
    with p3:
        max_orders = st.number_input(
            "Nombre maximal d’ordres",
            min_value=1,
            max_value=8,
            value=int(
                settings["monthly_max_orders"]
            ),
            step=1,
        )

    p4, p5, p6 = st.columns(3)
    with p4:
        strategy = st.selectbox(
            "Méthode de répartition",
            STRATEGIES,
            index=(
                STRATEGIES.index(
                    settings["monthly_strategy"]
                )
                if settings["monthly_strategy"]
                in STRATEGIES
                else 1
            ),
        )
    with p5:
        selected_brokerage_plan = st.selectbox(
            "Tarif Fortuneo",
            FORTUNEO_PLANS,
            index=(
                FORTUNEO_PLANS.index(
                    brokerage_plan
                )
                if brokerage_plan
                in FORTUNEO_PLANS
                else 0
            ),
        )
    with p6:
        minimum_score = st.number_input(
            "Score Alpha Zen minimal",
            min_value=0.0,
            max_value=100.0,
            value=float(
                settings["monthly_min_score"]
            ),
            step=5.0,
        )

    respect_mm200 = st.toggle(
        "Suspendre les achats sous la MM200",
        value=bool(
            settings["monthly_respect_mm200"]
        ),
    )
    always_allow_core = st.toggle(
        "Toujours autoriser le Socle Zen",
        value=True,
        help=(
            "Les ETF du Socle peuvent être renforcés même "
            "si leur cours est temporairement sous la MM200."
        ),
    )
    use_existing_cash = st.toggle(
        "Utiliser aussi les anciennes liquidités disponibles",
        value=False,
    )

    if st.button(
        "💾 Enregistrer les paramètres",
        use_container_width=True,
    ):
        save_monthly_settings(
            {
                "monthly_plan_enabled": enabled,
                "monthly_purchase_day": purchase_day,
                "monthly_max_orders": max_orders,
                "monthly_strategy": strategy,
                "monthly_respect_mm200": respect_mm200,
                "monthly_min_score": minimum_score,
            }
        )
        st.session_state.monthly_contribution = float(
            contribution
        )
        st.success("Paramètres enregistrés.")
        st.rerun()

if not enabled:
    st.warning(
        "Le plan mensuel est désactivé. Active-le dans "
        "les paramètres pour enregistrer un versement."
    )

due = (
    enabled
    and now.day >= int(purchase_day)
    and not status.contribution_recorded
)

if due:
    st.warning(
        f"📅 Le versement de {euro(contribution)} "
        f"prévu le {int(purchase_day)} du mois est à enregistrer."
    )
elif status.contribution_recorded:
    st.success(
        f"✅ Versement du mois enregistré : "
        f"{euro(status.amount)}."
    )
else:
    st.info(
        f"Prochain versement prévu le {int(purchase_day)} "
        f"de ce mois."
    )

s1, s2, s3, s4 = st.columns(4)
s1.metric(
    "Versement mensuel",
    euro(contribution),
)
s2.metric(
    "Liquidités actuelles",
    euro(
        float(
            st.session_state.get(
                "virtual_cash",
                0.0,
            )
        )
    ),
)
s3.metric(
    "Statut du mois",
    (
        "Exécuté"
        if status.plan_executed
        else "Versé"
        if status.contribution_recorded
        else "À verser"
    ),
)
s4.metric(
    "Tarif",
    selected_brokerage_plan,
)

if (
    enabled
    and not status.contribution_recorded
):
    confirm_deposit = st.checkbox(
        "Je confirme l’ajout du versement mensuel "
        "au portefeuille virtuel."
    )
    if st.button(
        "➕ Ajouter le versement mensuel",
        use_container_width=True,
        disabled=not confirm_deposit,
    ):
        try:
            record_monthly_contribution(
                contribution,
                contribution,
            )
            st.success(
                "Versement ajouté aux liquidités et "
                "sauvegardé dans Supabase."
            )
            st.rerun()
        except Exception as error:
            st.error(str(error))

positions = st.session_state.virtual_positions.copy()
frame, summary = calculate_portfolio(
    UNIVERSE,
    market_data,
    positions,
    float(
        st.session_state.get(
            "capital_reference",
            capital_reference,
        )
    ),
)

cash = float(
    st.session_state.get(
        "virtual_cash",
        0.0,
    )
)

if status.contribution_recorded:
    plan_budget = (
        cash
        if use_existing_cash
        else min(
            float(status.amount),
            cash,
        )
    )
    total_for_targets = float(
        summary["total_value"]
    )
else:
    plan_budget = (
        cash + float(contribution)
        if use_existing_cash
        else float(contribution)
    )
    total_for_targets = (
        float(summary["total_value"])
        + float(contribution)
    )

plan, plan_summary_values = calculate_monthly_plan(
    frame=frame,
    budget=plan_budget,
    current_total_value=(
        total_for_targets - plan_budget
    ),
    brokerage_plan=selected_brokerage_plan,
    transactions=st.session_state.get(
        "virtual_transactions",
        pd.DataFrame(),
    ),
    max_orders=int(max_orders),
    strategy=strategy,
    respect_mm200=respect_mm200,
    minimum_score=minimum_score,
    always_allow_core=always_allow_core,
)

st.divider()
st.subheader("Plan d’achat calculé")

m1, m2, m3, m4 = st.columns(4)
m1.metric(
    "Budget analysé",
    euro(plan_summary_values["budget"]),
)
m2.metric(
    "Montant investi",
    euro(plan_summary_values["invested"]),
)
m3.metric(
    "Frais estimés",
    euro(plan_summary_values["fees"]),
)
m4.metric(
    "Reste en liquidités",
    euro(plan_summary_values["remaining"]),
)

st.caption(plan_summary(selected_brokerage_plan))

if plan.empty:
    st.warning(
        "Aucun ordre n’est possible avec les règles actuelles. "
        "Essaie d’augmenter le budget, d’autoriser le Socle Zen "
        "ou de diminuer le score minimal."
    )
else:
    st.dataframe(
        plan,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Quantité à acheter": (
                st.column_config.NumberColumn(
                    "Quantité",
                    format="%d",
                )
            ),
            "Cours (€)": (
                st.column_config.NumberColumn(
                    "Cours",
                    format="%.2f €",
                )
            ),
            "Montant brut (€)": (
                st.column_config.NumberColumn(
                    "Montant",
                    format="%.2f €",
                )
            ),
            "Frais (€)": (
                st.column_config.NumberColumn(
                    "Frais",
                    format="%.2f €",
                )
            ),
            "Coût total (€)": (
                st.column_config.NumberColumn(
                    "Coût total",
                    format="%.2f €",
                )
            ),
            "Score Alpha Zen": (
                st.column_config.ProgressColumn(
                    "Score",
                    min_value=0,
                    max_value=100,
                    format="%.0f",
                )
            ),
            "Poids après achat (%)": (
                st.column_config.NumberColumn(
                    "Poids après",
                    format="%.2f %%",
                )
            ),
        },
    )

    st.info(
        "Ce plan est une aide mécanique. Vérifie les actifs, "
        "les quantités et les frais avant de passer tes ordres "
        "réels dans Fortuneo."
    )

    can_execute = (
        status.contribution_recorded
        and not status.plan_executed
        and float(
            plan_summary_values["total_cost"]
        ) <= cash + 1e-9
    )

    confirm_execution = st.checkbox(
        "Je confirme l’exécution de tous ces achats "
        "dans le portefeuille virtuel.",
        disabled=not can_execute,
    )

    if status.plan_executed:
        st.success(
            "Le plan de ce mois a déjà été exécuté. "
            f"Montant : {euro(status.invested_amount)}, "
            f"frais : {euro(status.fees)}."
        )
    elif not status.contribution_recorded:
        st.warning(
            "Enregistre d’abord le versement mensuel. "
            "Le tableau ci-dessus reste une prévisualisation."
        )

    if st.button(
        "✅ Exécuter le plan mensuel virtuel",
        use_container_width=True,
        type="primary",
        disabled=not (
            can_execute
            and confirm_execution
        ),
    ):
        completed = []
        try:
            for _, order in plan.iterrows():
                transaction = execute_trade(
                    trade_type="Achat",
                    asset_name=str(order["Actif"]),
                    ticker=str(order["Ticker"]),
                    quantity=float(
                        order["Quantité à acheter"]
                    ),
                    price=float(order["Cours (€)"]),
                    fees=float(order["Frais (€)"]),
                    brokerage_plan=(
                        selected_brokerage_plan
                    ),
                )
                completed.append(transaction)

            invested_amount = float(
                plan["Montant brut (€)"].sum()
            )
            total_fees = float(
                plan["Frais (€)"].sum()
            )
            mark_plan_executed(
                invested_amount,
                total_fees,
            )

            updated_positions = (
                st.session_state.virtual_positions.copy()
            )
            updated_value = market_value(
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
                    updated_value + updated_cash
                ),
                positions_value=updated_value,
                cash=updated_cash,
                invested=invested_cost,
                capital_reference=float(
                    st.session_state.get(
                        "capital_reference",
                        capital_reference,
                    )
                ),
                unrealized_gain=(
                    updated_value - invested_cost
                ),
                transactions=st.session_state.get(
                    "virtual_transactions",
                    pd.DataFrame(),
                ),
            )
            save_daily_snapshot(snapshot)

            st.success(
                f"{len(completed)} achat(s) virtuel(s) exécuté(s)."
            )
            st.rerun()

        except Exception as error:
            st.error(
                "Exécution interrompue : "
                f"{error}"
            )

st.divider()
st.subheader("Pourquoi ces actifs ?")

if not plan.empty:
    for _, order in plan.iterrows():
        with st.expander(
            f"{order['Actif']} — "
            f"{int(order['Quantité à acheter'])} unité(s)"
        ):
            st.write(
                f"**Poche :** {order['Poche']}"
            )
            st.write(
                f"**Score Alpha Zen :** "
                f"{order['Score Alpha Zen']:.0f}/100"
            )
            st.write(
                f"**Signal :** {order['Signal']}"
            )
            st.write(
                f"**Coût avec frais :** "
                f"{euro(order['Coût total (€)'])}"
            )
            st.write(
                f"**Poids estimé après achat :** "
                f"{order['Poids après achat (%)']:.2f} %"
            )

st.caption(
    "Important : Streamlit ne peut pas envoyer automatiquement "
    "un ordre réel à Fortuneo. L’application calcule les quantités "
    "et exécute seulement une simulation ; les ordres réels doivent "
    "être confirmés manuellement dans Fortuneo."
)
