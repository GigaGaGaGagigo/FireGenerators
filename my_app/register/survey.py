import streamlit as st
from supabase import create_client, Client


st.title("Request 1")
st.write(st.session_state.user)
