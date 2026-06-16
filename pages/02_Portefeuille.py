import streamlit as st
import pandas as pd

st.set_page_config(layout="wide")

st.title("📊 Portefeuille Alpha Zen")

portfolio = pd.DataFrame({
    "Actif": [
        "Amundi MSCI World",
        "Amundi S&P500",
        "Amundi Nasdaq100",
        "Amundi Europe",
        "BNP Défense",
        "Schneider Electric",
        "Air Liquide",
        "TotalEnergies",
        "Dassault Aviation",
        "Thales",
        "STMicroelectronics",
        "Sanofi",
        "Amundi Emergents"
    ],
    "ISIN":[
        "FR001400U5Q4",
        "FR0011871128",
        "FR0011871110",
        "FR0013412038",
        "LU3047998896",
        "FR0000121972",
        "FR0000120073",
        "FR0000120271",
        "FR0014004L86",
        "FR0000121329",
        "NL0000226223",
        "FR0000120578",
        "FR0013412020"
    ],
    "Allocation":[
        20,15,10,5,
        10,5,3,2,
        5,5,5,5,10
    ]
})

st.dataframe(
    portfolio,
    use_container_width=True
)

st.subheader("Répartition stratégique")

st.write("Socle Zen : 60 %")
st.write("Momentum : 25 %")
st.write("Satellite : 15 %")
