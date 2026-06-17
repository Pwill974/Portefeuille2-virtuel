import streamlit as st

from services.auth import require_authentication, show_logout_button

st.set_page_config(
    page_title="Alpha Zen Pro",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

require_authentication()
show_logout_button()

st.title("📈 Alpha Zen Pro")
st.write("Tableau de bord de gestion PEA")
