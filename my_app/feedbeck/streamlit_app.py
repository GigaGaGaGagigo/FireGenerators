import streamlit as st
from dotenv import load_dotenv
import os
import pandas as pd
from supabase import create_client
from auto_trade_feedback import auto_trade_feedback

# .env 파일 로드
load_dotenv()

# Supabase 클라이언트 초기화
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# 고정된 사용자 ID
FIXED_USER_ID = "04918ed9-4175-4b9d-adf8-1956f6dc8168"

def get_user_traded_stocks(user_id: str) -> list[str]:
    """사용자가 거래한 모든 주식 종목의 리스트를 반환합니다."""
    try:
        res = supabase.table("trade_history").select("symbol").eq("user_id", user_id).execute()
        if res.data:
            # 중복을 제거하고 정렬된 리스트 반환
            return sorted(list(set([item['symbol'] for item in res.data])))
        return []
    except Exception as e:
        st.error(f"거래 종목을 불러오는 데 실패했습니다: {e}")
        return []

def get_user_profile(user_id: str) -> dict:
    """사용자 프로필 정보를 가져옵니다."""
    try:
        profile_res = supabase.table("profiles").select("*").eq("id", user_id).single().execute()
        return profile_res.data or {}
    except Exception as e:
        st.error(f"프로필 정보를 불러오는 데 실패했습니다: {e}")
        return {}

# --- Streamlit UI ---
st.title("📈 종목 피드백")

# 사용자 정보 가져오기
user_profile = get_user_profile(FIXED_USER_ID)
traded_stocks = get_user_traded_stocks(FIXED_USER_ID)

if not user_profile:
    st.error(f"ID={FIXED_USER_ID} 사용자를 찾을 수 없습니다. 앱을 계속할 수 없습니다.")
    st.stop()

if not traded_stocks:
    st.warning("아직 거래 기록이 없습니다. 피드백을 받으려면 먼저 거래를 입력해주세요.")
    st.stop()

st.markdown("피드백을 받고 싶은 종목과 피드백의 스타일을 선택하세요.")

# UI 컨트롤
selected_stock = st.selectbox(
    "종목 선택",
    options=traded_stocks,
    help="피드백을 받고 싶은 거래 이력이 있는 종목을 선택하세요."
)

# 사용자 프로필 기반으로 기본값 설정
default_tone_index = ['friendly', 'expert', 'youth', 'serious'].index(user_profile.get("preferred_tone", "friendly"))
default_risk_index = ['conservative', 'normal', 'aggressive'].index(user_profile.get("risk_profile", "normal"))

selected_tone = st.selectbox(
    "Tone (피드백 어조)",
    options=['friendly', 'expert', 'youth', 'serious'],
    index=default_tone_index,
    help="피드백 메시지의 어조를 선택합니다."
)

selected_risk_profile = st.selectbox(
    "Risk Profile (투자 성향)",
    options=['conservative', 'normal', 'aggressive'],
    index=default_risk_index,
    help="설정된 투자 성향입니다. 피드백 생성 시 참고됩니다."
)

if st.button("피드백하기"):
    if selected_stock:
        with st.spinner("최신 거래를 기반으로 피드백을 생성하는 중입니다..."):
            try:
                # 선택된 종목의 가장 최근 거래 기록 가져오기
                latest_trade_res = supabase.table("trade_history") \
                    .select("id") \
                    .eq("user_id", FIXED_USER_ID) \
                    .eq("symbol", selected_stock) \
                    .order("id", desc=True) \
                    .limit(1) \
                    .single() \
                    .execute()

                if not latest_trade_res.data:
                    st.error("해당 종목의 거래 기록을 찾을 수 없습니다.")
                else:
                    trade_id = latest_trade_res.data['id']

                    # 피드백 함수 호출 (LLM 사용 활성화)
                    fmsg, url, ai_feedback, llm_prompt = auto_trade_feedback(trade_id, FIXED_USER_ID, selected_tone, use_llm=True)

                    st.divider()
                    st.subheader("📝 입력된 정보")
                    st.text(f"- 종목: {selected_stock}")
                    st.text(f"- Tone: {selected_tone}")
                    st.text(f"- Risk Profile: {selected_risk_profile}")
                    st.text(f"- 분석 기준 Trade ID: {trade_id}")


                    st.divider()
                    st.subheader("💬 피드백 결과")

                    # 결과 출력
                    st.info(f"**[규칙 기반 피드백]**\n{fmsg}")

                    if ai_feedback:
                        st.success(f"**[AI 코칭]**\n{ai_feedback}")
                        if llm_prompt:
                            with st.expander("LLM 프롬프트 보기"):
                                st.text_area("LLM Prompt", llm_prompt, height=300)
                    else:
                        st.warning("AI 코칭 결과가 없습니다. LLM 호출에 실패했거나 빈 응답일 수 있습니다.")

                    # if url:
                    #     st.image(url, caption="관련 차트")
                    # else:
                    #     st.warning("차트 이미지를 가져올 수 없습니다.")

            except Exception as e:
                st.error(f"피드백 생성 중 오류가 발생했습니다: {e}")
    else:
        st.warning("피드백을 생성하려면 먼저 종목을 선택해야 합니다.")
