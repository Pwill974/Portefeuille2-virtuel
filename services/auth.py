from __future__ import annotations

import hmac
import time

import streamlit as st


MAX_ATTEMPTS = 5
LOCK_SECONDS = 60


def get_secret_password() -> str:
    """Récupère le mot de passe enregistré dans Streamlit Secrets."""
    try:
        password = str(st.secrets["auth"]["password"])
    except (KeyError, FileNotFoundError):
        password = ""

    if not password:
        st.error(
            "Le mot de passe n'est pas configuré dans Streamlit Secrets."
        )
        st.info(
            'Ajoute dans Settings > Secrets :\n\n'
            '[auth]\npassword = "TON_MOT_DE_PASSE"'
        )
        st.stop()

    return password


def hide_navigation_before_login() -> None:
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"],
        [data-testid="collapsedControl"] {
            display: none;
        }

        [data-testid="stAppViewContainer"] {
            background:
                radial-gradient(
                    circle at 50% -20%,
                    rgba(0, 215, 173, 0.12),
                    transparent 30rem
                ),
                linear-gradient(
                    180deg,
                    #06101f 0%,
                    #071321 100%
                );
        }

        .login-card {
            max-width: 430px;
            margin: 8vh auto 0 auto;
            padding: 28px;
            border: 1px solid #22334f;
            border-radius: 18px;
            background: linear-gradient(
                145deg,
                #101b2f,
                #0a1526
            );
            box-shadow: 0 22px 65px rgba(0, 0, 0, 0.35);
        }

        .login-logo {
            width: 58px;
            height: 58px;
            margin: 0 auto 14px auto;
            display: grid;
            place-items: center;
            border: 1px solid #00d7ad;
            border-radius: 14px;
            font-size: 1.8rem;
        }

        .login-title {
            color: #f2f6ff;
            text-align: center;
            font-size: 1.8rem;
            font-weight: 800;
        }

        .login-subtitle {
            color: #8794aa;
            text-align: center;
            margin: 5px 0 20px 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def require_authentication() -> None:
    """Bloque la page tant que le bon mot de passe n'est pas saisi."""

    if st.session_state.get("az_authenticated", False):
        return

    hide_navigation_before_login()

    current_time = time.time()
    locked_until = float(
        st.session_state.get("az_locked_until", 0.0)
    )

    st.markdown(
        """
        <div class="login-card">
            <div class="login-logo">📈</div>
            <div class="login-title">Alpha Zen Pro</div>
            <div class="login-subtitle">
                Portefeuille PEA privé
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if current_time < locked_until:
        remaining = max(
            int(locked_until - current_time),
            1,
        )

        st.error(
            f"Trop de tentatives incorrectes. "
            f"Réessaie dans {remaining} secondes."
        )
        st.stop()

    with st.form("login_form"):
        entered_password = st.text_input(
            "Mot de passe",
            type="password",
            placeholder="Saisis ton mot de passe",
        )

        submitted = st.form_submit_button(
            "Se connecter",
            use_container_width=True,
            type="primary",
        )

    if submitted:
        expected_password = get_secret_password()

        password_is_correct = hmac.compare_digest(
            entered_password.encode("utf-8"),
            expected_password.encode("utf-8"),
        )

        if password_is_correct:
            st.session_state["az_authenticated"] = True
            st.session_state["az_failed_attempts"] = 0
            st.session_state.pop(
                "az_locked_until",
                None,
            )
            st.rerun()

        failed_attempts = int(
            st.session_state.get(
                "az_failed_attempts",
                0,
            )
        ) + 1

        st.session_state[
            "az_failed_attempts"
        ] = failed_attempts

        if failed_attempts >= MAX_ATTEMPTS:
            st.session_state[
                "az_locked_until"
            ] = current_time + LOCK_SECONDS

            st.session_state[
                "az_failed_attempts"
            ] = 0

            st.error(
                "Trop de tentatives incorrectes. "
                "Accès bloqué pendant 60 secondes."
            )
        else:
            remaining_attempts = (
                MAX_ATTEMPTS - failed_attempts
            )

            st.error(
                "Mot de passe incorrect. "
                f"Il reste {remaining_attempts} tentative(s)."
            )

    st.stop()


def show_logout_button() -> None:
    """Affiche le bouton de déconnexion."""

    if not st.session_state.get(
        "az_authenticated",
        False,
    ):
        return

    with st.sidebar:
        st.divider()

        if st.button(
            "🔒 Se déconnecter",
            use_container_width=True,
            key="logout_button",
        ):
            st.session_state.pop(
                "az_authenticated",
                None,
            )

            st.session_state.pop(
                "az_failed_attempts",
                None,
            )

            st.session_state.pop(
                "az_locked_until",
                None,
            )

            st.rerun()
