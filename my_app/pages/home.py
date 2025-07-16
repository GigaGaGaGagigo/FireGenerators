import streamlit as st
from pathlib import Path

LOGO_PATH = Path(__file__).parent.parent / "assets" / "FIRE_LOGO_large.png"

st.set_page_config(
    page_title="Home",
    page_icon=str(LOGO_PATH),
)


def move_to_page(page: str):
    st.session_state["page"] = page


def google_login() -> None:
    st.login("google")
    return None


def google_logout() -> None:
    if st.user.is_logged_in:
        st.logout()
    return None


st.image(LOGO_PATH, width=300)


col1, col2 = st.columns(2)

with col1:
    st.button("Google Login", on_click=google_login)
with col2:
    st.button("Google Logout", on_click=google_logout)

st.json(st.user)
