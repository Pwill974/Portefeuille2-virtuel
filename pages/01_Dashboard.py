import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(layout="wide")

st.title("📈 Alpha Zen Pro")

# Données portefeuille

capital = 10000
investi = 9437
liquidites = 563
plus_value = 0

# KPI

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Valeur totale", f"{capital:,.0f} €")

with col2:
    st.metric("Investi", f"{investi:,.0f} €")

with col3:
    st.metric("Liquidités", f"{liquidites:,.0f} €")

with col4:
    st.metric("Plus-value", f"{plus_value:,.0f} €")

st.divider()

# Allocation stratégique

st.subheader("Répartition Alpha Zen")

alloc = pd.DataFrame({
    "Poche":[
        "Socle Zen",
        "Momentum",
        "Satellite"
    ],
    "Poids":[
        50,
        35,
        15
    ]
})

fig = px.pie(
    alloc,
    values="Poids",
    names="Poche",
    hole=0.65
)

st.plotly_chart(
    fig,
    use_container_width=True
)

st.divider()

# Répartition réelle

st.subheader("Répartition du portefeuille")

portfolio = pd.DataFrame({
    "Actif":[
        "MSCI World",
        "S&P500",
        "Nasdaq100",
        "Europe",
        "Emergents",
        "BNP Défense",
        "Schneider",
        "Air Liquide",
        "TotalEnergies",
        "Dassault Aviation",
        "Thales",
        "STMicroelectronics",
        "Sanofi"
    ],
    "Poids":[
        20,15,10,5,10,
        10,5,3,2,
        5,5,5,5
    ]
})

fig2 = px.bar(
    portfolio,
    x="Actif",
    y="Poids"
)

st.plotly_chart(
    fig2,
    use_container_width=True
)

st.divider()

st.subheader("Score Alpha Zen")

st.progress(89)

st.success("Portefeuille Alpha Zen : 89/100")
