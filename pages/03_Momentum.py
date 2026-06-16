import streamlit as st
import pandas as pd

st.title("Momentum")

df = pd.DataFrame({
 "Actif":[
  "Thales",
  "Schneider",
  "World"
 ],
 "Score":[
  88,
  82,
  71
 ]
})

st.bar_chart(
 df.set_index("Actif")
)
