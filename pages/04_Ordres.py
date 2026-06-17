import streamlit as st

from services.auth import require_authentication, show_logout_button


require_authentication()
show_logout_button()


st.title("Ordres du mois")

st.success(
    """
    Acheter :

    Thales : 400 €

    World : 300 €

    Nasdaq : 300 €
    """
)
