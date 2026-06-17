import streamlit as st

from services.auth import require_authentication, show_logout_button


require_authentication()
show_logout_button()


st.title("Backtest")

capital = st.number_input(
    "Capital initial",
    value=10000,
)

versement = st.number_input(
    "Versement mensuel",
    value=1000,
)

st.write(f"Simulation : {capital}")
