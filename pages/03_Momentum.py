import streamlit as st
import pandas as pd

from services.auth import 
require_authentication, 
show_logout_button

require_authentication()
show_logout_button()

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
