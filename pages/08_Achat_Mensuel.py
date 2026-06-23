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
    build_momentum_ranking,
    build_sell_recommendations,
    calculate_monthly_plan,
    get_monthly_status,
    load_monthly_settings,
    record_monthly_contribution,
    reunion_now,
    save_monthly_settings,
)
from services.performance_history_service import (
    load_brokerage_plan,
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
from services.portfolio_persistence_service import (
    hydrate_market_data,
    persistence_health,
    repair_session_pru_from_transactions,
    save_live_valuation,
    save_market_state,
)
from services.trading_service import (
    initialize_trading_state,
)


st.set_page_config(
    page_title="Alpha Zen Pro — Décision Momentum",
    page_icon="🧭",
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


def show_orders_link() -> None:
    if hasattr(st, "page_link"):
        st.page_link(
            "pages/04_Ordres.py",
            label="Ouvrir la page Acheter / Vendre",
            icon="💱",
            use_container_width=True,
        )
    else:
        st.info(
            "Ouvre la page « Acheter / Vendre » dans le menu "
            "de gauche pour saisir toi-même l'ordre."
        )


st.title("🧭 Centre de décision Momentum")
st.caption(
    "L'application analyse et indique quoi vendre ou acheter. "
    "Elle ne passe aucun ordre : c'est toi qui exécutes chaque "
    "opération dans la page Acheter / Vendre."
)

st.success(
    "Mode entraînement réel activé : aucune vente et aucun achat "
    "ne sont exécutés automatiquement."
)

with st.expander(
    "📘 La méthode suivie",
    expanded=False,
):
    st.markdown(
        """
1. **Vendre manuellement** les positions détenues qui passent
   sous leur MM200.
2. Revenir sur cette page après les ventes.
3. Classer les actifs restants par score Momentum.
4. Acheter manuellement les plus forts, uniquement s'ils sont
   au-dessus de la MM200 et sous leur allocation cible.
5. Conserver le reliquat si aucune part entière ne respecte
   encore les règles.
        """
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
        "☁️ Mode local : configure Supabase pour conserver "
        "durablement tes opérations."
    )

with st.spinner("Analyse des cours, MM200 et scores Momentum…"):
    market_data = load_market_data(
        tuple(UNIVERSE["Ticker"].tolist())
    )
    market_data = hydrate_market_data(market_data)
    try:
        save_market_state(market_data)
    except Exception as error:
        st.session_state["az_market_error"] = str(error)

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
repair_session_pru_from_transactions()

settings = load_monthly_settings()
brokerage_plan = load_brokerage_plan()
status = get_monthly_status()
now = reunion_now()

saved_score = float(
    settings.get(
        "monthly_min_score",
        60.0,
    )
    or 60.0
)
default_score = max(saved_score, 60.0)

with st.expander(
    "⚙️ Paramètres de décision",
    expanded=False,
):
    enabled = st.toggle(
        "Activer le rendez-vous mensuel",
        value=bool(
            settings.get(
                "monthly_plan_enabled",
                True,
            )
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
            "Jour de contrôle mensuel",
            min_value=1,
            max_value=28,
            value=int(
                settings.get(
                    "monthly_purchase_day",
                    5,
                )
            ),
            step=1,
        )
    with p3:
        max_orders = st.number_input(
            "Nombre maximal d'achats",
            min_value=1,
            max_value=5,
            value=min(
                max(
                    int(
                        settings.get(
                            "monthly_max_orders",
                            3,
                        )
                    ),
                    1,
                ),
                5,
            ),
            step=1,
        )

    p4, p5 = st.columns(2)
    with p4:
        minimum_score = st.number_input(
            "Score Momentum minimal",
            min_value=0.0,
            max_value=100.0,
            value=default_score,
            step=5.0,
            help=(
                "60/100 constitue un seuil raisonnablement "
                "sélectif pour commencer."
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

    st.info(
        "Les filtres MM200 et allocation cible restent obligatoires. "
        "Le programme fournit uniquement des indications."
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
                "monthly_strategy": "Momentum",
                "monthly_respect_mm200": True,
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
        "Le rendez-vous mensuel est désactivé. "
        "L'analyse reste visible, mais aucun rappel n'est affiché."
    )

due = (
    enabled
    and now.day >= int(purchase_day)
    and not status.contribution_recorded
)

if due:
    st.warning(
        f"📅 Contrôle mensuel à effectuer. "
        f"Versement prévu : {euro(contribution)}."
    )
elif status.contribution_recorded:
    st.success(
        f"✅ Versement du mois enregistré : "
        f"{euro(status.amount)}."
    )
else:
    st.info(
        f"Prochain contrôle prévu le {int(purchase_day)} du mois."
    )

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

k1, k2, k3, k4 = st.columns(4)
k1.metric("Liquidités actuelles", euro(cash))
k2.metric(
    "Valeur des positions",
    euro(summary["positions_value"]),
)
k3.metric(
    "Valeur totale",
    euro(summary["total_value"]),
)
k4.metric(
    "Score minimal",
    f"{minimum_score:.0f}/100",
)

if enabled and not status.contribution_recorded:
    st.subheader("0️⃣ Ajouter le versement du mois")
    st.write(
        "Cette action ajoute seulement les liquidités au portefeuille "
        "virtuel. Elle ne réalise aucun achat."
    )

    confirm_deposit = st.checkbox(
        "Je confirme l'ajout du versement mensuel."
    )
    if st.button(
        "➕ Ajouter le versement",
        use_container_width=True,
        disabled=not confirm_deposit,
    ):
        try:
            record_monthly_contribution(
                contribution,
                contribution,
            )
            st.success(
                "Versement enregistré. Tu peux maintenant "
                "suivre les indications de vente et d'achat."
            )
            st.rerun()
        except Exception as error:
            st.error(str(error))

st.divider()
st.header("1️⃣ Indications de vente")

sell_plan, sell_summary = build_sell_recommendations(
    frame=frame,
    brokerage_plan=selected_brokerage_plan,
    transactions=st.session_state.get(
        "virtual_transactions",
        pd.DataFrame(),
    ),
)

pending_sales = not sell_plan.empty

if pending_sales:
    st.error(
        "Des positions détenues sont sous leur MM200. "
        "La méthode Momentum indique de les vendre avant "
        "de calculer les achats définitifs."
    )

    v1, v2, v3, v4 = st.columns(4)
    v1.metric(
        "Ventes indiquées",
        int(sell_summary["orders"]),
    )
    v2.metric(
        "Montant brut estimé",
        euro(sell_summary["gross"]),
    )
    v3.metric(
        "Frais estimés",
        euro(sell_summary["fees"]),
    )
    v4.metric(
        "Liquidités nettes estimées",
        euro(sell_summary["net_proceeds"]),
    )

    st.dataframe(
        sell_plan,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Priorité vente": (
                st.column_config.NumberColumn(
                    "Ordre",
                    format="%d",
                )
            ),
            "Quantité à vendre": (
                st.column_config.NumberColumn(
                    "Quantité",
                    format="%.4f",
                )
            ),
            "Cours indicatif (€)": (
                st.column_config.NumberColumn(
                    "Cours",
                    format="%.2f €",
                )
            ),
            "Distance MM200 (%)": (
                st.column_config.NumberColumn(
                    "Distance MM200",
                    format="%.2f %%",
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
            "Montant brut (€)": (
                st.column_config.NumberColumn(
                    "Montant brut",
                    format="%.2f €",
                )
            ),
            "Frais estimés (€)": (
                st.column_config.NumberColumn(
                    "Frais",
                    format="%.2f €",
                )
            ),
            "Produit net estimé (€)": (
                st.column_config.NumberColumn(
                    "Produit net",
                    format="%.2f €",
                )
            ),
            "Plus-value estimée (€)": (
                st.column_config.NumberColumn(
                    "Résultat estimé",
                    format="%.2f €",
                )
            ),
        },
    )

    st.markdown(
        """
**Ce que tu dois faire :**

1. Ouvre la page **Acheter / Vendre**.
2. Choisis **Vente**.
3. Sélectionne le premier actif indiqué.
4. Saisis exactement la quantité affichée.
5. Vérifie le cours et les frais.
6. Confirme toi-même la vente virtuelle.
7. Répète pour chaque ligne, puis reviens ici.
        """
    )
    show_orders_link()

    if st.button(
        "🔄 J'ai effectué les ventes : actualiser l'analyse",
        use_container_width=True,
    ):
        st.cache_data.clear()
        st.rerun()
else:
    st.success(
        "Aucune position détenue n'est sous la MM200. "
        "Tu peux passer à la sélection des achats."
    )

st.divider()
st.header("2️⃣ Acheter les actifs les plus forts")

ranking = build_momentum_ranking(
    frame=frame,
    budget=max(cash, 0.0),
    current_total_value=float(
        summary["positions_value"]
    ),
    minimum_score=minimum_score,
)

with st.expander(
    "🔎 Voir le classement Momentum complet",
    expanded=pending_sales,
):
    if ranking.empty:
        st.info("Aucune donnée de classement disponible.")
    else:
        st.dataframe(
            ranking,
            hide_index=True,
            use_container_width=True,
            column_config={
                "Rang Momentum": (
                    st.column_config.NumberColumn(
                        "Rang",
                        format="%d",
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
                "Distance MM200 (%)": (
                    st.column_config.NumberColumn(
                        "Distance MM200",
                        format="%.2f %%",
                    )
                ),
                "Allocation cible (%)": (
                    st.column_config.NumberColumn(
                        "Cible",
                        format="%.2f %%",
                    )
                ),
                "Poids actuel (%)": (
                    st.column_config.NumberColumn(
                        "Poids actuel",
                        format="%.2f %%",
                    )
                ),
                "Écart à la cible (€)": (
                    st.column_config.NumberColumn(
                        "Écart cible",
                        format="%.2f €",
                    )
                ),
            },
        )

if pending_sales:
    st.warning(
        "Les meilleurs actifs sont visibles dans le classement, "
        "mais les quantités d'achat ne sont pas encore définitives. "
        "Effectue d'abord les ventes : les liquidités seront alors "
        "mises à jour et les quantités seront recalculées."
    )
elif cash <= 0.01:
    st.warning(
        "Aucune liquidité disponible. Ajoute le versement mensuel "
        "ou réalise les ventes indiquées avant d'acheter."
    )
else:
    buy_plan, buy_summary = calculate_monthly_plan(
        frame=frame,
        budget=cash,
        current_total_value=float(
            summary["positions_value"]
        ),
        brokerage_plan=selected_brokerage_plan,
        transactions=st.session_state.get(
            "virtual_transactions",
            pd.DataFrame(),
        ),
        max_orders=int(max_orders),
        strategy="Momentum",
        respect_mm200=True,
        minimum_score=minimum_score,
        always_allow_core=False,
        strict_target=True,
    )

    b1, b2, b3, b4, b5 = st.columns(5)
    b1.metric(
        "Budget disponible",
        euro(buy_summary["budget"]),
    )
    b2.metric(
        "Actifs admissibles",
        int(buy_summary["eligible_assets"]),
    )
    b3.metric(
        "Montant à investir",
        euro(buy_summary["invested"]),
    )
    b4.metric(
        "Frais estimés",
        euro(buy_summary["fees"]),
    )
    b5.metric(
        "Reliquat",
        euro(buy_summary["remaining"]),
    )

    st.caption(plan_summary(selected_brokerage_plan))

    if buy_plan.empty:
        st.warning(
            "Aucun achat ne respecte actuellement toutes les règles : "
            "MM200 positive, score minimal, allocation cible, prix "
            "d'une part et liquidités disponibles. Garde le cash."
        )
    else:
        st.success(
            "Voici les ordres à saisir toi-même, dans cet ordre."
        )

        st.dataframe(
            buy_plan,
            hide_index=True,
            use_container_width=True,
            column_config={
                "Rang Momentum": (
                    st.column_config.NumberColumn(
                        "Ordre",
                        format="%d",
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
                "Distance MM200 (%)": (
                    st.column_config.NumberColumn(
                        "Distance MM200",
                        format="%.2f %%",
                    )
                ),
                "Allocation cible (%)": (
                    st.column_config.NumberColumn(
                        "Cible maximum",
                        format="%.2f %%",
                    )
                ),
                "Poids avant achat (%)": (
                    st.column_config.NumberColumn(
                        "Poids avant",
                        format="%.2f %%",
                    )
                ),
                "Quantité à acheter": (
                    st.column_config.NumberColumn(
                        "Quantité",
                        format="%d",
                    )
                ),
                "Cours (€)": (
                    st.column_config.NumberColumn(
                        "Cours indicatif",
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
                "Poids après achat (%)": (
                    st.column_config.NumberColumn(
                        "Poids après",
                        format="%.2f %%",
                    )
                ),
                "Cible respectée": (
                    st.column_config.CheckboxColumn(
                        "Cible respectée",
                    )
                ),
            },
        )

        st.markdown(
            """
**Ce que tu dois faire :**

1. Ouvre la page **Acheter / Vendre**.
2. Choisis **Achat**.
3. Commence par le rang Momentum n°1.
4. Saisis la quantité indiquée.
5. Vérifie le cours réel et les frais.
6. Confirme toi-même l'achat virtuel.
7. Reviens ici après chaque ordre pour recalculer le suivant.
            """
        )
        show_orders_link()

        st.warning(
            "Les cours peuvent changer entre l'analyse et la saisie. "
            "Après chaque ordre, reviens ici et actualise avant de "
            "passer le suivant."
        )

        if st.button(
            "🔄 J'ai passé un ordre : recalculer",
            use_container_width=True,
        ):
            st.cache_data.clear()
            st.rerun()

st.divider()
st.subheader("✅ Checklist d'entraînement")

st.checkbox(
    "J'ai vérifié la MM200 avant chaque vente.",
    key="manual_check_sell",
)
st.checkbox(
    "J'ai contrôlé le score et le rang Momentum avant chaque achat.",
    key="manual_check_rank",
)
st.checkbox(
    "J'ai vérifié la quantité, le cours et les frais.",
    key="manual_check_fees",
)
st.checkbox(
    "J'ai respecté l'allocation cible et conservé le reliquat inutile.",
    key="manual_check_target",
)

st.caption(
    "Cette page fournit des indications mécaniques, pas une garantie "
    "de gain ni un conseil financier personnalisé. Les opérations "
    "réelles chez Fortuneo restent toujours sous ta responsabilité."
)
