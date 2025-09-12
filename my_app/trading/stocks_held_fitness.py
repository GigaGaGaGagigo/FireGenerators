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
import json
from openai import OpenAI

# .env 로드
load_dotenv()

# Supabase 초기화
SUPABASE_URL = os.getenv("SUPABASE_URL") 
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# OpenAI API Key 설정
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# 세션 user_id
if "user_id" not in st.session_state:
    st.session_state.user_id = "5eb9789f-bd00-4b3c-8149-bf4652af8540"

USER_ID = st.session_state.user_id


st.title("📊 모의투자 보유주식 관리")

def fetch_usd_krw_rate() -> float:
    """
    최근 USD/KRW 환율(종가)을 가져옵니다. 
    실패 시 0.0 반환.
    """
    try:
        # yfinance 로부터 KRW=X 티커(달러당 원화 환율) 가져오기
        df = yf.Ticker("KRW=X").history(period="1d")
        return float(df["Close"].iloc[-1])
    except:
        return 0.0

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
    # if action == "buy":
    #     after = df.iloc[idx:idx+7]['종가']
    #     max_profit = np.round((after.max() - trade_price) / trade_price * 100, 2)
    #     min_profit = np.round((after.min() - trade_price) / trade_price * 100, 2)
    #     result["max_profit"] = float(max_profit)
    #     result["min_profit"] = float(min_profit)
    # else:
    #     after = df.iloc[idx:idx+7]['종가']
    #     missed_profit = np.round((after.max() - trade_price) / trade_price * 100, 2)
    #     result["missed_profit"] = float(missed_profit)
    return result

def fetch_fundamentals(symbol: str, market: str) -> dict:
    """
    Yahoo Finance info를 통해 PER, PBR, 사업 개요(business summary) 등을 가져옵니다.
    KR 시장의 경우 간단히 None 처리하거나, 추가 API를 붙이면 됩니다.
    """
    try:
        if market == "US":
            info = yf.Ticker(symbol).info
            # print("--------------------------")
            # print(info)
            return {
                "PER":       info.get("trailingPE", None),
                "PBR":       info.get("priceToBook", None),
                "EPS":       info.get("epsTrailingTwelveMonths", None),
                "사업개요":  info.get("longBusinessSummary", "")[:300]  # 앞 300자만
            }
        else:  # KR
            # 간단히 None 반환 (여기에 DART API나 Open DART 라이브러리를 붙이시면 됩니다)
            return {
                "PER":      None,
                "PBR":      None,
                "EPS":      None,
                "사업개요": ""
            }
    except Exception as e:
        return {
            "PER":      None,
            "PBR":      None,
            "EPS":      None,
            "사업개요": ""
        }


# ====== 기존 함수 ======
def save_trade(
    user_id: str,
    symbol: str,
    market: str,
    price: float,
    qty: float,
    action: str,
    trade_time: date,
    commission: float = 0.0
):
    # 1️⃣ trade_history 저장
    data = {
        "user_id":    user_id,
        "symbol":     symbol.upper(),
        "market":     market,
        "price":      price,
        "qty":     qty,
        "action":     action.lower(),
        "trade_time": trade_time.isoformat(),
        "commission": commission
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
        "style_type": "default"
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

def get_holdings_data(user_id: str):
    """
    v_current_holdings 뷰를 읽어서
      - symbol, market, net_qty, avg_buy_price 가져옴
      - 현재가/환율 조회 → 투자금액, 평가금액, 손익 계산
    반환: (holdings_df, total_invested, total_value)
    """
    # 1) 뷰 조회
    res = (
        supabase
        .table("v_current_holdings")        # View 이름을 table() 에 그대로 넘기면 됩니다
        .select("symbol, market, net_qty, avg_buy_price")
        .eq("user_id", user_id)
        .execute()
    )
    # 에러 체크
    if getattr(res, "status_code", 0) >= 400:
        msg = getattr(res, "error_message", f"status={res.status_code}")
        st.error(f"보유내역 조회 실패: {msg}")
        return pd.DataFrame(), 0.0, 0.0

    # 데이터가 없으면 빈 값 리턴
    if not res.data:
        return pd.DataFrame(), 0.0, 0.0

    df = pd.DataFrame(res.data)

    # 2) 현재가·환율 조회 후 손익 계산
    usdkrw = fetch_usd_krw_rate()  # 미리 구현해 둔 함수
    rows = []
    total_invested = 0.0
    total_value    = 0.0

    for r in df.to_dict(orient="records"):
        sym = r["symbol"]
        mk  = r["market"]
        qty = float(r["net_qty"])
        buy_p = float(r["avg_buy_price"])
        cur_p = fetch_current_price(sym, mk)  # 미리 구현해 둔 함수

        # 원화 환산
        rate = usdkrw if mk == "US" else 1
        inv_krw = buy_p * qty * rate
        val_krw = cur_p * qty * rate
        pl       = val_krw - inv_krw
        pl_pct   = (pl / inv_krw * 100) if inv_krw else 0.0

        rows.append({
            "종목":       f"{get_company_name(sym, mk)} ({sym}/{mk})",
            "매입단가":     buy_p,
            "보유수량":     qty,
            "투자금액(원)":  inv_krw,
            "현재가":       cur_p,
            "평가금액(원)":  val_krw,
            "손익금액(원)":  pl,
            "수익률(%)":    pl_pct,
            # internal 용
            "symbol": sym,
            "market": mk,
        })
        total_invested += inv_krw
        total_value    += val_krw

    holdings_df = pd.DataFrame(rows)
    return holdings_df, total_invested, total_value

# 콜백 함수: 삭제
def delete_trade(trade_id):
    resp = supabase.table("trade_history") \
                   .delete() \
                   .eq("id", trade_id) \
                   .execute()
    if getattr(resp, "status_code", 0) < 300:
        st.success("삭제 완료")
    else:
        st.error("삭제 실패")

# 콜백 함수: 수정
def update_trade(trade_id, new_date, new_action, new_symbol, new_market,
                 new_price, new_qty):
    update_data = {
        "trade_time": new_date.isoformat(),
        "action":     new_action,
        "symbol":     new_symbol.upper(),
        "market":     new_market,
        "price":      float(new_price),
        "qty":   float(new_qty)
    }
    resp = supabase.table("trade_history") \
                   .update(update_data) \
                   .eq("id", trade_id) \
                   .execute()
    if getattr(resp, "status_code", 0) < 300:
        st.success("수정 완료")
    else:
        st.error("수정 실패")

# ① 총 손익 영역
holdings_df, total_inv, total_val = get_holdings_data(USER_ID)
total_pl      = total_val - total_inv
total_pl_pct  = total_pl/total_inv*100 if total_inv else 0
usdkrw = fetch_usd_krw_rate()

st.markdown(
    f"## 📈 총 손익(원화): "
    f"{total_pl:+,.0f}원 ({total_pl_pct:+.2f}%)  |  환율 USD/KRW: {usdkrw:.2f}"
)

# ====== 입력 영역 ======
tab_buy, tab_sell = st.tabs(["💹 매수", "💰 매도"])

# ▶ 매수 탭
with tab_buy:
    st.subheader("① 보유주식 입력 (매수)")
    with st.form("buy_form"):
        col1, col2 = st.columns(2)
        with col1:
            buy_symbol = st.text_input("종목코드", placeholder="005930 or AAPL")
            buy_market = st.selectbox("시장", ["KR", "US"], key="buy_market")
            buy_date   = st.date_input("구매일", value=date.today(), key="buy_date")
        with col2:
            buy_price = st.number_input("매입단가", min_value=0.0, step=0.01, key="buy_price")
            buy_qty   = st.number_input("수량",     min_value=0.0, step=1.0, key="buy_qty")
            memo      = st.text_area("메모(선택)", height=50, key="buy_memo")

        submitted_buy = st.form_submit_button("매수 저장")
        if submitted_buy:
            if not buy_symbol or buy_price <= 0 or buy_qty <= 0:
                st.error("종목, 단가, 수량을 모두 입력해주세요.")
            else:
                save_trade(
                    USER_ID,
                    buy_symbol, buy_market,
                    float(buy_price),
                    float(buy_qty),
                    "buy",
                    buy_date,
                    commission=0,
                    memo=memo
                )

# ▶ 매도 탭
with tab_sell:
    st.subheader("매도 입력")
    if holdings_df.empty:
        st.info("매도할 보유주식이 없습니다.")
    else:
        selected = st.selectbox("매도 종목 선택", holdings_df["종목"])
        row = holdings_df[holdings_df["종목"]==selected].iloc[0]
        sym, mk, max_qty = row["symbol"], row["market"], int(row["보유수량"])
        default_price = fetch_current_price(sym, mk)
        sell_price = st.number_input("매도 단가", value=default_price, step=0.01)
        sell_qty   = st.number_input("매도 수량", min_value=1, max_value=max_qty, step=1)
        sell_date  = st.date_input("매도일", value=date.today())
        if st.button("매도 저장"):
            save_trade(USER_ID, sym, mk, sell_price, sell_qty, "sell", sell_date)
            st.success("매도 저장 완료")
            # 탭 안에서는 바로 holdings_df 를 갱신해도 됨

# ③ 보유 종목 테이블
st.subheader("현재 보유주식 현황")
if holdings_df.empty:
    st.info("보유종목이 없습니다.")
else:
    # .applymap → .map 으로 교체
    display_df = (
        holdings_df
        .drop(columns=["symbol","market"])
        .style
        .format({
            "매입단가":    "{:,.2f}",
            "투자금액(원)": "{:,.0f}",
            "현재가":      "{:,.2f}",
            "평가금액(원)": "{:,.0f}",
            "손익금액(원)": "{:+,.0f}",
            "수익률(%)":   "{:+.2f}%"
        })
        .map(lambda v: "color:red" if v>0 
                       else "color:blue" if v<0 
                       else None,
             subset=["손익금액(원)", "수익률(%)"])
    )
    st.dataframe(display_df, use_container_width=True)

st.subheader("🤖 AI 코칭 받기")
if st.button("AI 조언 받기"):
    # 0) 사용자 이름 조회
    ures = supabase.table("profiles") \
        .select("name") \
        .eq("id", USER_ID) \
        .single() \
        .execute()
    name = ures.data.get("name", USER_ID)

    # 1) 최근 거래내역 조회 (10건)
    trades = supabase.table("trade_history") \
        .select("*") \
        .eq("user_id", USER_ID) \
        .order("trade_time", desc=True) \
        .limit(10) \
        .execute().data or []

    # 2) 프롬프트 기본 문장
    prompt_lines = [
        "=== 입력 데이터 ===",
        f"사용자: {name}"
    ]

    # 3) 최근 거래내역 요약
    prompt_lines.append("\n최근 거래내역 :")
    for t in trades:
        sym, mk = t["symbol"], t["market"]
        action = t["action"].upper()
        dt = t["trade_time"][:10]
        vol, pr = t["qty"], t["price"]
        cur_price = fetch_current_price(sym, mk)
        prompt_lines.append(
            f"- {dt} {action} {sym}/{mk} {vol}주 @ {pr:.2f}, 현재가 {cur_price:.2f}"
        )

    # 4) 오늘 기준 요약 지표(compute_advanced_stats) & 펀더멘털
    prompt_lines.append("\n오늘 기술지표 & 펀더멘털:")
    # 거래된 종목들을 중복 없이
    symbols = list({t["symbol"] for t in trades})
    for sym in symbols:
        mk = next(t["market"] for t in trades if t["symbol"] == sym)
        # 4-1) 가격 데이터 로딩
        df_price = (
            fdr.DataReader(sym) if mk == "KR"
            else yf.Ticker(sym).history(period="1y")
        )
        df_price = df_price.rename(
            columns={"Close":"종가","High":"고가","Low":"저가","Volume":"거래량"}
        )
        df_price.index = df_price.index.tz_localize(None)
        df_price = df_price.dropna()

        # 4-2) 현재가, 마지막 인덱스 위치
        cur_price = fetch_current_price(sym, mk)
        idx = len(df_price) - 1

        print("---------------")
        print(sym)
        # 4-3) 지표 계산 (action은 여기에 영향 없으므로 "buy"로 통일)
        stats = compute_advanced_stats(df_price, cur_price, idx, action="buy")
        stats_json = json.dumps(stats, ensure_ascii=False, indent=2)

        print("---------------")
        print(stats)
        print(stats_json)

        # 4-4) 펀더멘털 정보 가져오기
        fnd = fetch_fundamentals(sym, mk)

        # 4-5) 프롬프트에 추가
        prompt_lines.append(f"\n-- {sym}/{mk} --")
        prompt_lines.append("```json\n" + stats_json + "\n```")
        prompt_lines.append(
            f"PER: {fnd['PER']}, PBR: {fnd['PBR']}, EPS: {fnd['EPS']}\n"
            f"사업개요: {fnd['사업개요']}\n"
        )
        # 보유 현황 추가
        holding_info = holdings_df[holdings_df['symbol'] == sym]
        if not holding_info.empty:
            h_row = holding_info.iloc[0]
            prompt_lines.append(
                f"보유 현황: 현재가 {h_row['현재가']:,.2f}, "
                f"보유수량 {h_row['보유수량']}, "
                f"수익률 {h_row['수익률(%)']:.2f}%"
            )
    
    role_json = {
      "symbol":      "종목코드/시장 (예: AAPU/US)",
      "buy_timing":  "구체적인 매수 시점 제안 float값으로 표시",
      "sell_timing": "구체적인 매도 시점 제안 float값으로 표시",
      "stop_loss":   "손절가 제안 float값으로 표시",
      "rationale":   "제안 근거를 간략하게 설명하고 현재 보유주식을 어떻게 할지 제시"
    }
    role_json = json.dumps(role_json, ensure_ascii=False, indent=2)

    prompt_lines.append("\n=== 응답 JSON 스키마 ===")
    prompt_lines.append("결과는 반드시 각 기술지표 & 펀더멘털당 하나씩 아래 JSON 형태로만 반환하세요.")
    prompt_lines.append("```json\n" + role_json + "\n```")

    full_prompt = "\n".join(prompt_lines)

    system_message = [
        "당신은 친절하고 논리적인 투자 코치입니다.",
        "사용자가 제시한 과거 거래내역과 기술지표·펀더멘털 데이터를 보고,",
        "매수·매도 타이밍과 손절가를 제안해주세요.",
        "출력은 반드시 아래 JSON 스키마를 준수해야 합니다."
    ]
    full_system_message = "\n".join(system_message)

    #디버그
    st.text_area("시스템 프롬프트", full_system_message, height=300)
    st.text_area("프롬프트", full_prompt, height=300)
    

    # 5) OpenAI API 호출
    with st.spinner("AI 코칭 생성 중..."):
        # 2) 새 인터페이스로 호출
        response = client.chat.completions.create(
            model="gpt-5",    # 혹은 gpt-5-2025-08-07
            messages=[
                {"role":"system","content": full_system_message},
                {"role":"user","content": full_prompt}
            ],
            max_completion_tokens=6000,
        timeout=None       # 최대 생성 토큰 수
        )

        # 디버그
        # st.write(response)
        # st.write("finish_reason:", response.choices[0].finish_reason)
        # st.write("usage:", response.usage)


        ai_text = response.choices[0].message.content
        st.markdown("**✨ AI 코칭 결과**")
        st.write(ai_text)