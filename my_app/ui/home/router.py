import streamlit as st
import streamlit.components.v1 as components

PAGE_KEYS = {
    "홈 화면": "home",
    "Chatbot": "chatbot",
    "오늘의 퀴즈": "quiz",
    "맞춤형 금융 지식": "content",
    "맞춤형 상품 추천": "rag_recommendation",
    "현재 보유주식 AI코칭": "simulation",
    "종목 피드백": "analysis",
    "Settings": "settings",
    "Logout": "logout",
}
ALLOWED_PAGES = set(PAGE_KEYS.values())

def sync_nav_hash_bidirectional():
    if "current_page" not in st.session_state:
        st.session_state.current_page = "home"

    val = components.html(
        """
        <script>
        (function(){
          function getNavFromHash(){
            const h = window.location.hash || "";
            const m = h.match(/(?:^|#|&)nav=([^&]+)/);
            return m ? decodeURIComponent(m[1]) : "";
          }
          function setValue(v){
            window.parent.postMessage(
              { isStreamlitMessage: true, type: "streamlit:setComponentValue", value: v },
              "*"
            );
          }
          setValue(getNavFromHash());
          window.addEventListener("hashchange", ()=> setValue(getNavFromHash()));
          document.addEventListener("click", function(e){
            const a = e.target.closest && e.target.closest("a.hash-nav");
            if(!a) return;
            const href = a.getAttribute("href") || "";
            if(!href.startsWith("#nav=")) return;
            e.preventDefault();
            const v = decodeURIComponent(href.split("=").slice(1).join("="));
            window.location.hash = "nav=" + encodeURIComponent(v);
            setValue(v);
          });
        })();
        </script>
        """,
        height=0, scrolling=False,
    )
    if val and isinstance(val, str) and val in ALLOWED_PAGES:
        st.session_state.current_page = val
