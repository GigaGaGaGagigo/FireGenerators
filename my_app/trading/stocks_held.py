import os
from dotenv import load_dotenv
import streamlit as st
import pandas as pd
import yfinance as yf
import FinanceDataReader as fdr
from supabase import create_client, Client
from datetime import date
import numpy as np
import pandas_ta as ta
import google.generativeai as genai
import json

# .env 로드
load_dotenv()

# Supabase 초기화
SUPABASE_URL = os.getenv("SUPABASE_URL") 
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
gemini_model = genai.GenerativeModel("gemini-1.5-flash")

# 세션 user_id
if "user_id" not in st.session_state:
    st.session_state.user_id = "0bfc599a-db77-49ef-8556-31d2be8ffdaf"

USER_ID = st.session_state.user_id


st.title("📊 모의투자 보유주식 관리")


# feedbeck code
def compute_advanced_stats(df, trade_price, trade_idx, action):
    # EMA, RSI, MACD, Stochastic, 볼린저밴드, VWAP
    df['EMA20'] = ta.ema(df['종가'], length=20)
    df['EMA60'] = ta.ema(df['종가'], length=60)
    df['EMA120'] = ta.ema(df['종가'], length=120)
    df['RSI14'] = ta.rsi(df['종가'], length=14)
    macd = ta.macd(df['종가'])
    df['MACD'] = macd['MACD_12_26_9']
    df['MACD_SIGNAL'] = macd['MACDs_12_26_9']
    stoch = ta.stoch(df['고가'], df['저가'], df['종가'])
    df['STOCH_K'] = stoch['STOCHk_14_3_3']
    df['STOCH_D'] = stoch['STOCHd_14_3_3']
    bbands = ta.bbands(df['종가'], length=20)
    df['BB_UPPER'] = bbands['BBU_20_2.0']
    df['BB_LOWER'] = bbands['BBL_20_2.0']
    df['VWAP'] = ta.vwap(df['고가'], df['저가'], df['종가'], df['거래량'])
    idx = trade_idx
    result = {
        "EMA20": float(df['EMA20'].iloc[idx]),
        "EMA60": float(df['EMA60'].iloc[idx]),
        "EMA120": float(df['EMA120'].iloc[idx]),
        "RSI14": float(df['RSI14'].iloc[idx]),
        "MACD": float(df['MACD'].iloc[idx]),
        "MACD_SIGNAL": float(df['MACD_SIGNAL'].iloc[idx]),
        "STOCH_K": float(df['STOCH_K'].iloc[idx]),
        "STOCH_D": float(df['STOCH_D'].iloc[idx]),
        "BB_UPPER": float(df['BB_UPPER'].iloc[idx]),
        "BB_LOWER": float(df['BB_LOWER'].iloc[idx]),
        "VWAP": float(df['VWAP'].iloc[idx])
    }
    if action == "buy":
        after = df.iloc[idx:idx+7]['종가']
        max_profit = np.round((after.max() - trade_price) / trade_price * 100, 2)
        min_profit = np.round((after.min() - trade_price) / trade_price * 100, 2)
        result["max_profit"] = float(max_profit)
        result["min_profit"] = float(min_profit)
    else:
        after = df.iloc[idx:idx+7]['종가']
        missed_profit = np.round((after.max() - trade_price) / trade_price * 100, 2)
        result["missed_profit"] = float(missed_profit)
    return result


# ====== 기존 함수 ======
def save_trade(
    user_id: str,
    symbol: str,
    market: str,
    price: float,
    quantity: float,
    action: str,
    trade_time: date,
    commission: float = 0.0,
    memo: str = ""
):
    # 1️⃣ trade_history 저장
    data = {
        "user_id":    user_id,
        "symbol":     symbol.upper(),
        "market":     market,
        "price":      price,
        "quantity":     quantity,
        "action":     action.lower(),
        "trade_time": trade_time.isoformat(),
        "commission": commission,
        "memo":       memo
    }
    res = supabase.table("trade_history").insert(data).execute()

    if getattr(res, "status_code", 0) >= 400 or not res.data:
        st.error("거래 저장 실패")
        return

    trade_id = res.data[0]["id"]

    # 2️⃣ 고급 통계 계산 (여기서 summary_stats 준비)
    try:
        df_price = fdr.DataReader(symbol) if market == "KR" else yf.Ticker(symbol).history(period="1y")
        df_price = df_price.rename(columns={"Close": "종가", "High": "고가", "Low": "저가", "Volume": "거래량"})
        df_price.index = df_price.index.tz_localize(None)
        trade_ts = pd.to_datetime(trade_time)
        idx = df_price.index.get_loc(trade_ts)
        summary_stats = compute_advanced_stats(df_price, price, idx, action)
    except Exception as e:
        summary_stats = {}
        st.warning(f"통계 계산 실패: {e}")

    # 3️⃣ trade_feedback 저장
    feedback_data = {
        "user_id": user_id,
        "trade_id": trade_id,
        "chart_url": "",  # 추후 차트 이미지 URL 생성 가능
        "summary_stats": summary_stats,
        "style_type": "default",
        "rank_in_group": None,
        "benchmark_return": None
    }
    res_fb = supabase.table("trade_feedback").insert(feedback_data).execute()
    if getattr(res_fb, "status_code", 0) >= 400:
        st.warning("피드백 저장 실패")
    else:
        st.success(f"{action.upper()} 저장 및 피드백 생성 완료")

def get_trade_history(user_id: str) -> pd.DataFrame:
    res = (
        supabase
        .table("trade_history")
        .select("*")
        .eq("user_id", user_id)
        .execute()
    )
    if getattr(res, "status_code", 0) >= 400:
        msg = getattr(res, "error_message", f"status={res.status_code}")
        st.error(f"조회 실패: {msg}")
        return pd.DataFrame()
    if not res.data:
        return pd.DataFrame()
    return pd.DataFrame(res.data)

def fetch_current_price(symbol: str, market: str) -> float:
    try:
        if market == "US":
            ticker = yf.Ticker(symbol)
            df = ticker.history(period="1d")
            return float(df["Close"].iloc[-1])
        else:  # KR
            df = fdr.DataReader(symbol)
            return float(df["Close"].iloc[-1])
    except Exception as e:
        st.warning(f"{symbol}@{market} 현재가 조회 실패: {e}")
        return 0.0

# ====== 신규 함수 ======
def get_company_name(symbol: str, market: str) -> str:
    try:
        if market == "US":
            info = yf.Ticker(symbol).info
            return info.get("shortName", symbol)
        else:  # KR
            df = fdr.DataReader(symbol)
            if not df.empty:
                return fdr.StockListing("KRX")[fdr.StockListing("KRX")["Code"] == symbol]["Name"].values[0]
            return symbol
    except:
        return symbol

# ====== 입력 영역 ======
st.subheader("① 보유주식 입력")
with st.form("holding_form"):
    col1, col2 = st.columns(2)
    with col1:
        symbol = st.text_input("종목코드", placeholder="005930 or AAPL")
        market = st.selectbox("시장", ["KR", "US"])
        purchase_date = st.date_input("구매일", value=date.today())
    with col2:
        purchase_price = st.number_input("매입단가", min_value=0.0, step=0.01)
        quantity = st.number_input("수량", min_value=0.0, step=1.0)
        memo = st.text_area("메모(선택)", height=50)

    submitted = st.form_submit_button("매수 저장")
    if submitted:
        if not symbol or quantity <= 0 or purchase_price <= 0:
            st.error("종목, 단가, 수량을 모두 입력해주세요.")
        else:
            save_trade(USER_ID, symbol, market, purchase_price, quantity, "buy", purchase_date, 0, memo)

# ====== 현황 영역 ======
st.subheader("② 현재 보유주식 현황")

def render_holdings_table():
    """보유 주식 현황 표와 총 손익 표시"""
    df = get_trade_history(USER_ID)
    if df.empty:
        st.info("입력된 보유주식이 없습니다.")
        return pd.DataFrame()

    # 종목별 매수, 매도 집계
    buy_df = df[df["action"] == "buy"].groupby(["symbol", "market"]).agg({"price": "mean", "quantity": "sum"}).reset_index()
    sell_df = df[df["action"] == "sell"].groupby(["symbol", "market"]).agg({"quantity": "sum"}).reset_index()

    # 매도 수량을 매수 집계에서 차감
    merged = pd.merge(buy_df, sell_df, on=["symbol", "market"], how="left", suffixes=("_buy", "_sell"))
    merged["quantity_sell"] = merged["quantity_sell"].fillna(0)
    merged["net_quantity"] = merged["quantity_buy"] - merged["quantity_sell"]

    # 순보유량이 0 이하이면 제외
    holdings = merged[merged["net_quantity"] > 0].copy()

    rows = []
    total_invested = 0
    total_value = 0

    for _, row in holdings.iterrows():
        sym = row["symbol"]
        mk = row["market"]
        buy_price = float(row["price"])
        qty = int(row["net_quantity"])  # 정수 수량
        cur_price = fetch_current_price(sym, mk)
        name = get_company_name(sym, mk)

        invested = buy_price * qty
        current_val = cur_price * qty
        pl_amount = current_val - invested
        pl_rate = (pl_amount / invested * 100) if invested > 0 else 0.0

        total_invested += invested
        total_value += current_val

        rows.append({
            "종목": f"{name} ({sym}/{mk})",
            "매입단가": buy_price,
            "보유수량": qty,
            "투자금액": invested,
            "현재가": cur_price,
            "평가금액": current_val,
            "손익금액": pl_amount,
            "수익률(%)": pl_rate,
            "symbol": sym,
            "market": mk
        })

    # 총 손익 계산
    total_pl = total_value - total_invested
    total_pl_rate = (total_pl / total_invested * 100) if total_invested > 0 else 0.0

    # 총 손익 표시
    st.markdown(f"### 📈 총 손익: {'+' if total_pl >= 0 else ''}{total_pl:,.0f}원 ({total_pl_rate:+.2f}%)")

    result_df = pd.DataFrame(rows)

    def color_profit(val):
        if val > 0:
            return "color: red"
        elif val < 0:
            return "color: blue"
        else:
            return "color: black"

    styled = (
        result_df.drop(columns=["symbol", "market"])
        .style
        .format({
            "매입단가": "{:,.2f}",
            "투자금액": "{:,.0f}",
            "현재가": "{:,.2f}",
            "평가금액": "{:,.0f}",
            "손익금액": "{:+,.0f}",
            "수익률(%)": "{:+.2f}%",
            "보유수량": "{:,.0f}"
        })
        .applymap(color_profit, subset=["손익금액", "수익률(%)"])
    )

    st.dataframe(styled, use_container_width=True)
    return result_df

# 최초 표 출력
result_df = render_holdings_table()

# ====== 매도 기능 ======
st.subheader("💰 매도하기")
if not result_df.empty:
    sell_symbol = st.selectbox("매도 종목 선택", result_df["종목"])
    sell_qty = st.number_input("매도 수량", min_value=1, step=1, format="%d")
    sell_date = st.date_input("매도일", value=date.today())

    if st.button("매도 실행"):
        sel_row = result_df[result_df["종목"] == sell_symbol].iloc[0]
        sym, mk = sel_row["symbol"], sel_row["market"]
        cur_price = fetch_current_price(sym, mk)

        if sell_qty > sel_row["보유수량"]:
            st.error("보유 수량보다 많이 매도할 수 없습니다.")
        else:
            save_trade(USER_ID, sym, mk, cur_price, sell_qty, "sell", sell_date, 0, "매도")
            st.success("매도 완료! 현황을 갱신합니다.")
            # 매도 후 즉시 표 갱신
            result_df = render_holdings_table()

# ====== AI 조언 받기 ======
st.subheader("🤖 AI 코칭 받기")
if st.button("AI 조언 받기"):
    # 0) 사용자 이름 조회
    ures = supabase.table("profiles") \
        .select("name") \
        .eq("id", "46351220-8554-4806-bf46-55d2ad935330") \
        .single() \
        .execute()
    name = ures.data.get("name", "46351220-8554-4806-bf46-55d2ad935330")

    # 1) 최근 거래내역 조회
    trades = supabase.table("trade_history") \
        .select("*") \
        .eq("user_id", USER_ID) \
        .order("trade_time", desc=True) \
        .limit(10) \
        .execute().data or []

    # 2) 최근 피드백 조회
    feedbacks = supabase.table("trade_feedback") \
        .select("*") \
        .eq("user_id", USER_ID) \
        .order("created_at", desc=True) \
        .limit(5) \
        .execute().data or []

    # 3) 프롬프트 작성
    prompt_lines = []
    prompt_lines.append(f"당신은 친절하고 논리적인 투자 코치입니다.")
    prompt_lines.append(f"사용자({name})의 최근 거래내역과 자동 피드백, 그리고 현재 주가를 참고하여")
    prompt_lines.append("향후 매수·매도 타이밍과 위험 관리 전략을 제안해주세요.")
    prompt_lines.append("예시: “주식 가치가 높으니 100달러까지 보유를 추천합니다. 그 이후엔 분할매도…” 등으로 답변해 주세요.")
    prompt_lines.append("\n=== 최근 거래내역 ===")

    for t in trades:
        sym    = t["symbol"]
        mk     = t["market"]
        action = t["action"].upper()
        dt     = t["trade_time"][:10]
        vol    = t["quantity"]
        pr     = t["price"]
        fee    = t.get("commission", 0.0)

        # 현재가 조회
        cur_price = fetch_current_price(sym, mk)

        prompt_lines.append(
            f"- {dt} {action} {sym}/{mk} {vol}주 @ {pr:.2f} (수수료 {fee:.2f}), 현재가 {cur_price:.2f}"
        )

    prompt_lines.append("\n=== 최근 자동 피드백 & 요약 지표 ===")
    for f in feedbacks:
        dt_fb = f["created_at"][:10]
        msg   = f["feedback_message"]
        stats = f.get("summary_stats", {})
        # JSON 를 예쁘게 들여쓰기
        stats_json = json.dumps(stats, ensure_ascii=False, indent=2)

        prompt_lines.append(f"- {dt_fb}: {msg}")
        prompt_lines.append(f"  요약 지표:\n```\n{stats_json}\n```")

    # 4) 하나의 문자열로 합치기
    full_prompt = "\n".join(prompt_lines)

    # (디버깅)
    # st.text_area("프롬프트", full_prompt, height=300)

    # 5) Gemini 호출
    with st.spinner("AI 코칭 생성 중..."):
        ai_resp = gemini_model.generate_content(full_prompt)

    # 6) 결과 출력
    st.markdown("**✨ AI 코칭 결과**")
    st.write(ai_resp.text)