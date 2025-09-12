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
import random


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
    start_date = end_date - datetime.timedelta(days=180)
    st.write(f"테스트 기간: {start_date} ~ {end_date}")
    run_btn = st.button("시뮬레이션 실행")

if run_btn:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    forward_window = 30   # 매수 후 최대 며칠까지 관찰 (예: 30일)
    monte_carlo_k = 5     # 각 스냅샷마다 랜덤 매도 시점 개수

    # 기간을 3개월로 변경
    end_date = date.today()
    start_date = end_date - datetime.timedelta(days=90)
    st.write(f"테스트 기간 (3개월): {start_date} ~ {end_date}")

    # 주간 스냅샷 (매주 1번)
    week_dates = pd.date_range(start=start_date, end=end_date, freq='7D').to_pydatetime().tolist()
    records = []

    for snapshot_date in week_dates:
        snapshot_str = snapshot_date.strftime("%Y-%m-%d")

        # 그 시점까지의 가격 데이터를 불러옵니다
        if test_market == "US":
            df_price = yf.Ticker(test_symbol).history(
                start=start_date - datetime.timedelta(days=10),
                end=snapshot_date + datetime.timedelta(days=1)
            )
        else:
            df_price = fdr.DataReader(test_symbol, start=start_date - datetime.timedelta(days=10),
                                      end=snapshot_date)

        if df_price.empty:
            continue

        df_price = df_price.rename(columns={"Close":"종가","High":"고가","Low":"저가","Volume":"거래량"})
        df_price.index = df_price.index.tz_localize(None)
        df_price = df_price.loc[:snapshot_date].dropna()
        if len(df_price) < 30:
            continue

        idx = len(df_price) - 1
        cur_price = float(df_price['종가'].iloc[-1])

        # 지표 및 펀더멘털 계산
        stats = compute_advanced_stats(df_price, trade_price=cur_price, trade_idx=idx, action="buy")
        fnd   = fetch_fundamentals(test_symbol, test_market)

        # LLM에 매수 타이밍(buy_t)만 묻도록 프롬프트 구성
        prompt = []
        prompt.append(f"=== 입력 데이터 ===\n시점: {snapshot_str}")
        prompt.append(f"-- {test_symbol}/{test_market} --")
        prompt.append(json.dumps(stats, ensure_ascii=False))
        prompt.append(f"PER: {fnd['PER']}, PBR: {fnd['PBR']}, EPS: {fnd['EPS']}")
        prompt.append("\n질문: 이 시점에서 권하는 **매수 가격(buy_t)** 을 float으로만 숫자 형태로 알려주세요. (예: 123.45). 만약 매수를 권하지 않으면 NaN으로 반환하세요.")

        full_prompt = "\n".join(prompt)
        system_message = (
            "당신은 친절하고 논리적인 투자 코치입니다.\n"
            "사용자가 제시한 기술지표·펀더멘털 데이터를 보고, 매수 타이밍(가격)을 제안해 주세요.\n"
            "출력은 오직 하나의 숫자(또는 NaN)로만 응답하세요."
        )

        # LLM 호출
        try:
            response = client.chat.completions.create(
                model="gpt-5",
                messages=[
                    {"role":"system","content":system_message},
                    {"role":"user","content": full_prompt}
                ],
                timeout=None
            )
            ai_text = response.choices[0].message.content.strip()
            cleaned = ai_text.replace("```", "").strip()
            # 숫자 파싱: NaN 또는 float
            try:
                buy_t = float(cleaned)
            except Exception:
                buy_t = np.nan
        except Exception as e:
            st.warning(f"LLM 호출 실패 (스냅샷 {snapshot_str}): {e}")
            buy_t = np.nan

        # 매수 권고가 NaN이면 스킵 (Monte Carlo 시뮬레이션 불필요)
        if np.isnan(buy_t):
            records.append({
                "snapshot_date": snapshot_str,
                "cur_price": cur_price,
                "buy_t": np.nan,
                "mc_avg_return(%)": np.nan,
                "mc_samples": []
            })
            continue

        # 매수 시점 이후 forward_window 일간의 실제 가격(종가) 시계열 확보
        if test_market == "US":
            fut = yf.Ticker(test_symbol).history(
                start=snapshot_date + datetime.timedelta(days=1),
                end=snapshot_date + datetime.timedelta(days=forward_window+1)
            )['Close']
        else:
            fut = fdr.DataReader(test_symbol,
                                 start=snapshot_date + datetime.timedelta(days=1),
                                 end=snapshot_date + datetime.timedelta(days=forward_window))['Close']

        if fut.empty or len(fut) == 0:
            records.append({
                "snapshot_date": snapshot_str,
                "cur_price": cur_price,
                "buy_t": buy_t,
                "mc_avg_return(%)": np.nan,
                "mc_samples": []
            })
            continue

        fut = fut.reset_index(drop=True)

        # Monte Carlo: k개의 랜덤 매도 시점(최소 하루 뒤)을 뽑아 '매수 가격 = buy_t' 기준 수익률 계산
        mc_returns = []
        for _ in range(monte_carlo_k):
            # fut 길이에 맞춰 랜덤 인덱스 선택 (1 .. len(fut)-1 포함)
            sell_idx = random.randint(0, max(0, len(fut)-1))
            sell_price = float(fut.iloc[sell_idx])
            # 수익률 = (sell_price - buy_t) / buy_t * 100
            ret_pct = (sell_price - buy_t) / buy_t * 100
            mc_returns.append(round(ret_pct, 4))

        avg_mc_return = float(np.mean(mc_returns)) if mc_returns else np.nan

        records.append({
            "snapshot_date": snapshot_str,
            "cur_price": cur_price,
            "buy_t": buy_t,
            "mc_avg_return(%)": round(avg_mc_return, 4),
            "mc_samples": mc_returns
        })

        # 결과 DataFrame
    df_res = pd.DataFrame(records)
    st.subheader("▶ LLM(매수) + Random Monte Carlo(매도) 백테스트 결과 (3개월)")

    # 컬럼 설명
    st.markdown("""
    **컬럼 설명**
    - `snapshot_date`: 백테스트 시점(매수 후보 시점)  
    - `cur_price`: 해당 시점의 실제 종가  
    - `buy_t`: LLM이 제안한 매수 가격 (숫자). NaN이면 LLM이 매수를 권하지 않음  
    - `mc_avg_return(%)`: Monte Carlo로 K번 랜덤 매도했을 때의 평균 수익률(%) — **buy_t 기준**  
    - `mc_samples`: 개별 Monte Carlo 샘플(각 샘플의 수익률 % 리스트)
    """)

    st.dataframe(df_res)

    # 요약 통계: Monte Carlo 평균 수익률 & Annualized Sharpe Ratio
    valid_mc = df_res["mc_avg_return(%)"].dropna()
    if len(valid_mc) > 0:
        mean_mc = valid_mc.mean()
        st.markdown(f"**📊 Monte Carlo 평균 수익률(스냅샷별 avg):** {mean_mc:.4f}%")

        # 샤프비율 계산: 퍼센트 -> 소수
        mc_rets_decimal = valid_mc / 100.0
        if len(mc_rets_decimal) > 1 and mc_rets_decimal.std() != 0:
            sharpe_mc = mc_rets_decimal.mean() / mc_rets_decimal.std() * np.sqrt(52)  # 주간 스냅샷 기준 연환산
            st.markdown(f"**📈 Annualized Sharpe Ratio (Monte Carlo):** {sharpe_mc:.4f}")
        else:
            st.markdown("Monte Carlo 샤프 계산: 데이터 부족 또는 표준편차 0")
    else:
        st.markdown("유효한 Monte Carlo 결과 없음")

    # 발표용 해석 가이드 텍스트
    st.markdown("""
    **해석 가이드 (예시)**  
    - Annualized Sharpe Ratio 해석:
      - 1.0 이상 → 준수한 성과  
      - 2.0 이상 → 펀드 매니저도 인정하는 매우 우수한 성과  
      - 3.0 이상 → 뛰어난 전략 (월가 퀀트 수준)  
    - 본 평가 방식은 **LLM이 제시한 매수(가격)** 을 고정한 뒤, **랜덤 매도 시점 K개**를 뽑아 얻은 평균 성과를 측정합니다.  
      즉, 이 수치는 'LLM의 매수 타이밍이 랜덤 매도에 대해 어느 정도 유리한가'를 보여줍니다.
    """)

    # ===== 월별 수익률 비교 =====
    st.subheader("📊 월별 평균 수익률 비교")

    try:
        # 1. 월별 수익률 계산
        if test_market == "US":
            df_month = yf.download(test_symbol, start=start_date, end=end_date, auto_adjust=False)
        else:
            df_month = fdr.DataReader(test_symbol, start=start_date, end=end_date)

        if not df_month.empty:
            df_month = df_month.rename(columns={"Close": "종가"})
            monthly_returns = df_month["종가"].resample("ME").last().pct_change() * 100
            monthly_avg = float(monthly_returns.mean())  # float으로 캐스팅

            st.write(f"**{test_symbol}/{test_market} 월별 평균 수익률:** {monthly_avg:.2f}%")

            # 2. 유저 Monte Carlo 결과 평균과 비교
            valid_mc = df_res["mc_avg_return(%)"].dropna()
            if len(valid_mc) > 0:
                user_avg = valid_mc.mean()
                diff = user_avg - monthly_avg
                st.write(f"**유저 전략 평균 수익률:** {user_avg:.2f}%")
                st.write(f"➡️ 유저 전략은 월평균 대비 **{diff:+.2f}%** {'높습니다' if diff>0 else '낮습니다'}")
            
            # 3. 상세 표 출력
            st.dataframe(monthly_returns.rename("월별 수익률(%)").to_frame())
        else:
            st.warning("월별 수익률 데이터를 불러올 수 없습니다.")

    except Exception as e:
        st.error(f"월별 수익률 계산 실패: {e}")
