# -*- coding: utf-8 -*-
"""
🚀 Auto Trade Feedback — production-grade indicators & feedback (HARDENED++ FINAL)
- Leakage-safe snapshot (no bfill leak), strict rolling(min_periods), ddof=0
- Required lookback auto sizing (config-aware)
- MACD hist, Keltner, SQUEEZE, OBV Z, (D)VWAP, AVWAP (YTD/MTD grouped reset)
- Peer percentile (ordered + user-weighted) + sample guard + self-exclude
- Cost model: slippage + fees + taxes + min_fee (configurable/fallback)
- Tick-aware risk sizing (KR/US tick rules; KR precise-table override via config)
- Cash/risk caps; guard for tiny ATR
- Robust logging, masked PII, JSON-safe stats
- Session-aware date snap (optional pandas-market-calendars via config, business-day peer window)
- Resilient LLM (retry/timeout) w/ safety disclaimer; model from config
- Supabase storage upload upsert compatibility; feedback upsert-safe
"""

from __future__ import annotations

import os
from pathlib import Path
import io
import json
import datetime as dt
from functools import lru_cache
import logging
import math
import time
from typing import Dict, Any, Tuple, Optional, List

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")  # headless-safe
import matplotlib.pyplot as plt

import pandas_ta as ta
from dotenv import load_dotenv

from supabase import create_client
from pykrx import stock
import yfinance as yf
import google.generativeai as genai

try:
    import pandas_market_calendars as mcal  # optional
except Exception:
    mcal = None

try:
    from zoneinfo import ZoneInfo  # py>=3.9
except Exception:
    ZoneInfo = None


# =========================
# 로깅 & 환경
# =========================
load_dotenv()

logger = logging.getLogger("auto_trade_feedback")
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s"))
logger.addHandler(handler)
logger.setLevel(logging.INFO)

matplotlib.rcParams["axes.unicode_minus"] = False
try:
    if os.uname().sysname == "Darwin":
        matplotlib.rcParams["font.family"] = "AppleGothic"
    else:
        matplotlib.rcParams["font.family"] = matplotlib.rcParams.get("font.family", ["sans-serif"])
except Exception:
    pass

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = os.environ.get("CONFIG_PATH", str(BASE_DIR / "config.json"))
with open(CONFIG_PATH, encoding="utf-8") as f:
    service_config: Dict[str, Any] = json.load(f)

# ---- Config bindings ----
VERSION = service_config.get("version", "unknown")

FEEDBACK = service_config.get("feedback_policy", {})
ANALYSIS_MODE: str = FEEDBACK.get("analysis_mode", "backtest")
PEER_GROUP_SIZE: int = int(FEEDBACK.get("peer_group_size", 100))
MIN_DATA_DAYS: int = int(FEEDBACK.get("min_data_period_days", 60))
ANALYSIS_WINDOW_DAYS: int = int(FEEDBACK.get("analysis_window_days", 7))
PEER_MIN_SAMPLES: int = int(FEEDBACK.get("peer_min_samples", 50))
PEER_WINDOW_DAYS: int = int(FEEDBACK.get("peer_window_days", 3))  # ±N days (business days if calendar enabled)

EXEC_CFG = service_config.get("execution", {})
SLIPPAGE_BPS: float = float(EXEC_CFG.get("slippage_bps", 5))                 # 5 bps
ACCOUNT_RISK: float = float(EXEC_CFG.get("account_risk_per_trade", 0.01))    # 1%
ACCOUNT_SIZE: float = float(EXEC_CFG.get("account_size", 10_000_000))        # 1천만원
STOP_ATR_MULT: float = float(EXEC_CFG.get("stop_atr_mult", 1.2))
TP1_ATR_MULT: float = float(EXEC_CFG.get("tp1_atr_mult", 2.0))

# Cost model (per notional side; min_fee per order supported)
COST_MODEL = EXEC_CFG.get("cost_model", {
    "KR": {"fee_buy": 0.00015, "fee_sell": 0.00015, "tax_sell": 0.002, "min_fee": 0.0},
    "US": {"fee_buy": 0.0005,  "fee_sell": 0.0005,  "tax_sell": 0.0,   "min_fee": 0.0}
})

# Optional precise KR tick table (override default)
KR_TICK_TABLE = EXEC_CFG.get("kr_tick_table")  # e.g., [[0,1000,1],[1000,5000,5],...]

CALC = service_config.get("calc", {})
WINSOR_SIGMA: float = float(CALC.get("winsorize_sigma", 4.0))
OBV_Z_WINDOW: int = int(CALC.get("obv_z_window", 20))
VOL_Z_WINDOW: int = int(CALC.get("vol_z_window", 20))
MIN_CONSEC_BARS: int = int(CALC.get("min_consecutive_bars", 200))

CAL_CFG = service_config.get("calendar", {})
USE_MCAL: bool = bool(CAL_CFG.get("use_market_calendars", True))
EXCHANGE_CODES: Dict[str, str] = CAL_CFG.get("exchange_codes", {"KR": "XKRX", "US": "XNYS"})

LLM_CFG = service_config.get("llm", {})
LLM_ENABLED_DEFAULT: bool = bool(LLM_CFG.get("enabled_default", False))
LLM_MODEL_NAME: str = LLM_CFG.get("model", "gemini-1.5-flash-latest")

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Supabase URL/KEY가 설정되지 않았습니다.")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
STORAGE_BUCKET_NAME = os.environ.get("CHARTS_BUCKET", "charts")

np.seterr(all="ignore")  # 지표 계산시 경고 억제(분모 0 등)


# =========================
# 시장/타임존 유틸
# =========================
def market_tz(market: str) -> str:
    m = (market or "").upper()
    if m == "KR":
        return "Asia/Seoul"
    return "America/New_York"


def _calendar_code(market: str) -> Optional[str]:
    if (mcal is None) or (not USE_MCAL):
        return None
    m = (market or "").upper()
    return EXCHANGE_CODES.get(m, None)


def snap_to_session_close(ts_local: pd.Timestamp, market: str) -> Optional[pd.Timestamp]:
    """
    ts_local(시장 현지시간)을 포함하는 정규장 세션 종가 시각을 '시장 현지 naive'로 반환.
    캘린더가 없거나 매칭 실패시 None.
    """
    code = _calendar_code(market)
    if not code:
        return None
    try:
        cal = mcal.get_calendar(code)
        # 넉넉히 조회
        sched = cal.schedule(
            start_date=ts_local.date() - pd.Timedelta(days=30),
            end_date=ts_local.date() + pd.Timedelta(days=30)
        )
        in_sess = (sched["market_open"] <= ts_local.tz_convert(sched["market_open"].dt.tz)) & \
                  (ts_local.tz_convert(sched["market_close"].dt.tz) <= sched["market_close"])
        if in_sess.any():
            # market_close는 tz-aware (보통 UTC). 시장 타임존으로 변환 후 naive로 반환.
            tz = ZoneInfo(market_tz(market)) if ZoneInfo else None
            close = sched.loc[in_sess, "market_close"].iloc[0]
            close_local = close.tz_convert(tz) if (tz and close.tzinfo) else close
            return close_local.tz_localize(None) if close_local.tzinfo else close_local
        return None
    except Exception as e:
        logger.debug(f"snap_to_session_close failed: {e}")
        return None


def parse_trade_date_for_market(trade_time_iso: str, market: str) -> pd.Timestamp:
    """
    trade_time(ISO)을 해당 시장 타임존으로 해석 → 일봉 스냅용 '시장 현지 naive 날짜/시각' 반환
    - 캘린더가 있으면 세션 종가로 스냅, 없으면 현지 자정 normalize
    - 반환은 tz-naive(시장 현지 기준)
    """
    tz = ZoneInfo(market_tz(market)) if ZoneInfo else None
    ts = pd.to_datetime(trade_time_iso)
    ts_local = ts.tz_convert(tz) if (tz and ts.tzinfo) else (ts.tz_localize(tz) if tz else ts)
    close_ts = snap_to_session_close(ts_local, market)
    if close_ts is not None:
        return close_ts  # already local-naive
    return ts_local.normalize().tz_localize(None) if ts_local.tzinfo else pd.to_datetime(str(ts_local.date()))


def business_window_utc(trade_time_iso: str, market: str, n_days: int) -> Optional[Tuple[str, str]]:
    """
    ± n 영업일 경계(세션 open/close) → UTC ISO 문자열 반환.
    캘린더 미사용 시 None.
    """
    code = _calendar_code(market)
    if not code:
        return None
    try:
        tz = ZoneInfo(market_tz(market)) if ZoneInfo else None
        cal = mcal.get_calendar(code)
        ts = pd.to_datetime(trade_time_iso)
        ts_local = ts.tz_convert(tz) if (tz and ts.tzinfo) else (ts.tz_localize(tz) if tz else ts)

        sched = cal.schedule(
            start_date=ts_local.date() - pd.Timedelta(days=60),
            end_date=ts_local.date() + pd.Timedelta(days=60)
        ).sort_index()

        # 세션 인덱스 찾기: 포함/이후 첫 세션
        mask = (sched["market_open"] <= ts_local.tz_convert(sched["market_open"].dt.tz)) & \
               (ts_local.tz_convert(sched["market_close"].dt.tz) <= sched["market_close"])
        if mask.any():
            idx = sched.index.get_loc(sched.index[mask][0])
        else:
            idx = sched.index.get_indexer([ts_local.date()], method="backfill")[0]
            if idx < 0:
                idx = 0

        lo = max(0, idx - n_days)
        hi = min(len(sched) - 1, idx + n_days)
        start_utc = sched["market_open"].iloc[lo].tz_convert("UTC").isoformat()
        end_utc   = sched["market_close"].iloc[hi].tz_convert("UTC").isoformat()
        return start_utc, end_utc
    except Exception as e:
        logger.debug(f"business_window_utc failed: {e}")
        return None


def snap_to_index_or_next(idx: pd.DatetimeIndex, t: pd.Timestamp) -> pd.Timestamp:
    """인덱스에 정확히 없으면 그 이후 첫 거래일로 스냅 (없으면 마지막 날짜)"""
    if t in idx:
        return t
    mask = idx >= t
    return idx[mask][0] if mask.any() else idx[-1]


# =========================
# 시계열 로딩 유틸
# =========================
def _normalize_index(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    try:
        df.index = df.index.normalize()
    except Exception:
        pass
    return df


def _yf_retry(symbol: str, start: str, end: str, tries: int = 2, sleep: float = 0.6) -> pd.DataFrame:
    last = None
    for _ in range(max(1, tries)):
        try:
            df = yf.download(symbol, start=start, end=end, progress=False, auto_adjust=False)
        except Exception:
            df = None
        if df is not None and not df.empty:
            return df
        last = df
        time.sleep(sleep)
    return last if last is not None else pd.DataFrame()


def _kr_retry(symbol: str, start: str, end: str, tries: int = 3, sleep: float = 0.6) -> pd.DataFrame:
    for _ in range(max(1, tries)):
        try:
            df = stock.get_market_ohlcv_by_date(start, end, symbol)
        except Exception:
            df = None
        if df is not None and not df.empty:
            return df
        time.sleep(sleep)
    return pd.DataFrame()


@lru_cache(maxsize=128)
def get_stock_price_cached(symbol: str, market: str, start_date: str, end_date: str) -> pd.DataFrame:
    if (market or "").upper() == "KR":
        df = _kr_retry(symbol, start_date, end_date, tries=3)
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.rename(columns={"종가": "Close", "고가": "High", "저가": "Low", "거래량": "Volume"})
    else:
        df = _yf_retry(symbol, start=start_date, end=end_date, tries=2)
        if df is None or df.empty:
            return pd.DataFrame()

    df = _normalize_index(df)
    out = pd.DataFrame(index=df.index)
    out["종가"] = df["Close"].astype(float)
    out["고가"] = df["High"].astype(float)
    out["저가"] = df["Low"].astype(float)
    out["거래량"] = df["Volume"].astype(float)
    return out


def get_stock_price(symbol: str, market: str, start: str, end: str) -> pd.DataFrame:
    return get_stock_price_cached(symbol, market, str(start), str(end)).copy()


# =========================
# DB 접근
# =========================
def fetch_trade(trade_id: int) -> Optional[Dict[str, Any]]:
    try:
        res = (
            supabase.table("trade_history")
            .select("*")
            .eq("id", trade_id)
            .single()
            .execute()
        )
        return res.data
    except Exception as e:
        logger.error(f"fetch_trade failed: {e}")
        return None


def fetch_and_normalize_user(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Supabase profiles → 분석코드에서 기대하는 key로 정규화
    """
    try:
        raw = (
            supabase.table("profiles")
            .select("*")
            .eq("id", user_id)
            .single()
            .execute()
            .data
        )
    except Exception as e:
        logger.error(f"fetch_user failed: {e}")
        raw = None

    if not raw:
        return None

    user = dict(raw)
    if "investment_level" in user:
        user["investor_level"] = user.get("investment_level")
    if "emotions" in user and isinstance(user.get("emotions"), list) and user["emotions"]:
        user["last_emotion"] = user["emotions"][-1]
    else:
        user["last_emotion"] = None
    user.setdefault("preferred_tone", "friendly")
    user.setdefault("risk_profile", "normal")
    return user


# =========================
# 피어 데이터
# =========================
def fetch_peer_trades(
    symbol: str,
    market: str,
    trade_time_iso: str,
    action: str,
    group_size: Optional[int] = None,
    user_id_exclude: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    동일 종목/시장/행동의 ±N(영업)일 피어 체결(정렬/자기제외). 결과는 원시 리스트 반환.
    """
    if group_size is None:
        group_size = PEER_GROUP_SIZE

    start_iso, end_iso = None, None
    win = business_window_utc(trade_time_iso, market, PEER_WINDOW_DAYS)
    if win:
        start_iso, end_iso = win
    else:
        # 캘린더 미사용 시 달력일로 fallback
        t = pd.to_datetime(trade_time_iso)
        start_iso = (t - pd.Timedelta(days=PEER_WINDOW_DAYS)).strftime("%Y-%m-%d")
        end_iso   = (t + pd.Timedelta(days=PEER_WINDOW_DAYS)).strftime("%Y-%m-%d")

    try:
        q = (
            supabase.table("trade_history")
            .select("user_id, price, qty, trade_time")
            .eq("symbol", symbol)
            .eq("market", market)
            .eq("action", action)
            .gte("trade_time", start_iso)
            .lte("trade_time", end_iso)
            .order("trade_time", desc=False)
            .limit(group_size)
        )
        if user_id_exclude:
            q = q.neq("user_id", user_id_exclude)
        res = q.execute()
        return res.data or []
    except Exception as e:
        logger.error(f"fetch_peer_trades failed: {e}")
        return []


# =========================
# 공통 유틸
# =========================
def _sanitize_for_json(obj: Any) -> Any:
    """dict/list/float 안의 NaN, Inf를 전부 None으로 바꿔 JSONB에 안전하게 넣기"""
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_json(v) for v in obj]
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, np.floating):
        x = float(obj)
        if math.isnan(x) or math.isinf(x):
            return None
        return x
    return obj


def _mask_user(u: Dict[str, Any]) -> Dict[str, Any]:
    if not u:
        return u
    v = dict(u)
    if "email" in v and isinstance(v["email"], str):
        parts = v["email"].split("@")
        v["email"] = (parts[0][:2] + "***@" + parts[1]) if len(parts) == 2 else "***"
    keys = ["id", "investor_level", "preferred_tone", "risk_profile", "last_emotion"]
    return {k: v.get(k) for k in keys}


def required_lookback_days(cfg: Dict[str, Any]) -> int:
    ind = cfg.get("indicator_settings", {})
    ema = ind.get("EMA", [20, 50, 200])
    rsi = ind.get("RSI", [14])
    macd = ind.get("MACD", {"slow": 26})
    bb   = ind.get("BBANDS", {"period": 20})
    base = max(
        int(ema[-1]) if ema else 200,
        int(rsi[0]) if rsi else 14,
        int(macd.get("slow", 26)),
        int(bb.get("period", 20)),
        14  # ATR/ADX/MFI 기본
    )
    return max(MIN_DATA_DAYS, base * 4)


def user_weighted_peer_prices(peers: List[Dict[str, Any]]) -> pd.Series:
    """동일 사용자 다중 체결 → 수량가중 평균으로 축약"""
    from collections import defaultdict
    acc = defaultdict(lambda: {"pv": 0.0, "v": 0.0})
    for p in peers:
        price = p.get("price"); qty = p.get("qty"); uid = p.get("user_id")
        if price is None or qty in (None, 0) or uid is None:
            continue
        acc[uid]["pv"] += float(price) * float(qty)
        acc[uid]["v"]  += float(qty)
    out = []
    for _, a in acc.items():
        if a["v"] > 0:
            out.append(a["pv"]/a["v"])
    return pd.Series(out, dtype="float64")


def percent_rank_by_action(
    action: str,
    peer_prices: pd.Series,
    my_price: float,
    min_samples: int = 50
) -> Tuple[Optional[float], Optional[float], int]:
    peer = pd.Series([p for p in peer_prices if pd.notna(p)], dtype="float64")
    if peer.empty or len(peer) < min_samples:
        return None, None, int(len(peer))
    if action == "buy":
        rank_percentile = 100.0 * float(np.mean(peer <= my_price))
    else:
        rank_percentile = 100.0 * float(np.mean(peer >= my_price))
    return float(peer.median()), rank_percentile, int(len(peer))


# =========================
# 호가단위 & 비용 모델
# =========================
def tick_size_kr(price: float) -> float:
    """KR 호가단위. config.kr_tick_table 제공시 그것을 사용."""
    if KR_TICK_TABLE and isinstance(KR_TICK_TABLE, list):
        for lo, hi, step in KR_TICK_TABLE:
            if lo <= price < hi:
                return float(step)
        return float(KR_TICK_TABLE[-1][-1])
    # 기본 근사 (코스피/코스닥 공통 근사)
    if price < 1000: return 1
    if price < 5000: return 5
    if price < 10000: return 10
    if price < 50000: return 50
    if price < 100000: return 100
    return 500


def tick_size_us(_: float) -> float:
    return 0.01


def round_to_tick(px: float, market: str) -> float:
    if not np.isfinite(px):
        return px
    if (market or "").upper() == "KR":
        t = tick_size_kr(px)
    else:
        t = tick_size_us(px)
    return round(px / t) * t


def effective_unit_price(px: float, action: str, market: str, slippage_bps: float, per_share_fee: float = 0.0) -> float:
    """
    슬리피지 + 수수료 + 세금 반영한 '체결 단가' 근사
    - per_share_fee: 주문 단위 수수료를 주가 단가로 환산한 값(= commission / qty)
    """
    model = COST_MODEL.get((market or "US").upper(), COST_MODEL["US"])
    fee_buy  = float(model.get("fee_buy", 0.0))
    fee_sell = float(model.get("fee_sell", 0.0))
    tax_sell = float(model.get("tax_sell", 0.0))
    slip = px * (slippage_bps / 1e4)
    eff = px + (slip if action == "buy" else -slip)
    if action == "buy":
        eff *= (1 + fee_buy)
    else:
        eff *= (1 + fee_sell + tax_sell)
    return eff + per_share_fee


def per_order_min_fee(notional: float, market: str, side: str) -> float:
    """주문 금액 기준 최소 수수료 반영(근사)."""
    m = COST_MODEL.get((market or "US").upper(), COST_MODEL["US"])
    rate = float(m.get("fee_buy" if side == "buy" else "fee_sell", 0.0))
    min_fee = float(m.get("min_fee", 0.0))
    return max(notional * rate, min_fee)


# =========================
# 지표 계산(스냅샷 전용)
# =========================
def compute_advanced_stats(
    df_hist: pd.DataFrame,   # 과거~사건시점만 slice된 데이터프레임
    trade_idx: int,
    cfg: Dict[str, Any]
) -> Dict[str, Optional[float]]:
    """
    df_hist: OHLCV ['종가','고가','저가','거래량'] index: Date (사건시점까지)
    mutates df_hist by adding indicator columns; returns snapshot dict at trade_idx
    """
    def _as_float_series(x, index):
        if x is None:
            return pd.Series(np.nan, index=index, dtype="float64")
        if hasattr(x, "index"):
            return x.reindex(index).astype("float64", errors="ignore")
        s = pd.Series(x, index=index)
        return s.astype("float64", errors="ignore")

    ind = cfg.get("indicator_settings", {})
    ema_fast, ema_mid, ema_slow = ind.get("EMA", [20, 50, 200])
    rsi_len = ind.get("RSI", [14])[0]
    macd_cfg = ind.get("MACD", {"fast": 12, "slow": 26, "signal": 9})
    bb_cfg = ind.get("BBANDS", {"period": 20, "stddev": 2.0})
    stoch_cfg = ind.get("STOCH", {"k": 14, "d": 3, "smooth": 3})
    kel_cfg = ind.get("KELTNER", {"period": 20, "mult": 1.5})

    # 결측 보정 (과거→미래 only within hist)
    df_hist.ffill(inplace=True)

    # strict rolling helpers
    def roll_mean(s, n): return s.rolling(n, min_periods=n).mean()
    def roll_std(s, n):  return s.rolling(n, min_periods=n).std(ddof=0)

    # EMA / RSI
    df_hist["EMA_FAST"] = _as_float_series(ta.ema(df_hist["종가"], length=ema_fast), df_hist.index)
    df_hist["EMA_MID"]  = _as_float_series(ta.ema(df_hist["종가"], length=ema_mid),  df_hist.index)
    df_hist["EMA_SLOW"] = _as_float_series(ta.ema(df_hist["종가"], length=ema_slow), df_hist.index)
    df_hist["RSI"]      = _as_float_series(ta.rsi(df_hist["종가"], length=rsi_len),   df_hist.index)

    # MACD (+ histogram)
    macd = ta.macd(df_hist["종가"], fast=macd_cfg["fast"], slow=macd_cfg["slow"], signal=macd_cfg["signal"])
    if macd is None:
        df_hist["MACD"] = pd.Series(np.nan, index=df_hist.index, dtype="float64")
        df_hist["MACD_SIGNAL"] = pd.Series(np.nan, index=df_hist.index, dtype="float64")
        df_hist["MACD_HIST"] = pd.Series(np.nan, index=df_hist.index, dtype="float64")
    else:
        base = f"{macd_cfg['fast']}_{macd_cfg['slow']}_{macd_cfg['signal']}"
        df_hist["MACD"]        = _as_float_series(macd.get(f"MACD_{base}"),  df_hist.index)
        df_hist["MACD_SIGNAL"] = _as_float_series(macd.get(f"MACDs_{base}"), df_hist.index)
        df_hist["MACD_HIST"]   = _as_float_series(macd.get(f"MACDh_{base}"), df_hist.index)

    # STOCH
    stoch = ta.stoch(
        df_hist["고가"], df_hist["저가"], df_hist["종가"],
        k=stoch_cfg["k"], d=stoch_cfg["d"], smooth_k=stoch_cfg["smooth"]
    )
    if stoch is None:
        df_hist["STOCH_K"] = pd.Series(np.nan, index=df_hist.index, dtype="float64")
        df_hist["STOCH_D"] = pd.Series(np.nan, index=df_hist.index, dtype="float64")
    else:
        k_key = f"STOCHk_{stoch_cfg['k']}_{stoch_cfg['d']}_{stoch_cfg['smooth']}"
        d_key = f"STOCHd_{stoch_cfg['k']}_{stoch_cfg['d']}_{stoch_cfg['smooth']}"
        df_hist["STOCH_K"] = _as_float_series(stoch.get(k_key), df_hist.index)
        df_hist["STOCH_D"] = _as_float_series(stoch.get(d_key), df_hist.index)

    # BBANDS
    bb = ta.bbands(df_hist["종가"], length=bb_cfg["period"], std=bb_cfg["stddev"])
    if bb is None:
        df_hist["BB_UPPER"] = pd.Series(np.nan, index=df_hist.index, dtype="float64")
        df_hist["BB_LOWER"] = pd.Series(np.nan, index=df_hist.index, dtype="float64")
        df_hist["BB_MID"]   = pd.Series(np.nan, index=df_hist.index, dtype="float64")
    else:
        p = bb_cfg["period"]; s = float(bb_cfg["stddev"])
        df_hist["BB_UPPER"] = _as_float_series(bb.get(f"BBU_{p}_{s}"), df_hist.index)
        df_hist["BB_LOWER"] = _as_float_series(bb.get(f"BBL_{p}_{s}"), df_hist.index)
        df_hist["BB_MID"]   = _as_float_series(bb.get(f"BBM_{p}_{s}"), df_hist.index)

    # Keltner & SQUEEZE
    ema_kc  = _as_float_series(ta.ema(df_hist["종가"], length=kel_cfg["period"]), df_hist.index)
    atr_kc  = _as_float_series(ta.atr(df_hist["고가"], df_hist["저가"], df_hist["종가"], length=kel_cfg["period"]), df_hist.index)
    df_hist["KC_UPPER"] = ema_kc + atr_kc * kel_cfg["mult"]
    df_hist["KC_LOWER"] = ema_kc - atr_kc * kel_cfg["mult"]
    with np.errstate(divide='ignore', invalid='ignore'):
        bbw = (df_hist["BB_UPPER"] - df_hist["BB_LOWER"]) / ema_kc
        kcw = (df_hist["KC_UPPER"] - df_hist["KC_LOWER"]) / ema_kc
        df_hist["SQUEEZE"] = (bbw / kcw).replace([np.inf, -np.inf], np.nan)

    # 추가 지표
    df_hist["ATR"] = _as_float_series(ta.atr(df_hist["고가"], df_hist["저가"], df_hist["종가"], length=14), df_hist.index)
    adxout = ta.adx(df_hist["고가"], df_hist["저가"], df_hist["종가"], length=14)
    df_hist["ADX"] = _as_float_series(adxout.get("ADX_14") if adxout is not None else None, df_hist.index)

    df_hist["OBV"] = _as_float_series(ta.obv(df_hist["종가"], df_hist["거래량"]), df_hist.index)
    mu_obv  = roll_mean(df_hist["OBV"], OBV_Z_WINDOW)
    sd_obv  = roll_std(df_hist["OBV"],  OBV_Z_WINDOW).replace(0, np.nan)
    df_hist["OBV_Z"] = ((df_hist["OBV"] - mu_obv) / sd_obv).clip(lower=-WINSOR_SIGMA, upper=WINSOR_SIGMA)

    df_hist["MFI"] = _as_float_series(ta.mfi(df_hist["고가"], df_hist["저가"], df_hist["종가"], df_hist["거래량"], length=14), df_hist.index)
    try:
        df_hist["CMF"] = _as_float_series(ta.cmf(df_hist["고가"], df_hist["저가"], df_hist["종가"], df_hist["거래량"], length=20), df_hist.index)
    except Exception:
        df_hist["CMF"] = pd.Series(np.nan, index=df_hist.index, dtype="float64")

    # 거래량 Z-score
    vol_ma  = roll_mean(df_hist["거래량"], VOL_Z_WINDOW)
    vol_std = roll_std(df_hist["거래량"],  VOL_Z_WINDOW).replace(0, np.nan)
    df_hist["VOL_Z"] = ((df_hist["거래량"] - vol_ma) / vol_std).clip(lower=-WINSOR_SIGMA, upper=WINSOR_SIGMA)

    # (D)VWAP (전 구간 누적; 히스토리 범위 내)
    tp = (df_hist["고가"] + df_hist["저가"] + df_hist["종가"]) / 3.0
    cum_pv = (tp * df_hist["거래량"]).cumsum()
    cum_v  = df_hist["거래량"].cumsum().replace(0, np.nan)
    df_hist["VWAP"] = (cum_pv / cum_v).astype("float64")

    # Anchored VWAP (YTD/MTD) — 그룹별 리셋 (연/월)
    def _anchored_vwap_grouped(freq: str) -> pd.Series:
        grp = df_hist.index.to_period('Y' if freq == 'Y' else 'M')
        typical = (df_hist["고가"] + df_hist["저가"] + df_hist["종가"]) / 3.0
        pv = (typical * df_hist["거래량"]).groupby(grp).cumsum()
        vv = df_hist["거래량"].groupby(grp).cumsum().replace(0, np.nan)
        out = (pv / vv).astype("float64")
        out.name = f"AVWAP_{'YTD' if freq == 'Y' else 'MTD'}"
        return out

    try:
        df_hist["AVWAP_YTD"] = _anchored_vwap_grouped('Y')
    except Exception:
        df_hist["AVWAP_YTD"] = pd.Series(np.nan, index=df_hist.index, dtype="float64")
    try:
        df_hist["AVWAP_MTD"] = _anchored_vwap_grouped('M')
    except Exception:
        df_hist["AVWAP_MTD"] = pd.Series(np.nan, index=df_hist.index, dtype="float64")

    # === stat 스냅샷 ===
    idx = int(trade_idx)
    cols = [
        "EMA_FAST","EMA_MID","EMA_SLOW","RSI","MACD","MACD_SIGNAL","MACD_HIST",
        "STOCH_K","STOCH_D","BB_UPPER","BB_LOWER","BB_MID",
        "KC_UPPER","KC_LOWER","SQUEEZE","ATR","ADX","OBV","OBV_Z","MFI","CMF","VOL_Z",
        "AVWAP_YTD","AVWAP_MTD","VWAP"
    ]
    stat: Dict[str, Optional[float]] = {}
    for col in cols:
        val = df_hist[col].iloc[idx] if col in df_hist.columns else np.nan
        stat[col] = (None if (val is None or pd.isna(val)) else float(val))
    return stat


# =========================
# 차트 + 업로드 (xpt 명시)
# =========================
def make_trade_chart(
    df: pd.DataFrame,
    xpt: pd.Timestamp,                 # 사건 시점(시장 현지 naive, df.index와 동일 스케일)
    trade_price: float,
    action: str,
    peer_median: Optional[float] = None,
    bench_price: Optional[float] = None
) -> io.BytesIO:
    plt.figure(figsize=(14, 8))
    plt.plot(df.index, df["종가"], label="종가", color="black", linewidth=1.3)
    for key, style in [
        ("EMA_FAST", "--"), ("EMA_MID", ":"), ("EMA_SLOW", "-."),
        ("BB_UPPER", "-"), ("BB_LOWER", "-"), ("KC_UPPER", "-"), ("KC_LOWER", "-"),
        ("AVWAP_YTD", "-"), ("AVWAP_MTD", "-"), ("VWAP", "-"),
    ]:
        if key in df.columns:
            if key in ["BB_UPPER","BB_LOWER"]:
                plt.plot(df.index, df[key], alpha=0.3, label=key)
            elif key in ["KC_UPPER","KC_LOWER","AVWAP_YTD","AVWAP_MTD", "VWAP"]:
                plt.plot(df.index, df[key], alpha=0.5, label=key)
            else:
                plt.plot(df.index, df[key], style, label=key)
    if "BB_UPPER" in df.columns and "BB_LOWER" in df.columns:
        plt.fill_between(df.index, df["BB_LOWER"], df["BB_UPPER"], alpha=0.08)

    # 사건 시점 표시 (동일 xpt 사용)
    plt.axvline(xpt, color=("red" if action == "sell" else "green"), linestyle="--")
    plt.scatter([xpt], [trade_price], color=("red" if action == "sell" else "green"), s=140, zorder=5)

    if peer_median is not None:
        plt.hlines(peer_median, df.index[0], df.index[-1], alpha=0.4, label="Peer Median")
    if bench_price is not None:
        plt.hlines(bench_price, df.index[0], df.index[-1], alpha=0.5, label="Bench Price")

    plt.title("Auto Trade Analysis")
    plt.legend()
    plt.grid(True)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close()
    buf.seek(0)
    return buf


# =========================
# LLM (안전가드 포함)
# =========================
def build_llm_context(
    user: Dict[str, Any],
    trade: Dict[str, Any],
    feedback_text: str,
    stats: Dict[str, Any],
    config: Dict[str, Any],
    selected_tone: str
) -> str:
    tone_guide = config.get("tone_guide", {
        "friendly": "최대한 쉽고, 친절하고, 일상 대화체.",
        "expert": "애널리스트 보고서 톤.",
        "youth": "간결하고 캐주얼.",
        "serious": "정중하고 단호."
    })
    investor_guide = config.get("investor_level_guide", {
        "beginner": "기초 개념부터 차근차근.",
        "intermediate": "핵심 지표 중심으로.",
        "advanced": "전략/리스크 최적화 관점."
    })
    default_tone = config.get("user_customization", {}).get("default_tone", "friendly")
    tone_msg = tone_guide.get(selected_tone, tone_guide.get(default_tone, ""))
    inv_msg = investor_guide.get(user.get("investor_level", "beginner"), investor_guide.get("beginner", ""))
    ai_goal = config.get("ai_coaching_goal", "사용자에게 실행가능한 코칭을 제공하라.")

    safety = (
        "※ 유의: 본 코칭은 교육 목적이며 수익을 보장하지 않습니다. 최종 투자 결정과 책임은 사용자에게 있습니다. "
        "과도한 레버리지·집중투자를 지양하고, 손실 가능성을 충분히 고려하세요."
    )

    ctx = f"""
[시스템]
- 코드 버전: {VERSION}

[사용자정보]
- 투자레벨: {user.get('investor_level','beginner')} ({inv_msg})
- 선택 톤: {tone_msg}
- 최근감정: {user.get('last_emotion','')}

[트레이드]
- 종목: {trade['symbol']}
- 가격: {trade['price']}
- 날짜: {str(trade['trade_time'])[:19]}
- 액션: {trade['action']}
- rule피드백: {feedback_text}

[주요지표]
{json.dumps(stats, ensure_ascii=False, indent=2)}

[AI코칭목표]
{ai_goal}

[안전고지]
{safety}

(위 정보를 바탕으로 사용자의 말투/투자등급에 맞춰, 구체적이고 검증 가능한 행동 제안 위주로 코칭 메시지를 작성하시오.
금액·비중·리스크 한도를 명시하고, 불확실성과 대안 시나리오를 함께 제시하시오.)
"""
    return ctx.strip()


def ai_commentary(context: str, tries: int = 2, timeout: int = 20) -> Optional[str]:
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        logger.info("GOOGLE_API_KEY not set; skipping LLM commentary.")
        return None
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(LLM_MODEL_NAME)
    last_err = None
    for _ in range(max(1, tries)):
        try:
            resp = model.generate_content(context, request_options={"timeout": timeout})
            return getattr(resp, "text", None)
        except Exception as e:
            last_err = e
            time.sleep(0.6)
    logger.warning(f"LLM commentary failed after retries: {last_err}")
    return None


# =========================
# 메인 분석
# =========================
def analyze_and_feedback(
    trade: Dict[str, Any],
    user: Dict[str, Any],
    cfg: Dict[str, Any],
    selected_tone: str = "friendly",
    use_llm: bool = False
) -> Tuple[str, Optional[str], Dict[str, Any], str, Optional[float], Optional[float], Optional[str]]:
    symbol = trade["symbol"]
    market = (trade.get("market") or "KR").upper()
    action = trade["action"]
    price = float(trade["price"])
    trade_time_iso = str(trade["trade_time"])  # 전체 ISO 유지
    commission = float(trade.get("commission", 0) or 0.0)
    qty = float(trade.get("qty", 0) or 0.0)

    # === 데이터 구간 ===
    lookback_days = required_lookback_days(cfg)
    t_parsed = pd.to_datetime(trade_time_iso)
    if market == "KR":
        start_dt = (t_parsed - pd.Timedelta(days=lookback_days)).strftime("%Y%m%d")
        fwd = 1 if ANALYSIS_MODE == "realtime" else (ANALYSIS_WINDOW_DAYS + 7)
        end_dt = (t_parsed + pd.Timedelta(days=fwd)).strftime("%Y%m%d")
    else:
        start_dt = (t_parsed - pd.Timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        fwd = 1 if ANALYSIS_MODE == "realtime" else (ANALYSIS_WINDOW_DAYS + 7)
        end_dt = (t_parsed + pd.Timedelta(days=fwd)).strftime("%Y-%m-%d")

    df = get_stock_price(symbol, market, start_dt, end_dt)
    if df.empty:
        logger.warning(f"Price data empty: {symbol} {market} {start_dt}~{end_dt}")
        return "데이터 없음", None, {}, None, None, None, None

    if len(df) < MIN_CONSEC_BARS:
        logger.warning(f"Insufficient bars ({len(df)} < {MIN_CONSEC_BARS}) for stable indicators.")

    # === 트레이드 인덱스 (시장 현지 naive) ===
    trade_dt_local = parse_trade_date_for_market(trade_time_iso, market)  # local-naive
    df.index = pd.to_datetime(df.index).tz_localize(None)
    xpt = snap_to_index_or_next(df.index, trade_dt_local)
    trade_idx = df.index.get_loc(xpt)

    # === 스냅샷 누수 방지: 과거 구간만으로 지표 계산 ===
    df_hist = df.loc[:xpt].copy()
    stats = compute_advanced_stats(df_hist, trade_idx, cfg)

    # === 피어 ===
    peers_raw = fetch_peer_trades(symbol, market, trade_time_iso, action, user_id_exclude=user.get("id"))
    peer_prices_series = user_weighted_peer_prices(peers_raw)
    p50, rank_percentile, cnt = percent_rank_by_action(action, peer_prices_series, price, min_samples=PEER_MIN_SAMPLES)

    # === 이후 구간 (백테스트) ===
    after = pd.Series(dtype="float64") if ANALYSIS_MODE == "realtime" \
        else df.loc[xpt:].iloc[:ANALYSIS_WINDOW_DAYS]["종가"]

    # === 비용모델 + 최소수수료 보정 ===
    # per-share fee 우선순위: 명시 commission > cost model 추정
    if qty > 0 and commission > 0:
        per_share_fee_side = commission / qty
    elif qty > 0:
        notional = price * qty
        per_share_fee_side = per_order_min_fee(notional, market, action) / qty
    else:
        per_share_fee_side = 0.0

    eff_buy  = effective_unit_price(price, "buy",  market, SLIPPAGE_BPS, per_share_fee_side if action=="buy" else 0.0)
    eff_sell = effective_unit_price(price, "sell", market, SLIPPAGE_BPS, per_share_fee_side if action=="sell" else 0.0)

    bench_ret, bench_px = None, None
    if not after.empty:
        if action == "buy":
            bench_px = float(after.max())
            bench_ret = float(np.round((bench_px - eff_buy) / eff_buy * 100, 2))
            stats["max_profit"] = bench_ret  # 스냅샷 dict에 반영
            stats["min_profit"] = float(np.round((float(after.min()) - eff_buy) / eff_buy * 100, 2))
        else:
            bench_px = float(after.min())
            bench_ret = float(np.round((eff_sell - bench_px) / eff_sell * 100, 2))  # 하락 회피율
            stats["missed_profit"] = float(np.round((float(after.max()) - eff_sell) / eff_sell * 100, 2))
    else:
        stats["max_profit"] = None
        stats["min_profit"] = None
        stats["missed_profit"] = None

    # === 룰 피드백 ===
    parts = []
    ef, em, es = stats.get("EMA_FAST"), stats.get("EMA_MID"), stats.get("EMA_SLOW")
    rsi = stats.get("RSI")
    macd, macds = stats.get("MACD"), stats.get("MACD_SIGNAL")
    vwap = stats.get("VWAP")  # 히스토리에서 계산된 값
    atr = stats.get("ATR")
    adx = stats.get("ADX")
    avwap_y = stats.get("AVWAP_YTD", np.nan)
    squeeze = stats.get("SQUEEZE", np.nan)
    volz = stats.get("VOL_Z", np.nan)

    if action == "buy":
        if all(x is not None for x in [ef, em, es]) and ef > em > es: parts.append("상승 추세.")
        if adx is not None and adx >= 20: parts.append(f"추세강도(ADX={adx:.1f}) 양호.")
        if rsi is not None and rsi < 30 and stats.get("STOCH_K", np.nan) < 30: parts.append("과매도 반등 기대.")
        if rsi is not None and rsi > 70: parts.append("과매수 위험.")
        if None not in (macd, macds) and macd > macds: parts.append("MACD 매수신호.")
        if np.isfinite(avwap_y) and price >= avwap_y: parts.append("연초 AVWAP 이상.")
        if np.isfinite(vwap) and price < vwap: parts.append("VWAP 아래 매수.")
        if np.isfinite(volz) and abs(volz) >= 2: parts.append("이례적 거래량.")
        if np.isfinite(squeeze) and squeeze < 1.0: parts.append("변동성 수축(SQUEEZE) 구간.")
        mp = stats.get("max_profit")
        if mp is not None:
            if mp >= 10: parts.append(f"이후 최대 {mp}% 상승 여지.")
            if mp < 0: parts.append("매수 후 하락 위험 노출.")
    else:
        if rsi is not None and rsi > 70: parts.append("과매수 매도.")
        if adx is not None and adx >= 20 and None not in (macd, macds) and macd < macds: parts.append("MACD 매도신호.")
        if np.isfinite(vwap) and price > vwap: parts.append("VWAP 상단 매도.")
        mp = stats.get("missed_profit")
        if mp is not None:
            if mp > 5: parts.append(f"매도 후 {mp}% 추가 상승 지속.")
            if mp < 0: parts.append("매도 후 하락 진행.")

    if p50 is not None:
        if action == "buy":
            rel = "저렴" if price <= p50 else "비싸게"
        else:
            rel = "고점" if price >= p50 else "저점"
        parts.append(f"Peer중앙({p50:.2f}) 대비 {rel}.")
        if rank_percentile is not None:
            parts.append(f"피어 {cnt}명 기준 약 ~{int(round(rank_percentile))} 퍼센타일.")
    else:
        parts.append(f"피어 표본 부족({cnt}명)으로 신뢰도 제한.")

    if bench_ret is not None:
        if action == "buy":
            parts.append(f"최적 시나리오(비용 반영): {bench_ret}% 수익.")
        else:
            parts.append(f"최적 방어(비용 반영): {bench_ret}% 하락 회피.")

    if commission > 0:
        parts.append(f"수수료 {int(commission)}원 반영 완료.")

    # === 리스크 코칭: ATR 기반 사이징 (설정값 반영) ===
    stop_dist = (atr or 0.0) * STOP_ATR_MULT if atr is not None else 0.0
    if not np.isfinite(stop_dist) or stop_dist <= 0:
        stop_dist = max(price * 0.005, 1e-3)  # 0.5% fallback

    stop_raw = price - stop_dist if action == "buy" else price + stop_dist
    tp1_raw  = price + (atr or 0.0) * TP1_ATR_MULT if action == "buy" else price - (atr or 0.0) * TP1_ATR_MULT
    stop = round_to_tick(stop_raw, market)
    tp1  = round_to_tick(tp1_raw, market)

    risk_cash = ACCOUNT_SIZE * ACCOUNT_RISK
    denom = max(abs(price - stop), 1e-6)
    size_by_risk = int(max(risk_cash // denom, 0))
    size_by_cash = int(max(ACCOUNT_SIZE // price, 0))
    size = max(1, min(size_by_risk, size_by_cash))
    parts.append(f"손절 {round(stop,3)}, 1차익절 {round(tp1,3)}, 권장수량 {size}.")

    feedback_text = " ".join([p for p in parts if p]).strip()

    # === 차트 업로드 (xpt 전달) ===
    chart_url = None
    try:
        # 1. Chart creation
        logger.info("Creating chart...")
        # 차트에서는 전체 df를 사용하되, 사건선은 xpt로 고정
        # 지표 라인(EMA 등)은 df_hist 기준으로만 계산했으므로 시각화를 위해 df에 병합(선택)
        for col in ["EMA_FAST","EMA_MID","EMA_SLOW","BB_UPPER","BB_LOWER","KC_UPPER","KC_LOWER",
                    "AVWAP_YTD","AVWAP_MTD","VWAP"]:
            if col in df_hist.columns:
                df[col] = df_hist[col]
        buf = make_trade_chart(df, xpt, price, action, peer_median=p50, bench_price=bench_px)
        logger.info("Chart created successfully.")

        # 2. Upload to Supabase
        filename = f"{trade['id']}.png"
        logger.info(f"Uploading {filename} to bucket {STORAGE_BUCKET_NAME}...")
        try:
            # Try v2 syntax first
            response = supabase.storage.from_(STORAGE_BUCKET_NAME).upload(
                filename, buf.getvalue(), file_options={"content-type": "image/png", "upsert": "true"}
            )
            logger.info(f"Upload response (v2 style): {response}")
        except TypeError: # Catching specific error for syntax change
            logger.warning("Upload with file_options failed (likely v1 client), trying legacy syntax.")
            # Fallback to v1 syntax
            response = supabase.storage.from_(STORAGE_BUCKET_NAME).upload(
                filename, buf.getvalue(), {"content-type": "image/png", "upsert": True}
            )
            logger.info(f"Upload response (v1 style): {response}")
        logger.info("Upload successful.")

        # 3. Get public URL
        logger.info(f"Getting public URL for {filename}...")
        url_info = supabase.storage.from_(STORAGE_BUCKET_NAME).get_public_url(filename)
        logger.info(f"Public URL response: {url_info}")
        chart_url = url_info.get("publicUrl") if isinstance(url_info, dict) else url_info
        if not chart_url:
            logger.warning("Could not extract publicUrl from response.")

    except Exception as e:
        logger.error(f"Chart generation or upload process failed: {e}", exc_info=True) # Use error and exc_info
        chart_url = None

    # === 스타일 예시 ===
    style_type = "중립"
    if stats.get("max_profit", 0) and stats.get("max_profit", 0) > 10 and (rsi is not None and rsi < 30):
        style_type = "단타추세"
    elif stats.get("max_profit", 0) is not None and stats.get("max_profit", 0) < 0 and (rsi is not None and rsi > 70):
        style_type = "고점방어"

    # === LLM 코칭 (옵션 + config 기본값) ===
    _use_llm = bool(use_llm or LLM_ENABLED_DEFAULT)
    ai_msg = None
    llm_prompt = None
    if _use_llm:
        try:
            llm_prompt = build_llm_context(user, trade, feedback_text, stats, cfg, selected_tone)
            ai_msg = ai_commentary(llm_prompt)
        except Exception as e:
            logger.warning(f"LLM commentary error: {e}")
            ai_msg = None

    return feedback_text, chart_url, stats, style_type, rank_percentile, bench_ret, ai_msg, llm_prompt


# =========================
# endpoint wrapper
# =========================
def auto_trade_feedback(
    trade_id: int,
    user_id: str,
    selected_tone: str = "friendly",
    use_llm: bool = False
) -> Tuple[str, Optional[str], Optional[str], Optional[str]]:
    trade = fetch_trade(trade_id)
    if not trade:
        raise ValueError("trade not found")
    user = fetch_and_normalize_user(user_id)
    if not user:
        raise ValueError("user not found")

    # MARKET 전처리
    m = (trade.get("market") or "").upper()
    if m in ["KRX", "KOSPI", "KOSDAQ"]:
        trade["market"] = "KR"
    elif m in ["NASDAQ", "NYSE", "AMEX", "US"]:
        trade["market"] = "US"
    else:
        trade["market"] = m  # 이미 KR/US면 그대로

    logger.info("==== 입력값 확인 ====")
    logger.info(f"version: {VERSION}")
    logger.info(f"trade_id: {trade_id}")
    logger.info(f"user_id: {user_id}")
    logger.info(f"trade record (masked): "
                f"{{'id': {trade.get('id')}, 'symbol': {trade.get('symbol')}, 'market': {trade.get('market')}, "
                f"'action': {trade.get('action')}, 'price': {trade.get('price')}, 'qty': {trade.get('qty')}, "
                f"'commission': {trade.get('commission')}, 'trade_time': {trade.get('trade_time')}}}")
    logger.info(f"user record: {_mask_user(user)}")
    logger.info(f"cfg.keys: {list(service_config.keys())}")

    fb, img, stats, stype, r, bench, ai, llm_prompt = analyze_and_feedback(
        trade, user, service_config, selected_tone, use_llm
    )

    clean_stats = _sanitize_for_json(stats)
    rank_repr = None if r is None else f"~{int(round(r))}퍼센타일"

    payload = {
        "user_id": user_id,
        "trade_id": trade_id,
        "feedback_message": fb,
        "chart_url": img,
        "summary_stats": clean_stats,
        "style_type": stype,
        "rank_percentile": rank_repr,
        "benchmark_return": bench,
        "ai_coaching": ai,
        "selected_tone": selected_tone,
        "created_at": dt.datetime.now().isoformat()
    }

    try:
        # upsert-safe: trade_id에 UNIQUE 인덱스가 있다고 가정
        supabase.table("trade_feedback").upsert(payload, on_conflict="trade_id").execute()
    except Exception as e:
        logger.warning(f"feedback upsert failed, fallback to insert: {e}")
        try:
            supabase.table("trade_feedback").insert(payload).execute()
        except Exception as e2:
            logger.error(f"feedback insert failed: {e2}")

    return fb, img, ai, llm_prompt


# =========== 사용 예 ===========
# if __name__ == "__main__":
#     fb, url, coach = auto_trade_feedback(101, "abcd1234", selected_tone="expert", use_llm=True)
#     print(fb, url, coach, sep="\n\n")
