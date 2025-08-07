import streamlit as st
from pathlib import Path

def render(init_supabase_func):
    """로그인 페이지 렌더링"""
    st.set_page_config(page_title="FIREgenerator - Login", layout="centered")
    
    st.markdown(
        """
        <center>
            <h1>FIREgenerator</h1>
        </center>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        try:
            image_path = Path(__file__).parent.parent / "assets" / "FIRE_LOGO_large.png"
            if image_path.exists():
                st.image(image_path)
        except:
            st.markdown("### 🔥 FIREgenerator")
        
        if st.button("Sign in with Google", use_container_width=True):
            supabase = init_supabase_func()
            current_url = st.get_option("browser.serverAddress") or "localhost"
            port = st.get_option("browser.serverPort")
            redirect_url = f"http://{current_url}:{port}/"

            try:
                response = supabase.auth.sign_in_with_oauth(
                    {
                        "provider": "google",
                        "options": {
                            "redirect_to": redirect_url,
                            "scopes": "email profile",
                        },
                    }
                )

                if response and response.url:
                    st.markdown(
                        f'<meta http-equiv="refresh" content="0;url={response.url}">',
                        unsafe_allow_html=True,
                    )
                    st.info("Google Login 중입니다..")

            except Exception as e:
                st.error(f"Login failed: {e}")