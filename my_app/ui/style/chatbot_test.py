import streamlit as st

def run():
    st.markdown("## 🚒 금융 구조대")
    st.markdown("### 당신의 금융 구조대, FIREgenerator의 챗봇을 소개합니다!")

    # 컬럼 구성: 소개 카드 (2/3) + 챗봇 창 (1/3)
    col1, col2 = st.columns([2, 1])

    with col1:
        with st.container():
            st.markdown("""
            <div style="background-color: white; padding: 30px; border-radius: 16px;
                        box-shadow: 0 4px 10px rgba(0,0,0,0.05);">
                <h3 style="color:#FE7743;">FIREgenerator란?</h3>
                <p>FIREgenerator는 2030세대의 성공적인 투자 경험을 지원하는 AI 기반 금융 파트너입니다. 📈<br><br>
                챗봇과의 대화를 바탕으로 당신에게 꼭 필요한 맞춤형 컨텐츠롸 상품을 제공해드릴게요.<br><br>
                지금 오른쪽 챗봇에게 질문해보세요! 💬</p>
            </div>
            """, unsafe_allow_html=True)

    with col2:
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