# -*- coding: utf-8 -*-
import os
from pathlib import Path
import io
import json
import datetime as dt
from functools import lru_cache
from uuid import UUID

import numpy as np
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
import pandas_ta as ta
from dotenv import load_dotenv

# 외부 API
from supabase import create_client
from pykrx import stock
import yfinance as yf
import google.generativeai as genai

import traceback
import streamlit as st


# =========================
# 환경 준비
# =========================
load_dotenv()
st.set_page_config(page_title="Trade Feedback", page_icon="📈", layout="wide")

# Matplotlib 한글 폰트 (환경에 맞게 조정)
matplotlib.rcParams["axes.unicode_minus"] = False
try:
    if os.uname().sysname == "Darwin":
        matplotlib.rcParams["font.family"] = "AppleGothic"
    else:
        matplotlib.rcParams["font.family"] = matplotlib.rcParams.get("font.family", ["sans-serif"])
except Exception:
    pass


# =========================
# 설정값 로드 (config.json)
# =========================
BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = os.environ.get("CONFIG_PATH", str(BASE_DIR / "config.json"))
with open(CONFIG_PATH, encoding="utf-8") as f:
    service_config = json.load(f)

# 새 옵션(없어도 안전 동작)
FEEDBACK = service_config.get("feedback_policy", {})
ANALYSIS_MODE = FEEDBACK.get("analysis_mode", "backtest")  # 'backtest' | 'realtime'
PEER_GROUP_SIZE = int(FEEDBACK.get("peer_group_size", 100))
MIN_DATA_DAYS = int(FEEDBACK.get("min_data_period_days", 60))
ANALYSIS_WINDOW_DAYS = int(FEEDBACK.get("analysis_window_days", 7))


# =========================
# Supabase 초기화
# =========================
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")  # 또는 SERVICE_ROLE_KEY

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError(
        "Supabase URL/KEY가 설정되지 않았습니다. .env에 SUPABASE_URL, SUPABASE_KEY 설정하세요."
    )

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# =========================
# 유틸
# =========================
def is_uuid(s: str) -> bool:
    try:
        UUID(str(s))
        return True
    except Exception:
        return False


def _normalize_index(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    try:
        df.index = df.index.normalize()
    except Exception:
        pass
    return df


def _yf_download_retry(symbol, start, end, tries=2):
    last = None
    for _ in range(max(1, tries)):
        df = yf.download(symbol, start=start, end=end, progress=False)
        if df is not None and not df.empty:
            return df
        last = df
    return last if last is not None else pd.DataFrame()


@lru_cache(maxsize=128)
def get_stock_price_cached(symbol: str, market: str, start_date: str, end_date: str) -> pd.DataFrame:
    if market == "KR":
        # pykrx는 날짜 문자열 포맷: YYYYMMDD
        df = stock.get_market_ohlcv_by_date(start_date, end_date, symbol)
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.rename(columns={"종가": "Close", "고가": "High", "저가": "Low", "거래량": "Volume"})
    else:
        # 해외/미국
        df = _yf_download_retry(symbol, start=start_date, end=end_date, tries=2)
        if df is None or df.empty:
            return pd.DataFrame()

    df = _normalize_index(df)
    out = pd.DataFrame(index=df.index)
    out["종가"] = df["Close"].astype(float)
    out["고가"] = df["High"].astype(float)
    out["저가"] = df["Low"].astype(float)
    out["거래량"] = df["Volume"].astype(float)
    return out


def get_stock_price(symbol, market, start_date, end_date):
    # 캐시 래퍼 (pykrx/yf의 date 포맷을 문자열로 고정)
    return get_stock_price_cached(symbol, market, str(start_date), str(end_date)).copy()


# =========================
# DB 접근
# =========================
def fetch_trade(trade_id: str):
    res = supabase.table("trade_history").select("*").eq("id", str(trade_id)).single().execute()
    return res.data


def fetch_user(user_id: str):
    res = supabase.table("users").select("*").eq("id", str(user_id)).single().execute()
    return res.data


def get_trade_history(user_id: str) -> pd.DataFrame:
    res = (
        supabase
        .table("trade_history")
        .select("*")
        .eq("user_id", str(user_id))
        .order("trade_time", desc=True)
        .limit(100)
        .execute()
    )
    if getattr(res, "status_code", 0) >= 400:
        msg = getattr(res, "error_message", f"status={res.status_code}")
        st.error(f"조회 실패: {msg}")
        return pd.DataFrame()
    if not res.data:
        return pd.DataFrame()
    return pd.DataFrame(res.data)


def get_feedback_history(user_id: str) -> pd.DataFrame:
    res = (
        supabase
        .table("trade_feedback")
        .select("*")
        .eq("user_id", str(user_id))
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    )
    if getattr(res, "status_code", 0) >= 400:
        msg = getattr(res, "error_message", f"status={res.status_code}")
        st.error(f"피드백 조회 실패: {msg}")
        return pd.DataFrame()
    if not res.data:
        return pd.DataFrame()
    return pd.DataFrame(res.data)


def fetch_peer_trades(symbol, market, trade_time, action, group_size=None):
    if group_size is None:
        group_size = PEER_GROUP_SIZE
    target_date = pd.to_datetime(trade_time)
    start = (target_date - pd.Timedelta(days=3)).strftime("%Y-%m-%d")
    end = (target_date + pd.Timedelta(days=3)).strftime("%Y-%m-%d")
    res = (
        supabase.table("trade_history")
        .select("*")
        .eq("symbol", symbol)
        .eq("market", market)
        .eq("action", action)
        .gte("trade_time", start)
        .lte("trade_time", end)
        .limit(group_size)
        .execute()
    )
    return res.data or []


# =========================
# 피어 통계 (중앙값/퍼센타일)
# =========================
def robust_peer_stats(peers):
    prices = pd.Series([p.get("price") for p in peers if p.get("price") is not None], dtype="float64")
    prices = prices[np.isfinite(prices)]
    if prices.empty:
        return None
    desc = prices.describe(percentiles=[0.25, 0.5, 0.75])
    return {
        "count": int(desc["count"]),
        "p25": float(desc["25%"]),
        "p50": float(desc["50%"]),  # median
        "p75": float(desc["75%"]),
        "iqr": float(desc["75%"] - desc["25%"]),
    }


# =========================
# 리스크/사이징 코칭
# =========================
def position_sizing(equity, risk_pct, atr, tick_value=1.0):
    try:
        equity = float(equity)
        risk_pct = float(risk_pct)
        atr = float(atr)
    except Exception:
        return 0
    risk_capital = max(equity * risk_pct, 0.0)
    stop_width = max(atr, 1e-8)
    qty = int(risk_capital / (stop_width * tick_value))
    return max(qty, 0)


def risk_coaching(entry_price, atr_value, equity=10_000_000, risk_pct=0.01):
    # 기본: 1% 리스크, ATR 1.2배 손절, 2배 익절
    stop = entry_price - atr_value * 1.2
    tp1 = entry_price + atr_value * 2.0
    size = position_sizing(equity, risk_pct, atr_value)
    return {
        "stop": round(float(stop), 3),
        "tp1": round(float(tp1), 3),
        "size": int(size),
    }


# =========================
# 지표 계산(프로 확장)
# =========================
def _anchored_vwap(df: pd.DataFrame, anchor_idx: int) -> pd.Series:
    """anchor_idx(포함)부터의 AVWAP을 계산"""
    if df.empty or anchor_idx >= len(df.index):
        return pd.Series(index=df.index, dtype="float64")
    price = df["종가"].iloc[anchor_idx:]
    high = df["고가"].iloc[anchor_idx:]
    low = df["저가"].iloc[anchor_idx:]
    vol = df["거래량"].iloc[anchor_idx:]
    typical = (high + low + price) / 3.0
    pv = (typical * vol).cumsum()
    vv = vol.cumsum()
    av = pv / vv.replace(0, np.nan)
    out = pd.Series(index=df.index, dtype="float64")
    out.iloc[anchor_idx:] = av.values
    return out


def compute_advanced_stats(df: pd.DataFrame, trade_price: float, trade_idx: int, action: str, cfg) -> dict:
    # 기존 설정
    ema_fast, ema_mid, ema_slow = cfg["indicator_settings"]["EMA"]
    rsi_len = cfg["indicator_settings"]["RSI"][0]
    macd_cfg = cfg["indicator_settings"]["MACD"]
    bb_cfg = cfg["indicator_settings"]["BBANDS"]
    stoch_cfg = cfg["indicator_settings"]["STOCH"]

    # 기본 지표
    df["EMA_FAST"] = ta.ema(df["종가"], length=ema_fast)
    df["EMA_MID"] = ta.ema(df["종가"], length=ema_mid)
    df["EMA_SLOW"] = ta.ema(df["종가"], length=ema_slow)
    df["RSI"] = ta.rsi(df["종가"], length=rsi_len)

    macd = ta.macd(df["종가"], fast=macd_cfg["fast"], slow=macd_cfg["slow"], signal=macd_cfg["signal"])
    df["MACD"] = macd[f"MACD_{macd_cfg['fast']}_{macd_cfg['slow']}_{macd_cfg['signal']}"]
    df["MACD_SIGNAL"] = macd[f"MACDs_{macd_cfg['fast']}_{macd_cfg['slow']}_{macd_cfg['signal']}"]

    stoch = ta.stoch(
        df["고가"], df["저가"], df["종가"],
        k=stoch_cfg["k"], d=stoch_cfg["d"], smooth_k=stoch_cfg["smooth"]
    )
    df["STOCH_K"] = stoch[f"STOCHk_{stoch_cfg['k']}_{stoch_cfg['d']}_{stoch_cfg['smooth']}"]
    df["STOCH_D"] = stoch[f"STOCHd_{stoch_cfg['k']}_{stoch_cfg['d']}_{stoch_cfg['smooth']}"]

    bb = ta.bbands(df["종가"], length=bb_cfg["period"], std=bb_cfg["stddev"])
    df["BB_UPPER"] = bb[f"BBU_{bb_cfg['period']}_{float(bb_cfg['stddev'])}"]
    df["BB_LOWER"] = bb[f"BBL_{bb_cfg['period']}_{float(bb_cfg['stddev'])}"]

    df["VWAP"] = ta.vwap(df["고가"], df["저가"], df["종가"], df["거래량"]) if cfg["indicator_settings"]["VWAP"] else np.nan

    # --- 추가 지표 (프로 레벨) ---
    # 변동성/추세
    df["ATR"] = ta.atr(df["고가"], df["저가"], df["종가"], length=14)
    adx_df = ta.adx(df["고가"], df["저가"], df["종가"], length=14)
    df["ADX"] = adx_df["ADX_14"]

    # 수급/거래량
    df["OBV"] = ta.obv(df["종가"], df["거래량"])
    df["MFI"] = ta.mfi(df["고가"], df["저가"], df["종가"], df["거래량"], length=14)
    df["CMF"] = ta.cmf(df["고가"], df["저가"], df["종가"], df["거래량"], length=20)

    # 볼륨 스파이크: 20일 평균 대비 z-score
    vol_ma = df["거래량"].rolling(20).mean()
    vol_std = df["거래량"].rolling(20).std()
    df["VOL_Z"] = (df["거래량"] - vol_ma) / vol_std.replace(0, np.nan)

    # Anchored VWAP: 연초, 월초 기준
    try:
        year_mask = df.index.year == df.index[-1].year
        year_anchor = df.index.get_loc(df.index[year_mask][0])
        df["AVWAP_YTD"] = _anchored_vwap(df, year_anchor)
    except Exception:
        df["AVWAP_YTD"] = np.nan

    try:
        month_mask = df.index.month == df.index[-1].month
        month_anchor = df.index.get_loc(df.index[month_mask][0])
        df["AVWAP_MTD"] = _anchored_vwap(df, month_anchor)
    except Exception:
        df["AVWAP_MTD"] = np.nan

    # NaN 보정
    df.fillna(method="bfill", inplace=True)
    df.fillna(method="ffill", inplace=True)

    idx = int(trade_idx)
    stat = {
        "EMA_FAST": float(df["EMA_FAST"].iloc[idx]),
        "EMA_MID": float(df["EMA_MID"].iloc[idx]),
        "EMA_SLOW": float(df["EMA_SLOW"].iloc[idx]),
        "RSI": float(df["RSI"].iloc[idx]),
        "MACD": float(df["MACD"].iloc[idx]),
        "MACD_SIGNAL": float(df["MACD_SIGNAL"].iloc[idx]),
        "STOCH_K": float(df["STOCH_K"].iloc[idx]),
        "STOCH_D": float(df["STOCH_D"].iloc[idx]),
        "BB_UPPER": float(df["BB_UPPER"].iloc[idx]),
        "BB_LOWER": float(df["BB_LOWER"].iloc[idx]),
        "VWAP": float(df["VWAP"].iloc[idx]),
        # 추가 지표
        "ATR": float(df["ATR"].iloc[idx]),
        "ADX": float(df["ADX"].iloc[idx]),
        "OBV": float(df["OBV"].iloc[idx]),
        "MFI": float(df["MFI"].iloc[idx]),
        "CMF": float(df["CMF"].iloc[idx]),
        "VOL_Z": float(df["VOL_Z"].iloc[idx]) if np.isfinite(df["VOL_Z"].iloc[idx]) else 0.0,
        "AVWAP_YTD": float(df["AVWAP_YTD"].iloc[idx]) if np.isfinite(df["AVWAP_YTD"].iloc[idx]) else np.nan,
        "AVWAP_MTD": float(df["AVWAP_MTD"].iloc[idx]) if np.isfinite(df["AVWAP_MTD"].iloc[idx]) else np.nan,
    }

    # 미래누수 방지: realtime 모드일 때 D0 이후 수익률 측정 금지
    if ANALYSIS_MODE == "realtime":
        after = pd.Series(dtype="float64")
    else:
        after = df.iloc[idx: idx + ANALYSIS_WINDOW_DAYS]["종가"]

    if action == "buy":
        stat["max_profit"] = float(np.round((after.max() - trade_price) / trade_price * 100, 2)) if not after.empty else None
        stat["min_profit"] = float(np.round((after.min() - trade_price) / trade_price * 100, 2)) if not after.empty else None
    else:
        stat["missed_profit"] = float(np.round((after.max() - trade_price) / trade_price * 100, 2)) if not after.empty else None

    return stat


# =========================
# 차트 생성
# =========================
def make_trade_chart(df, trade_time, trade_price, action, stats, peer_median=None, bench_price=None):
    plt.figure(figsize=(14, 8))
    plt.plot(df.index, df["종가"], label="종가", color="black")
    plt.plot(df.index, df["EMA_FAST"], "--", label="EMA_FAST")
    plt.plot(df.index, df["EMA_MID"], ":", label="EMA_MID")
    plt.plot(df.index, df.get("VWAP", pd.Series(index=df.index)), label="VWAP", color="gray")
    plt.plot(df.index, df.get("BB_UPPER", pd.Series(index=df.index)), alpha=0.3, label="BB Upper")
    plt.plot(df.index, df.get("BB_LOWER", pd.Series(index=df.index)), alpha=0.3, label="BB Lower")
    plt.fill_between(df.index, df.get("BB_LOWER", 0), df.get("BB_UPPER", 0), alpha=0.08)

    # AVWAP 라인
    if "AVWAP_YTD" in df.columns:
        plt.plot(df.index, df["AVWAP_YTD"], alpha=0.6, label="AVWAP_YTD")
    if "AVWAP_MTD" in df.columns:
        plt.plot(df.index, df["AVWAP_MTD"], alpha=0.6, label="AVWAP_MTD")

    tt = pd.to_datetime(str(trade_time)).tz_localize(None)
    if tt in df.index:
        xpt = tt
    else:
        mask = df.index >= tt
        xpt = df.index[mask][0] if mask.any() else df.index[-1]

    plt.axvline(xpt, color=("red" if action == "sell" else "green"), linestyle="--", label="매수/매도")
    plt.scatter([xpt], [trade_price], color=("red" if action == "sell" else "green"), s=140, zorder=5)

    if peer_median is not None:
        plt.hlines(peer_median, df.index[0], df.index[-1], alpha=0.4, label="Peer 중앙값")
    if bench_price is not None:
        plt.hlines(bench_price, df.index[0], df.index[-1], alpha=0.5, label="가상수익선")

    plt.title("실전 자동매매 타이밍/지표 분석")
    plt.legend()
    plt.grid(True)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close()
    buf.seek(0)
    return buf


# =========================
# 컨텍스트 & LLM
# =========================
def build_context(user, trade, feedback, stats, config, selected_tone):
    tone_guide = config["tone_guide"]
    investor_guide = config["investor_level_guide"]
    tone_msg = tone_guide.get(selected_tone, tone_guide[config["user_customization"]["default_tone"]])
    inv_msg = investor_guide.get(user.get("investor_level", "beginner"), investor_guide["beginner"])

    context = f"""
[사용자 정보]
- 투자자 등급: {user.get('investor_level','beginner')} ({inv_msg})
- 선택한 말투/스타일: {tone_msg}
- 최근 감정: {user.get('last_emotion', '')}
- 누적 수익률: {user.get('cumulative_return', 'N/A')}%

[분석 거래]
- 종목: {trade['symbol']} ({trade.get('market','KR')})
- 가격: {trade['price']}
- 거래일: {str(trade['trade_time'])[:10]}
- 액션: {trade['action']}
- 피드백: {feedback}

[주요 기술적 지표 요약]
{json.dumps(stats, ensure_ascii=False, indent=2)}

[AI 코칭 목표]
{config['ai_coaching_goal']}

(반드시 위 투자자 등급/말투에 맞게, 정확하고, 친절하거나 논리적이거나, 유저가 이해하기 쉽게 답변할 것)
"""
    return context


def ai_commentary(context):
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY 환경변수가 없습니다. .env에 GOOGLE_API_KEY를 설정하세요.")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash-latest")
    response = model.generate_content(context)
    return response.text


# =========================
# 메인 분석
# =========================
def analyze_and_feedback(trade, user, config, selected_tone="friendly", use_llm=False):
    symbol = trade["symbol"]
    market = trade.get("market", "KR")
    action = trade["action"]
    price = float(trade["price"])
    trade_time = str(trade["trade_time"])[:10]
    commission = float(trade.get("commission", 0) or 0)

    # 날짜 범위
    if market == "KR":
        trade_time_fmt = trade_time.replace("-", "")
        start_dt = (pd.to_datetime(trade_time) - pd.Timedelta(days=MIN_DATA_DAYS)).strftime("%Y%m%d")
        # 리얼타임 모드는 D0 이후를 크게 보지 않음(미래누수 방지)
        forward_days = 1 if ANALYSIS_MODE == "realtime" else (ANALYSIS_WINDOW_DAYS + 7)
        end_dt = (pd.to_datetime(trade_time) + pd.Timedelta(days=forward_days)).strftime("%Y%m%d")
    else:
        trade_time_fmt = trade_time
        start_dt = (pd.to_datetime(trade_time) - pd.Timedelta(days=MIN_DATA_DAYS)).strftime("%Y-%m-%d")
        forward_days = 1 if ANALYSIS_MODE == "realtime" else (ANALYSIS_WINDOW_DAYS + 7)
        end_dt = (pd.to_datetime(trade_time) + pd.Timedelta(days=forward_days)).strftime("%Y-%m-%d")

    df = get_stock_price(symbol, market, start_dt, end_dt)
    if df.empty:
        return "데이터 없음", None, {}, None, None, None, None

    # 거래 인덱스 계산
    trade_dt = pd.to_datetime(trade_time_fmt)
    df.index = pd.to_datetime(df.index).tz_localize(None)
    mask = df.index >= trade_dt
    trade_idx = df.index.get_loc(df.index[mask][0]) if mask.any() else len(df.index) - 1

    # 최장 EMA 보장 (초반 지표 안정화)
    try:
        min_ready = max(config["indicator_settings"]["EMA"])
    except Exception:
        min_ready = 60
    if trade_idx < min_ready and len(df) > min_ready:
        trade_idx = min_ready

    stats = compute_advanced_stats(df, price, trade_idx, action, config)

    # 피어 비교(로버스트)
    peers = fetch_peer_trades(symbol, market, trade_time, action)
    rstats = robust_peer_stats(peers)
    if rstats:
        peer_median = rstats["p50"]
        # 랭크: 체결가가 피어 중 몇 퍼센타일인지(매수는 낮을수록 좋음 / 매도는 높을수록 좋음)
        if action == "buy":
            rank_percentile = 100.0 * (sum(1 for p in peers if p.get("price") is not None and price <= p["price"]) / rstats["count"])
        else:
            rank_percentile = 100.0 * (sum(1 for p in peers if p.get("price") is not None and price >= p["price"]) / rstats["count"])
        total_peers = rstats["count"]
    else:
        peer_median, rank_percentile, total_peers = None, None, 0

    # 벤치마크 시나리오 (리얼타임은 미계산)
    if ANALYSIS_MODE == "realtime":
        after = pd.Series(dtype="float64")
    else:
        after = df.iloc[trade_idx: trade_idx + ANALYSIS_WINDOW_DAYS]["종가"]

    if action == "buy":
        bench_return = float(np.round((after.max() - price) / price * 100, 2)) if not after.empty else None
        bench_price = float(after.max()) if not after.empty else None
    else:
        bench_return = float(np.round((price - after.min()) / price * 100, 2)) if not after.empty else None
        bench_price = float(after.min()) if not after.empty else None

    # 룰 기반 피드백(확장 지표 포함)
    feedback_parts = []
    ef, em, es = stats["EMA_FAST"], stats["EMA_MID"], stats["EMA_SLOW"]
    rsi = stats["RSI"]
    macd, macds = stats["MACD"], stats["MACD_SIGNAL"]
    vwap = stats["VWAP"]
    atr = stats["ATR"]
    adx = stats["ADX"]
    avwap_ytd = stats.get("AVWAP_YTD", np.nan)
    avwap_mtd = stats.get("AVWAP_MTD", np.nan)

    if action == "buy":
        if ef > em > es:
            feedback_parts.append("중장기 상승 추세.")
        if adx >= 20:
            feedback_parts.append(f"추세 강도(ADX={adx:.1f}) 양호.")
        if rsi < 30 and stats["STOCH_K"] < 30:
            feedback_parts.append("과매도 구간, 단기 반등 기대.")
        if rsi > 70:
            feedback_parts.append("과매수 구간, 급락 위험 주의.")
        if macd > macds:
            feedback_parts.append("MACD 매수 신호.")
        if np.isfinite(avwap_ytd) and price >= avwap_ytd:
            feedback_parts.append("연초 AVWAP 상방 유지.")
        if np.isfinite(vwap) and price < vwap:
            feedback_parts.append("기관 평균가(VWAP) 아래 매수, 추가 상승 기대.")
        if abs(stats["VOL_Z"]) >= 2:
            feedback_parts.append("비정상 거래량(스파이크) 관찰.")
        if stats.get("max_profit") is not None:
            if stats["max_profit"] >= 10:
                feedback_parts.append(f"매수 후 최대 {stats['max_profit']}% 급등 구간 관찰.")
            elif stats["max_profit"] < 0:
                feedback_parts.append("매수 후 하락, 변동성 주의.")
    else:
        if rsi > 70:
            feedback_parts.append("과매수 구간 매도, 차익실현 타이밍.")
        if adx >= 20 and macd < macds:
            feedback_parts.append("추세 둔화 + MACD 매도 신호.")
        if np.isfinite(vwap) and price > vwap:
            feedback_parts.append("VWAP 상단에서 매도, 이익 극대화.")
        mp = stats.get("missed_profit")
        if mp is not None:
            if mp > 5:
                feedback_parts.append(f"매도 후 {mp}% 추가 상승. 더 기다렸다면 수익 확대 가능.")
            elif mp < 0:
                feedback_parts.append("매도 후 하락, 좋은 타이밍.")

    # 피어 비교 문구
    if rstats:
        if action == "buy":
            rel = "더 저렴" if price <= rstats["p50"] else "더 비싸게"
            feedback_parts.append(f"Peer 중앙값({rstats['p50']:.2f}) 대비 {rel} 매수.")
        else:
            rel = "더 고점" if price >= rstats["p50"] else "더 저점"
            feedback_parts.append(f"Peer 중앙값({rstats['p50']:.2f}) 대비 {rel} 매도.")
        feedback_parts.append(f"피어 {total_peers}명 기준, 체결가 퍼센타일 ~{rank_percentile:.0f}%.")

    if bench_return is not None:
        if action == "buy":
            feedback_parts.append(f"최적 시나리오: {bench_return}% 수익 가능.")
        else:
            feedback_parts.append(f"최적 시나리오: {bench_return}% 이익 또는 손실 회피.")

    if commission > 0:
        feedback_parts.append(f"수수료 {int(commission)}원 반영 필요.")

    # 리스크 코칭(ATR 기반)
    rc = risk_coaching(price, atr)
    feedback_parts.append(f"제안 손절 {rc['stop']}, 1차 익절 {rc['tp1']}, 권장 수량 {rc['size']}.")

    feedback = " ".join(feedback_parts)

    # 차트 생성 & 업로드 (피어 중앙값 사용)
    buf = make_trade_chart(df, trade_time, price, action, stats,
                           peer_median=(rstats["p50"] if rstats else None),
                           bench_price=bench_price)
    file_name = f"charts/{trade['id']}.png"
    chart_url = None
    try:
        supabase.storage.from_("charts").upload(
            file_name, buf.getvalue(), {"content-type": "image/png", "upsert": "true"}
        )
        public_url = supabase.storage.from_("charts").get_public_url(file_name)
        chart_url = public_url or None
    except Exception:
        chart_url = None

    summary_stats = {
        # 핵심
        "EMA_FAST": stats["EMA_FAST"],
        "EMA_MID": stats["EMA_MID"],
        "EMA_SLOW": stats["EMA_SLOW"],
        "RSI": stats["RSI"],
        "MACD": stats["MACD"],
        "MACD_SIGNAL": stats["MACD_SIGNAL"],
        "STOCH_K": stats["STOCH_K"],
        "STOCH_D": stats["STOCH_D"],
        "VWAP": stats["VWAP"],
        # 확장
        "ATR": stats["ATR"],
        "ADX": stats["ADX"],
        "OBV": stats["OBV"],
        "MFI": stats["MFI"],
        "CMF": stats["CMF"],
        "VOL_Z": stats["VOL_Z"],
        "AVWAP_YTD": stats.get("AVWAP_YTD"),
        "AVWAP_MTD": stats.get("AVWAP_MTD"),
        # 결과/피어
        "max_profit": stats.get("max_profit"),
        "min_profit": stats.get("min_profit"),
        "missed_profit": stats.get("missed_profit"),
        "peer_p50": (rstats["p50"] if rstats else None),
        "peer_count": total_peers,
        "rank_percentile": rank_percentile,
        "bench_return": bench_return,
        # 리스크
        "risk": rc,
        "analysis_mode": ANALYSIS_MODE,
    }

    # 스타일 분류(예시)
    if stats.get("max_profit") is not None and stats.get("max_profit", 0) > 10 and rsi < 30 and ef > em:
        style_type = "단타+추세매매"
    elif stats.get("max_profit") is not None and stats.get("max_profit", 0) < 0 and rsi > 70:
        style_type = "고점매수/방어형"
    else:
        style_type = "중립/시장평균"

    ai_coaching = None
    if use_llm:
        try:
            context = build_context(user, trade, feedback, summary_stats, config, selected_tone)
            ai_coaching = ai_commentary(context)
        except Exception:
            ai_coaching = None

    # 퍼센타일 랭크를 rank 대용으로 반환(정수 랭킹보다 직관적)
    rank_repr = None if rank_percentile is None else f"~{int(round(rank_percentile))}퍼센타일"

    return feedback, chart_url, summary_stats, style_type, rank_repr, bench_return, ai_coaching


# =========================
# 엔드포인트성 래퍼 (직접 호출용)
# =========================
def auto_trade_feedback(trade_id, user_id, selected_tone="friendly", use_llm=False):
    trade = fetch_trade(trade_id)
    if not trade:
        raise ValueError(f"trade_history에서 id={trade_id} 레코드를 찾을 수 없습니다.")
    user = fetch_user(user_id)
    if not user:
        raise ValueError(f"users에서 id={user_id} 레코드를 찾을 수 없습니다.")

    feedback, chart_url, summary_stats, style_type, rank_repr, bench_return, ai_coaching = analyze_and_feedback(
        trade, user, service_config, selected_tone, use_llm
    )

    try:
        supabase.table("trade_feedback").insert({
            "user_id": user_id,
            "trade_id": trade_id,
            "feedback_message": feedback,
            "chart_url": chart_url,
            "summary_stats": summary_stats,
            "style_type": style_type,
            "rank_in_group": rank_repr,
            "benchmark_return": bench_return,
            "ai_coaching": ai_coaching,
            "selected_tone": selected_tone,
            "created_at": dt.datetime.now().isoformat()
        }).execute()
    except Exception:
        pass

    return feedback, chart_url, ai_coaching


# ---------------------------
# 기본 페이지 UI
# ---------------------------

# --- 세션 user_id 고정 (임시) ---
if "user_id" not in st.session_state:
    st.session_state.user_id = "0bfc599a-db77-49ef-8556-31d2be8ffdaf"
USER_ID = st.session_state.user_id

st.title("📈 자동 트레이드 피드백 대시보드")
st.caption("pykrx / yfinance / pandas-ta / Supabase / Gemini 기반 분석")

with st.sidebar:
    st.header("환경 상태")
    ok_url = bool(os.environ.get("SUPABASE_URL"))
    ok_key = bool(os.environ.get("SUPABASE_KEY"))
    ok_gem = bool(os.environ.get("GOOGLE_API_KEY"))

    st.write(f"Supabase URL: {'✅' if ok_url else '❌'}")
    st.write(f"Supabase KEY: {'✅' if ok_key else '❌'}")
    st.write(f"Gemini API: {'✅' if ok_gem else '⚠️(LLM 옵션 off 권장)'}")

    st.divider()
    st.subheader("분석 옵션")
    mode = st.radio("분석 모드", options=["backtest", "realtime"], index=0, horizontal=True)
    ANALYSIS_MODE = mode

    tones = list(service_config.get("tone_guide", {}).keys()) or ["friendly", "expert", "youth", "serious"]
    selected_tone = st.selectbox("톤(말투)", options=tones, index=0)

    use_llm = st.toggle("LLM 코칭 사용 (Gemini)", value=False, help="GOOGLE_API_KEY 필요")

    st.divider()
    st.subheader("입력 (DB 기반)")
    st.caption(f"현재 사용자: {USER_ID}")

    trades_df = get_trade_history(USER_ID)

    if trades_df.empty:
        st.warning("이 사용자의 거래내역이 없습니다. trade_history 테이블을 확인하세요.")
        selected_trade_id = ""
        options = []
    else:
        trades_df = trades_df.sort_values("trade_time", ascending=False).reset_index(drop=True)

        def _fmt_row(r):
            t = str(r.get("trade_time", ""))[:19]
            sym = r.get("symbol", "")
            act = r.get("action", "")
            px  = r.get("price", "")
            mid = r.get("market", "")
            tid = r.get("id", "")
            return f"[{t}] {sym} ({mid}) {act}@{px}  — id={tid}"

        options = [ _fmt_row(row) for _, row in trades_df.iterrows() ]
        ids     = trades_df["id"].astype(str).tolist()
        default_index = 0
        selected_label = st.selectbox("최근 거래에서 선택", options=options, index=default_index if options else 0)
        selected_trade_id = ids[options.index(selected_label)] if options else ""

    manual_trade_id = st.text_input("직접 trade_id(UUID) 입력 (선택)", value="", placeholder="입력 시 위 선택보다 우선합니다")
    final_trade_id = (manual_trade_id or selected_trade_id).strip()

    run_btn = st.button("분석 실행", type="primary")


# ---------------------------
# 메인 영역
# ---------------------------
tab_main, tab_stats, tab_raw = st.tabs(["요약", "지표/리스크 상세", "원본 레코드"])

if run_btn:
    try:
        if not final_trade_id or not is_uuid(final_trade_id):
            st.error("유효한 trade_id(UUID)를 선택하거나 입력하세요.")
            st.stop()

        with st.spinner("데이터 로딩 및 분석 중..."):
            trade = fetch_trade(final_trade_id)
            user = fetch_user(USER_ID)

            if not trade:
                st.error(f"trade_history에서 id={final_trade_id} 레코드를 찾지 못했습니다.")
                st.stop()
            if not user:
                st.error(f"users에서 id={USER_ID} 레코드를 찾지 못했습니다.")
                st.stop()

            feedback, chart_url, summary_stats, style_type, rank_repr, bench_return, ai_coaching = analyze_and_feedback(
                trade=trade,
                user=user,
                config=service_config,
                selected_tone=selected_tone,
                use_llm=use_llm,
            )

        with tab_main:
            left, right = st.columns([2, 1], gap="large")

            with left:
                st.subheader("피드백")
                st.success(feedback or "피드백이 비어 있습니다.")
                if chart_url:
                    st.image(chart_url, caption="거래 타이밍/지표 차트", use_column_width=True)
                else:
                    st.info("차트 URL을 가져오지 못했습니다. (스토리지 업로드 실패 또는 권한 문제)")

            with right:
                st.subheader("핵심 메타")
                st.metric("분석 모드", ANALYSIS_MODE.upper())
                st.metric("매매 성향(추정)", style_type or "-")
                st.metric("피어 퍼센타일", rank_repr or "-")
                st.metric("벤치마크 수익률", f"{bench_return:.2f}%" if bench_return is not None else "-")

                if use_llm:
                    st.divider()
                    st.subheader("AI 코칭(Gemini)")
                    if ai_coaching:
                        st.write(ai_coaching)
                    else:
                        st.info("AI 코칭 응답이 비어 있거나 호출 실패.")

        with tab_stats:
            st.subheader("요약 지표")
            if summary_stats:
                order_keys = [
                    "EMA_FAST","EMA_MID","EMA_SLOW","RSI","MACD","MACD_SIGNAL","STOCH_K","STOCH_D","VWAP",
                    "ATR","ADX","OBV","MFI","CMF","VOL_Z","AVWAP_YTD","AVWAP_MTD",
                    "max_profit","min_profit","missed_profit","peer_p50","peer_count",
                    "rank_percentile","bench_return","risk","analysis_mode"
                ]
                pretty = {k: summary_stats.get(k) for k in order_keys if k in summary_stats}
                df_show = pd.DataFrame([pretty]).T.reset_index()
                df_show.columns = ["항목", "값"]
                st.dataframe(df_show, use_container_width=True, height=520)
            else:
                st.info("요약 지표가 없습니다.")

        with tab_raw:
            st.subheader("원본 Trade 레코드")
            st.json(trade)
            st.subheader("원본 User 레코드")
            st.json(user)

        with st.expander("결과를 trade_feedback 테이블에 저장하기"):
            do_save = st.checkbox("DB에 저장", value=False)
            if do_save:
                try:
                    supabase.table("trade_feedback").insert({
                        "user_id": USER_ID,
                        "trade_id": final_trade_id,
                        "feedback_message": feedback,
                        "chart_url": chart_url,
                        "summary_stats": summary_stats,
                        "style_type": style_type,
                        "rank_in_group": rank_repr,
                        "benchmark_return": bench_return,
                        "ai_coaching": ai_coaching,
                        "selected_tone": selected_tone,
                    }).execute()
                    st.success("저장 완료")
                except Exception as e:
                    st.error(f"저장 실패: {e}")

    except Exception as e:
        st.error("분석 중 오류가 발생했습니다.")
        st.code("".join(traceback.format_exc()))
else:
    # 초기 화면: 최근 거래/피드백 요약 테이블
    st.info("좌측에서 최근 거래를 선택하거나 trade_id(UUID)를 입력 후 [분석 실행]을 누르세요.")
    try:
        trades_df_preview = get_trade_history(USER_ID).head(10)
        if not trades_df_preview.empty:
            st.subheader("최근 거래 (상위 10건)")
            st.dataframe(
                trades_df_preview[["id","trade_time","symbol","market","action","price","commission"]],
                use_container_width=True,
                height=320
            )
        feedback_df_preview = get_feedback_history(USER_ID).head(5)
        if not feedback_df_preview.empty:
            st.subheader("최근 피드백 (상위 5건)")
            st.dataframe(
                feedback_df_preview[["trade_id","created_at","style_type","rank_in_group","benchmark_return"]],
                use_container_width=True,
                height=260
            )
    except Exception as e:
        st.warning(f"요약 테이블 표시 중 경고: {e}")

