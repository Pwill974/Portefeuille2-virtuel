import streamlit as st
import pandas as pd

st.title("Portefeuille")

df = pd.DataFrame({
 "Actif":[
  "World",
  "Nasdaq",
  "Thales"
 ],
 "Poids":[20,10,5]
})

st.dataframe(
 df,
 use_container_width=True
)
