# streamlit_app.py
import streamlit as st
import requests
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

# 1) 설정
API_URL = st.secrets.get("API_URL", "http://localhost:8000")

st.set_page_config(page_title="투자 시뮬레이션 퀴즈", layout="centered")


# 2) session_state 초기화
if "quiz" not in st.session_state:
    st.session_state.quiz = None
if "result" not in st.session_state:
    st.session_state.result = None


# 3) 퀴즈 요청 함수
def fetch_quiz(security_id: str, user_id: int = 1):
    """FastAPI /quiz/{security_id} 호출"""
    resp = requests.get(f"{API_URL}/quiz/{security_id}", params={"user_id": user_id})

    print(resp)
    resp.raise_for_status()
    return resp.json()


# 4) 정답 제출 함수
def submit_answer(quiz_id: int, selected_pct: float):
    """FastAPI /quiz/{quiz_id}/submit 호출"""
    payload = {"user_id": 1, "selected_pct": selected_pct}
    resp = requests.post(f"{API_URL}/quiz/{quiz_id}/submit", json=payload)
    resp.raise_for_status()
    return resp.json()


# 5) 사이드바: 종목 입력
st.sidebar.header("🔍 종목 선택")
security_id = st.sidebar.text_input("ETF 티커 입력", value="SMH")
if st.sidebar.button("퀴즈 불러오기"):
    try:
        data = fetch_quiz(security_id)
        st.session_state.quiz = data
        st.session_state.result = None
    except Exception as e:
        st.error(f"퀴즈를 불러오는 중 오류: {e}")
        st.session_state.quiz = None


# 6) 퀴즈가 로딩된 경우
if st.session_state.quiz:
    quiz = st.session_state.quiz

    st.header(f"3개월 전 {security_id} 수익률 예측 퀴즈")
    st.markdown(f"- 퀴즈ID: **{quiz['quiz_id']}**, 날짜: **{quiz['quiz_date']}**")
    st.markdown("### 1) 차트 보기 (최근 3개월 종가)")
    # 차트용 데이터: yfinance에서 가져오기 (optional)
    try:
        today = datetime.strptime(quiz["quiz_date"], "%Y-%m-%d").date()
        start = today - timedelta(days=90)
        df = yf.download(security_id, start=start, end=today + timedelta(days=1))
        df.columns = df.columns.get_level_values(1)
        st.line_chart(df)
    except Exception:
        st.info("차트 데이터 로딩에 실패했습니다. yfinance 설치 및 네트워크 연결을 확인하세요.")

    st.markdown("### 2) 당시 주요 뉴스 요약")
    for news in quiz["news"]:
        st.subheader(news["title"])
        st.write(news["summary"])

    st.markdown("### 3) 수익률 예측")
    options = quiz["options"]
    # 보기 텍스트: “+10%” 형태로 가공
    labels = [f"{opt:+.1f}%" for opt in options]
    choice = st.radio("어느 정도 상승·하락했을까요?", labels, index=2)

    if st.button("🔢 정답 제출하기"):
        # 선택값에서 숫자만 뽑아서 float 변환
        selected_pct = float(choice.replace("%", ""))
        try:
            result = submit_answer(quiz["quiz_id"], selected_pct)
            st.session_state.result = result
        except Exception as e:
            st.error(f"제출 중 오류 발생: {e}")


# 7) 결과 표시
if st.session_state.result:
    res = st.session_state.result
    st.success("✅ 퀴즈 결과")
    st.write(f"- 실제 수익률(actual_pct): **{res['actual_pct']:+.2f}%**")
    st.write(f"- 오차(error_pct): **{res['error_pct']:.2f}%**")
    st.write(f"- 획득 점수(skill_score): **{res['skill_score']:.1f}점**")
    st.write(f"- 정답 여부: **{'정답!' if res['is_correct'] else '아쉽지만 오답'}**")

    # ‘다시 풀기’ 버튼
    if st.button("🔄 다시 풀기"):
        st.session_state.quiz = None
        st.session_state.result = None


# 8) 기본 안내
if not st.session_state.quiz and not st.session_state.result:
    st.write("왼쪽에서 종목 티커를 입력하고 ‘퀴즈 불러오기’ 버튼을 눌러주세요.")