import streamlit as st

st.title("Admin 1")
st.write(f"Welcome, You are logged in as {st.session_state.role}.")

st.header("User Management")
st.write("This is where you can manage users and permissions.")

# Example user management interface
with st.expander("Add New User"):
    with st.form("add_user_form"):
        st.text_input("Username", placeholder="Enter username...")
        st.text_input("Email", placeholder="Enter email...")
        st.selectbox("Role", ["User", "Admin"])
        submitted = st.form_submit_button("Add User")

        if submitted:
            st.success("User added successfully!")

st.subheader("Current Users")
st.write("List of all registered users will appear here.")
