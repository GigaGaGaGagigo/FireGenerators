import streamlit as st


st.title("Authentication")

if st.user.is_logged_in:
    st.logout()

if st.button("Authenticate"):
    st.login("google")

st.json(st.user)
