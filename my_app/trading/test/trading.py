import streamlit as st
import pandas as pd
import numpy as np
from datetime import date

st.set_page_config(page_title="소규모 자산 운용 연습", layout="wide")

# ──────────────────────────────────
# 1. 투자 여력 계산기
# ──────────────────────────────────

st.title("💸 소규모 자산 운용 연습")

with st.expander("1️⃣ 투자 여력 계산기", expanded=True):
    col1, col2, col3 = st.columns(3)
    with col1:
        income = st.number_input("📥 월 소득(₩)", value=3000000, step=100000)
    with col2:
        expense = st.number_input("📤 월 지출(₩)", value=1800000, step=100000)
    with col3:
        risk = st.selectbox("투자 성향", ["안정형", "중립형", "적극투자형", "공격투자형"])

    coeff = {"안정형":0.3, "중립형":0.5, "적극투자형":0.7, "공격투자형":0.9}[risk]
    invest_cap = (income - expense) * coeff
    st.metric("월 투자 가능 금액", f"{int(invest_cap):,}₩")

# ──────────────────────────────────
# 2. 맞춤형 상품 추천 (가상)
# ──────────────────────────────────

with st.expander("2️⃣ 맞춤형 상품 추천", expanded=True):
    st.write("투자 성향과 투자 여력에 기반해 간단 예시 포트폴리오를 제시합니다.")

    cat = st.radio("카테고리 선택", ["ETF", "주식", "국채"])

    # 가상 데이터
    sample_data = {
        "ETF": [
            {"symbol":"QQQ","name":"Invesco QQQ","risk":"High","exp":0.2},
            {"symbol":"TIGER미국S&P500","name":"TIGER S&P500","risk":"Mid","exp":0.09},
        ],
        "주식": [
            {"symbol":"AAPL","name":"Apple","risk":"Mid"},
            {"symbol":"TSLA","name":"Tesla","risk":"High"},
        ],
        "국채": [
            {"symbol":"KTB3Y","name":"Korea Treasury 3Y","risk":"Low"},
        ]
    }

    df = pd.DataFrame(sample_data[cat])
    st.dataframe(df, use_container_width=True)

    st.subheader("비율 선택")
    weights = st.slider("포트폴리오 투자 비율(%)", 0, 100, (40,60))
    st.write(f"선택 비율: {weights[0]}% ~ {weights[1]}%")

# ──────────────────────────────────
# 3. 자산 성장 시뮬레이터
# ──────────────────────────────────

with st.expander("3️⃣ 보유 자산 성장 시뮬레이터", expanded=True):
    col1, col2, col3 = st.columns(3)
    with col1:
        monthly = st.number_input("월 납입금(₩)", value=int(invest_cap), step=50000)
    with col2:
        rate = st.slider("예상 연수익률(%)", 1.0, 15.0, 7.0, 0.1)
    with col3:
        months = st.slider("투자 기간(개월)", 12, 360, 60, 12)

    # 복리 계산
    r = rate/100/12
    values = [monthly*((1+r)**i - 1)/r for i in range(1, months+1)]
    sim_df = pd.DataFrame({"Month":range(1, months+1), "Balance":values})
    st.line_chart(sim_df.set_index("Month"))

# ──────────────────────────────────
# 4. 금융 윤리 체크리스트 (간단)
# ──────────────────────────────────

with st.expander("4️⃣ 금융 윤리 점검", expanded=False):
    q1 = st.checkbox("총 부채가 순자산의 50%를 초과하지 않는다.")
    q2 = st.checkbox("투자를 위해 생활 필수비를 줄이지 않는다.")
    q3 = st.checkbox("높은 레버리지(신용·미수) 투자를 하지 않는다.")

    if st.button("윤리 점검 결과 보기"):
        passed = all([q1, q2, q3])
        if passed:
            st.success("건전한 투자 습관을 유지하고 있습니다!")
        else:
            st.error("위험 신호 감지: 체크되지 않은 항목을 확인하세요.")

# ──────────────────────────────────
# 5. 자동 매매 모의 실행 (데모)
# ──────────────────────────────────

with st.expander("5️⃣ 자동 매매 시뮬레이터", expanded=False):
    st.write("RSI < 30 매수, RSI > 70 매도 (가상 파라미터)")
    if st.button("모의 매매 실행"):
        trade_log = pd.DataFrame([
            {"Date": date.today(), "Action":"buy", "Symbol":"AAPL", "Price": 180, "Reason":"RSI 28"},
            {"Date": date.today(), "Action":"sell", "Symbol":"TSLA", "Price": 250, "Reason":"RSI 75"},
        ])
        st.dataframe(trade_log)

st.markdown("---")
st.caption("데모용 가상 데이터 — 실제 투자 판단 근거로 사용하지 마세요.")