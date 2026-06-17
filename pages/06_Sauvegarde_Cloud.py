from __future__ import annotations

import pandas as pd
import streamlit as st

from services.auth import require_authentication, show_logout_button
from services.supabase_service import (
    SupabaseConfigurationError,
    SupabaseSyncError,
    cloud_status,
    load_cloud_state_into_session,
    supabase_is_configured,
    test_supabase_connection,
)
from services.trading_service import save_current_state_to_cloud


st.set_page_config(
    page_title="Alpha Zen Pro — Sauvegarde Cloud",
    page_icon="☁️",
    layout="wide",
)

require_authentication()
show_logout_button()

st.title("☁️ Sauvegarde Supabase")
st.caption(
    "Contrôle de la sauvegarde permanente des positions, "
    "liquidités et transactions."
)

status = cloud_status()

c1, c2, c3 = st.columns(3)
c1.metric(
    "Configuration",
    "Active" if status["configured"] else "Absente",
)
c2.metric(
    "Données cloud",
    "Présentes" if status["has_data"] else "Non chargées",
)
c3.metric(
    "Profil",
    status["profile_id"],
)

if not supabase_is_configured():
    st.error(
        "Supabase n'est pas encore configuré dans les Secrets Streamlit."
    )
    st.code(
        """[supabase]
url = "https://TON-PROJET.supabase.co"
secret_key = "sb_secret_..."
profile_id = "william"
""",
        language="toml",
    )
    st.stop()

if status["error"]:
    st.warning(status["error"])

button1, button2, button3 = st.columns(3)

with button1:
    if st.button(
        "🔌 Tester la connexion",
        use_container_width=True,
    ):
        try:
            result = test_supabase_connection()
            st.success(
                "Connexion réussie — profil "
                f"{result['profile_id']}."
            )
        except (
            SupabaseConfigurationError,
            SupabaseSyncError,
        ) as exc:
            st.error(str(exc))

with button2:
    if st.button(
        "⬇️ Recharger depuis Supabase",
        use_container_width=True,
    ):
        if load_cloud_state_into_session(force=True):
            st.success("Données Supabase rechargées.")
            st.rerun()
        else:
            st.warning(
                "Aucune sauvegarde n'a été trouvée ou la lecture a échoué."
            )

with button3:
    if st.button(
        "⬆️ Sauvegarder maintenant",
        use_container_width=True,
    ):
        if save_current_state_to_cloud():
            st.success("Sauvegarde terminée.")
            st.rerun()
        else:
            st.error(
                "Aucune position en mémoire ou synchronisation impossible."
            )

st.divider()
st.subheader("Données actuellement en mémoire")

positions = st.session_state.get(
    "virtual_positions",
    pd.DataFrame(),
)
transactions = st.session_state.get(
    "virtual_transactions",
    pd.DataFrame(),
)
cash = float(
    st.session_state.get("virtual_cash", 0.0)
)

m1, m2, m3 = st.columns(3)
m1.metric("Positions", len(positions))
m2.metric("Transactions", len(transactions))
m3.metric("Liquidités", f"{cash:,.2f} €")

if not positions.empty:
    st.dataframe(
        positions,
        hide_index=True,
        use_container_width=True,
    )

st.info(
    "Le fichier SQL doit avoir été exécuté dans Supabase. "
    "La clé secrète reste uniquement dans les Secrets Streamlit "
    "et ne doit jamais être placée sur GitHub."
)
