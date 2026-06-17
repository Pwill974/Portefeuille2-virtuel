import pandas as pd
import plotly.express as px
import streamlit as st

from services.auth import require_authentication, show_logout_button
from services.portfolio_engine import UNIVERSE, build_default_positions
from services.supabase_service import (
    cloud_status,
    load_cloud_state_into_session,
    supabase_is_configured,
)
from services.trading_service import (
    initialize_trading_state,
    reset_trading_state,
    save_current_state_to_cloud,
)
from services.yahoo_services import get_market_snapshot, mm200_signal


st.set_page_config(
    page_title="Alpha Zen Pro — Portefeuille",
    page_icon="💼",
    layout="wide",
)

require_authentication()
show_logout_button()
load_cloud_state_into_session()

st.title("💼 Portefeuille Alpha Zen")
st.caption(
    "Cours automatiques, quantités, PRU, liquidités "
    "et contrôle de l’allocation cible."
)


status = cloud_status()

if status["configured"]:
    if status["error"]:
        st.warning(
            "☁️ Supabase configuré, mais la dernière synchronisation "
            f"a échoué : {status['error']}"
        )
    else:
        st.success(
            "☁️ Sauvegarde Supabase active — "
            f"profil : {status['profile_id']}"
        )
else:
    st.info(
        "☁️ Supabase n'est pas encore configuré. "
        "La page fonctionne temporairement avec la mémoire Streamlit."
    )


@st.cache_data(ttl=900, show_spinner=False)
def load_market_data(tickers: tuple[str, ...]) -> pd.DataFrame:
    return get_market_snapshot(list(tickers))


def euro(value: float) -> str:
    return (
        f"{float(value):,.2f} €"
        .replace(",", " ")
        .replace(".", ",")
    )


settings_col, refresh_col = st.columns([3, 1])

with settings_col:
    capital_reference = st.number_input(
        "Capital virtuel à répartir",
        min_value=0.0,
        value=float(
            st.session_state.get(
                "cloud_capital_reference",
                10_000.0,
            )
        ),
        step=500.0,
        format="%.2f",
        key="portfolio_capital_reference",
    )

with refresh_col:
    st.write("")
    st.write("")
    if st.button(
        "🔄 Actualiser les cours",
        use_container_width=True,
    ):
        load_market_data.clear()
        st.rerun()


with st.spinner("Téléchargement des derniers cours disponibles…"):
    market_data = load_market_data(
        tuple(UNIVERSE["Ticker"].tolist())
    )

missing = market_data.loc[
    market_data["Statut données"] != "OK",
    "Ticker",
].tolist()

if missing:
    st.warning(
        "Cours indisponible pour : "
        + ", ".join(missing)
        + ". Les autres lignes restent calculées."
    )

initialize_trading_state(
    UNIVERSE,
    market_data,
    capital_reference,
    float(
        st.session_state.get(
            "cloud_monthly_contribution",
            1000.0,
        )
    ),
)

initial_positions = build_default_positions(
    UNIVERSE,
    market_data,
    capital_reference,
)

if st.button(
    "🎯 Recalculer les quantités selon l’allocation cible"
):
    reset_trading_state(
        UNIVERSE,
        market_data,
        capital_reference,
        float(
            st.session_state.get(
                "monthly_contribution",
                1000.0,
            )
        ),
    )
    st.rerun()

positions_input = UNIVERSE.merge(
    st.session_state.virtual_positions,
    on="Ticker",
    how="left",
)

st.subheader("Quantités du portefeuille virtuel")
st.caption(
    "Les cours sont automatiques. Tu peux modifier la quantité et le PRU, "
    "ou utiliser la page Acheter / Vendre pour enregistrer une opération."
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
        "Actif": st.column_config.TextColumn(
            "Actif",
            disabled=True,
        ),
        "Ticker": st.column_config.TextColumn(
            "Ticker",
            disabled=True,
        ),
        "Poche": st.column_config.TextColumn(
            "Poche",
            disabled=True,
        ),
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

previous_positions = (
    st.session_state.virtual_positions[
        ["Ticker", "Quantité", "PRU (€)"]
    ]
    .reset_index(drop=True)
    .copy()
)

new_positions = edited_positions[
    ["Ticker", "Quantité", "PRU (€)"]
].reset_index(drop=True)

st.session_state.virtual_positions = new_positions.copy()

if not new_positions.equals(previous_positions):
    save_current_state_to_cloud(
        capital_reference,
        float(
            st.session_state.get(
                "monthly_contribution",
                1000.0,
            )
        ),
    )


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

df["Quantité"] = pd.to_numeric(
    df["Quantité"],
    errors="coerce",
).fillna(0.0)
df["PRU (€)"] = pd.to_numeric(
    df["PRU (€)"],
    errors="coerce",
).fillna(0.0)
df["Cours (€)"] = pd.to_numeric(
    df["Cours (€)"],
    errors="coerce",
).fillna(0.0)

df["Investi (€)"] = df["Quantité"] * df["PRU (€)"]
df["Valeur actuelle (€)"] = (
    df["Quantité"] * df["Cours (€)"]
)
df["Plus-value (€)"] = (
    df["Valeur actuelle (€)"] - df["Investi (€)"]
)
df["Plus-value (%)"] = (
    df["Plus-value (€)"]
    .div(df["Investi (€)"].replace(0, pd.NA))
    .mul(100)
    .fillna(0.0)
)

df["Signal MM200"] = df.apply(
    lambda row: mm200_signal(
        row["Cours (€)"],
        row["MM200 (€)"],
    ),
    axis=1,
)

valeur_positions = float(
    df["Valeur actuelle (€)"].sum()
)
montant_investi = float(
    df["Investi (€)"].sum()
)
plus_value = valeur_positions - montant_investi
liquidites_virtuelles = float(
    st.session_state.get("virtual_cash", 0.0)
)
valeur_totale = (
    valeur_positions + liquidites_virtuelles
)

if valeur_positions > 0:
    df["Poids réel (%)"] = (
        df["Valeur actuelle (€)"]
        / valeur_positions
        * 100.0
    )
else:
    df["Poids réel (%)"] = 0.0

df["Écart cible (%)"] = (
    df["Poids réel (%)"]
    - df["Allocation cible (%)"]
)

kpi1, kpi2 = st.columns(2)
kpi3, kpi4 = st.columns(2)

kpi1.metric(
    "Valeur totale",
    euro(valeur_totale),
)
kpi2.metric(
    "Valeur des positions",
    euro(valeur_positions),
)
kpi3.metric(
    "Plus-value latente",
    euro(plus_value),
    delta=(
        f"{(plus_value / montant_investi * 100):+.2f} %"
        if montant_investi > 0
        else "0,00 %"
    ),
)
kpi4.metric(
    "Liquidités virtuelles",
    euro(liquidites_virtuelles),
)

st.divider()
st.subheader("Répartition réelle")

poche_df = (
    df.groupby(
        "Poche",
        as_index=False,
    )["Valeur actuelle (€)"]
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
        margin=dict(
            l=10,
            r=10,
            t=20,
            b=10,
        ),
    )
    st.plotly_chart(
        fig_poches,
        use_container_width=True,
    )

with graph2:
    fig_actifs = px.bar(
        df.sort_values(
            "Poids réel (%)",
            ascending=True,
        ),
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
        margin=dict(
            l=10,
            r=10,
            t=20,
            b=10,
        ),
    )
    st.plotly_chart(
        fig_actifs,
        use_container_width=True,
    )

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

st.dataframe(
    df[display_columns],
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
        "Cours (€)": st.column_config.NumberColumn(
            "Cours",
            format="%.2f €",
        ),
        "Valeur actuelle (€)": st.column_config.NumberColumn(
            "Valeur",
            format="%.2f €",
        ),
        "Plus-value (€)": st.column_config.NumberColumn(
            "Plus-value",
            format="%+.2f €",
        ),
        "Plus-value (%)": st.column_config.NumberColumn(
            "Performance",
            format="%+.2f %%",
        ),
        "Poids réel (%)": st.column_config.NumberColumn(
            "Poids",
            format="%.2f %%",
        ),
        "MM200 (€)": st.column_config.NumberColumn(
            "MM200",
            format="%.2f €",
        ),
        "Momentum 6M (%)": st.column_config.NumberColumn(
            "Momentum 6M",
            format="%+.2f %%",
        ),
        "Date du cours": st.column_config.DatetimeColumn(
            "Date du cours",
            format="DD/MM/YYYY",
        ),
    },
)

st.download_button(
    "⬇️ Sauvegarder mes quantités et PRU",
    data=st.session_state.virtual_positions.to_csv(
        index=False,
        sep=";",
    ).encode("utf-8-sig"),
    file_name="positions_alpha_zen.csv",
    mime="text/csv",
)

st.caption(
    "Les prix peuvent être retardés. Les opérations sont virtuelles. "
    "Lorsque Supabase est configuré, les positions et les liquidités "
    "sont sauvegardées automatiquement."
)
