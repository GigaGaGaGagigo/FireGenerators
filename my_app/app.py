import streamlit as st
from streamlit.navigation.page import Page as Page


pages: dict[str, list[Page]] = {
    "Home": [st.Page("pages/home.py", title="home")],
    "Hidden": [st.Page("pages/account/google_login.py", title="google_login")],
}

if st.session_state.get("page") is None:
    st.session_state["page"] = "home"

pg = st.navigation(pages, position="hidden")
pg.run()
