import streamlit as st
import pandas as pd
import plotly.express as px

st.title("💼 Portefeuille Alpha Zen")

st.caption(
    "Portefeuille virtuel PEA — suivi des allocations et rééquilibrage mécanique."
)

# ---------------------------------------------------
# PARAMÈTRES
# ---------------------------------------------------

col_capital, col_cash = st.columns(2)

with col_capital:
    capital_reference = st.number_input(
        "Capital de référence",
        min_value=0.0,
        value=10000.0,
        step=500.0,
        format="%.2f",
    )

with col_cash:
    liquidites = st.number_input(
        "Liquidités disponibles",
        min_value=0.0,
        value=563.0,
        step=50.0,
        format="%.2f",
    )

# ---------------------------------------------------
# PORTEFEUILLE INITIAL
# ---------------------------------------------------

portfolio_initial = pd.DataFrame(
    {
        "Actif": [
            "Amundi PEA MSCI World",
            "Amundi PEA S&P 500",
            "Amundi PEA Nasdaq-100",
            "Amundi PEA MSCI Europe",
            "GUARD BNP Défense",
            "Schneider Electric",
            "Air Liquide",
            "TotalEnergies",
            "Dassault Aviation",
            "Thales",
            "STMicroelectronics",
            "Sanofi",
            "Amundi PEA Émergents",
        ],
        "ISIN": [
            "FR001400U5Q4",
            "FR0011871128",
            "FR0011871110",
            "FR0013412038",
            "LU3047998896",
            "FR0000121972",
            "FR0000120073",
            "FR0014000MR3",
            "FR0014004L86",
            "FR0000121329",
            "NL0000226223",
            "FR0000120578",
            "FR0013412020",
        ],
        "Poche": [
            "Socle Zen",
            "Socle Zen",
            "Socle Zen",
            "Socle Zen",
            "Momentum",
            "Momentum",
            "Momentum",
            "Momentum",
            "Momentum",
            "Momentum",
            "Satellite",
            "Momentum",
            "Satellite",
        ],
        "Allocation cible (%)": [
            20.0,
            15.0,
            10.0,
            5.0,
            10.0,
            5.0,
            3.0,
            2.0,
            5.0,
            5.0,
            5.0,
            5.0,
            10.0,
        ],
    }
)

# Valeurs initiales calculées à partir de l'allocation cible
portfolio_initial["Investi (€)"] = (
    capital_reference * portfolio_initial["Allocation cible (%)"] / 100
)

portfolio_initial["Valeur actuelle (€)"] = portfolio_initial["Investi (€)"]

if "portfolio_editor" not in st.session_state:
    st.session_state.portfolio_editor = portfolio_initial.copy()

# ---------------------------------------------------
# ÉDITEUR DE PORTEFEUILLE
# ---------------------------------------------------

st.subheader("Positions")

st.info(
    "Pour le moment, renseigne manuellement les montants investis et les "
    "valeurs actuelles. La connexion automatique aux cours sera ajoutée ensuite."
)

edited = st.data_editor(
    st.session_state.portfolio_editor,
    use_container_width=True,
    hide_index=True,
    num_rows="fixed",
    column_config={
        "Actif": st.column_config.TextColumn(
            "Actif",
            disabled=True,
        ),
        "ISIN": st.column_config.TextColumn(
            "ISIN",
            disabled=True,
        ),
        "Poche": st.column_config.SelectboxColumn(
            "Poche",
            options=["Socle Zen", "Momentum", "Satellite"],
        ),
        "Allocation cible (%)": st.column_config.NumberColumn(
            "Cible",
            min_value=0.0,
            max_value=100.0,
            step=0.5,
            format="%.1f %%",
        ),
        "Investi (€)": st.column_config.NumberColumn(
            "Investi",
            min_value=0.0,
            step=10.0,
            format="%.2f €",
        ),
        "Valeur actuelle (€)": st.column_config.NumberColumn(
            "Valeur",
            min_value=0.0,
            step=10.0,
            format="%.2f €",
        ),
    },
    key="portfolio_data_editor",
)

st.session_state.portfolio_editor = edited.copy()

# ---------------------------------------------------
# CALCULS
# ---------------------------------------------------

df = edited.copy()

df["Plus-value (€)"] = df["Valeur actuelle (€)"] - df["Investi (€)"]

df["Plus-value (%)"] = (
    df["Plus-value (€)"]
    .div(df["Investi (€)"].replace(0, pd.NA))
    .mul(100)
    .fillna(0)
)

valeur_positions = float(df["Valeur actuelle (€)"].sum())
montant_investi = float(df["Investi (€)"].sum())
plus_value = valeur_positions - montant_investi
valeur_totale = valeur_positions + liquidites

if valeur_positions > 0:
    df["Poids réel (%)"] = (
        df["Valeur actuelle (€)"] / valeur_positions * 100
    )
else:
    df["Poids réel (%)"] = 0.0

df["Écart cible (%)"] = (
    df["Poids réel (%)"] - df["Allocation cible (%)"]
)

def decision_reequilibrage(ecart: float) -> str:
    if ecart <= -1:
        return "🟢 Renforcer"
    if ecart >= 1:
        return "🟠 Alléger"
    return "✅ Équilibré"

df["Signal allocation"] = df["Écart cible (%)"].apply(
    decision_reequilibrage
)

# ---------------------------------------------------
# KPI
# ---------------------------------------------------

st.divider()

kpi1, kpi2 = st.columns(2)
kpi3, kpi4 = st.columns(2)

with kpi1:
    st.metric(
        "Valeur totale",
        f"{valeur_totale:,.2f} €".replace(",", " "),
    )

with kpi2:
    st.metric(
        "Montant investi",
        f"{montant_investi:,.2f} €".replace(",", " "),
    )

with kpi3:
    st.metric(
        "Plus-value",
        f"{plus_value:+,.2f} €".replace(",", " "),
    )

with kpi4:
    st.metric(
        "Liquidités",
        f"{liquidites:,.2f} €".replace(",", " "),
    )

# ---------------------------------------------------
# GRAPHIQUES
# ---------------------------------------------------

st.divider()
st.subheader("Répartition du portefeuille")

poche_df = (
    df.groupby("Poche", as_index=False)["Valeur actuelle (€)"]
    .sum()
)

graph1, graph2 = st.columns(2)

with graph1:
    fig_poches = px.pie(
        poche_df,
        values="Valeur actuelle (€)",
        names="Poche",
        hole=0.62,
        title="Répartition stratégique réelle",
        color="Poche",
        color_discrete_map={
            "Socle Zen": "#00D8B4",
            "Momentum": "#3887F6",
            "Satellite": "#F5A000",
        },
    )

    fig_poches.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend_title_text="",
    )

    st.plotly_chart(fig_poches, use_container_width=True)

with graph2:
    fig_actifs = px.bar(
        df.sort_values("Poids réel (%)", ascending=True),
        x="Poids réel (%)",
        y="Actif",
        orientation="h",
        title="Poids réel par actif",
        color="Poche",
        color_discrete_map={
            "Socle Zen": "#00D8B4",
            "Momentum": "#3887F6",
            "Satellite": "#F5A000",
        },
    )

    fig_actifs.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend_title_text="",
        xaxis_title="Poids réel (%)",
        yaxis_title="",
    )

    st.plotly_chart(fig_actifs, use_container_width=True)

# ---------------------------------------------------
# TABLEAU D'ANALYSE
# ---------------------------------------------------

st.divider()
st.subheader("Analyse des positions")

display_columns = [
    "Actif",
    "Poche",
    "Allocation cible (%)",
    "Poids réel (%)",
    "Écart cible (%)",
    "Investi (€)",
    "Valeur actuelle (€)",
    "Plus-value (€)",
    "Plus-value (%)",
    "Signal allocation",
]

st.dataframe(
    df[display_columns].style.format(
        {
            "Allocation cible (%)": "{:.1f} %",
            "Poids réel (%)": "{:.1f} %",
            "Écart cible (%)": "{:+.1f} %",
            "Investi (€)": "{:,.2f} €",
            "Valeur actuelle (€)": "{:,.2f} €",
            "Plus-value (€)": "{:+,.2f} €",
            "Plus-value (%)": "{:+.2f} %",
        }
    ),
    use_container_width=True,
    hide_index=True,
)

# ---------------------------------------------------
# CONTRÔLE DE L'ALLOCATION
# ---------------------------------------------------

st.divider()
st.subheader("Contrôle Alpha Zen")

allocation_poches = (
    df.groupby("Poche")["Poids réel (%)"]
    .sum()
    .reindex(["Socle Zen", "Momentum", "Satellite"])
    .fillna(0)
)

targets = {
    "Socle Zen": 50.0,
    "Momentum": 35.0,
    "Satellite": 15.0,
}

for poche, cible in targets.items():
    reel = float(allocation_poches.get(poche, 0))
    ecart = reel - cible

    st.write(
        f"**{poche}** : {reel:.1f} % "
        f"— cible {cible:.1f} % "
        f"— écart {ecart:+.1f} %"
    )

    st.progress(
        min(max(int(reel), 0), 100)
    )

st.caption(
    "Les signaux affichés sont des indications mécaniques de rééquilibrage, "
    "pas des recommandations personnalisées d’achat ou de vente."
)
