import streamlit as st

def render():

        # 2열 레이아웃: 왼쪽 콘텐츠, 오른쪽 챗봇
    col1, col2 = st.columns([2, 1])
    
    with col1:

        with st.container():
            st.title("🔥 FIRE 달성을 위한 가이드")
            st.markdown("""
            <div style="background-color: white; padding: 30px; border-radius: 16px;
                        box-shadow: 0 4px 10px rgba(0,0,0,0.05);">
                <h3 style="color:#FE7743;">FIREgenerator란?</h3>
                <p>FIREgenerator는 2030세대의 성공적인 투자 경험을 지원하는 AI 기반 금융 파트너입니다. 📈<br>
                챗봇과의 대화를 바탕으로 당신에게 꼭 필요한 맞춤형 컨텐츠롸 상품을 제공해드릴게요.<br>
                지금 오른쪽 챗봇에게 질문해보세요! 💬</p>
            </div>
            """, unsafe_allow_html=True)
        
            # 카드 형태의 콘텐츠
            st.markdown(
            """
            <div style="background-color: white; padding: 15px; border-radius: 16px;
                        box-shadow: 0 4px 10px rgba(0,0,0,0.05);">
                <h3>💰 FIRE란?</h3>
                <p>Financial Independence, Retire Early<br>
                경제적 자유를 통한 조기 은퇴를 목표로 하는 라이프스타일입니다.</p>
            </div>
            """,unsafe_allow_html=True,)
        
            st.markdown(
            """
            <div style="background-color: white; padding: 15px; border-radius: 16px;
                        box-shadow: 0 4px 10px rgba(0,0,0,0.05);">
                <h3>📊 4% 규칙</h3>
                <p>연간 생활비의 25배를 모으면 4% 수익률로 평생 생활할 수 있다는 원칙입니다.</p>
            </div>
            """, unsafe_allow_html=True,)

    with col2:
        st.markdown("## 🚒 금융 구조대")

        with st.container():
            st.markdown("""
            <div style="background-color: white; padding: 20px; border-radius: 16px;
                        box-shadow: 0 4px 10px rgba(0,0,0,0.05); height: 100%;">
                <h4 style="color:#FE7743;">💬 챗봇</h4>
            """, unsafe_allow_html=True)

            # 입력창 + 버튼
            user_input = st.text_input("질문을 입력하세요", placeholder="예: ETF란 무엇인가요?", label_visibility="collapsed")

            if user_input:
                # 여기에 챗봇 응답 로직 연결 가능
                st.markdown(f"""
                        <div style="margin-top:10px; padding:10px; background-color:#FEE5A5; border-radius:8px;">
                        <b>챗봇 응답:</b> ETF는 상장지수펀드로, 주식처럼 거래되는 펀드입니다.
                        </div>
                    """, unsafe_allow_html=True)

            st.markdown("</div>", unsafe_allow_html=True)