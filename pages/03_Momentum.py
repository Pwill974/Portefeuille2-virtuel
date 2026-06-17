import streamlit as st
import pandas as pd

from services.auth import require_authentication, show_logout_button

st.set_page_config(
    page_title="Alpha Zen Pro — Momentum",
    page_icon="📊",
    layout="wide",
)

require_authentication()
show_logout_button()

st.title("📊 Analyse Momentum")
st.caption("Classement simplifié des actifs selon leur score Momentum.")

df = pd.DataFrame({
    "Actif": [
        "Thales",
        "Schneider Electric",
        "Amundi PEA MSCI World",
    ],
    "Score": [
        88,
        82,
        71,
    ],
})

df = df.sort_values("Score", ascending=False)

st.dataframe(
    df,
    hide_index=True,
    use_container_width=True,
    column_config={
        "Actif": st.column_config.TextColumn("Actif"),
        "Score": st.column_config.ProgressColumn(
            "Score Momentum",
            min_value=0,
            max_value=100,
            format="%d",
        ),
    },
)

st.bar_chart(
    df.set_index("Actif")["Score"],
    use_container_width=True,
)
