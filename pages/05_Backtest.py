import streamlit as st

st.title("Backtest")

capital = st.number_input(
 "Capital initial",
 value=10000
)

versement = st.number_input(
 "Versement mensuel",
 value=1000
)

st.write(
 f"Simulation : {capital}"
)
