import os
from dotenv import load_dotenv
from supabase import create_client
import datetime
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import io
import json
import pandas_ta as ta

load_dotenv()

# LLM API 연동
import google.generativeai as genai

from pykrx import stock
import yfinance as yf

# 설정값 불러오기
with open("config.json", encoding="utf-8") as f:
    service_config = json.load(f)

url = "url입력"
key = "key입력"
supabase = create_client(url, key)

def get_stock_price(symbol, market, start_date, end_date):
    if market == 'KR':
        df = stock.get_market_ohlcv_by_date(start_date, end_date, symbol)
        if not df.empty:
            df['종가'] = df['종가'].astype(float)
            df['고가'] = df['고가'].astype(float)
            df['저가'] = df['저가'].astype(float)
            df['거래량'] = df['거래량'].astype(float)
    else:
        df = yf.download(symbol, start=start_date, end=end_date)
        if not df.empty:
            df['종가'] = df['Close']
            df['고가'] = df['High']
            df['저가'] = df['Low']
            df['거래량'] = df['Volume']
    return df

def fetch_trade(trade_id):
    return supabase.table("trade_history").select("*").eq("id", trade_id).single().execute().data

def fetch_user(user_id):
    return supabase.table("users").select("*").eq("id", user_id).single().execute().data

def fetch_peer_trades(symbol, market, trade_time, action, group_size=100):
    target_date = pd.to_datetime(trade_time)
    start = (target_date - pd.Timedelta(days=3)).strftime("%Y-%m-%d")
    end = (target_date + pd.Timedelta(days=3)).strftime("%Y-%m-%d")
    peers = supabase.table("trade_history").select("*") \
        .eq("symbol", symbol).eq("market", market).eq("action", action) \
        .gte("trade_time", start).lte("trade_time", end).limit(group_size).execute().data
    return peers

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

def make_trade_chart(df, trade_time, trade_price, action, stats, peer_avg=None, bench_price=None):
    plt.figure(figsize=(14,8))
    plt.plot(df.index, df['종가'], label="종가", color='black')
    plt.plot(df.index, df['EMA20'], '--', label="EMA20")
    plt.plot(df.index, df['EMA60'], ':', label="EMA60")
    plt.plot(df.index, df['VWAP'], label="VWAP", color='gray')
    plt.plot(df.index, df['BB_UPPER'], color='orange', alpha=0.3, label="BB Upper")
    plt.plot(df.index, df['BB_LOWER'], color='blue', alpha=0.3, label="BB Lower")
    plt.fill_between(df.index, df['BB_LOWER'], df['BB_UPPER'], color="lightblue", alpha=0.1)
    plt.axvline(pd.to_datetime(trade_time), color='red' if action=="sell" else 'green', linestyle='--', label="매수/매도")
    plt.scatter([pd.to_datetime(trade_time)], [trade_price], color='red' if action=="sell" else 'green', s=150, zorder=5)
    if peer_avg is not None:
        plt.hlines(peer_avg, df.index[0], df.index[-1], color='purple', alpha=0.5, label="Peer 평균매입가")
    if bench_price is not None:
        plt.hlines(bench_price, df.index[0], df.index[-1], color='orange', alpha=0.7, label="가상수익선")
    plt.title("실전 자동매매 타이밍/지표분석 차트")
    plt.legend()
    plt.grid(True)
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    plt.close()
    buf.seek(0)
    return buf

# 컨텍스트 생성 함수
def build_context(user, trade, feedback, stats, config, selected_tone):
    tone_guide = config["tone_guide"]
    investor_guide = config["investor_level_guide"]
    tone_msg = tone_guide[selected_tone]
    inv_msg = investor_guide[user['investor_level']]
    context = f"""
[사용자 정보]
- 투자자 등급: {user['investor_level']} ({inv_msg})
- 선택한 말투/스타일: {tone_msg}
- 최근 감정: {user.get('last_emotion', '')}
- 누적 수익률: {user.get('cumulative_return', 'N/A')}%

[분석 거래]
- 종목: {trade['symbol']} ({trade['market']})
- 가격: {trade['price']}
- 거래일: {trade['trade_time'][:10]}
- 액션: {trade['action']}
- 피드백: {feedback}

[주요 기술적 지표]
{json.dumps(stats, ensure_ascii=False, indent=2)}

[AI 코칭 목표]
{config['ai_coaching_goal']}

(반드시 위 투자자 등급/말투에 맞게, 정확하고, 친절하거나 논리적이거나, 유저가 이해하기 쉽게 답변할 것)
"""
    return context

# LLM 코칭 호출 함수
#def ai_commentary(context):
    # 실제 서비스에선 API KEY 환경변수로
    openai.api_key = os.environ.get("OPENAI_API_KEY")
    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": context}],
        temperature=0.7,
    )
    return response.choices[0].message.content


def ai_commentary(context):
    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))  #실제 사용 시 .environ.get("GOOGLE_API_KEY")
    model = genai.GenerativeModel("gemini-1.5-flash-latest")
    response = model.generate_content(context)

    return response.text

def analyze_and_feedback(trade, user, config, selected_tone="friendly", use_llm=False):
    symbol = trade['symbol']
    market = trade.get('market', 'KR')
    action = trade['action']
    price = trade['price']
    trade_time = trade['trade_time'][:10]
    commission = trade.get('commission', 0)
    if market == 'KR':
        trade_time_fmt = trade_time.replace('-', '')
        start_dt = (pd.to_datetime(trade_time) - pd.Timedelta(days=60)).strftime("%Y%m%d")
        end_dt = (pd.to_datetime(trade_time) + pd.Timedelta(days=14)).strftime("%Y%m%d")
    else:
        trade_time_fmt = trade_time
        start_dt = (pd.to_datetime(trade_time) - pd.Timedelta(days=60)).strftime("%Y-%m-%d")
        end_dt = (pd.to_datetime(trade_time) + pd.Timedelta(days=14)).strftime("%Y-%m-%d")
    df = get_stock_price(symbol, market, start_dt, end_dt)
    if df.empty:
        return "데이터 없음", None, {}, None, None, None
    if pd.to_datetime(trade_time_fmt) not in df.index:
        trade_idx = df.index.get_loc(df.index[df.index >= pd.to_datetime(trade_time_fmt)][0])
    else:
        trade_idx = df.index.get_loc(pd.to_datetime(trade_time_fmt))
    stats = compute_advanced_stats(df, price, trade_idx, action)
    peers = fetch_peer_trades(symbol, market, trade_time, action)
    peer_prices = [t['price'] for t in peers]
    peer_avg = np.mean(peer_prices) if peer_prices else None
    rank = 1 + sum(1 for p in peer_prices if (price < p if action=='buy' else price > p))
    total_peers = len(peer_prices)
    after = df.iloc[trade_idx:trade_idx+7]['종가']
    bench_return = float(np.round((after.max() - price) / price * 100, 2)) if action=='buy' else float(np.round((price - after.min()) / price * 100, 2))
    bench_price = after.max() if action=='buy' else after.min()

    # 자동 피드백 메시지(템플릿)
    feedback = ""
    if action == "buy":
        if stats["EMA20"] > stats["EMA60"] and stats["EMA60"] > stats["EMA120"]:
            feedback += "중장기 상승 추세. "
        if stats["RSI14"] < 30 and stats["STOCH_K"] < 30:
            feedback += "과매도 구간, 단기 반등 기대. "
        if stats["RSI14"] > 70:
            feedback += "과매수 구간, 단기 급락 주의. "
        if stats["MACD"] > stats["MACD_SIGNAL"]:
            feedback += "MACD 매수 신호. "
        if price < stats["VWAP"]:
            feedback += "기관 평균가 이하 매수, 추가 상승 기대. "
        if stats["max_profit"] >= 10:
            feedback += f"매수 후 1주일간 최대 {stats['max_profit']}% 급등 구간! "
        elif stats["max_profit"] < 0:
            feedback += "매수 후 하락, 변동성 주의! "
        if peer_avg is not None:
            feedback += f"Peer 평균 대비 {'더 저렴' if price < peer_avg else '더 비싸게'} 매수. "
        feedback += f"그룹 {total_peers}명 중 {rank}위. "
        feedback += f"최적 시나리오: {bench_return}% 수익 가능."
    else:
        if stats["RSI14"] > 70:
            feedback += "과매수 구간 매도, 차익실현 타이밍. "
        if stats["MACD"] < stats["MACD_SIGNAL"]:
            feedback += "MACD 매도 신호. "
        if price > stats["VWAP"]:
            feedback += "기관 평균가 위 매도, 이익 극대화. "
        if stats.get("missed_profit", 0) > 5:
            feedback += f"매도 후 {stats['missed_profit']}% 추가 상승. 더 기다렸으면 더 수익! "
        elif stats.get("missed_profit", 0) < 0:
            feedback += "매도 후 하락, 좋은 타이밍! "
        if peer_avg is not None:
            feedback += f"Peer 평균 대비 {'더 고점' if price > peer_avg else '더 저점'} 매도. "
        feedback += f"그룹 {total_peers}명 중 {rank}위. "
        feedback += f"최적 시나리오: {bench_return}% 이익 또는 손실 회피."
    if commission > 0:
        feedback += f"수수료 {commission}원 포함 실질 수익률."
    buf = make_trade_chart(df, trade_time, price, action, stats, peer_avg, bench_price)
    file_name = f"charts/{trade['id']}.png"
    try:
        supabase.storage.from_("charts").upload(file_name, buf, {"content-type": "image/png"})
        chart_url = f"https://{url.split('//')[1]}/storage/v1/object/public/charts/{trade['id']}.png"
    except Exception:
        chart_url = None

    summary_stats = {
        "EMA20": stats["EMA20"],
        "EMA60": stats["EMA60"],
        "EMA120": stats["EMA120"],
        "RSI14": stats["RSI14"],
        "MACD": stats["MACD"],
        "MACD_SIGNAL": stats["MACD_SIGNAL"],
        "STOCH_K": stats["STOCH_K"],
        "STOCH_D": stats["STOCH_D"],
        "max_profit": stats.get("max_profit"),
        "min_profit": stats.get("min_profit"),
        "missed_profit": stats.get("missed_profit"),
        "peer_avg": float(peer_avg) if peer_avg else None,
        "rank_in_group": int(rank),
        "group_size": total_peers,
        "bench_return": bench_return
    }
    if stats.get("max_profit", 0) > 10 and stats["RSI14"] < 30 and stats["EMA20"] > stats["EMA60"]:
        style_type = "단타+추세매매"
    elif stats.get("max_profit", 0) < 0 and stats["RSI14"] > 70:
        style_type = "고점매수/방어형"
    else:
        style_type = "중립/시장평균"

    # LLM 코칭 활성화 옵션
    ai_coaching = None
    if use_llm:
        context = build_context(user, trade, feedback, summary_stats, config, selected_tone)
        ai_coaching = ai_commentary(context)

    return feedback, chart_url, summary_stats, style_type, rank, bench_return, ai_coaching

def auto_trade_feedback(trade_id, user_id, selected_tone="friendly", use_llm=False):
    trade = fetch_trade(trade_id)
    user = fetch_user(user_id)
    feedback, chart_url, summary_stats, style_type, rank, bench_return, ai_coaching = analyze_and_feedback(
        trade, user, service_config, selected_tone, use_llm
    )
    supabase.table("trade_feedback").insert({
        "user_id": user_id,
        "trade_id": trade_id,
        "feedback_message": feedback,
        "chart_url": chart_url,
        "summary_stats": summary_stats,
        "style_type": style_type,
        "rank_in_group": rank,
        "benchmark_return": bench_return,
        "ai_coaching": ai_coaching,
        "selected_tone": selected_tone,
        "created_at": datetime.datetime.now().isoformat()
    }).execute()
    return feedback, chart_url, ai_coaching

# ----------- 호출 예시 -----------
# feedback, chart_url, ai_coaching = auto_trade_feedback(trade_id=101, user_id='abcd1234', selected_tone="expert", use_llm=True)
