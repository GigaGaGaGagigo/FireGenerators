import streamlit as st

st.title("Set your Asset")

col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("현금성 자산")
    cash_type = st.radio("", ["예금", "적금"], key="cash_type")
    st.subheader("적금")
    saving_type = st.radio("", ["정기적금", "수시적금", "청약저축"], key="saving_type")
    st.subheader("투자 자산")
    invest_type = st.radio("", ["주식(국내, 해외)", "펀드", "ETF"], key="invest_type")
    st.subheader("대체 투자")
    alt_type = st.radio("", ["부동산", "금", "자동차"], key="alt_type")
    st.subheader("연금/보험")
    pension_type = st.radio(
        "",
        ["연금저축(개인연금, 퇴직연금)", "보험(종신보험, 변액보험)"],
        key="pension_type",
    )

with col2:
    cash = st.slider(" ", 0, 500, 460, step=10, format="%d만원", key="cash")
    st.markdown(
        f"<span style='color:#228be6;font-weight:bold;'>{cash}만원</span>",
        unsafe_allow_html=True,
    )
    st.write("0원", " " * 30, "500만원")
    saving = st.slider("  ", 0, 500, 270, step=10, format="%d만원", key="saving")
    st.markdown(
        f"<span style='color:#228be6;font-weight:bold;'>{saving}만원</span>",
        unsafe_allow_html=True,
    )
    st.write("0원", " " * 30, "500만원")
    invest = st.slider("   ", 0, 500, 10, step=10, format="%d만원", key="invest")
    st.markdown(
        f"<span style='color:#228be6;font-weight:bold;'>{invest}만원</span>",
        unsafe_allow_html=True,
    )
    st.write("0원", " " * 30, "500만원")
    alt = st.slider("    ", 0, 5000, 2800, step=100, format="%d만원", key="alt")
    st.markdown(
        f"<span style='color:#228be6;font-weight:bold;'>{alt}만원</span>",
        unsafe_allow_html=True,
    )
    st.write("0원", " " * 30, "5000만원")
    pension = st.slider("     ", 0, 5000, 0, step=100, format="%d만원", key="pension")
    st.markdown(
        f"<span style='color:#228be6;font-weight:bold;'>{pension}만원</span>",
        unsafe_allow_html=True,
    )
    st.write("0원", " " * 30, "5000만원")


if st.button("다음"):
    # 각 데이터 임시 저장 딕셔너리 생성
    asset_data = {
        "cash_type": cash_type,
        "saving_type": saving_type,
        "invest_type": invest_type,
        "alt_type": alt_type,
        "pension_type": pension_type,
        "cash": cash,
        "saving": saving,
        "invest": invest,
        "alt": alt,
        "pension": pension,
    }
    st.write(asset_data)
    st.session_state.asset_data = asset_data
    st.switch_page("register/chatbot.py")
