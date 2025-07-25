import streamlit as st

st.title("Admin 2")
st.write(f"Welcome, You are logged in as {st.session_state.role}.")

st.header("Security & Settings")
st.write("This is where you can manage security settings and system configuration.")

# Example security settings
with st.expander("Security Settings"):
    st.checkbox("Enable Two-Factor Authentication")
    st.checkbox("Require Strong Passwords")
    st.checkbox("Enable Session Timeout")
    st.slider("Session Timeout (minutes)", 15, 480, 60)

with st.expander("System Configuration"):
    st.text_input("System Name", value="FIREgen Request Manager")
    st.text_input("Admin Email", placeholder="admin@example.com")
    st.selectbox("Log Level", ["DEBUG", "INFO", "WARNING", "ERROR"])

st.subheader("System Status")
col1, col2 = st.columns(2)
with col1:
    st.metric("Active Users", "12")
    st.metric("System Uptime", "99.9%")
with col2:
    st.metric("Total Requests", "156")
    st.metric("Avg Response Time", "1.8h")
