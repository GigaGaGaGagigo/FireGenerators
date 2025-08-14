import streamlit as st
from pathlib import Path
import uuid
import time

# Constants
def stream_data(message: str) -> None:
    """스트림 데이터 생성기"""
    for word in message:
        yield word
        time.sleep(0.01)

def generate_simple_response(prompt):
    """간단한 응답 생성"""
    prompt_lower = prompt.lower()
    
    if any(keyword in prompt_lower for keyword in ['fire', '파이어', '조기은퇴', '경제적 자유']):
        return """
🔥 **FIRE(Financial Independence, Retire Early)**에 대해 설명드리겠습니다!

**FIRE의 핵심 원칙:**
1. **높은 저축률**: 소득의 50% 이상 저축
2. **투자를 통한 자산 증대**: 인덱스 펀드, ETF 등 활용
3. **생활비 절약**: 불필요한 지출 줄이기
4. **4% 규칙**: 연간 생활비의 25배 자산 확보

더 구체적인 계획이 필요하시다면 말씀해 주세요!
        """
    
    elif any(keyword in prompt_lower for keyword in ['투자', '주식', '펀드', 'etf']):
        return """
💰 **투자 전략**에 대해 알려드리겠습니다!

**초보자 추천 투자 방법:**
1. **인덱스 펀드**: S&P 500, 전세계 주식 등
2. **ETF**: 낮은 수수료, 높은 유동성
3. **분산 투자**: 여러 자산군에 투자
4. **달러 코스트 평균법**: 정기적으로 일정 금액 투자

리스크 허용도와 투자 목표를 알려주시면 더 구체적인 조언을 드릴 수 있습니다!
        """
    
    elif any(keyword in prompt_lower for keyword in ['저축', '절약', '생활비']):
        return """
💡 **효과적인 저축 전략**을 제안합니다!

**저축률 높이는 방법:**
1. **가계부 작성**: 지출 패턴 파악
2. **고정비 줄이기**: 구독 서비스, 보험료 검토
3. **자동이체**: 월급날 바로 저축
4. **50-30-20 규칙**: 필수 50%, 욕구 30%, 저축 20%

현재 저축률이나 목표가 있으시다면 더 맞춤형 조언을 드릴 수 있습니다!
        """
    
    elif any(keyword in prompt_lower for keyword in ['계산', '시뮬레이션', '얼마나', '언제']):
        return """
📊 **FIRE 달성 계산**을 도와드리겠습니다!

**기본 계산 공식:**
- 필요 자산 = 연간 생활비 × 25
- 예시: 연 4,000만원 생활 → 10억원 필요

**달성 기간 예상:**
- 저축률 20%: 약 37년
- 저축률 50%: 약 17년  
- 저축률 70%: 약 9년

현재 상황(소득, 지출, 저축률)을 알려주시면 더 정확한 계산을 해드릴 수 있습니다!
        """
    
    else:
        return """
감사합니다! FIRE 달성과 관련된 다양한 주제로 도움을 드릴 수 있습니다.

**자주 묻는 질문들:**
- FIRE란 무엇인가요?
- 어떻게 투자를 시작해야 하나요?
- 저축률을 어떻게 높일 수 있나요?
- FIRE 달성에 얼마나 걸리나요?

구체적인 질문을 해주시면 더 도움이 될 것 같아요! 😊
        """

def render():
    """메인 렌더링 함수"""
    
    # 페이지 설정
    st.set_page_config(layout="wide", page_title="FIRE 달성 가이드")
    
    # 세션 상태 초기화
    if "messages" not in st.session_state:
        st.session_state.messages = []
        # 초기 봇 메시지 추가
        st.session_state.messages.append({
            "id": str(uuid.uuid4()),
            "role": "assistant",
            "content": "안녕하세요! FIRE 달성을 위한 AI 어시스턴트입니다. 투자, 저축, 재정 관리에 대해 궁금한 것이 있으시면 언제든 물어보세요! 😊",
        })

    # CSS 스타일 추가
    st.markdown("""
    <style>
    .card {
        background-color: #f8f9fa;
        padding: 20px;
        border-radius: 10px;
        margin-bottom: 15px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .card h3 {
        color: #2c3e50;
        margin-bottom: 10px;
    }
    .card p {
        color: #5a6c7d;
        margin: 0;
        line-height: 1.6;
    }
    .stChatMessage {
        margin-bottom: 10px;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # 레이아웃 구성: 콘텐츠 + 여백 + 채팅
    left_content, spacer, right_chat = st.columns([4, 0.5, 3])
    
    # 왼쪽 콘텐츠 영역
    with left_content:
        st.title("FIRE 달성을 위한 가이드")
        
        # 카드 형태의 콘텐츠들
        st.markdown("""
        <div class="card">
            <h2>💰 FIRE란?</h2>
            <p>Financial Independence, Retire Early<br>
            경제적 자유를 통한 조기 은퇴를 목표로 하는 라이프스타일입니다.</p>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("""
        <div class="card">
            <h2>📊 4% 규칙</h2>
            <p>연간 생활비의 25배를 모으면<br>
            4% 수익률로 평생 생활할 수 있다는 원칙입니다.</p>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class="card">
            <h2>💡 맞춤형 정보 제공</h2>
            <p>당신의 관심사와 정보를 바탕으로<br>
            꼭 맞는 금융 정보와 상품을 추천할게요!</p>
        </div>
        """, unsafe_allow_html=True)


    # 오른쪽 채팅 영역
    with right_chat:
        st.title("🚒 금융 구조대")
        # 채팅 메시지 영역 (높이 고정)
        chat_container = st.container(border=True, height=500)
        
        with chat_container:
            # 기존 메시지들 표시
            for i, message in enumerate(st.session_state.messages):
                with st.chat_message(message["role"]):
                    # 가장 마지막 메시지이고 AI 메시지인 경우에만 stream 사용
                    if (i == len(st.session_state.messages) - 1 
                        and message["role"] == "assistant" 
                        and "streaming" in st.session_state 
                        and st.session_state.streaming):
                        st.write_stream(stream_data(message["content"]))
                        # 스트리밍 완료 후 플래그 제거
                        if "streaming" in st.session_state:
                            del st.session_state.streaming
                    else:
                        st.write(message["content"])
        
        # 채팅 입력 영역
        if prompt := st.chat_input("투자나 FIRE에 대해 질문해보세요...", key="fire_chatbot"):
            # 사용자 메시지 추가
            st.session_state.messages.append({
                "id": str(uuid.uuid4()),
                "role": "user", 
                "content": prompt
            })
            
            # AI 응답 생성
            response = generate_simple_response(prompt)
            st.session_state.messages.append({
                "id": str(uuid.uuid4()),
                "role": "assistant", 
                "content": response
            })
            
            # 스트리밍 플래그 설정
            st.session_state.streaming = True
            
            # 페이지 새로고침
            st.rerun()

# 메인 실행
if __name__ == "__main__":
    render()