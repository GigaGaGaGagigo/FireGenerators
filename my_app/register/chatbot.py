import streamlit as st

st.title("Chatbot")
st.write(f"Welcome, {st.session_state.user.email}")
