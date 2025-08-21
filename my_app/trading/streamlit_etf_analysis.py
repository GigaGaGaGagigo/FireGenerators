import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from datetime import datetime, timedelta
from openai import OpenAI
import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# — 설정(환경변수 or streamlit secrets) —
DEEPSEARCH_API_KEY = os.getenv("DEEPSEARCH_API_KEY") 
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# — 유틸 함수들 —
def fetch_chart_data(ticker: str, months: int = 3) -> pd.DataFrame:
    """
    yfinance 로부터 최근 months 개월치 종가(‘Close’)만 조회해서
    항상 단일 레벨 DataFrame 으로 반환.
    """
    end = datetime.today()
    start = end - timedelta(days=30 * months)

    # ※ group_by 는 'column' 또는 'ticker' 만 받습니다.
    #    기본값인 group_by='column'을 사용할 것이므로 명시적으로 건드릴 필요 없습니다.
    df = yf.download(
        tickers=ticker,
        start=start,
        end=end,
        auto_adjust=False,   # 보정된 가격 대신 원본 OHLC를 받고 싶으면 False
        progress=False
    )

    # 1) MultiIndex 컬럼이면 level 0 에 'Close' 가 있을 것(OHLC 그룹):
    if isinstance(df.columns, pd.MultiIndex):
        # level=0 이 ['Open','High','Low','Close',...] 이고
        # level=1 이 실제 ticker 명들입니다.
        # → level=0 기준으로 'Close' 슬라이스
        df_close = df.xs('Close', axis=1, level=0)
    else:
        # SingleIndex 면 평범하게 꺼내기
        df_close = df['Close']

    # 2) Series 면 DataFrame 으로 변환
    if isinstance(df_close, pd.Series):
        df_close = df_close.to_frame(name='Close')
    else:
        # DataFrame 인데 컬럼명이 리스트로 돼 있으면(멀티티커인 경우)
        # 컬럼명을 'Close' 하나로 바꿔주시면 st.line_chart 에 깔끔히 들어갑니다.
        if df_close.shape[1] == 1:
            df_close.columns = ['Close']

    return df_close

def fetch_news_via_deepsearch(
    query:      str,    # 검색어 (키워드 or 종목코드)
    from_date:  str,    # YYYY-MM-DD
    to_date:    str,    # YYYY-MM-DD
    page_size:  int = 10,
    global_news: bool = False,  # True 면 /v1/global-articles (해외 뉴스), False 면 /v1/articles (국내 뉴스)
) -> list:
    """
    DeepSearch API 로 뉴스 가져오기

    query 가 'KRX:'나 'NYSE:' 등을 포함하면 symbols 검색,
    아니면 keyword 검색으로 동작합니다.
    """
    base_url = "https://api-v2.deepsearch.com"
    endpoint = "/v1/global-articles" if global_news else "/v1/articles"

    # 공통 파라미터
    params = {
        "api_key":    DEEPSEARCH_API_KEY,
        "date_from":  from_date,
        "date_to":    to_date,
        "page_size":  page_size,
    }

    # query 분기
    if ":" in query:
        # 종목코드 검색
        print("cechk")
        params["symbols"] = query
    else:
        # 키워드 검색
        params["keyword"] = query

    # 실제 호출
    resp = requests.get(f"{base_url}{endpoint}", params=params)
    resp.raise_for_status()
    result = resp.json()

    # 응답 JSON 구조: { "detail": {...}, "total_items":.., "page":.., "data": [ {...}, ... ] }
    return result.get("data", [])

def summarize_with_openai(text: str) -> str:
    # 시스템 / 유저 메시지는 상황에 맞게 바꿔주세요
    messages = [
        {"role": "system", "content": "You are a helpful assistant that summarizes text concisely in Korean."},
        {"role": "user",   "content": f"다음 텍스트를 2문장 이내로 요약해줘:\n\n{text}"}
    ]

    # v1 방식으로 생성
    res = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=messages,
        temperature=0.2,
        max_tokens=200,
    )

    # 반환 형식은 choices → message → content
    return res.choices[0].message.content.strip()

# — Streamlit UI —


# 공유 변수
TICKER = "AAPL"         # 반도체 ETF A 예시 (iShares PHLX Semiconductor ETF)
ETF_NAME = "애플"

st.set_page_config(layout="centered")
st.title(ETF_NAME +" 분석")
st.write(ETF_NAME + "의 3개월 전 차트와 관련 뉴스를 분석합니다.")

col1, col2, col3 = st.columns(3)
with col1:
    if st.button("📈 차트 보기"):
        st.session_state.view = "chart"
with col2:
    if st.button("📰 뉴스 요약 보기"):
        st.session_state.view = "news"
with col3:
    if st.button("💡 투자 시뮬레이션 보기"):
        st.session_state.view = "sim"

# 기본 뷰 지정
if "view" not in st.session_state:
    st.session_state.view = "chart"


# — 1) 차트 보기 —
if st.session_state.view == "chart":
    st.subheader("3개월 전" + ETF_NAME + " 차트")
    df_chart = fetch_chart_data(TICKER, months=3)
    st.line_chart(df_chart)

    st.write("**특징 1** 반도체 시장 공급이 일시적으로 증가하여 가격 변동 예상.")
    st.write("**특징 2** 반도체 공급이 일시적으로 증가하여 가격 변동 예상.")
    st.write("**특징 3** 기술 회사들, 반도체 생산 확대를 위한 투자 발표.")

# — 2) 뉴스 요약 보기 —
elif st.session_state.view == "news":
    st.subheader("3개월 전 관련 뉴스 요약")
    # 날짜 범위
    to_date   = (datetime.today() - timedelta(days=90)).strftime("%Y-%m-%d")
    from_date = (datetime.today() - timedelta(days=120)).strftime("%Y-%m-%d")

    articles = fetch_news_via_deepsearch(TICKER, from_date, to_date, page_size=3)
    if not articles:
        st.warning("관련 뉴스를 찾을 수 없습니다.")
    else:
        for art in articles:
            # 1) 제목을 원문 링크로
            title = art.get("title", "제목 없음")
            url   = art.get("content_url")
            if url:
                st.markdown(f"### [{title}]({url})")
            else:
                st.markdown(f"### {title}")

            # 2) 이미지 (image_url, thumbnail_url 등 키 확인)
            img = (
                art.get("image_url")
                or art.get("thumbnail_url")
                or art.get("image")
                or art.get("urlToImage")   # 혹시 뉴스API 필드명이 남아있다면
            )
            if img:
                st.image(img, caption=title, use_container_width=True)

            # 3) 발행사(publisher)와 날짜
            pub_date = art.get("publishedAt") or art.get("published_at") or ""
            pub  = art.get("publisher") or art.get("sourceName") or ""
            st.write(f"{pub} | {pub_date[:10]}")

            # 4) 요약문 또는 본문 일부
            # DeepSearch 는 'summary' 키에 요약, 'content' 키에 전문 스니펫을 담아줍니다.
            excerpt = art.get("summary") or art.get("content") or ""
            if excerpt:
                st.write(excerpt)
            else:
                st.info("본문/요약이 없습니다.")

            # 5) 원문 바로 가기
            if url:
                st.markdown(f"[🔗 원문 바로 가기]({url})")

            st.write("---")
    # if st.button("🔄 다시 추천 받기"):
    #     st.session_state.view = "news"
    #     st.experimental_rerun()

# — 3) 투자 시뮬레이션 보기 —
else:
    st.subheader("투자 시뮬레이션 퀴즈")
    st.write("3개월 전 30만 원 투자 시 현재 가치는 얼마나 되었을까요?")
    options = ["+5%", "+10%", "+15%", "+20%"]
    choice = st.radio("예상 수익률을 선택하세요", options)
    if st.button("제출"):
        # 실제 계산 로직(예시)
        p0 = df_chart.iloc[0]["Close"]
        p1 = df_chart.iloc[-1]["Close"]
        actual_pct = (p1 - p0) / p0 * 100
        user_pct = float(choice.replace("%",""))
        error = abs(user_pct - actual_pct)
        score = max(0, 100 - 2*error)
        st.write(f"실제 수익률: {actual_pct:.2f}%")
        st.write(f"오차율: {error:.2f}%  |  획득 점수: {score:.1f}")
