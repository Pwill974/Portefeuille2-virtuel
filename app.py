import streamlit as st

from services.auth import (
    require_authentication,
    show_logout_button,
)

st.set_page_config(
    page_title="Alpha Zen Pro",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Bloque l'application tant que le mot de passe n'est pas validé
require_authentication()

# Affiche le bouton de déconnexion après connexion
show_logout_button()

st.title("📈 Alpha Zen Pro")
st.write("Tableau de bord de gestion PEA")
