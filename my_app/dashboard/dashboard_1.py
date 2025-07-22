import streamlit as st

st.title("Dashboard 1")
st.write(f"Welcome, {st.session_state.user.email}")
