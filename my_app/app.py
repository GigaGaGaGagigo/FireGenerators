import streamlit as st
from streamlit.navigation.page import Page as Page
from supabase import create_client, Client
from pathlib import Path


# Define available user roles in the system
ROLES: list[str | None] = [None, "Register", "User", "Admin"]


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
        supabase = init_supabase()
        st.session_state.supabase = supabase

        try:
            # Core part: Exchange authorization code for actual session
            # Convert temporary code from Google to usable session with Supabase
            response = supabase.auth.exchange_code_for_session({"auth_code": code})

            if response.session:
                # Store user information
                st.session_state.session = response.session  # Store session token
                st.session_state.user = response.user  # Store user info

                # Load Role Data from DB
                response_user_data = (
                    supabase.table("users")
                    .select("*")
                    .eq("user_email", st.session_state.user.email)
                    .execute()
                )

                # Use .data to get the data from the response
                if response_user_data.data:
                    st.session_state.role = response_user_data.data[0]["role"]
                else:
                    st.session_state.role = "Register"

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
            supabase = init_supabase()

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
                    st.info("Redirecting to Google login...")

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
        supabase = init_supabase()
        try:
            # Logout from Supabase server
            supabase.auth.sign_out()
        except:
            pass

    # Selectively delete authentication-related info from session state
    for key in ["session", "user", "role"]:
        if key in st.session_state:
            del st.session_state[key]

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
    and st.session_state.role in ["User", "Register", "Admin"]
    and "user" in st.session_state
):
    st.sidebar.success(f"Logged in as: {st.session_state.user.email}")

# Page configuration
role = st.session_state.role

# Define navigation pages with icons and access control
logout_page: Page = st.Page(logout, title="Log out", icon=":material/logout:")
settings: Page = st.Page("settings.py", title="Settings", icon=":material/settings:")
register_1: Page = st.Page(
    "register/register.py",
    title="Register",
    icon=":material/person_add:",
    default=(role == "Register"),
)
register_2: Page = st.Page(
    "register/survey.py",
    title="Survey",
    icon=":material/help:",
)
register_3: Page = st.Page(
    "register/asset.py",
    title="Input Asset",
    icon=":material/wallet:",
)
register_4: Page = st.Page(
    "register/chatbot.py",
    title="Chatbot",
    icon=":material/chat:",
)
dashboard_1: Page = st.Page(
    "dashboard/dashboard_1.py",
    title="Dashboard 1",
    icon=":material/healing:",
    default=(role == "User"),
)
dashboard_2: Page = st.Page(
    "dashboard/dashboard_2.py",
    title="Dashboard 2",
    icon=":material/handyman:",
)
admin_1: Page = st.Page(
    "admin/admin_1.py",
    title="Admin 1",
    icon=":material/person_add:",
    default=(role == "Admin"),
)
admin_2: Page = st.Page(
    "admin/admin_2.py",
    title="Admin 2",
    icon=":material/security:",
    default=(role == "Admin"),
)

# Group pages by functionality
account_pages: list[Page] = [logout_page, settings]
register_pages: list[Page] = [register_1, register_2, register_3, register_4]
dashboard_pages: list[Page] = [dashboard_1, dashboard_2]
admin_pages: list[Page] = [admin_1, admin_2]


# Configure logo and icon paths
logo_path = Path(__file__).parent / "assets" / "FIREgen_horizontal_logo.png"
icon_path = Path(__file__).parent / "assets" / "FIRE_LOGO_small.png"

st.logo(str(logo_path), icon_image=str(icon_path))

# Build navigation dictionary based on user role
page_dict: dict[str, list[Page]] = {}
if st.session_state.role in ["Register", "Admin"]:
    page_dict["Register"] = register_pages
if st.session_state.role in ["User", "Register", "Admin"]:
    page_dict["Dashboard"] = dashboard_pages
if st.session_state.role == "Admin":
    page_dict["Admin"] = admin_pages

# Display appropriate navigation based on login status
if len(page_dict) > 0:
    pg = st.navigation({"Account": account_pages} | page_dict)
else:
    pg = st.navigation([st.Page(login)])

# Run the selected page
pg.run()
