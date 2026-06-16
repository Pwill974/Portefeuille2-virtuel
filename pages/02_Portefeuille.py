import math

import pandas as pd
import plotly.express as px
import streamlit as st

from services.yahoo_services import get_market_snapshot, mm200_signal


st.title("💼 Portefeuille Alpha Zen")
st.caption(
    "Cours automatiques, portefeuille virtuel et contrôle de l’allocation cible."
)


UNIVERSE = pd.DataFrame(
    [
        {
            "Actif": "Amundi PEA MSCI World",
            "ISIN": "FR001400U5Q4",
            "Ticker": "DCAM.PA",
            "Poche": "Socle Zen",
            "Allocation cible (%)": 20.0,
        },
        {
            "Actif": "Amundi PEA S&P 500",
            "ISIN": "FR0011871128",
            "Ticker": "PSP5.PA",
            "Poche": "Socle Zen",
            "Allocation cible (%)": 15.0,
        },
        {
            "Actif": "Amundi PEA Nasdaq-100",
            "ISIN": "FR0011871110",
            "Ticker": "PUST.PA",
            "Poche": "Socle Zen",
            "Allocation cible (%)": 10.0,
        },
        {
            "Actif": "Amundi PEA MSCI Europe",
            "ISIN": "FR0013412038",
            "Ticker": "PCEU.PA",
            "Poche": "Socle Zen",
            "Allocation cible (%)": 5.0,
        },
        {
            "Actif": "GUARD BNP Défense",
            "ISIN": "LU3047998896",
            "Ticker": "GUARD.PA",
            "Poche": "Momentum",
            "Allocation cible (%)": 10.0,
        },
        {
            "Actif": "Schneider Electric",
            "ISIN": "FR0000121972",
            "Ticker": "SU.PA",
            "Poche": "Momentum",
            "Allocation cible (%)": 5.0,
        },
        {
            "Actif": "Air Liquide",
            "ISIN": "FR0000120073",
            "Ticker": "AI.PA",
            "Poche": "Momentum",
            "Allocation cible (%)": 3.0,
        },
        {
            "Actif": "TotalEnergies",
            "ISIN": "FR0000120271",
            "Ticker": "TTE.PA",
            "Poche": "Momentum",
            "Allocation cible (%)": 2.0,
        },
        {
            "Actif": "Dassault Aviation",
            "ISIN": "FR0014004L86",
            "Ticker": "AM.PA",
            "Poche": "Momentum",
            "Allocation cible (%)": 5.0,
        },
        {
            "Actif": "Thales",
            "ISIN": "FR0000121329",
            "Ticker": "HO.PA",
            "Poche": "Momentum",
            "Allocation cible (%)": 5.0,
        },
        {
            "Actif": "STMicroelectronics",
            "ISIN": "NL0000226223",
            "Ticker": "STM.PA",
            "Poche": "Satellite",
            "Allocation cible (%)": 5.0,
        },
        {
            "Actif": "Sanofi",
            "ISIN": "FR0000120578",
            "Ticker": "SAN.PA",
            "Poche": "Momentum",
            "Allocation cible (%)": 5.0,
        },
        {
            "Actif": "Amundi PEA Émergents",
            "ISIN": "FR0013412020",
            "Ticker": "PAEEM.PA",
            "Poche": "Satellite",
            "Allocation cible (%)": 10.0,
        },
    ]
)


@st.cache_data(ttl=900, show_spinner=False)
def load_market_data(tickers: tuple[str, ...]) -> pd.DataFrame:
    return get_market_snapshot(list(tickers))


def euro(value: float) -> str:
    return f"{value:,.2f} €".replace(",", " ").replace(".", ",")


def build_target_positions(
    universe: pd.DataFrame,
    market: pd.DataFrame,
    capital: float,
) -> pd.DataFrame:
    frame = universe.merge(market, on="Ticker", how="left")
    frame["Montant cible (€)"] = (
        capital * frame["Allocation cible (%)"] / 100.0
    )

    def quantity_from_target(row: pd.Series) -> int:
        price = row["Cours (€)"]
        if pd.isna(price) or float(price) <= 0:
            return 0
        return max(math.floor(float(row["Montant cible (€)"]) / float(price)), 0)

    frame["Quantité"] = frame.apply(quantity_from_target, axis=1)
    frame["PRU (€)"] = frame["Cours (€)"]
    return frame


settings_col, refresh_col = st.columns([3, 1])

with settings_col:
    capital_reference = st.number_input(
        "Capital virtuel à répartir",
        min_value=0.0,
        value=10_000.0,
        step=500.0,
        format="%.2f",
    )

with refresh_col:
    st.write("")
    st.write("")
    if st.button("🔄 Actualiser les cours", use_container_width=True):
        load_market_data.clear()
        st.rerun()


with st.spinner("Téléchargement des derniers cours disponibles…"):
    market_data = load_market_data(tuple(UNIVERSE["Ticker"].tolist()))

missing = market_data.loc[
    market_data["Statut données"] != "OK", "Ticker"
].tolist()

if missing:
    st.warning(
        "Cours indisponible pour : "
        + ", ".join(missing)
        + ". Les autres lignes restent calculées."
    )

initial_positions = build_target_positions(
    UNIVERSE,
    market_data,
    capital_reference,
)

if "virtual_positions" not in st.session_state:
    st.session_state.virtual_positions = initial_positions[
        ["Ticker", "Quantité", "PRU (€)"]
    ].copy()

if st.button("🎯 Recalculer les quantités selon l’allocation cible"):
    st.session_state.virtual_positions = initial_positions[
        ["Ticker", "Quantité", "PRU (€)"]
    ].copy()
    st.rerun()


positions_input = UNIVERSE.merge(
    st.session_state.virtual_positions,
    on="Ticker",
    how="left",
)

st.subheader("Quantités du portefeuille virtuel")
st.caption(
    "Les cours sont automatiques. Tu peux modifier seulement la quantité et le PRU."
)

edited_positions = st.data_editor(
    positions_input[
        [
            "Actif",
            "Ticker",
            "Poche",
            "Allocation cible (%)",
            "Quantité",
            "PRU (€)",
        ]
    ],
    hide_index=True,
    use_container_width=True,
    num_rows="fixed",
    column_config={
        "Actif": st.column_config.TextColumn("Actif", disabled=True),
        "Ticker": st.column_config.TextColumn("Ticker", disabled=True),
        "Poche": st.column_config.TextColumn("Poche", disabled=True),
        "Allocation cible (%)": st.column_config.NumberColumn(
            "Cible",
            format="%.1f %%",
            disabled=True,
        ),
        "Quantité": st.column_config.NumberColumn(
            "Quantité",
            min_value=0.0,
            step=1.0,
            format="%.4f",
        ),
        "PRU (€)": st.column_config.NumberColumn(
            "PRU",
            min_value=0.0,
            step=0.01,
            format="%.2f €",
        ),
    },
    key="positions_editor",
)

st.session_state.virtual_positions = edited_positions[
    ["Ticker", "Quantité", "PRU (€)"]
].copy()


df = (
    UNIVERSE.merge(
        st.session_state.virtual_positions,
        on="Ticker",
        how="left",
    )
    .merge(
        market_data,
        on="Ticker",
        how="left",
    )
)

df["Quantité"] = pd.to_numeric(df["Quantité"], errors="coerce").fillna(0.0)
df["PRU (€)"] = pd.to_numeric(df["PRU (€)"], errors="coerce").fillna(0.0)
df["Cours (€)"] = pd.to_numeric(df["Cours (€)"], errors="coerce")

df["Investi (€)"] = df["Quantité"] * df["PRU (€)"]
df["Valeur actuelle (€)"] = df["Quantité"] * df["Cours (€)"].fillna(0.0)
df["Plus-value (€)"] = df["Valeur actuelle (€)"] - df["Investi (€)"]
df["Plus-value (%)"] = (
    df["Plus-value (€)"]
    .div(df["Investi (€)"].replace(0, pd.NA))
    .mul(100)
    .fillna(0.0)
)

df["Signal MM200"] = df.apply(
    lambda row: mm200_signal(row["Cours (€)"], row["MM200 (€)"]),
    axis=1,
)

valeur_positions = float(df["Valeur actuelle (€)"].sum())
montant_investi = float(df["Investi (€)"].sum())
plus_value = valeur_positions - montant_investi
liquidites_virtuelles = max(capital_reference - montant_investi, 0.0)
valeur_totale = valeur_positions + liquidites_virtuelles

if valeur_positions > 0:
    df["Poids réel (%)"] = (
        df["Valeur actuelle (€)"] / valeur_positions * 100.0
    )
else:
    df["Poids réel (%)"] = 0.0

df["Écart cible (%)"] = (
    df["Poids réel (%)"] - df["Allocation cible (%)"]
)

kpi1, kpi2 = st.columns(2)
kpi3, kpi4 = st.columns(2)

with kpi1:
    st.metric("Valeur totale", euro(valeur_totale))

with kpi2:
    st.metric("Valeur des positions", euro(valeur_positions))

with kpi3:
    st.metric(
        "Plus-value",
        euro(plus_value),
        delta=(
            f"{(plus_value / montant_investi * 100):+.2f} %"
            if montant_investi > 0
            else "0,00 %"
        ),
    )

with kpi4:
    st.metric("Liquidités virtuelles", euro(liquidites_virtuelles))


st.divider()
st.subheader("Répartition réelle")

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
        margin=dict(l=10, r=10, t=20, b=10),
    )
    st.plotly_chart(fig_poches, use_container_width=True)

with graph2:
    fig_actifs = px.bar(
        df.sort_values("Poids réel (%)", ascending=True),
        x="Poids réel (%)",
        y="Actif",
        orientation="h",
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
        margin=dict(l=10, r=10, t=20, b=10),
    )
    st.plotly_chart(fig_actifs, use_container_width=True)


st.divider()
st.subheader("Valeurs automatiques des actifs")

display_columns = [
    "Actif",
    "Ticker",
    "Quantité",
    "PRU (€)",
    "Cours (€)",
    "Valeur actuelle (€)",
    "Plus-value (€)",
    "Plus-value (%)",
    "Poids réel (%)",
    "MM200 (€)",
    "Momentum 6M (%)",
    "Signal MM200",
    "Date du cours",
]

display_df = df[display_columns].copy()

st.dataframe(
    display_df.style.format(
        {
            "Quantité": "{:,.4f}",
            "PRU (€)": "{:,.2f} €",
            "Cours (€)": "{:,.2f} €",
            "Valeur actuelle (€)": "{:,.2f} €",
            "Plus-value (€)": "{:+,.2f} €",
            "Plus-value (%)": "{:+.2f} %",
            "Poids réel (%)": "{:.2f} %",
            "MM200 (€)": "{:,.2f} €",
            "Momentum 6M (%)": "{:+.2f} %",
            "Date du cours": lambda value: (
                value.strftime("%d/%m/%Y")
                if pd.notna(value)
                else "—"
            ),
        }
    ),
    hide_index=True,
    use_container_width=True,
)


csv_export = st.session_state.virtual_positions.to_csv(
    index=False,
    sep=";",
).encode("utf-8-sig")

st.download_button(
    "⬇️ Sauvegarder mes quantités et PRU",
    data=csv_export,
    file_name="positions_alpha_zen.csv",
    mime="text/csv",
)

st.caption(
    "Les prix proviennent de Yahoo Finance via yfinance et peuvent être retardés. "
    "Ils servent au suivi indicatif, pas à l’exécution d’ordres."
)
