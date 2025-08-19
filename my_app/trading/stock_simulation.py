import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

# 환율 설정
USD_KRW = 1300

# Streamlit 기본 설정
st.set_page_config(page_title="투자 시뮬레이션", layout="centered")
st.title("📈 실시간 주가 기반 투자 시뮬레이션 게임")

# 종목 선택
ticker = st.selectbox("📊 종목 선택", ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"])

# 오늘 날짜로부터 최근 10일 데이터 로드
end = datetime.today()
start = end - timedelta(days=20)  # 휴장일 포함 여유 있게

# 🔧 auto_adjust 옵션 명시적으로 설정 + 버그 방지
data = yf.download(ticker, start=start, end=end, auto_adjust=False)

# 종가만 추출
price_df = data[["Close"]].dropna().reset_index()
price_df["Date"] = price_df["Date"].dt.strftime("%Y-%m-%d")

if price_df.empty:
    st.error("주가 데이터를 불러올 수 없습니다. 다른 종목을 선택해주세요.")
    st.stop()

# 시뮬레이션 상태 초기화
if "cash" not in st.session_state:
    st.session_state.cash = 1_000_000
    st.session_state.stocks = 0
    st.session_state.history = []
    st.session_state.day_index = 0
    st.session_state.ticker = ticker

# 다른 종목 선택 시 초기화
if st.session_state.ticker != ticker:
    st.session_state.cash = 1_000_000
    st.session_state.stocks = 0
    st.session_state.history = []
    st.session_state.day_index = 0
    st.session_state.ticker = ticker

# 현재 날짜 및 가격
current_row = price_df.iloc[st.session_state.day_index]
date = current_row["Date"]
price_usd = float(current_row["Close"])  # ✅ 버그 수정: float으로 변환
price_krw = price_usd * USD_KRW

st.subheader(f"📅 {date} | 💵 {ticker} 종가: {price_usd:.2f}$ ≒ {price_krw:,.0f}원")

# 상태 표시
total_assets = st.session_state.cash + st.session_state.stocks * price_krw
st.write(f"💰 보유 현금: {st.session_state.cash:,.0f}원")
st.write(f"📦 보유 주식: {st.session_state.stocks}주")
st.write(f"📊 총 자산: {total_assets:,.0f}원")

# 거래 수량
qty = st.number_input("거래 수량", min_value=1, value=1)

# 버튼 구성
col1, col2, col3 = st.columns(3)

with col1:
    if st.button("📥 매수"):
        cost = qty * price_krw
        if st.session_state.cash >= cost:
            st.session_state.cash -= cost
            st.session_state.stocks += qty
            st.session_state.history.append(f"{date}: {qty}주 매수 @ {price_usd:.2f}$")
        else:
            st.warning("💸 현금 부족")

with col2:
    if st.button("📤 매도"):
        if st.session_state.stocks >= qty:
            st.session_state.stocks -= qty
            st.session_state.cash += qty * price_krw
            st.session_state.history.append(f"{date}: {qty}주 매도 @ {price_usd:.2f}$")
        else:
            st.warning("📉 보유 주식 부족")

with col3:
    if st.button("▶ 다음 날"):
        if st.session_state.day_index < len(price_df) - 1:
            st.session_state.day_index += 1
        else:
            st.success("🎉 마지막 날입니다!")

# 거래 내역 출력
st.markdown("---")
st.subheader("📝 거래 내역")
if st.session_state.history:
    for log in st.session_state.history:
        st.write(log)
else:
    st.write("거래 내역 없음")