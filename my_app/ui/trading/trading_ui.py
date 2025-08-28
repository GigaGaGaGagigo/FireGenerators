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
USER_ID = st.session_state.user.id

if USER_ID == "":
    USER_ID = "62f90625-6e2d-4125-8d22-2214eb0da631"


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
               .agg(avg_price=("price","mean"), qty_buy=("qty","sum")) \
               .reset_index()
    sell_df= df[df.action=="sell"].groupby(["symbol","market"]) \
               .agg(qty_sell=("qty","sum")) \
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

def render ():

    st.title("📊 모의투자 보유주식 관리")

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
    tab_buy, tab_sell, tab_history = st.tabs(["💹 매수", "💰 매도", "📜 거래내역"])

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
                        commission=0
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

    # ▶ 거래내역 탭
    with tab_history:
        st.subheader("거래내역 수정/삭제")
        df_trades = get_trade_history(USER_ID)
        if df_trades.empty:
            st.info("거래내역이 없습니다.")
        else:
            # 최근 순으로 정렬
            df_trades = df_trades.sort_values("trade_time", ascending=False)
            for _, row in df_trades.iterrows():
                trade_id   = row["id"]
                symbol     = row["symbol"]
                market     = row["market"]
                action     = row["action"].upper()
                trade_time = row["trade_time"][:10]
                price      = row["price"]
                qty   = row["qty"]

                exp = st.expander(f"{trade_time} | {action} | {symbol}/{market}", expanded=False)
                with exp:
                    # 1행 3컬럼 레이아웃
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        new_date   = st.date_input("거래일", value=pd.to_datetime(trade_time),
                                                key=f"date_{trade_id}")
                        new_action = st.selectbox("행동", ["buy","sell"],
                                                index=0 if action=="BUY" else 1,
                                                key=f"act_{trade_id}")
                    with c2:
                        new_symbol = st.text_input("종목코드", value=symbol,
                                                key=f"sym_{trade_id}")
                        new_market = st.selectbox("시장", ["KR","US"],
                                                index=0 if market=="KR" else 1,
                                                key=f"mk_{trade_id}")
                    with c3:
                        new_price  = st.number_input("단가", value=float(price),
                                                    key=f"pr_{trade_id}")
                        new_qty    = st.number_input("수량", value=float(qty),
                                                    key=f"qty_{trade_id}")


                    # 버튼 배치
                    btn_col1, btn_col2 = st.columns([1,1])
                    with btn_col1:
                        st.button("수정 저장",
                                key=f"edit_{trade_id}",
                                on_click=update_trade,
                                args=(trade_id, new_date, new_action,
                                        new_symbol, new_market,
                                        new_price, new_qty,))
                    with btn_col2:
                        st.button("삭제",
                                key=f"del_{trade_id}",
                                on_click=delete_trade,
                                args=(trade_id,))


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

    st.subheader("🤖 AI 코칭")
    res_latest = (
        supabase.table("ai_coaching")
        .select("*")
        .eq("user_id", USER_ID)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    if res_latest.data:
        latest = res_latest.data[0]
        st.markdown(
            f"📌 최근 AI 코칭 결과 ({latest['created_at'][:10]})"
        )
        st.write(latest["result"])
        st.divider()

    if st.button("AI 코칭 받기"):
        # 0) 사용자 이름 조회
        ures = supabase.table("profiles") \
            .select("name") \
            .eq("id", USER_ID) \
            .limit(1) \
            .execute()
        name = ures.data[0]["name"]

        


        # 1) 최근 거래내역 조회 (10건)
        trades = supabase.table("trade_history") \
            .select("*") \
            .eq("user_id", USER_ID) \
            .order("trade_time", desc=True) \
            .limit(10) \
            .execute().data or []

        # 2) 프롬프트 기본 문장
        system_message = [
            "당신은 친절하고 논리적인 투자 코치입니다.",
            f"사용자({name})의 최근 거래내역과 오늘 기준 기술지표,펀더멘털,per를 참고하여",
            "매수·매도 타이밍과 손절가를 제안해주세요.",
            "기술지표를 어린이도 알기 쉽게 풀어서 설명해 주면서 예상 상승 가격 또는 하락 가격을 알려줘"
        ]
        full_system_message = "\n".join(system_message)


        prompt_lines = []

        # 3) 최근 거래내역 요약
        prompt_lines.append("\n=== 최근 거래내역 ===")
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
        prompt_lines.append("\n=== 오늘 기술지표 & 펀더멘털 ===")
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

            # 4-3) 지표 계산 (action은 여기에 영향 없으므로 "buy"로 통일)
            stats = compute_advanced_stats(df_price, cur_price, idx, action="buy")
            stats_json = json.dumps(stats, ensure_ascii=False, indent=2)

            # 4-4) 펀더멘털 정보 가져오기
            fnd = fetch_fundamentals(sym, mk)

            # 4-5) 프롬프트에 추가
            prompt_lines.append(f"\n-- {sym}/{mk} --")
            prompt_lines.append("```json\n" + stats_json + "\n```")
            prompt_lines.append(
                f"PER: {fnd['PER']}, PBR: {fnd['PBR']}, EPS: {fnd['EPS']}\n"
                f"사업개요: {fnd['사업개요']}\n"
            )

        full_prompt = "\n".join(prompt_lines)
        st.text_area("프롬프트", full_prompt, height=300)

        # 5) OpenAI API 호출
        with st.spinner("AI 코칭 생성 중..."):
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role":"system","content": full_system_message},
                    {"role":"user","content": full_prompt}
                ],
                temperature=0.7,
                max_tokens=500
            )

            ai_text = response.choices[0].message.content
            st.markdown("**✨ AI 코칭 결과**")
            st.write(ai_text)

            # ✅ 결과 DB에 저장
            save_data = {
                "user_id": USER_ID,
                "prompt": full_prompt,
                "result": ai_text
            }
            save_res = supabase.table("ai_coaching").insert(save_data).execute()

            if getattr(save_res, "status_code", 0) < 300:
                st.success("AI 코칭 결과 저장 완료 ✅")
            else:
                st.error("AI 코칭 결과 저장 실패 ❌")