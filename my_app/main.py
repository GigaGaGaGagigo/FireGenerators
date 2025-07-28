import streamlit as st
import yfinance as yf
import pandas as pd
import streamlit.components.v1 as components

st.set_page_config(layout="wide")

st.markdown(
    """
    <style>
    .filter-group {
        display: flex;
        gap: 10px;
        flex-wrap: wrap;
        margin-bottom: 10px;
    }
    .filter-button {
        padding: 6px 14px;
        border-radius: 20px;
        border: 1px solid #ccc;
        background-color: #f2f2f2;
        color: #333;
        font-size: 14px;
        cursor: pointer;
        transition: 0.2s;
    }
    .filter-button:hover {
        background-color: #e0e0e0;
    }
    .filter-button.selected {
        background-color: #0072f5;
        color: white;
        border-color: #0072f5;
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.title("📊 실시간 종목 필터링 앱")

# ✅ 종목 리스트
tickers = [
    '005930.KS', '000660.KS', '035420.KS',  # 삼성전자, SK하이닉스, NAVER
    '035720.KQ', '086790.KQ', '035900.KQ',  # 카카오게임즈, 하나기술, 젬백스
    'AAPL', 'TSLA', 'GOOGL', 'MSFT', 'NVDA', 'AMZN', 'META',  # 미국 대형주
    'SOXL', 'TQQQ', 'CWEB', 'ARKK'  # 미국 레버리지/테마 ETF
]

# ✅ 실시간으로 데이터 불러오기
@st.cache_data(ttl=3600)  # 1시간 캐시
def get_stock_data(tickers):
    result = []
    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            cap = info.get('marketCap', 0)
            market = '코스피' if '.KS' in ticker else ('코스닥' if '.KQ' in ticker else '나스닥')
            cap_display = round(cap / 1e8) if market != '나스닥' else round(cap / 1e8, 2)
            currency = '억원' if market != '나스닥' else '억 달러'

            result.append({
                '종목명': info.get('shortName', 'N/A'),
                '티커': ticker,
                '시장': market,
                '카테고리': info.get('sector', '정보 없음'),
                '시가총액': f"{cap_display} {currency}",
                '시가총액(RAW)': cap,
                'PER': info.get('trailingPE', 0),
                '매출증가율(%)': info.get('revenueGrowth', 0) * 100 if info.get('revenueGrowth') else 0,
                '매출액': info.get('totalRevenue', 0),
                '순이익': info.get('netIncomeToCommon', 0),
                '총자산': info.get('totalAssets', 0),
                '자기자본': info.get('totalStockholderEquity', 0)
            })
        except Exception as e:
            print(f"{ticker} 오류: {e}")
    return pd.DataFrame(result)

df = get_stock_data(tickers)

# 새 재무 항목 단위 변환 컬럼 추가
df['매출액(억 원)'] = df['매출액'] // 1e8
df['순이익(억 원)'] = df['순이익'] // 1e8
df['총자산(억 원)'] = df['총자산'] // 1e8
df['자기자본(억 원)'] = df['자기자본'] // 1e8

# ✅ 필터 선택 UI
st.markdown("#### 📍 시장 선택")
시장 = st.multiselect("", options=df["시장"].unique(), default=list(df["시장"].unique()))

st.markdown("#### 📂 카테고리 선택")
카테고리 = st.multiselect("", options=df["카테고리"].unique(), default=list(df["카테고리"].unique()))

col1, col2 = st.columns(2)
with col1:
    시총최소, 시총최대 = st.slider("💰 시가총액 범위 (원화 기준 억 단위)", 0, int(df["시가총액(RAW)"].max() / 1e8), (0, int(df["시가총액(RAW)"].max() / 1e8)))
with col2:
    per최소, per최대 = st.slider("📈 PER 범위", 0.0, 100.0, (0.0, 50.0))

매출성장최소 = st.slider("📊 매출 성장률 (%) 이상", -100.0, 100.0, 0.0)

# ✅ 필터링
filtered_df = df[
    (df["시장"].isin(시장)) &
    (df["카테고리"].isin(카테고리)) &
    (df["시가총액(RAW)"] >= 시총최소 * 1e8) & (df["시가총액(RAW)"] <= 시총최대 * 1e8) &
    (df["PER"] >= per최소) & (df["PER"] <= per최대) &
    (df["매출증가율(%)"] >= 매출성장최소)
]

# ✅ 출력
st.dataframe(
    filtered_df.drop(columns=["시가총액(RAW)", "매출액", "순이익", "총자산", "자기자본"]),
    use_container_width=True
)
# ✅ 투자 성향 입력
st.markdown("### 🧠 투자 성향 기반 추천")
성향 = st.selectbox("당신의 투자 성향은?", ["안정형", "위험중립형", "적극형", "공격형"])

def 추천필터(df, 성향):
    if 성향 == "안정형":
        return df[(df["시가총액(RAW)"] >= df["시가총액(RAW)"].quantile(0.6)) & 
                  (df["PER"] <= 20) & 
                  (df["매출증가율(%)"] >= 0)]
    elif 성향 == "위험중립형":
        return df[(df["시가총액(RAW)"] >= df["시가총액(RAW)"].quantile(0.4)) & 
                  (df["PER"] <= 30) & 
                  (df["매출증가율(%)"] >= 5)]
    elif 성향 == "적극형":
        return df[(df["PER"] <= 60) & 
                  (df["매출증가율(%)"] >= 10)]
    elif 성향 == "공격형":
        return df[(df["매출증가율(%)"] >= 20)]
    else:
        return df

추천결과 = 추천필터(filtered_df, 성향)

# ✅ 추천 결과 출력
st.markdown(f"#### 🎯 {성향} 투자자에게 추천 종목")
st.dataframe(
    추천결과.drop(columns=["시가총액(RAW)", "매출액", "순이익", "총자산", "자기자본"]),
    use_container_width=True
)