from __future__ import annotations

import pandas as pd
import streamlit as st

from services.auth import (
    require_authentication,
    show_logout_button,
)
from services.portfolio_persistence_service import (
    fetch_live_valuation,
    fetch_saved_market_state,
    persistence_health,
    repair_session_pru_from_transactions,
)
from services.supabase_service import (
    cloud_status,
    fetch_cloud_state,
    load_cloud_state_into_session,
)
from services.trading_service import (
    save_current_state_to_cloud,
)


st.set_page_config(
    page_title="Alpha Zen Pro — État permanent",
    page_icon="☁️",
    layout="wide",
)

require_authentication()
show_logout_button()
load_cloud_state_into_session()

st.title("☁️ État permanent du portefeuille")
st.caption(
    "Cette page permet de contrôler que les quantités, PRU, "
    "liquidités, derniers cours et plus-values sont bien conservés."
)

status = cloud_status()
positions = st.session_state.get(
    "virtual_positions",
    pd.DataFrame(),
)
health = persistence_health(positions)
valuation = fetch_live_valuation()
saved_market = fetch_saved_market_state()

k1, k2, k3, k4 = st.columns(4)
k1.metric(
    "Supabase",
    "Connecté"
    if status["configured"] and not status["error"]
    else "Erreur",
)
k2.metric(
    "Positions actives",
    health["active_positions"],
)
k3.metric(
    "PRU manquants",
    health["missing_pru"],
)
k4.metric(
    "Cours sauvegardés",
    len(saved_market),
)

if status["error"]:
    st.error(status["error"])

if st.session_state.get("az_cloud_load_failed"):
    st.error(
        "Le dernier chargement Supabase a échoué. "
        "Le portefeuille n'a pas été remplacé par une copie neuve."
    )

if health["healthy"]:
    st.success(
        "Les positions actives possèdent toutes un PRU. "
        "Les plus-values peuvent être recalculées après chaque retour."
    )
else:
    st.warning(
        "Certaines positions ont un PRU nul. "
        "Utilise la réparation depuis l'historique ou renseigne "
        "le PRU dans la page Portefeuille."
    )

c1, c2, c3 = st.columns(3)

with c1:
    if st.button(
        "🔄 Recharger Supabase",
        use_container_width=True,
    ):
        st.session_state["az_cloud_checked"] = False
        load_cloud_state_into_session(force=True)
        st.rerun()

with c2:
    if st.button(
        "🧰 Réparer les PRU",
        use_container_width=True,
    ):
        repaired = repair_session_pru_from_transactions()
        if repaired:
            save_current_state_to_cloud()
            st.success(
                f"{repaired} PRU réparé(s) et sauvegardé(s)."
            )
        else:
            st.info(
                "Aucun PRU réparable à partir des transactions."
            )

with c3:
    if st.button(
        "☁️ Sauvegarder maintenant",
        use_container_width=True,
    ):
        if save_current_state_to_cloud():
            st.success("Sauvegarde terminée.")
        else:
            st.error("Sauvegarde impossible.")

if valuation:
    st.subheader("Dernière valorisation persistante")
    v1, v2, v3, v4 = st.columns(4)
    v1.metric(
        "Valeur totale",
        f"{float(valuation.get('total_value', 0)):,.2f} €",
    )
    v2.metric(
        "Plus-value latente",
        f"{float(valuation.get('unrealized_gain', 0)):+,.2f} €",
    )
    v3.metric(
        "Performance",
        f"{float(valuation.get('performance', 0)):+.2f} %",
    )
    v4.metric(
        "Dernière mise à jour",
        str(valuation.get("updated_at", "—"))[:19],
    )

st.subheader("Positions sauvegardées")
if positions is None or positions.empty:
    st.info("Aucune position chargée.")
else:
    st.dataframe(
        positions,
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
        },
    )

st.caption(
    "Une application Streamlit peut dormir lorsqu'elle n'est pas "
    "utilisée. Les données permanentes restent dans Supabase, et le "
    "workflow GitHub optionnel met la valorisation à jour sans ouvrir "
    "l'application."
)
