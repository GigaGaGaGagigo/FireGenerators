import streamlit as st
from dotenv import load_dotenv
import os
import uuid
from supabase import create_client
from auto_trade_feedback import auto_trade_feedback

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.title("🔧 AutoTrade Feedback 테스트 대시보드 (with DEBUG)")

tabs = st.tabs(["1) 프로필 생성", "2) Trade 입력", "3) 분석 실행", "4) 테이블 조회"])


# --- 1) 프로필 생성 ---
with tabs[0]:
    st.subheader("신규 사용자(Profiles) 생성")
    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("name")
        email = st.text_input("email")
        age = st.number_input("age", 1, 150, 29)
    with col2:
        investment_level = st.selectbox("투자등급", ['beginner', 'intermediate', 'advanced', 'expert'])
        preferred_tone = st.selectbox("tone", ['friendly','expert','youth','serious'])
        risk_profile = st.selectbox("risk_profile",['conservative','normal','aggressive'])

    if st.button("Profiles 생성"):
        new_id = str(uuid.uuid4())
        supabase.table("profiles").insert({
            "id": new_id,
            "email": email,
            "name": name,
            "age": age,
            "investment_level": investment_level,
            "preferred_tone": preferred_tone,
            "risk_profile": risk_profile
        }).execute()
        st.success(f"✅ 생성 완료! user_id = {new_id}")


# --- 2) Trade 입력 ---
with tabs[1]:
    st.subheader("거래 입력 (trade_history)")
    user_id = st.text_input("user_id")
    symbol  = st.text_input("symbol (예:005930)")
    market  = st.selectbox("market", ['KR','US'])
    action  = st.selectbox("action", ['buy','sell'])
    price   = st.number_input("price", step=0.01)
    qty     = st.number_input("qty", value=0.0)
    commission = st.number_input("commission", value=0.0)

    if st.button("거래 INSERT"):
        res = supabase.table("trade_history").insert({
            "user_id": user_id,
            "symbol": symbol,
            "market": market,
            "action": action,
            "price": price,
            "qty": qty,
            "commission": commission
        }).execute()
        st.success(f"✅ 입력 성공 trade_id = {res.data[0]['id']}")


# --- 3) 분석 실행 ---
with tabs[2]:
    st.subheader("자동 Feedback 실행 (debug mode)")
    trade_id = st.number_input("trade_id", step=1, value=1)
    user_id2 = st.text_input("user_id(분석용)")
    selected_tone = st.selectbox("tone", ['friendly','expert','youth','serious'], key="tone_select_1")
    use_llm = st.checkbox("AI코칭 (Gemini)", value=False)

    # ✅ 디버그: 현재 LLM 스위치/키 유무 보여주기
    st.caption(f"use_llm={use_llm}, GOOGLE_API_KEY set={bool(os.getenv('GOOGLE_API_KEY'))}")

    if st.button("분석 실행"):
        # DEBUG: 입력값 먼저 출력
        st.write("==== 입력값 확인 ====")
        st.write("trade_id :", trade_id)
        st.write("user_id  :", user_id2)

        # DB 조회 결과 출력
        trade = supabase.table("trade_history").select("*").eq("id", trade_id).single().execute().data
        user  = supabase.table("profiles").select("*").eq("id", user_id2).single().execute().data
        st.write("trade record:", trade)
        st.write("user record:", user)

        try:
            fmsg, url, ai = auto_trade_feedback(trade_id, user_id2, selected_tone, use_llm)
            st.success("=== auto_trade_feedback 실행 성공 ===")
            st.write("Rule-Feedback =>", fmsg)

            if url:
                st.image(url, caption="Chart")
            else:
                st.warning("차트 URL이 없습니다. (Storage 업로드/퍼블릭 설정 확인)")

            # ✅ LLM 결과 항상 영역을 만들어 보여주기 (빈 경우에도)
            if use_llm:
                if ai:
                    st.info(ai)
                else:
                    st.warning("AI 코칭 결과가 비어있습니다. (LLM 호출이 실패했거나 빈 응답)")
        except Exception as e:
            st.error(f"분석 도중 예외 발생 => {e}")

# --- 4) 테이블 조회 ---
with tabs[3]:
    st.subheader("📄 테이블 조회")
    colA, colB = st.columns(2)
    with colA:
        st.write("profiles")
        pf = supabase.table("profiles").select("*").limit(20).execute().data
        st.table(pf)
    with colB:
        st.write("trade_history")
        th = supabase.table("trade_history").select("*").order("id", desc=True).limit(20).execute().data
        st.table(th)

    st.write("trade_feedback")
    tf = supabase.table("trade_feedback").select("*").order("id", desc=True).limit(20).execute().data
    st.table(tf)