import streamlit as st

def render():
    """설정 페이지 렌더링"""
    st.title("⚙️ 설정")
    
    # 프로필 설정
    st.subheader("👤 프로필 설정")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.image('my_app/assets/placeholder.jpg')
        if st.button("프로필 사진 변경"):
            st.info("프로필 사진 변경 기능을 준비 중입니다.")
    
    with col2:
        user_email = st.session_state.user.email if "user" in st.session_state else "user@example.com"
        st.text_input("이메일", value=user_email, disabled=True)
        st.text_input("이름", value="사용자")
        st.text_area("자기소개", placeholder="자기소개를 입력하세요...")
        
        if st.button("프로필 저장"):
            st.success("프로필이 저장되었습니다!")
    
    st.divider()
    
    # FIRE 목표 설정
    st.subheader("🎯 FIRE 목표 설정")
    
    col1, col2 = st.columns(2)
    
    with col1:
        target_amount = st.number_input(
            "목표 자산 (원)",
            min_value=10000000,
            max_value=10000000000,
            value=100000000,
            step=10000000,
            format="%d"
        )
        
        current_age = st.number_input(
            "현재 나이",
            min_value=20,
            max_value=65,
            value=30,
            step=1
        )
        
        monthly_income = st.number_input(
            "월 소득 (원)",
            min_value=1000000,
            max_value=50000000,
            value=5000000,
            step=100000,
            format="%d"
        )
    
    with col2:
        target_age = st.number_input(
            "목표 은퇴 나이",
            min_value=current_age + 1,
            max_value=70,
            value=45,
            step=1
        )
        
        monthly_expense = st.number_input(
            "월 생활비 (원)",
            min_value=1000000,
            max_value=10000000,
            value=3000000,
            step=100000,
            format="%d"
        )
        
        expected_return = st.slider(
            "기대 연 수익률 (%)",
            min_value=1.0,
            max_value=15.0,
            value=7.0,
            step=0.5,
            format="%.1f%%"
        )
    
    # FIRE 목표 계산
    savings_rate = ((monthly_income - monthly_expense) / monthly_income) * 100
    years_to_fire = target_age - current_age
    
    st.info(f"""
    **FIRE 목표 요약:**
    - 저축률: {savings_rate:.1f}%
    - FIRE까지 남은 기간: {years_to_fire}년
    - 월 저축 가능 금액: {monthly_income - monthly_expense:,}원
    """)
    
    if st.button("FIRE 목표 저장"):
        st.success("FIRE 목표가 저장되었습니다!")
    
    st.divider()
    
    # 알림 설정
    st.subheader("🔔 알림 설정")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.checkbox("포트폴리오 일일 리포트", value=True)
        st.checkbox("투자 기회 알림", value=True)
        st.checkbox("목표 달성 알림", value=True)
    
    with col2:
        st.checkbox("시장 뉴스 알림", value=False)
        st.checkbox("주간 분석 리포트", value=True)
        st.checkbox("이메일 알림", value=True)
    
    st.divider()
    
    # 테마 설정
    st.subheader("🎨 테마 설정")
    
    theme = st.selectbox(
        "테마 선택",
        ["기본", "다크", "라이트", "고대비"],
        index=0
    )
    
    language = st.selectbox(
        "언어 설정",
        ["한국어", "English", "日本語"],
        index=0
    )
    
    if st.button("테마 설정 저장"):
        st.success("테마 설정이 저장되었습니다!")
    
    st.divider()
    
    # 위험한 설정
    st.subheader("⚠️ 계정 관리")
    
    with st.expander("계정 삭제"):
        st.warning("계정을 삭제하면 모든 데이터가 영구적으로 삭제됩니다.")
        delete_confirm = st.text_input("계정 삭제를 원하시면 '삭제'를 입력하세요:")
        
        if st.button("계정 삭제", type="secondary"):
            if delete_confirm == "삭제":
                st.error("계정 삭제 기능은 관리자에게 문의하세요.")
            else:
                st.warning("올바른 확인 텍스트를 입력하세요.")