from __future__ import annotations

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Alpha Zen Pro — Portefeuille sécurisé",
    page_icon="🛡️",
    layout="wide",
)

try:
    from services.auth import require_authentication, show_logout_button
except Exception:
    def require_authentication():
        return None
    def show_logout_button():
        return None

from services.safe_portfolio_service import build_secure_portfolio


require_authentication()
show_logout_button()


def euro(value: float) -> str:
    return f"{float(value):,.2f} €".replace(",", " ").replace(".", ",")


def pct(value: float) -> str:
    return f"{float(value) * 100:.2f} %".replace(".", ",")


st.title("🛡️ Portefeuille sécurisé")
st.caption(
    "Cette page lit directement Supabase. Elle ne réinitialise pas les quantités et "
    "n'utilise pas les cours à zéro pour recalculer le portefeuille."
)

if st.button("🔄 Recharger depuis Supabase", use_container_width=True):
    st.cache_data.clear()
    st.cache_resource.clear()
    st.rerun()

try:
    portfolio, totals, missing_prices = build_secure_portfolio()
except Exception as error:
    st.error(str(error))
    st.stop()

if missing_prices:
    st.warning(
        "Cours manquants dans az_market_prices pour : "
        + ", ".join(missing_prices)
        + ". Pour éviter une remise à zéro, la page utilise provisoirement le PRU "
        + "sur ces lignes. Lance GitHub Actions update-portfolio pour remplir les cours."
    )

c1, c2, c3, c4 = st.columns(4)
c1.metric("Valeur totale", euro(totals["total_value"]))
c2.metric("Positions", euro(totals["positions_value"]))
c3.metric("Liquidités", euro(totals["cash"]))
c4.metric("Capital versé", euro(totals["capital_reference"]))

st.divider()

st.subheader("Répartition du portefeuille")

chart = portfolio[["Ticker", "Valeur"]].copy()
chart = chart[chart["Valeur"] > 0]
if chart.empty:
    st.info("Aucune position valorisée.")
else:
    st.bar_chart(chart.set_index("Ticker"), use_container_width=True)

st.subheader("Quantités sauvegardées")

display = portfolio.copy()
for col in ["Cible", "Poids actuel", "Écart cible", "+/- %"]:
    display[col] = display[col] * 100

st.dataframe(
    display[
        [
            "Ticker",
            "Nom",
            "Poche",
            "Quantité",
            "PRU",
            "Cours",
            "Source cours",
            "Valeur",
            "+/- €",
            "+/- %",
            "Cible",
            "Poids actuel",
            "Écart cible",
        ]
    ],
    hide_index=True,
    use_container_width=True,
    column_config={
        "Quantité": st.column_config.NumberColumn("Quantité", format="%.4f"),
        "PRU": st.column_config.NumberColumn("PRU", format="%.2f €"),
        "Cours": st.column_config.NumberColumn("Cours", format="%.2f €"),
        "Valeur": st.column_config.NumberColumn("Valeur", format="%.2f €"),
        "+/- €": st.column_config.NumberColumn("+/- €", format="%.2f €"),
        "+/- %": st.column_config.NumberColumn("+/- %", format="%.2f %%"),
        "Cible": st.column_config.NumberColumn("Cible %", format="%.2f %%"),
        "Poids actuel": st.column_config.NumberColumn("Poids actuel %", format="%.2f %%"),
        "Écart cible": st.column_config.NumberColumn("Écart cible %", format="%.2f %%"),
    },
)

st.error(
    "Sécurité : ne clique pas sur un bouton de recalcul global tant que les cours "
    "sont indisponibles. Les quantités doivent venir de az_positions, pas d'un recalcul."
)
