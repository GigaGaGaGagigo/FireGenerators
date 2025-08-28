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
import datetime


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
    st.session_state.user_id = "0bfc599a-db77-49ef-8556-31d2be8ffdaf"

USER_ID = st.session_state.user_id


st.title("📊 모의투자 보유주식 관리")

# 환율확인 함수
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

    # 0) 복사 및 NaN 보간
    df = df.copy()
    df['종가'] = df['종가'].ffill().bfill()
    df['고가'] = df['고가'].ffill().bfill()
    df['저가'] = df['저가'].ffill().bfill()
    df['거래량'] = df['거래량'].ffill().bfill()

    # 1) 최소 데이터 길이 체크 (MACD slow 기간 = 26)
    # if len(df) < 26:
    #     return {}

    # 2) EMA, RSI
    df['EMA20'] = ta.ema(df['종가'], length=20)
    df['EMA60'] = ta.ema(df['종가'], length=60)
    df['EMA120'] = ta.ema(df['종가'], length=120)
    df['RSI14'] = ta.rsi(df['종가'], length=14)

    # 3) MACD 안전 처리
    try:
        # DataFrame accessor 로 호출하면 None 리턴 안 함
        macd_df = df.ta.macd(close='종가', fast=12, slow=26, signal=9)
        df['MACD']        = macd_df['MACD_12_26_9']
        df['MACD_SIGNAL'] = macd_df['MACDs_12_26_9']
    except Exception:
        df['MACD']        = np.nan
        df['MACD_SIGNAL'] = np.nan

    # 4) STOCH, BBANDS, VWAP
    try:
        # DataFrame accessor 로 호출하면 None 리턴 안 함
        stoch = ta.stoch(df['고가'], df['저가'], df['종가'])
        df['STOCH_K'] = stoch['STOCHk_14_3_3']
        df['STOCH_D'] = stoch['STOCHd_14_3_3']
    except Exception:
        df['STOCH_K'] = np.nan
        df['STOCH_D'] = np.nan
    
    try:
        # DataFrame accessor 로 호출하면 None 리턴 안 함
        bbands = ta.bbands(df['종가'], length=20)
        df['BB_UPPER'] = bbands['BBU_20_2.0']
        df['BB_LOWER'] = bbands['BBL_20_2.0']
    except Exception:
        df['BB_UPPER'] = np.nan
        df['BB_LOWER'] = np.nan

    
    df['VWAP'] = ta.vwap(df['고가'], df['저가'], df['종가'], df['거래량'])

    # 5) 결과 추출
    idx = trade_idx
    def safe_float(x):
        return float(x) if (pd.notna(x) and x is not None) else None

    result = {
        "EMA20":       safe_float(df['EMA20'].iat[idx]),
        "EMA60":       safe_float(df['EMA60'].iat[idx]),
        "EMA120":      safe_float(df['EMA120'].iat[idx]),
        "RSI14":       safe_float(df['RSI14'].iat[idx]),
        "MACD":        safe_float(df['MACD'].iat[idx]),
        "MACD_SIGNAL": safe_float(df['MACD_SIGNAL'].iat[idx]),
        "STOCH_K":     safe_float(df['STOCH_K'].iat[idx]),
        "STOCH_D":     safe_float(df['STOCH_D'].iat[idx]),
        "BB_UPPER":    safe_float(df['BB_UPPER'].iat[idx]),
        "BB_LOWER":    safe_float(df['BB_LOWER'].iat[idx]),
        "VWAP":        safe_float(df['VWAP'].iat[idx]),
    }

    # 6) buy/sell 별 추가 지표
    after = df['종가'].iloc[idx:idx+7]
    if action == "buy":
        result["max_profit"] = float(((after.max() - trade_price)/trade_price * 100).round(2))
        result["min_profit"] = float(((after.min() - trade_price)/trade_price * 100).round(2))
    else:
        result["missed_profit"] = float(((after.max() - trade_price)/trade_price * 100).round(2))

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
            df = ticker.history(period="2d")
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
    trade_history를 읽어
    - 종목별(심볼, 시장) 순보유수량, 평균매입가 계산
    - 현재가 조회해 투자금액, 평가금액, 손익 계산
    반환값: (holdings_df, total_invested, total_value)
    """
    df = get_trade_history(user_id)
    if df.empty:
        return pd.DataFrame(), 0.0, 0.0

    # 1) 매수/매도 집계 → 순보유량
    buy_df = df[df.action=="buy"].groupby(["symbol","market"]) \
               .agg(avg_price=("price","mean"), qty_buy=("quantity","sum")) \
               .reset_index()
    sell_df= df[df.action=="sell"].groupby(["symbol","market"]) \
               .agg(qty_sell=("quantity","sum")) \
               .reset_index()
    merged = buy_df.merge(sell_df, how="left", on=["symbol","market"])
    merged.qty_sell = merged.qty_sell.fillna(0)
    merged["net_qty"] = merged.qty_buy - merged.qty_sell
    merged = merged[merged.net_qty>0].copy()

    # 2) 각 종목별 현재가·PL 계산
    rows = []
    total_invested = 0.0
    total_value    = 0.0
    usdkrw = fetch_usd_krw_rate()

    for _, r in merged.iterrows():
        sym, mk = r.symbol, r.market
        buy_p, qty = float(r.avg_price), int(r.net_qty)
        cur_p = fetch_current_price(sym,mk)
        # 환산
        inv_krw = buy_p*qty*(usdkrw if mk=="US" else 1)
        val_krw = cur_p*qty*(usdkrw if mk=="US" else 1)
        pl       = val_krw - inv_krw
        pl_pct   = pl/ inv_krw*100 if inv_krw else 0

        rows.append({
            "종목": f"{get_company_name(sym,mk)} ({sym}/{mk})",
            "매입단가":    buy_p,
            "보유수량":    qty,
            "투자금액(원)":inv_krw,
            "현재가":      cur_p,
            "평가금액(원)":val_krw,
            "손익금액(원)":pl,
            "수익률(%)":   pl_pct,
            "symbol":sym, "market":mk
        })
        total_invested += inv_krw
        total_value    += val_krw

    holdings_df = pd.DataFrame(rows)
    return holdings_df, total_invested, total_value
# → 여기에 “적응도 테스트” UI 및 로직 추가
st.subheader("🧪 적응도 테스트 (백테스트)")

with st.expander("▶ 1년치 주간 시뮬레이션 설정"):
    test_symbol = st.text_input("심볼 입력", value="AAPL")
    test_market = st.selectbox("시장", ["US", "KR"], index=0)
    # 1년 전부터 오늘까지
    end_date = date.today()
    start_date = end_date - datetime.timedelta(days=365)
    st.write(f"테스트 기간: {start_date} ~ {end_date}")
    run_btn = st.button("시뮬레이션 실행")

if run_btn:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    # 7일 후를 추적해볼 기간 (예: action="buy" 후 7일간)
    forward_window = 7

    # 1) 매주 1회, pandas.date_range로 생성
    week_dates = pd.date_range(start=start_date, end=end_date, freq='7D').to_pydatetime().tolist()
    records = []

    for snapshot_date in week_dates:
        snapshot_str = snapshot_date.strftime("%Y-%m-%d")
        # 2) 그 시점까지의 가격 데이터만 로드
        if test_market == "US":
            df_price = yf.Ticker(test_symbol).history(start=start_date - datetime.timedelta(days=10),
                                                       end=snapshot_date + datetime.timedelta(days=1))
        else:
            df_price = fdr.DataReader(test_symbol, start=start_date - datetime.timedelta(days=10),
                                      end=snapshot_date)

        if df_price.empty:
            continue
        df_price = df_price.rename(columns={"Close":"종가","High":"고가","Low":"저가","Volume":"거래량"})
        df_price.index = df_price.index.tz_localize(None)
        df_price = df_price.loc[:snapshot_date].dropna()
        if len(df_price) < 120:  # 최소 데이터량 체크
            continue

        # 3) 인덱스, 현재가
        idx = len(df_price) - 1
        cur_price = float(df_price['종가'].iloc[-1])

        # 4) 지표 & 펀더멘털 계산
        stats = compute_advanced_stats(df_price, trade_price=cur_price, trade_idx=idx, action="buy")
        fnd   = fetch_fundamentals(test_symbol, test_market)

        print("--------------------------------")
        print(stats)

        # 5) AI 에 질의 (매매 제안 받기)
        #    – prompt 생성은 기존 코드와 동일하게 재사용
        prompt = []
        prompt.append(f"=== 입력 데이터 ===\n시점: {snapshot_str}")
        prompt.append(f"-- {test_symbol}/{test_market} --")
        prompt.append(json.dumps(stats, ensure_ascii=False))
        prompt.append(f"PER: {fnd['PER']}, PBR: {fnd['PBR']}, EPS: {fnd['EPS']}")
        prompt.append("=== 응답 JSON 스키마 ===")
        role_json = {
        "symbol":      "종목코드/시장 (예: AAPU/US)",
        "buy_timing":  "구체적인 매수 시점 제안 float값으로 표시",
        "sell_timing": "구체적인 매도 시점 제안 float값으로 표시",
        "stop_loss":   "손절가 제안 float값으로 표시",
        "rationale":   "제안 근거를 간략하게 설명"
        }
        role_json = json.dumps(role_json, ensure_ascii=False, indent=2)

        prompt.append("\n=== 응답 JSON 스키마 ===")
        prompt.append("결과는 반드시 각 기술지표 & 펀더멘털당 하나씩 아래 JSON 형태로만 반환하세요.")
        prompt.append(role_json)

        full_prompt = "\n".join(prompt)
        # st.write("프롬프트확인:", full_prompt)

        system_message = [
        "당신은 친절하고 논리적인 투자 코치입니다.",
        "사용자가 제시한 과거 거래내역과 기술지표·펀더멘털 데이터를 보고,",
        "매수·매도 타이밍과 손절가를 제안해주세요.",
        "출력은 반드시 아래 JSON 스키마를 준수해야 합니다."
        "출력은 오직 하나의 JSON 오브젝트만, 배열도, 코드펜스도 없이 깔끔하게 주십시오."
        ]
        full_system_message = "\n".join(system_message)

        # 실제 API 호출 (테스트 양이 많으면 속도/비용을 고려하세요)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role":"system","content":full_system_message},
                {"role":"user","content": full_prompt}
            ],
            temperature=0.7
        )
        ai_json = response.choices[0].message.content
        # st.write("각결과 확인:", ai_json)
        # 6) AI 제안 파싱
        cleaned = ai_json.replace("```json", "").replace("```", "").strip()
        st.write("클린드", cleaned)
        suggestion = json.loads(cleaned)
        try:
            parsed = json.loads(cleaned)
            # 리스트로 나올 수도, dict(객체)로 나올 수도 있다
            if isinstance(parsed, list):
                # 첫 번째 제안만 쓸 거라면
                suggestion = parsed[0]
            elif isinstance(parsed, dict):
                suggestion = parsed
            else:
                raise ValueError("알 수 없는 JSON 타입")
            buy_t  = float(suggestion.get("buy_timing", np.nan))
            sell_t = float(suggestion.get("sell_timing", np.nan))
            sl_t   = float(suggestion.get("stop_loss", np.nan))
        except Exception as e:
            st.warning(f"JSON 파싱 실패: {e}")
            buy_t, sell_t, sl_t = np.nan, np.nan, np.nan
        
        st.write("타이밍", buy_t, sell_t, sl_t)

        # 7) 실제 다음 forward_window일간 가격으로 성과 측정
        #    pandas.Series.append() 는 pandas 2.x 에서 제거되었으므로 pd.concat() 사용
        if test_market == "US":
            fut = yf.Ticker(test_symbol).history(period=f"{forward_window}d")['Close']
        else:
            fut = fdr.DataReader(test_symbol).iloc[-forward_window:]['Close']
        fut = fut.rename("종가")

         # concat 하면 인덱스가 꼬이지 않도록 ignore_index=False 또는 인덱스를 리셋해도 좋습니다.
        future_series = pd.concat([df_price['종가'], fut])
        future = future_series.reset_index(drop=True).iloc[idx+1 : idx+1+forward_window]
        # 실제 수익률
        real_buy_ret = (future.max() - buy_t)/buy_t*100 if not np.isnan(buy_t) else np.nan
        real_sell_ret= (sell_t - future.min())/sell_t*100 if not np.isnan(sell_t) else np.nan

        records.append({
            "snapshot_date": snapshot_str,
            "cur_price":    cur_price,
            "buy_t":        buy_t,
            "sell_t":       sell_t,
            "stop_loss":    sl_t,
            "real_buy_pct": round(real_buy_ret,2),
            "real_sell_pct":round(real_sell_ret,2)
        })

    # 8) 결과 DataFrame으로 보여주기
    df_res = pd.DataFrame(records)
    st.subheader("▶ 백테스트 결과 (주간 시뮬레이션)")
    st.dataframe(df_res)
    # 요약 통계
    st.write("평균 실제 매수 수익률:", df_res["real_buy_pct"].mean())
    st.write("평균 실제 매도 수익률:", df_res["real_sell_pct"].mean())