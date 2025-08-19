from pathlib import Path

import streamlit as st
from streamlit.navigation.page import StreamlitPage
from supabase import Client, create_client
from supabase._sync.client import SyncClient

# Define available user roles in the system
ROLES: list[str | None] = [None, "User", "Admin"]


@st.cache_resource
def init_supabase():
    """
    Initialize and cache Supabase client connection

    Returns:
        Client: Supabase client instance for database operations

    Raises:
        Exception: If Supabase initialization fails
    """
    try:
        supabase: Client = create_client(
            st.secrets["supabase"]["url"], st.secrets["supabase"]["key"]
        )
        return supabase
    except Exception as e:
        st.error(f"Error initializing Supabase: {e}")
        st.stop()


def check_auth_params():
    """
    Handle OAuth callback processing after Google login

    Purpose:
    - When user completes Google login, Google redirects back to our app
    - URL contains an 'authorization code' that needs to be exchanged for a session
    - This function processes that code to create a valid login session

    Process:
    1. Check if 'code' parameter exists in URL
    2. If found, exchange the code with Supabase for a session
    3. On success, store user info and complete login
    """
    query_params = st.query_params  # Get URL parameters

    # Check if 'code' exists in URL (e.g., http://localhost:8501/?code=abc123)
    # If code is not exist, it means that the user doesn't click the login button
    if "code" in query_params:
        code = query_params["code"]
        supabase: SyncClient | None = init_supabase()

        if supabase is None:
            raise ValueError("Supabase client is not initialized")

        st.session_state.supabase = supabase

        try:
            # Core part: Exchange authorization code for actual session
            supabase_session = supabase.auth.exchange_code_for_session(
                {"auth_code": code}  # type: ignore
            )

            if supabase_session.session:
                # Store user information
                st.session_state.session = (
                    supabase_session.session
                )  # Store session token
                st.session_state.user = supabase_session.user  # Store user info

                # Load Role Data from DB
                response_user_data = (
                    supabase.table("profiles")
                    .select("*")
                    .eq("id", st.session_state.user.id)
                    .execute()
                )
                if "user_data" not in st.session_state:
                    user_data: dict = {
                        "user_email": response_user_data.data[0]["email"],
                        "name": response_user_data.data[0]["name"],
                        "age": response_user_data.data[0]["age"],
                        "gender": response_user_data.data[0]["gender"],
                        "investment_goal": response_user_data.data[0][
                            "investment_goal"
                        ],
                        "investment_emotions": response_user_data.data[0]["investment_emotions"],
                        "interests_categories": response_user_data.data[0][
                            "interests_categories"
                        ],
                        "investment_level": response_user_data.data[0][
                            "investment_level"
                        ],
                        "knowledge_level": response_user_data.data[0][
                            "knowledge_level"
                        ],
                    }
                    st.session_state.user_data = user_data
                # Use .data to get the data from the response
                if response_user_data.data and response_user_data.data[0]["role"] in [
                    "User",
                    "Admin",
                ]:
                    st.session_state.role = response_user_data.data[0]["role"]
                else:
                    raise Exception("User role is not valid")

                # Clean up URL (remove code parameter)
                st.query_params.clear()
                # Refresh page to reflect logged-in state
                st.rerun()

        except Exception as e:
            st.error(f"Authentication failed: {e}")
            st.query_params.clear()


def login() -> None:
    """
    Handle user login with Google OAuth

    Features:
    1. Improved button design (Google icon, center alignment)
    2. Actual OAuth URL redirection handling
    3. Enhanced error handling
    """
    st.markdown(
        """
    <center>
        <h1>FIREgenerator</h1>
    </center>
    """,
        unsafe_allow_html=True,
    )

    if "user" in st.session_state:
        st.write(st.session_state.user)

    # Column layout to center the button
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        image_path = Path(__file__).parent / "assets" / "FIRE_LOGO_large.png"
        st.image(image_path)
        if st.button("Sign in with Google", use_container_width=True):
            supabase: SyncClient | None = init_supabase()

            if supabase is None:
                raise ValueError("Supabase client is not initialized")

            # Dynamically get current app URL
            # Use localhost:8501 locally, actual domain when deployed
            current_url = st.get_option("browser.serverAddress")
            port = st.get_option("browser.serverPort")

            if not current_url:
                current_url = "localhost"

            redirect_url = f"http://{current_url}:{port}/"

            try:
                # Start Google OAuth login process
                response = supabase.auth.sign_in_with_oauth(
                    {
                        "provider": "google",
                        "options": {
                            "redirect_to": redirect_url,  # URL to return to after login
                            "scopes": "email profile",  # Requested permissions
                        },
                    }
                )

                if response and response.url:
                    # Key modification: Actually redirect to Google login page
                    # Use HTML meta tag for automatic redirection
                    st.markdown(
                        f'<meta http-equiv="refresh" content="0;url={response.url}">',
                        unsafe_allow_html=True,
                    )
                    st.info("Google Login 중입니다..")

            except Exception as e:
                st.error(f"Login failed: {e}")


def logout() -> None:
    """
    Handle user logout

    Changes:
    1. Logout from Supabase server as well
    2. Selectively delete session state (safer approach)
    """
    if "session" in st.session_state and st.session_state.session:
        supabase: SyncClient | None = init_supabase()

        if supabase is None:
            raise ValueError("Supabase client is not initialized")

        try:
            # Logout from Supabase server
            supabase.auth.sign_out()
        except Exception:
            # Ignore any authentication errors during logout
            pass

    for key in list(st.session_state.keys()):
        del st.session_state[key]

    st.cache_data.clear()
    st.cache_resource.clear()

    st.rerun()


# Initialize session state
if "role" not in st.session_state:
    st.session_state.role = None

# Check OAuth callback - runs on every page load
# Handle users returning from Google
check_auth_params()


# Display user info - show email if logged in
if (
    "role" in st.session_state
    and st.session_state.role in ["User", "Admin"]
    and "user" in st.session_state
):
    st.sidebar.success(f"Logged in as: {st.session_state.user.email}")

# Page configuration
role = st.session_state.role

# Define navigation pages with icons and access control
logout_page: StreamlitPage = st.Page(logout, title="Log out", icon=":material/logout:")
settings: StreamlitPage = st.Page(
    "ui/settings/settings.py",
    title="Settings",
    icon=":material/settings:",
)
chatbot_1: StreamlitPage = st.Page(
    "ui/chatbot/chatbot.py",
    title="Chatbot",
    icon=":material/chat:",
    default=(role == "User"),
)
dashboard_1: StreamlitPage = st.Page(
    "ui/dashboard/dashboard_1.py",
    title="Dashboard 1",
    icon=":material/healing:",
)
admin_1: StreamlitPage = st.Page(
    "ui/admin/admin_1.py",
    title="Admin 1",
    icon=":material/person_add:",
    default=(role == "Admin"),
)
admin_2: StreamlitPage = st.Page(
    "ui/admin/admin_2.py",
    title="Admin 2",
    icon=":material/security:",
)

# Group pages by functionality
account_pages: list[StreamlitPage] = [logout_page, settings]
chatbot_pages: list[StreamlitPage] = [chatbot_1]
dashboard_pages: list[StreamlitPage] = [dashboard_1]
admin_pages: list[StreamlitPage] = [admin_1, admin_2]


# Configure logo and icon paths
logo_path = Path(__file__).parent / "assets" / "FIREgen_horizontal_logo.png"
icon_path = Path(__file__).parent / "assets" / "FIRE_LOGO_small.png"

st.logo(str(logo_path), icon_image=str(icon_path))

# Build navigation dictionary based on user role
page_dict: dict[str, list[StreamlitPage]] = {}
if st.session_state.role in ["User", "Register"]:
    page_dict["Chatbot"] = chatbot_pages
if st.session_state.role in ["User", "Register"]:
    page_dict["Dashboard"] = dashboard_pages
if st.session_state.role == "Admin":
    page_dict["Admin"] = admin_pages

# Display appropriate navigation based on login status
if len(page_dict) > 0:
    pg = st.navigation({"Account": account_pages} | page_dict)  # type: ignore
else:
    pg = st.navigation([st.Page(login)])  # type: ignore

# Run the selected page
pg.run()
