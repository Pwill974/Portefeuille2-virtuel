import streamlit as st
import pandas as pd
import plotly.express as px

st.title("Dashboard")

portfolio_value = 10000

col1,col2,col3,col4 = st.columns(4)

col1.metric(
 "Portefeuille",
 f"{portfolio_value:,.0f} €"
)

col2.metric(
 "Performance",
 "+12.5%"
)

col3.metric(
 "Liquidités",
 "500 €"
)

col4.metric(
 "Score Alpha",
 "84"
)

df = pd.DataFrame({
 "Poche":[
  "Zen",
  "Momentum",
  "Satellite"
 ],
 "Poids":[50,35,15]
})

fig = px.pie(
 df,
 values="Poids",
 names="Poche",
 hole=0.6
)

st.plotly_chart(
 fig,
 use_container_width=True
)
