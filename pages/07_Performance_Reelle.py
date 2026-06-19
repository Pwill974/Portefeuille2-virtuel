from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from services.auth import require_authentication, show_logout_button
from services.performance_history_service import (
    fetch_performance_history,
    performance_statistics,
)


st.set_page_config(
    page_title="Alpha Zen Pro — Performance réelle",
    page_icon="📈",
    layout="wide",
)

require_authentication()
show_logout_button()

st.title("📈 Performance réelle")
st.caption(
    "Historique quotidien enregistré dans Supabase, "
    "net des frais de courtage saisis ou calculés."
)

history = fetch_performance_history()

if history is None or history.empty:
    st.info(
        "Aucun historique n'est encore disponible. "
        "Ouvre le Dashboard ou effectue une transaction "
        "pour créer le premier relevé quotidien."
    )
    st.stop()

history["Date"] = pd.to_datetime(
    history["Date"],
    errors="coerce",
)
history = history.dropna(subset=["Date"]).sort_values("Date")
stats = performance_statistics(history)

last = history.iloc[-1]

k1, k2, k3, k4 = st.columns(4)
k1.metric(
    "Valeur totale",
    f"{last['Valeur totale (€)']:,.2f} €",
)
k2.metric(
    "Performance nette",
    f"{last['Performance nette (%)']:+.2f} %",
)
k3.metric(
    "Frais cumulés",
    f"{last['Frais cumulés (€)']:,.2f} €",
)
k4.metric(
    "Max drawdown",
    f"{stats['max_drawdown']:.2f} %",
)

st.divider()

fig_perf = px.line(
    history,
    x="Date",
    y="Performance nette (%)",
    title="Performance réelle nette",
)
fig_perf.update_traces(line=dict(width=3))
fig_perf.update_layout(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    yaxis_ticksuffix=" %",
)
st.plotly_chart(
    fig_perf,
    use_container_width=True,
    config={"displayModeBar": False},
)

chart_data = history.melt(
    id_vars="Date",
    value_vars=[
        "Valeur totale (€)",
        "Capital de référence (€)",
    ],
    var_name="Série",
    value_name="Montant (€)",
)

fig_value = px.line(
    chart_data,
    x="Date",
    y="Montant (€)",
    color="Série",
    title="Valeur du portefeuille et capital de référence",
)
fig_value.update_layout(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
)
st.plotly_chart(
    fig_value,
    use_container_width=True,
    config={"displayModeBar": False},
)

st.subheader("Historique quotidien")
st.dataframe(
    history,
    hide_index=True,
    use_container_width=True,
    column_config={
        "Date": st.column_config.DateColumn(
            "Date",
            format="DD/MM/YYYY",
        ),
        "Valeur totale (€)": st.column_config.NumberColumn(
            "Valeur totale",
            format="%.2f €",
        ),
        "Frais cumulés (€)": st.column_config.NumberColumn(
            "Frais cumulés",
            format="%.2f €",
        ),
        "Performance nette (%)": st.column_config.NumberColumn(
            "Performance nette",
            format="%+.2f %%",
        ),
    },
)

st.caption(
    "L'historique réel commence à la date d'installation de ce module. "
    "Il ne reconstitue pas automatiquement les périodes antérieures."
)
