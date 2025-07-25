import streamlit as st
from datetime import date

"""
FIRE Lab — 임시 Home 화면 (데모)
실제 API·DB 연결 전까지는 하드코딩된 가상 데이터를 사용합니다.
"""

# ─────────────────────────────────────────────
# 가상 데이터 소스 (Mock)
# ─────────────────────────────────────────────

def get_mock_exchange_rate():
    return {
        "USD/KRW": 1382.4,
        "JPY/KRW": 8.93,
        "EUR/KRW": 1501.2,
    }


def get_mock_market_summary():
    return {
        "KOSPI": "▲ 0.37% (2,854.45)",
        "KOSDAQ": "▼ 0.15% (933.82)",
        "S&P 500": "▲ 0.28% (5,550.11)",
    }


def get_mock_portfolio():
    return [
        {"symbol": "QQQ", "shares": 8, "avg_price": 400, "value": 3200},
        {"symbol": "TIGER미국S&P500", "shares": 12, "avg_price": 13_200, "value": 158_400},
        {"symbol": "TSLA", "shares": 3, "avg_price": 220, "value": 660},
    ]


def get_mock_risk_profile():
    return "적극투자형 (β High)"


def get_mock_asset_snapshot():
    return {
        "총자산": "15,000,000₩",
        "총부채": "2,000,000₩",
        "순자산": "13,000,000₩",
    }

# ─────────────────────────────────────────────
# Streamlit UI
# ─────────────────────────────────────────────

st.set_page_config(page_title="FIRE Lab - Home", layout="wide")

# Header
col1, col2 = st.columns([1, 5])
with col1:
    st.image("https://placehold.co/120x120", caption="사용자", width=120)
with col2:
    st.markdown("## FIRE Lab ⛺ | 홈")
    st.caption(date.today().strftime("%Y-%m-%d (%a)"))

st.divider()

# Quick Tiles
qt1, qt2, qt3 = st.columns(3)
with qt1:
    st.button("💸 소규모 자산 운용 연습", use_container_width=True)
with qt2:
    st.metric(label="투자 성향", value=get_mock_risk_profile())
with qt3:
    snapshot = get_mock_asset_snapshot()
    st.metric(label="순자산", value=snapshot["순자산"])

st.divider()

# 자산 & 주식
asset_col, stock_col = st.columns(2)
with asset_col:
    st.subheader("자산 현황")
    st.json(snapshot, expanded=False)

with stock_col:
    st.subheader("보유 주식·ETF")
    port_df = [
        f"{item['symbol']} | 수량 {item['shares']} | 평가액 {item['value']:,}₩"
        for item in get_mock_portfolio()
    ]
    st.write("\n".join(port_df))

st.divider()

# 시장 정보
fx_col, mkt_col = st.columns(2)
with fx_col:
    st.subheader("오늘의 환율")
    for k, v in get_mock_exchange_rate().items():
        st.write(f"- **{k}**: {v}")

with mkt_col:
    st.subheader("오늘의 증시")
    for k, v in get_mock_market_summary().items():
        st.write(f"- **{k}** {v}")

st.markdown("\n")
