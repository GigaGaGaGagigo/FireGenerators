# -*- coding: utf-8 -*-
"""
🚀 Auto Trade Feedback — PRO+ (All-in-One FINAL, Ultra-Patched)
- Snapshot-safe (no leakage): 과거 데이터만으로 지표 계산, strict rolling(min_periods), ddof=0
- Lookback auto-size (config-aware), winsorized Z-scores
- Indicators: EMA(3), RSI, MACD(h), STOCH, ADX, MFI, CMF, BB(일관화), Keltner → SQUEEZE,
  OBV Z, VWAP(세션), VWAP_CUM(누적), Anchored VWAP(YTD/MTD), Donchian, Market-structure(HH/HL, LH/LL)
- Regime filters (trend vs mean), adaptive thresholds (EWMA var), multi-timeframe(weekly) confluence
- Peer percentile (user-weighted, same-session/timebox + time-decay + tick-equality) with business-day window
- Cost model: slippage (adaptive + bps) + fees + taxes + min_fee
- KR/US tick rules (config table override), trailing stop + 1R/2R/3R TP
- Risk: ATR sizing + portfolio caps (per-trade, symbol/sector, beta exposure, DDL)
- Data: Source redundancy & harmonize (KR: pykrx→FDR, US: yfinance→stooq), symbol meta hooks
- Observability: structured logs + metric stubs, DLQ on write failures
- LLM coaching (optional) with disclaimer; model from config
- Supabase storage upload (upsert standardized) + feedback upsert safe
- Backward-compat return: (fb, img, ai, stats)

Note: Optional deps guarded (pydantic, pandas_market_calendars, FinanceDataReader, pandas_datareader).
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
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import pandas_ta as ta
from dotenv import load_dotenv

from supabase import create_client
from pykrx import stock
import yfinance as yf
import google.generativeai as genai

# ---------- Optional deps ----------
try:
    import pandas_market_calendars as mcal  # business sessions
except Exception:
    mcal = None

try:
    from pandas_datareader import data as pdr  # Stooq fallback (US/Global)
except Exception:
    pdr = None

try:
    import FinanceDataReader as fdr  # KR fallback
except Exception:
    fdr = None

try:
    from pydantic import BaseModel, ValidationError  # config schema
except Exception:
    BaseModel = None
    ValidationError = Exception
# -----------------------------------

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
    _raw_cfg = json.load(f)


# =========================
# Config schema (optional)
# =========================
if BaseModel:
    class CostModel(BaseModel):
        fee_buy: float = 0.0
        fee_sell: float = 0.0
        tax_sell: float = 0.0
        min_fee: float = 0.0

    class ExecCfg(BaseModel):
        slippage_bps: float = 5.0
        account_risk_per_trade: float = 0.01
        account_size: float = 10_000_000
        stop_atr_mult: float = 1.2
        tp1_atr_mult: float = 2.0
        kr_tick_table: Optional[List[List[float]]] = None
        cost_model: Dict[str, CostModel] = {"KR": CostModel(), "US": CostModel()}

        # Adaptive slippage (optional regression-like params)
        # slip_bps ≈ a + 1e4*(b*spread_pct + c*vol_term + d*abs_ret)
        slip_adaptive: Dict[str, Dict[str, float]] = {
            "KR": {"a": 2.0, "b": 120.0, "c": 5.0, "d": 30.0},
            "US": {"a": 1.0, "b": 80.0, "c": 4.0, "d": 20.0},
        }

    class FeedbackCfg(BaseModel):
        analysis_mode: str = "backtest"  # or "realtime"
        peer_group_size: int = 100
        min_data_period_days: int = 60
        analysis_window_days: int = 7
        peer_min_samples: int = 50
        peer_window_days: int = 3
        # Peer sampling controls
        peer_same_session: bool = True          # only peers in same regular session
        peer_timebox_minutes: int = 60          # ±N minutes window around trade time
        peer_halflife_minutes: int = 60         # time-decay half-life in minutes

    class CalcCfg(BaseModel):
        winsorize_sigma: float = 4.0
        obv_z_window: int = 20
        vol_z_window: int = 20
        min_consecutive_bars: int = 200
        donchian_n: int = 20
        swing_window: int = 5
        ewma_lambda: float = 0.94
        regime_adx: float = 25.0
        regime_atr_pct: float = 0.01

    class CalendarCfg(BaseModel):
        use_market_calendars: bool = True
        exchange_codes: Dict[str, str] = {"KR": "XKRX", "US": "XNYS"}

    class LlmCfg(BaseModel):
        enabled_default: bool = False
        model: str = "gemini-1.5-flash-latest"

    class PortfolioCaps(BaseModel):
        per_trade_risk: float = 0.0025   # 0.25% of equity at risk cap
        daily_drawdown_limit: float = 0.005  # 0.5% DDL
        symbol_cap: float = 0.05         # 5% of equity
        sector_cap: float = 0.20         # 20%
        beta_expo_cap: float = 0.50      # 50% net beta exposure
        cash_buffer: float = 0.02        # 2% cash buffer

    class ServiceConfig(BaseModel):
        version: str = "unknown"
        feedback_policy: FeedbackCfg = FeedbackCfg()
        execution: ExecCfg = ExecCfg()
        calc: CalcCfg = CalcCfg()
        calendar: CalendarCfg = CalendarCfg()
        llm: LlmCfg = LlmCfg()
        user_customization: Dict[str, Any] = {}
        tone_guide: Dict[str, str] = {}
        investor_level_guide: Dict[str, str] = {}
        portfolio_caps: PortfolioCaps = PortfolioCaps()

    try:
        service_config_obj = ServiceConfig(**_raw_cfg)
        service_config: Dict[str, Any] = json.loads(service_config_obj.json())
    except ValidationError as ve:
        logger.warning(f"Config validation failed; using raw config. Detail: {ve}")
        service_config = _raw_cfg
else:
    service_config = _raw_cfg  # fallback without schema


# ---- Config bindings ----
VERSION = service_config.get("version", "unknown")

FEEDBACK = service_config.get("feedback_policy", {})
ANALYSIS_MODE: str = FEEDBACK.get("analysis_mode", "backtest")
PEER_GROUP_SIZE: int = int(FEEDBACK.get("peer_group_size", 100))
MIN_DATA_DAYS: int = int(FEEDBACK.get("min_data_period_days", 60))
ANALYSIS_WINDOW_DAYS: int = int(FEEDBACK.get("analysis_window_days", 7))
PEER_MIN_SAMPLES: int = int(FEEDBACK.get("peer_min_samples", 50))
PEER_WINDOW_DAYS: int = int(FEEDBACK.get("peer_window_days", 3))
PEER_SAME_SESSION: bool = bool(FEEDBACK.get("peer_same_session", True))
PEER_TIMEBOX_MIN: int = int(FEEDBACK.get("peer_timebox_minutes", 60))
PEER_HALFLIFE_MIN: int = int(FEEDBACK.get("peer_halflife_minutes", 60))

EXEC_CFG = service_config.get("execution", {})
SLIPPAGE_BPS: float = float(EXEC_CFG.get("slippage_bps", 5))
ACCOUNT_RISK: float = float(EXEC_CFG.get("account_risk_per_trade", 0.01))
ACCOUNT_SIZE: float = float(EXEC_CFG.get("account_size", 10_000_000))
STOP_ATR_MULT: float = float(EXEC_CFG.get("stop_atr_mult", 1.2))
TP1_ATR_MULT: float = float(EXEC_CFG.get("tp1_atr_mult", 2.0))
KR_TICK_TABLE = EXEC_CFG.get("kr_tick_table")
COST_MODEL = EXEC_CFG.get("cost_model", {
    "KR": {"fee_buy": 0.0, "fee_sell": 0.0, "tax_sell": 0.0, "min_fee": 0.0},
    "US": {"fee_buy": 0.0, "fee_sell": 0.0, "tax_sell": 0.0, "min_fee": 0.0}
})
SLIP_ADAPT = EXEC_CFG.get("slip_adaptive", {})

CALC = service_config.get("calc", {})
WINSOR_SIGMA: float = float(CALC.get("winsorize_sigma", 4.0))
OBV_Z_WINDOW: int = int(CALC.get("obv_z_window", 20))
VOL_Z_WINDOW: int = int(CALC.get("vol_z_window", 20))
MIN_CONSEC_BARS: int = int(CALC.get("min_consecutive_bars", 200))
DONCHIAN_N: int = int(CALC.get("donchian_n", 20))
SWING_W: int = int(CALC.get("swing_window", 5))
EWMA_LAM: float = float(CALC.get("ewma_lambda", 0.94))
REGIME_ADX: float = float(CALC.get("regime_adx", 25.0))
REGIME_ATR_PCT: float = float(CALC.get("regime_atr_pct", 0.01))

CAL_CFG = service_config.get("calendar", {})
USE_MCAL: bool = bool(CAL_CFG.get("use_market_calendars", True))
EXCHANGE_CODES: Dict[str, str] = CAL_CFG.get("exchange_codes", {"KR": "XKRX", "US": "XNYS"})

LLM_CFG = service_config.get("llm", {})
LLM_ENABLED_DEFAULT: bool = bool(LLM_CFG.get("enabled_default", False))
LLM_MODEL_NAME: str = LLM_CFG.get("model", "gemini-1.5-flash-latest")

PORT_CAPS = service_config.get("portfolio_caps", {
    "per_trade_risk": 0.0025,
    "daily_drawdown_limit": 0.005,
    "symbol_cap": 0.05,
    "sector_cap": 0.20,
    "beta_expo_cap": 0.50,
    "cash_buffer": 0.02
})

# Env var: Supabase 키 명칭 호환 (SUPABASE_KEY 또는 SUPABASE_ANON_KEY)
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_ANON_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Supabase URL/KEY가 설정되지 않았습니다. (SUPABASE_URL, SUPABASE_KEY|SUPABASE_ANON_KEY)")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
STORAGE_BUCKET_NAME = os.environ.get("CHARTS_BUCKET", "charts")

np.seterr(all="ignore")


# =========================
# Observability helpers
# =========================
def emit_metric(name: str, value: float, labels: Optional[Dict[str, str]] = None):
    """Stub for metrics export; replace with Prometheus/OTel as needed."""
    try:
        labels = labels or {}
        logger.info(f"[metric] {name}={value} | {labels}")
    except Exception:
        pass


# =========================
# 시장/타임존/캘린더
# =========================
def market_tz(market: str) -> str:
    m = (market or "").upper()
    if m == "KR":
        return "Asia/Seoul"
    return "America/New_York"


def _calendar_code(market: str) -> Optional[str]:
    if (mcal is None) or (not USE_MCAL):
        return None
    return EXCHANGE_CODES.get((market or "").upper(), None)


def snap_to_session_close(ts_local: pd.Timestamp, market: str) -> Optional[pd.Timestamp]:
    """
    ts_local: 시장 현지 tz-aware
    반환: 시장 현지 naive close 시각(해당 세션), 없으면 None
    """
    code = _calendar_code(market)
    if not code:
        return None
    try:
        cal = mcal.get_calendar(code)
        sched = cal.schedule(
            start_date=ts_local.date() - pd.Timedelta(days=60),
            end_date=ts_local.date() + pd.Timedelta(days=60)
        ).copy()

        # 모든 비교를 ts_local.tz 기준으로 통일
        local_tz = ts_local.tz
        open_local = sched["market_open"].dt.tz_convert(local_tz)
        close_local = sched["market_close"].dt.tz_convert(local_tz)

        in_sess = (open_local <= ts_local) & (ts_local <= close_local)
        if in_sess.any():
            close_l = close_local.loc[in_sess].iloc[0]
            return close_l.tz_localize(None)  # naive(현지)
        return None
    except Exception as e:
        logger.debug(f"snap_to_session_close failed: {e}")
        return None


def parse_trade_date_for_market(trade_time_iso: str, market: str) -> pd.Timestamp:
    """시장 현지 tz로 변환 → 세션 close 또는 현지 자정 → tz-naive 반환."""
    tz = ZoneInfo(market_tz(market)) if ZoneInfo else None
    ts = pd.to_datetime(trade_time_iso)
    ts_local = ts.tz_convert(tz) if (tz and ts.tzinfo) else (ts.tz_localize(tz) if tz else ts)
    close_ts = snap_to_session_close(ts_local, market)
    if close_ts is not None:
        return close_ts
    return ts_local.normalize().tz_localize(None) if ts_local.tzinfo else pd.to_datetime(str(ts_local.date()))


def business_window_utc(trade_time_iso: str, market: str, n_days: int) -> Optional[Tuple[str, str]]:
    """±n 영업일 (open~close) 경계를 UTC ISO로."""
    code = _calendar_code(market)
    if not code:
        return None
    try:
        tz = ZoneInfo(market_tz(market)) if ZoneInfo else None
        cal = mcal.get_calendar(code)
        ts = pd.to_datetime(trade_time_iso)
        ts_local = ts.tz_convert(tz) if (tz and ts.tzinfo) else (ts.tz_localize(tz) if tz else ts)

        sched = cal.schedule(
            start_date=ts_local.date() - pd.Timedelta(days=120),
            end_date=ts_local.date() + pd.Timedelta(days=120)
        ).sort_index()

        mask = (sched["market_open"].dt.tz_convert(ts_local.tz) <= ts_local) & \
               (ts_local <= sched["market_close"].dt.tz_convert(ts_local.tz))
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
    if t in idx:
        return t
    mask = idx >= t
    return idx[mask][0] if mask.any() else idx[-1]


# =========================
# Data sources & harmonize
# =========================
def _normalize_index(df: pd.DataFrame) -> pd.DataFrame:
    """Robust index normalization: remove tz if present (tz_localize(None)), then normalize to midnight."""
    if df is None or df.empty:
        return pd.DataFrame()
    idx = pd.to_datetime(df.index)
    try:
        # tz-aware → tz-naive
        if getattr(idx, "tz", None) is not None:
            idx = idx.tz_localize(None)
    except Exception:
        pass
    df = df.copy()
    df.index = idx
    try:
        df.index = df.index.normalize()
    except Exception:
        pass
    return df


def _harmonize(df: pd.DataFrame) -> pd.DataFrame:
    """Map various loaders to ['종가','고가','저가','거래량'] with safe fallbacks."""
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    df = _normalize_index(df)

    # Build lowercase column map
    cols_map = {c.lower(): c for c in df.columns}

    def _pick(*names) -> Optional[pd.Series]:
        for n in names:
            key = n.lower()
            if key in cols_map:
                return pd.to_numeric(df[cols_map[key]], errors="coerce")
        return None

    # Safe index to construct NaN series when missing
    base_index = df.index

    def _series_or_nan(s: Optional[pd.Series]) -> pd.Series:
        if s is None:
            return pd.Series(np.nan, index=base_index)
        return s

    close = _series_or_nan(_pick("close","adj close","adjclose"))
    high  = _series_or_nan(_pick("high"))
    low   = _series_or_nan(_pick("low"))
    vol   = _series_or_nan(_pick("volume")).fillna(0.0)

    out = pd.DataFrame(index=base_index)
    out["종가"] = close
    out["고가"] = high
    out["저가"] = low
    out["거래량"] = vol

    out = out.dropna(subset=["종가","고가","저가"])
    # Ensure float dtype
    for c in ["종가","고가","저가","거래량"]:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    return out


def _kr_primary(symbol: str, start: str, end: str) -> pd.DataFrame:
    try:
        df = stock.get_market_ohlcv_by_date(start, end, symbol)
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.rename(columns={"종가":"Close","고가":"High","저가":"Low","거래량":"Volume"})
        return _harmonize(df)
    except Exception:
        return pd.DataFrame()


def _kr_secondary(symbol: str, start: str, end: str) -> pd.DataFrame:
    if fdr is None:
        return pd.DataFrame()
    try:
        s = start if "-" in start else f"{start[:4]}-{start[4:6]}-{start[6:]}"
        e = end   if "-" in end   else f"{end[:4]}-{end[4:6]}-{end[6:]}"
        df = fdr.DataReader(symbol, s, e)
        return _harmonize(df)
    except Exception:
        return pd.DataFrame()


def _us_primary(symbol: str, start: str, end: str) -> pd.DataFrame:
    try:
        df = yf.download(symbol, start=start, end=end, progress=False, auto_adjust=True)
        return _harmonize(df)
    except Exception:
        return pd.DataFrame()


def _us_secondary(symbol: str, start: str, end: str) -> pd.DataFrame:
    if pdr is None:
        return pd.DataFrame()
    try:
        df = pdr.DataReader(symbol, "stooq", start=start, end=end).sort_index()
        return _harmonize(df)
    except Exception:
        return pd.DataFrame()


@lru_cache(maxsize=256)
def get_stock_price_cached(symbol: str, market: str, start_date: str, end_date: str) -> pd.DataFrame:
    m = (market or "").upper()
    if m == "KR":
        for loader in (_kr_primary, _kr_secondary):
            df = loader(symbol, start_date, end_date)
            if df is not None and not df.empty:
                return df
    else:
        for loader in (_us_primary, _us_secondary):
            df = loader(symbol, start_date, end_date)
            if df is not None and not df.empty:
                return df
    return pd.DataFrame()


def get_stock_price(symbol: str, market: str, start: str, end: str) -> pd.DataFrame:
    return get_stock_price_cached(symbol, market, str(start), str(end)).copy()

# =========================
# Supabase helpers
# =========================
def fetch_trade(trade_id: int) -> Optional[Dict[str, Any]]:
    try:
        res = (supabase.table("trade_history").select("*").eq("id", trade_id).single().execute())
        return res.data
    except Exception as e:
        logger.error(f"fetch_trade failed: {e}")
        return None


def fetch_and_normalize_user(user_id: str) -> Optional[Dict[str, Any]]:
    try:
        raw = (supabase.table("profiles").select("*").eq("id", user_id).single().execute().data)
    except Exception as e:
        logger.error(f"fetch_user failed: {e}")
        raw = None
    if not raw:
        return None
    user = dict(raw)
    if "investment_level" in user:
        user["investor_level"] = user.get("investment_level")
    if isinstance(user.get("emotions"), list) and user["emotions"]:
        user["last_emotion"] = user["emotions"][-1]
    else:
        user["last_emotion"] = None
    user.setdefault("preferred_tone", "friendly")
    user.setdefault("risk_profile", "normal")
    return user


def _sector_of(symbol: str) -> str:
    """섹터 맵 쿼리 캐시."""
    try:
        sm = supabase.table("sector_map").select("symbol,sector").eq("symbol", symbol).single().execute().data
        if sm and sm.get("sector"):
            return sm["sector"]
    except Exception:
        pass
    return "OTHER"


def fetch_positions_and_meta(user_id: str) -> Dict[str, Any]:
    """
    선택적: 포트폴리오/섹터/베타 정보를 가져오는 훅.
    없으면 기본값으로 초기화. equity 추정은 과대 추정 피해서 eq>0일 때만 사용.
    """
    out = {"equity": ACCOUNT_SIZE, "cash_avail": ACCOUNT_SIZE, "ddl_today": 0.0,
           "by_symbol": {}, "by_sector": {}, "beta_exposure": 0.0}
    try:
        res = supabase.table("positions").select("*").eq("user_id", user_id).execute()
        rows = res.data or []
        eq = 0.0
        by_sym = {}
        by_sec = {}
        beta_exp = 0.0
        for r in rows:
            s = r.get("symbol"); q = float(r.get("qty", 0) or 0); p = float(r.get("price", 0) or 0)
            sec = r.get("sector") or _sector_of(s)
            beta = float(r.get("beta", 1.0) or 1.0)
            notional = q * p
            eq += notional
            by_sym[s] = by_sym.get(s, 0.0) + notional
            by_sec[sec] = by_sec.get(sec, 0.0) + notional
            beta_exp += beta * (notional / max(1.0, ACCOUNT_SIZE))
        equity_est = eq if eq > 0 else ACCOUNT_SIZE
        out.update({"equity": equity_est, "by_symbol": by_sym, "by_sector": by_sec,
                    "beta_exposure": beta_exp})
        # daily drawdown (optional)
        dd = supabase.table("daily_drawdown").select("value").eq("user_id", user_id)\
             .order("date", desc=True).limit(1).execute()
        if dd.data:
            out["ddl_today"] = float(dd.data[0].get("value", 0.0) or 0.0)
        # cash (optional)
        cash = supabase.table("cash").select("available").eq("user_id", user_id)\
               .single().execute().data
        if cash:
            out["cash_avail"] = float(cash.get("available", ACCOUNT_SIZE))
    except Exception:
        pass
    return out


def fetch_peer_trades(
    symbol: str,
    market: str,
    trade_time_iso: str,
    action: str,
    group_size: Optional[int] = None,
    user_id_exclude: Optional[str] = None
) -> List[Dict[str, Any]]:
    """피어 표본은 영업일 윈도우(캘린더 기준)로 제한."""
    if group_size is None:
        group_size = PEER_GROUP_SIZE
    win = business_window_utc(trade_time_iso, market, PEER_WINDOW_DAYS)
    if win:
        start_iso, end_iso = win
    else:
        t = pd.to_datetime(trade_time_iso)
        start_iso = (t - pd.Timedelta(days=PEER_WINDOW_DAYS)).strftime("%Y-%m-%d")
        end_iso   = (t + pd.Timedelta(days=PEER_WINDOW_DAYS)).strftime("%Y-%m-%d")
    try:
        q = (supabase.table("trade_history")
             .select("user_id, price, qty, trade_time")
             .eq("symbol", symbol).eq("market", market).eq("action", action)
             .gte("trade_time", start_iso).lte("trade_time", end_iso)
             .order("trade_time", desc=False).limit(group_size))
        if user_id_exclude:
            q = q.neq("user_id", user_id_exclude)
        res = q.execute()
        return res.data or []
    except Exception as e:
        logger.error(f"fetch_peer_trades failed: {e}")
        return []


# =========================
# Peer utils (timebox + decay + tick equality)
# =========================
def _to_local(ts_iso: str, market: str) -> pd.Timestamp:
    tz = ZoneInfo(market_tz(market)) if ZoneInfo else None
    t = pd.to_datetime(ts_iso)
    return t.tz_convert(tz) if (tz and t.tzinfo) else (t.tz_localize(tz) if tz else t)


def _same_session_local(trade_ts_local: pd.Timestamp, other_ts_local: pd.Timestamp) -> bool:
    return trade_ts_local.date() == other_ts_local.date()


def user_weighted_peer_prices_timeboxed(
    peers: List[Dict[str, Any]],
    trade_time_iso: str,
    market: str,
    same_session: bool = True,
    timebox_min: Optional[int] = None,
    halflife_min: int = 60
) -> Tuple[pd.Series, pd.Series]:
    """
    peers: [{user_id, price, qty, trade_time}, ...]
    반환: (대표가격 series, 가중치 series) — 사용자별 체결을 수량*시간감쇠 가중으로 평균
    필터: 동일 세션, ±timebox 분, 시간감쇠(half-life 분)
    """
    if not peers:
        return pd.Series(dtype="float64"), pd.Series(dtype="float64")

    t0_local = _to_local(trade_time_iso, market)

    from collections import defaultdict
    acc_pv = defaultdict(float)  # user-wise price*weight 합
    acc_w  = defaultdict(float)  # user-wise weight 합

    def time_decay_w(dt_peer_local: pd.Timestamp) -> float:
        if halflife_min <= 0:
            return 1.0
        mins = abs((t0_local - dt_peer_local).total_seconds()) / 60.0
        return math.exp(-math.log(2) * mins / float(halflife_min))

    for p in peers:
        px = p.get("price"); q = p.get("qty"); uid = p.get("user_id"); ts = p.get("trade_time")
        if px is None or q in (None, 0) or uid is None or ts is None:
            continue
        peer_local = _to_local(str(ts), market)

        if same_session and not _same_session_local(t0_local, peer_local):
            continue
        if isinstance(timebox_min, int) and timebox_min > 0:
            if abs((t0_local - peer_local).total_seconds())/60.0 > timebox_min:
                continue

        w = float(q) * time_decay_w(peer_local)
        acc_pv[uid] += float(px) * w
        acc_w[uid]  += w

    prices = []
    weights = []
    for uid, w in acc_w.items():
        if w > 0:
            prices.append(acc_pv[uid]/w)
            weights.append(w)
    return pd.Series(prices, dtype="float64"), pd.Series(weights, dtype="float64")


def weighted_median(x: pd.Series, w: pd.Series) -> Optional[float]:
    if x.empty or w.empty or len(x) != len(w):
        return None
    order = np.argsort(x.values)
    xv = x.values[order]; wv = w.values[order]
    cdf = np.cumsum(wv) / np.sum(wv)
    idx = np.searchsorted(cdf, 0.5)
    idx = np.clip(idx, 0, len(xv)-1)
    return float(xv[idx])


# --- Tick helpers for equality ---
def tick_size_kr(price: float) -> float:
    if KR_TICK_TABLE and isinstance(KR_TICK_TABLE, list):
        for lo, hi, step in KR_TICK_TABLE:
            if lo <= price < hi:
                return float(step)
        return float(KR_TICK_TABLE[-1][-1])
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
    t = tick_size_kr(px) if (market or "").upper() == "KR" else tick_size_us(px)
    return round(px / t) * t


def _tick_equalize(series: pd.Series, market: str) -> pd.Series:
    if series is None or len(series) == 0:
        return series
    return series.apply(lambda v: round_to_tick(float(v), market) if np.isfinite(v) else v)


def weighted_percentile_rank_by_action(
    action: str, peer_prices: pd.Series, weights: pd.Series, my_price: float, market: Optional[str] = None
) -> Optional[float]:
    """
    가중 백분위: buy는 내 가격 이하의 가중비율, sell은 내 가격 이상의 가중비율
    - market이 주어지면 peer/my 가격을 틱 규칙에 맞춰 반올림하여 동등성 보정
    """
    if peer_prices.empty or weights.empty or len(peer_prices) != len(weights):
        return None
    if market:
        peer_prices = _tick_equalize(peer_prices, market)
        my_price = round_to_tick(my_price, market)
    wsum = float(np.sum(weights))
    if wsum <= 0:
        return None
    if action == "buy":
        sel = weights[peer_prices <= my_price]
    else:
        sel = weights[peer_prices >= my_price]
    return 100.0 * float(np.sum(sel) / wsum)


# =========================
# Cost model & slippage
# =========================
def per_order_min_fee(notional: float, market: str, side: str) -> float:
    m = COST_MODEL.get((market or "US").upper(), COST_MODEL.get("US", {}))
    rate = float(m.get("fee_buy" if side == "buy" else "fee_sell", 0.0))
    min_fee = float(m.get("min_fee", 0.0))
    return max(notional * rate, min_fee)


def adaptive_slippage_bps(symbol: str, market: str, df_hist: pd.DataFrame) -> float:
    """
    간단한 적응형 슬리피지 추정(bps).
    slip ≈ a + 1e4*(b*intraday_spread_pct + c*avg_abs_ret + d*last_abs_ret)
    """
    params = SLIP_ADAPT.get((market or "US").upper(), {})
    a = float(params.get("a", SLIPPAGE_BPS))
    b = float(params.get("b", 0.0))
    c = float(params.get("c", 0.0))
    d = float(params.get("d", 0.0))
    try:
        win = min(10, len(df_hist))
        close = df_hist["종가"].iloc[-win:]
        high = df_hist["고가"].iloc[-win:]; low = df_hist["저가"].iloc[-win:]
        spread_pct = float(np.nanmean((high - low) / close)) if win > 0 else 0.0
        vol_term = float(np.nanmean(close.pct_change().abs())) if win > 1 else 0.0
        abs_ret = float(abs(close.pct_change().iloc[-1])) if win > 1 else 0.0
        slip = a + 1e4*(b*spread_pct + c*vol_term + d*abs_ret)  # convert to bps
        return max(0.0, slip)
    except Exception:
        return SLIPPAGE_BPS


def effective_unit_price(px: float, action: str, market: str, slippage_bps: float, per_share_fee: float = 0.0) -> float:
    m = COST_MODEL.get((market or "US").upper(), {})
    fee_buy  = float(m.get("fee_buy", 0.0))
    fee_sell = float(m.get("fee_sell", 0.0))
    tax_sell = float(m.get("tax_sell", 0.0))
    slip = px * (slippage_bps / 1e4)
    eff = px + (slip if action == "buy" else -slip)
    if action == "buy":
        eff *= (1 + fee_buy)
    else:
        eff *= (1 + fee_sell + tax_sell)
    return eff + per_share_fee


# =========================
# Indicators (snapshot only, no leakage)
# =========================
def compute_indicators_snapshot(
    df_hist: pd.DataFrame,
    cfg: Dict[str, Any]
) -> Dict[str, Optional[float]]:
    """
    df_hist: 사건시점까지 포함된 과거 데이터.
    지표 컬럼을 df_hist에 추가하고 마지막 스냅샷 dict 반환 (미래 누출 방지).
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

    df_hist = df_hist.copy()
    df_hist.ffill(inplace=True)

    # EMA / RSI
    df_hist["EMA_FAST"] = _as_float_series(ta.ema(df_hist["종가"], length=ema_fast), df_hist.index)
    df_hist["EMA_MID"]  = _as_float_series(ta.ema(df_hist["종가"], length=ema_mid),  df_hist.index)
    df_hist["EMA_SLOW"] = _as_float_series(ta.ema(df_hist["종가"], length=ema_slow), df_hist.index)
    df_hist["RSI"]      = _as_float_series(ta.rsi(df_hist["종가"], length=rsi_len),   df_hist.index)

    # MACD (+ histogram)
    macd = ta.macd(df_hist["종가"], fast=macd_cfg["fast"], slow=macd_cfg["slow"], signal=macd_cfg["signal"])
    if macd is None:
        for k in ("MACD","MACD_SIGNAL","MACD_HIST"):
            df_hist[k] = pd.Series(np.nan, index=df_hist.index, dtype="float64")
    else:
        base = f"{macd_cfg['fast']}_{macd_cfg['slow']}_{macd_cfg['signal']}"
        df_hist["MACD"]        = _as_float_series(macd.get(f"MACD_{base}"),  df_hist.index)
        df_hist["MACD_SIGNAL"] = _as_float_series(macd.get(f"MACDs_{base}"), df_hist.index)
        df_hist["MACD_HIST"]   = _as_float_series(macd.get(f"MACDh_{base}"), df_hist.index)

    # STOCH
    stoch = ta.stoch(df_hist["고가"], df_hist["저가"], df_hist["종가"],
                     k=stoch_cfg["k"], d=stoch_cfg["d"], smooth_k=stoch_cfg["smooth"])
    if stoch is None:
        df_hist["STOCH_K"] = pd.Series(np.nan, index=df_hist.index, dtype="float64")
        df_hist["STOCH_D"] = pd.Series(np.nan, index=df_hist.index, dtype="float64")
    else:
        k_key = f"STOCHk_{stoch_cfg['k']}_{stoch_cfg['d']}_{stoch_cfg['smooth']}"
        d_key = f"STOCHd_{stoch_cfg['k']}_{stoch_cfg['d']}_{stoch_cfg['smooth']}"
        df_hist["STOCH_K"] = _as_float_series(stoch.get(k_key), df_hist.index)
        df_hist["STOCH_D"] = _as_float_series(stoch.get(d_key), df_hist.index)

    # === BBANDS (adaptive using EWMA var) — 중심/폭 기준 일관화 ===
    # 수익률 EWMA 분산 → 가격 스케일 표준편차로 환산하여 '종가' 중심(BB_MID=price) 기준 상·하단 산출
    ewvar = df_hist["종가"].pct_change().ewm(
        alpha=1 - EWMA_LAM, min_periods=bb_cfg["period"]
    ).var()
    sigma_price = (np.sqrt(ewvar) * df_hist["종가"]).rename("SIGMA_PRICE")

    k = float(bb_cfg.get("stddev", 2.0))
    center = df_hist["종가"]  # 중심을 '종가'로 통일 (SMA 혼용 불일치 제거)
    df_hist["BB_UPPER"] = _as_float_series(center + k * sigma_price, df_hist.index)
    df_hist["BB_LOWER"] = _as_float_series(center - k * sigma_price, df_hist.index)
    df_hist["BB_MID"]   = _as_float_series(center, df_hist.index)

    # Keltner & SQUEEZE
    ema_kc  = _as_float_series(ta.ema(df_hist["종가"], length=kel_cfg["period"]), df_hist.index)
    atr_kc  = _as_float_series(ta.atr(df_hist["고가"], df_hist["저가"], df_hist["종가"], length=kel_cfg["period"]), df_hist.index)
    df_hist["KC_UPPER"] = ema_kc + atr_kc * kel_cfg["mult"]
    df_hist["KC_LOWER"] = ema_kc - atr_kc * kel_cfg["mult"]
    with np.errstate(divide='ignore', invalid='ignore'):
        bbw = (df_hist["BB_UPPER"] - df_hist["BB_LOWER"]) / ema_kc
        kcw = (df_hist["KC_UPPER"] - df_hist["KC_LOWER"]) / ema_kc
        df_hist["SQUEEZE"] = (bbw / kcw).replace([np.inf, -np.inf], np.nan)

    # ATR/ADX/MFI/CMF
    df_hist["ATR"] = _as_float_series(ta.atr(df_hist["고가"], df_hist["저가"], df_hist["종가"], length=14), df_hist.index)
    adxout = ta.adx(df_hist["고가"], df_hist["저가"], df_hist["종가"], length=14)
    df_hist["ADX"] = _as_float_series(adxout.get("ADX_14") if adxout is not None else None, df_hist.index)
    df_hist["MFI"] = _as_float_series(ta.mfi(df_hist["고가"], df_hist["저가"], df_hist["종가"], df_hist["거래량"], length=14), df_hist.index)
    try:
        df_hist["CMF"] = _as_float_series(ta.cmf(df_hist["고가"], df_hist["저가"], df_hist["종가"], df_hist["거래량"], length=20), df_hist.index)
    except Exception:
        df_hist["CMF"] = pd.Series(np.nan, index=df_hist.index, dtype="float64")

    # OBV Z, VOL Z (winsorized)
    df_hist["OBV"] = _as_float_series(ta.obv(df_hist["종가"], df_hist["거래량"]), df_hist.index)
    mu_obv  = df_hist["OBV"].rolling(OBV_Z_WINDOW, min_periods=OBV_Z_WINDOW).mean()
    sd_obv  = df_hist["OBV"].rolling(OBV_Z_WINDOW, min_periods=OBV_Z_WINDOW).std(ddof=0).replace(0, np.nan)
    df_hist["OBV_Z"] = ((df_hist["OBV"] - mu_obv) / sd_obv).clip(lower=-WINSOR_SIGMA, upper=WINSOR_SIGMA)

    vol_ma  = df_hist["거래량"].rolling(VOL_Z_WINDOW, min_periods=VOL_Z_WINDOW).mean()
    vol_sd  = df_hist["거래량"].rolling(VOL_Z_WINDOW, min_periods=VOL_Z_WINDOW).std(ddof=0).replace(0, np.nan)
    df_hist["VOL_Z"] = ((df_hist["거래량"] - vol_ma) / vol_sd).clip(lower=-WINSOR_SIGMA, upper=WINSOR_SIGMA)

    # VWAPs
    tp = (df_hist["고가"] + df_hist["저가"] + df_hist["종가"]) / 3.0

    # (1) 세션(거래일) VWAP — 거래일별 누적 (daily VWAP; reset each day)
    grp_date = df_hist.index.date
    pv_day = (tp * df_hist["거래량"]).groupby(grp_date).cumsum()
    vv_day = df_hist["거래량"].groupby(grp_date).cumsum().replace(0, np.nan)
    df_hist["VWAP"] = (pv_day / vv_day).astype("float64")

    # (2) 누적 VWAP — 파일 전 기간 누적
    df_hist["VWAP_CUM"] = (tp.mul(df_hist["거래량"]).cumsum() / df_hist["거래량"].cumsum().replace(0, np.nan)).astype("float64")

    # Anchored VWAP — YTD / MTD (각 기간 첫 거래일부터 누적)
    def _anchored(freq: str) -> pd.Series:
        grp = df_hist.index.to_period('Y' if freq == 'Y' else 'M')
        pv = (tp * df_hist["거래량"]).groupby(grp).cumsum()
        vv = df_hist["거래량"].groupby(grp).cumsum().replace(0, np.nan)
        return (pv / vv).astype("float64")

    try:
        df_hist["AVWAP_YTD"] = _anchored('Y')
    except Exception:
        df_hist["AVWAP_YTD"] = pd.Series(np.nan, index=df_hist.index, dtype="float64")
    try:
        df_hist["AVWAP_MTD"] = _anchored('M')
    except Exception:
        df_hist["AVWAP_MTD"] = pd.Series(np.nan, index=df_hist.index, dtype="float64")

    # Donchian & market structure
    df_hist["DONCH_H"] = df_hist["고가"].rolling(DONCHIAN_N, min_periods=DONCHIAN_N).max()
    df_hist["DONCH_L"] = df_hist["저가"].rolling(DONCHIAN_N, min_periods=DONCHIAN_N).min()
    sw_high = df_hist["고가"].rolling(SWING_W, center=True, min_periods=1).max()
    sw_low  = df_hist["저가"].rolling(SWING_W, center=True, min_periods=1).min()
    df_hist["HH_HL"] = ((sw_high > sw_high.shift(1)) & (sw_low > sw_low.shift(1))).astype(int)  # trend up
    df_hist["LH_LL"] = ((sw_high < sw_high.shift(1)) & (sw_low < sw_low.shift(1))).astype(int)  # trend down

    # Regime flags
    df_hist["REGIME_TREND"] = ((df_hist["ADX"] > REGIME_ADX) &
                               ((df_hist["ATR"] / df_hist["종가"]) > REGIME_ATR_PCT)).astype(int)
    df_hist["REGIME_MEAN"] = (1 - df_hist["REGIME_TREND"]).astype(int)

    # Snapshot dict at last index
    cols = ["EMA_FAST","EMA_MID","EMA_SLOW","RSI","MACD","MACD_SIGNAL","MACD_HIST",
            "STOCH_K","STOCH_D","BB_UPPER","BB_LOWER","BB_MID","KC_UPPER","KC_LOWER",
            "SQUEEZE","ATR","ADX","OBV","OBV_Z","MFI","CMF","VOL_Z","AVWAP_YTD","AVWAP_MTD",
            "VWAP","VWAP_CUM","DONCH_H","DONCH_L","HH_HL","LH_LL","REGIME_TREND","REGIME_MEAN"]
    snap = {}
    for c in cols:
        val = df_hist[c].iloc[-1] if c in df_hist.columns and len(df_hist[c]) else np.nan
        snap[c] = None if (val is None or pd.isna(val)) else float(val)
    return snap


# =========================
# Multi-timeframe helper
# =========================
def weekly_trend_confluence(df_hist: pd.DataFrame) -> float:
    """주봉 추세와 일봉 추세의 합치도(0~1). 간단히 EMA(20) 방향성 비교."""
    try:
        w = df_hist["종가"].resample("W-FRI").last().dropna()
        if len(w) < 30 or len(df_hist) < 50:
            return 0.0
        w_ema = ta.ema(w, length=20)
        d_ema = ta.ema(df_hist["종가"], length=20)
        trend_w = float(np.sign(w_ema.iloc[-1] - w_ema.iloc[-5]))
        trend_d = float(np.sign(d_ema.iloc[-1] - d_ema.iloc[-5]))
        return 1.0 if (trend_w == trend_d and trend_w != 0) else 0.0
    except Exception:
        return 0.0


# =========================
# Chart
# =========================
def make_trade_chart(
    df: pd.DataFrame,
    xpt: pd.Timestamp,
    trade_price: float,
    action: str,
    peer_median: Optional[float] = None,
    bench_price: Optional[float] = None
) -> io.BytesIO:
    plt.figure(figsize=(14, 8))
    plt.plot(df.index, df["종가"], label="종가", color="black", linewidth=1.3)

    for key, style in [("EMA_FAST","--"),("EMA_MID",":"),("EMA_SLOW","-.")]:
        if key in df.columns: plt.plot(df.index, df[key], style, label=key)
    # 지표 라인: 이름 갱신 반영 (VWAP: 세션, VWAP_CUM: 누적)
    for key in ["BB_UPPER","BB_LOWER","KC_UPPER","KC_LOWER",
                "AVWAP_YTD","AVWAP_MTD","VWAP","VWAP_CUM","DONCH_H","DONCH_L"]:
        if key in df.columns: plt.plot(df.index, df[key], alpha=0.5, label=key)
    if "BB_UPPER" in df.columns and "BB_LOWER" in df.columns:
        plt.fill_between(df.index, df["BB_LOWER"], df["BB_UPPER"], alpha=0.08)

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
# LLM (optional)
# =========================
def build_llm_context(user: Dict[str, Any], trade: Dict[str, Any], feedback_text: str,
                      stats: Dict[str, Any], config: Dict[str, Any], selected_tone: str) -> str:
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

    safety = ("※ 유의: 본 코칭은 교육 목적이며 수익을 보장하지 않습니다. 최종 투자 결정과 책임은 사용자에게 있습니다. "
              "과도한 레버리지·집중투자를 지양하고, 손실 가능성을 충분히 고려하세요.")

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
""".strip()
    return ctx


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
# Misc utils
# =========================
def _sanitize_for_json(obj: Any) -> Any:
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
    base = max(int(ema[-1]) if ema else 200,
               int(rsi[0]) if rsi else 14,
               int(macd.get("slow", 26)),
               int(bb.get("period", 20)),
               14)
    return max(MIN_DATA_DAYS, base * 4)

# =========================
# Portfolio caps / sizing
# =========================
def cap_position_sizing(req_qty: int, symbol: str, price: float,
                        market: str, stop_dist: float, user_ctx: Dict[str, Any]) -> int:
    caps = PORT_CAPS
    equity = float(user_ctx.get("equity", ACCOUNT_SIZE))
    cash_avail = float(user_ctx.get("cash_avail", ACCOUNT_SIZE))
    ddl_today = float(user_ctx.get("ddl_today", 0.0))
    by_sym = user_ctx.get("by_symbol", {})
    by_sec = user_ctx.get("by_sector", {})
    beta_expo = float(user_ctx.get("beta_exposure", 0.0))

    # sector lookup (fallback 안전)
    sector = "OTHER"
    try:
        sm = supabase.table("sector_map").select("symbol,sector").eq("symbol", symbol).single().execute().data
        if sm and sm.get("sector"):
            sector = sm["sector"]
    except Exception:
        pass

    # Hard caps
    if ddl_today >= caps["daily_drawdown_limit"]:
        return 0
    if (by_sym.get(symbol, 0.0) / max(1.0, equity)) >= caps["symbol_cap"]:
        return 0
    if (by_sec.get(sector, 0.0) / max(1.0, equity)) >= caps["sector_cap"]:
        return 0
    if beta_expo >= caps["beta_expo_cap"]:
        return 0

    # Cash & risk caps
    allow_cash = max(0.0, cash_avail - caps["cash_buffer"] * equity)
    max_qty_cash = int(allow_cash // max(price, 1e-9))
    max_qty_risk = int(((caps["per_trade_risk"] * equity) / max(stop_dist, 1e-6)))
    return max(0, min(req_qty, max_qty_cash, max_qty_risk))


# =========================
# Main analysis & feedback
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
    trade_time_iso = str(trade["trade_time"])
    commission = float(trade.get("commission", 0) or 0.0)
    qty = float(trade.get("qty", 0) or 0.0)

    # Data window
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
        emit_metric("insufficient_bars", 1, {"symbol":symbol,"market":market})

    # Trade index (local-naive)
    trade_dt_local = parse_trade_date_for_market(trade_time_iso, market)
    df.index = pd.to_datetime(df.index).tz_localize(None)
    xpt = snap_to_index_or_next(df.index, trade_dt_local)

    # Snapshot: past-only
    df_hist = df.loc[:xpt].copy()
    stats = compute_indicators_snapshot(df_hist, cfg)

    # MTF confluence
    mtf_conf = weekly_trend_confluence(df_hist)
    stats["WEEKLY_CONFLUENCE"] = mtf_conf

    # Peer (timeboxed + time-decay + tick equality)
    peers_raw = fetch_peer_trades(symbol, market, trade_time_iso, action, user_id_exclude=user.get("id"))
    peer_prices, peer_w = user_weighted_peer_prices_timeboxed(
        peers_raw, trade_time_iso, market,
        same_session=PEER_SAME_SESSION,
        timebox_min=PEER_TIMEBOX_MIN,
        halflife_min=PEER_HALFLIFE_MIN
    )
    p50 = weighted_median(peer_prices, peer_w)
    rank_percentile = weighted_percentile_rank_by_action(action, peer_prices, peer_w, price, market=market)
    # effective sample size
    cnt = int(len(peer_prices))
    wsum = float(np.sum(peer_w)) if not peer_w.empty else 0.0
    w2sum = float(np.sum(np.square(peer_w))) if not peer_w.empty else 0.0
    n_eff = int(round((wsum**2 / w2sum))) if w2sum > 0 else 0
    stats["peer_count"] = cnt
    stats["peer_eff_count"] = n_eff

    # After window (backtest only)
    after = pd.Series(dtype="float64") if ANALYSIS_MODE == "realtime" else df.loc[xpt:].iloc[:ANALYSIS_WINDOW_DAYS]["종가"]

    # Adaptive slippage
    slip_bps = adaptive_slippage_bps(symbol, market, df_hist)

    # Fee per-share
    if qty > 0 and commission > 0:
        per_share_fee = commission / qty
    elif qty > 0:
        per_share_fee = per_order_min_fee(price * qty, market, action) / qty
    else:
        per_share_fee = 0.0

    eff_buy  = effective_unit_price(price, "buy",  market, slip_bps, per_share_fee if action=="buy" else 0.0)
    eff_sell = effective_unit_price(price, "sell", market, slip_bps, per_share_fee if action=="sell" else 0.0)

    bench_ret, bench_px = None, None
    if not after.empty:
        if action == "buy":
            bench_px = float(after.max())
            bench_ret = float(np.round((bench_px - eff_buy) / eff_buy * 100, 2))
            stats["max_profit"] = bench_ret
            stats["min_profit"] = float(np.round((float(after.min()) - eff_buy) / eff_buy * 100, 2))
        else:
            bench_px = float(after.min())
            bench_ret = float(np.round((eff_sell - bench_px) / eff_sell * 100, 2))
            stats["missed_profit"] = float(np.round((float(after.max()) - eff_sell) / eff_sell * 100, 2))
    else:
        stats["max_profit"] = None; stats["min_profit"] = None; stats["missed_profit"] = None

    # Rule-level feedback
    parts = []
    ef, em, es = stats.get("EMA_FAST"), stats.get("EMA_MID"), stats.get("EMA_SLOW")
    rsi = stats.get("RSI"); adx = stats.get("ADX")
    macd, macds = stats.get("MACD"), stats.get("MACD_SIGNAL")
    vwap = stats.get("VWAP"); vwap_cum = stats.get("VWAP_CUM")
    atr = stats.get("ATR")
    avwap_y = stats.get("AVWAP_YTD", np.nan); squeeze = stats.get("SQUEEZE", np.nan); volz = stats.get("VOL_Z", np.nan)
    donch_h, donch_l = stats.get("DONCH_H", np.nan), stats.get("DONCH_L", np.nan)
    hh_hl, lh_ll = stats.get("HH_HL", 0), stats.get("LH_LL", 0)
    regime_trend = stats.get("REGIME_TREND", 0)

    if action == "buy":
        if all(x is not None for x in [ef, em, es]) and ef > em > es: parts.append("상승 추세.")
        if adx is not None and adx >= 20: parts.append(f"추세강도(ADX={adx:.1f}) 양호.")
        if regime_trend: parts.append("레짐: 추세 우세.")
        if rsi is not None and rsi < 30: parts.append("과매도 반등 가능성.")
        if rsi is not None and rsi > 70: parts.append("과매수 위험.")
        if None not in (macd, macds) and macd > macds: parts.append("MACD 매수 신호.")
        if np.isfinite(avwap_y) and price >= avwap_y: parts.append("연초 AVWAP 이상.")
        if np.isfinite(vwap) and price < vwap: parts.append("세션 VWAP 아래 매수.")
        if np.isfinite(vwap_cum) and price < vwap_cum: parts.append("누적 VWAP 아래 매수.")
        if np.isfinite(donch_h) and price > donch_h: parts.append("Donchian 상단 돌파.")
        if int(hh_hl) == 1: parts.append("시장 구조: HH/HL (상향).")
        if np.isfinite(volz) and abs(volz) >= 2: parts.append("이례적 거래량.")
        if np.isfinite(squeeze) and squeeze < 1.0: parts.append("변동성 수축 구간.")
        mp = stats.get("max_profit")
        if mp is not None:
            if mp >= 10: parts.append(f"이후 최대 {mp}% 상승 여지.")
            if mp < 0: parts.append("매수 후 하락 위험 노출.")
    else:
        if rsi is not None and rsi > 70: parts.append("과매수 매도.")
        if adx is not None and adx >= 20 and None not in (macd, macds) and macd < macds: parts.append("MACD 매도 신호.")
        if np.isfinite(vwap) and price > vwap: parts.append("세션 VWAP 상단 매도.")
        if np.isfinite(vwap_cum) and price > vwap_cum: parts.append("누적 VWAP 상단 매도.")
        if np.isfinite(donch_l) and price < donch_l: parts.append("Donchian 하단 이탈.")
        if int(lh_ll) == 1: parts.append("시장 구조: LH/LL (하향).")
        mp = stats.get("missed_profit")
        if mp is not None:
            if mp > 5: parts.append(f"매도 후 {mp}% 추가 상승.")
            if mp < 0: parts.append("매도 후 하락 진행.")

    if p50 is not None:
        rel = ("저렴" if price <= p50 else "비싸게") if action == "buy" else ("고점" if price >= p50 else "저점")
        parts.append(f"Peer중앙({p50:.2f}) 대비 {rel}.")
        if rank_percentile is not None:
            rp = int(round(rank_percentile))
            parts.append(f"피어 가중치 기준 유효표본 ~{n_eff}명, 약 ~{rp} 퍼센타일.")
    else:
        parts.append(f"피어 표본 부족(원시 {cnt}명, 유효 {n_eff}명)으로 신뢰도 제한.")

    if bench_ret is not None:
        parts.append(("최적 시나리오(비용 반영): " if action=="buy" else "최적 방어(비용 반영): ") + f"{bench_ret}%")

    if commission > 0:
        parts.append(f"수수료 {int(commission)}원 반영.")

    # Risk coaching: stops, TP, trailing
    stop_dist = (atr or 0.0) * STOP_ATR_MULT if atr is not None else 0.0
    if not np.isfinite(stop_dist) or stop_dist <= 0:
        stop_dist = max(price * 0.005, 1e-3)

    stop_raw = price - stop_dist if action == "buy" else price + stop_dist
    tp1_raw  = price + (atr or 0.0) * TP1_ATR_MULT if action == "buy" else price - (atr or 0.0) * TP1_ATR_MULT
    stop = round_to_tick(stop_raw, market)
    tp1  = round_to_tick(tp1_raw, market)
    tp2  = round_to_tick(price + (tp1_raw - price)*2.0 if action=="buy" else price - (price - tp1_raw)*2.0, market)
    tp3  = round_to_tick(price + (tp1_raw - price)*3.0 if action=="buy" else price - (price - tp1_raw)*3.0, market)

    risk_cash = ACCOUNT_SIZE * ACCOUNT_RISK
    denom = max(abs(price - stop), 1e-6)
    size_by_risk = int(max(risk_cash // denom, 0))
    size_by_cash = int(max(ACCOUNT_SIZE // max(price, 1e-9), 0))
    base_size = max(1, min(size_by_risk, size_by_cash))

    # Portfolio caps
    user_ctx = fetch_positions_and_meta(user.get("id"))
    size_capped = cap_position_sizing(base_size, symbol, price, market, abs(price - stop), user_ctx)

    parts.append(
        f"손절 {round(stop,3)}, 익절 1R {round(tp1,3)} / 2R {round(tp2,3)} / 3R {round(tp3,3)}, "
        f"권장수량 {size_capped} (캡 전 {base_size})."
    )

    # Signal quality score (0~1)
    quality = 0.0
    quality += min(1.0, n_eff / max(1.0, PEER_MIN_SAMPLES)) * 0.2      # peer effective sample
    quality += (1.0 if regime_trend else 0.5) * 0.2                    # regime
    quality += mtf_conf * 0.2                                          # MTF confluence
    quality += (min(1.0, max(0.0, abs(volz or 0.0) / 2.0))) * 0.2      # volume confirmation
    q_struct = 0.1 if (hh_hl and action=="buy") or (lh_ll and action=="sell") else 0.0
    q_donch  = 0.1 if (np.isfinite(donch_h) and price>donch_h and action=="buy") or \
                        (np.isfinite(donch_l) and price<donch_l and action=="sell") else 0.0
    quality += (q_struct + q_donch)
    quality = max(0.0, min(1.0, quality))
    parts.append(f"신호 품질 스코어: {round(quality,2)}")

    feedback_text = " ".join([p for p in parts if p]).strip()

    # Chart upload
    chart_url = None
    try:
        # merge hist indicators for plotting continuity
        for col in ["EMA_FAST","EMA_MID","EMA_SLOW","BB_UPPER","BB_LOWER","KC_UPPER","KC_LOWER",
                    "AVWAP_YTD","AVWAP_MTD","VWAP","VWAP_CUM","DONCH_H","DONCH_L"]:
            if col in df_hist.columns:
                df[col] = df_hist[col]
        buf = make_trade_chart(df, xpt, price, action, peer_median=p50, bench_price=bench_px)
        filename = f"{trade['id']}.png"
        try:
            supabase.storage.from_(STORAGE_BUCKET_NAME).upload(
                filename, buf.getvalue(), file_options={"content-type": "image/png", "upsert": "true"}
            )
        except Exception:
            try:
                supabase.storage.from_(STORAGE_BUCKET_NAME).upload(
                    filename, buf.getvalue(), {"content-type": "image/png", "upsert": True}
                )
            except Exception:
                supabase.storage.from_(STORAGE_BUCKET_NAME).upload(
                    filename, buf.getvalue(), {"contentType": "image/png", "upsert": True}
                )
        url_info = supabase.storage.from_(STORAGE_BUCKET_NAME).get_public_url(filename)
        chart_url = url_info.get("publicUrl") if isinstance(url_info, dict) else url_info
    except Exception as e:
        logger.warning(f"chart upload failed: {e}")
        chart_url = None

    # Style label (example)
    style_type = "중립"
    if stats.get("max_profit", 0) and (stats.get("max_profit", 0) > 10) and (rsi is not None and rsi < 30):
        style_type = "단타추세"
    elif stats.get("max_profit", 0) is not None and stats.get("max_profit", 0) < 0 and (rsi is not None and rsi > 70):
        style_type = "고점방어"

    # LLM coaching
    _use_llm = bool(use_llm or LLM_ENABLED_DEFAULT)
    ai_msg = None
    if _use_llm:
        try:
            ctx = build_llm_context(user, trade, feedback_text, stats, cfg, selected_tone)
            ai_msg = ai_commentary(ctx)
        except Exception as e:
            logger.warning(f"LLM commentary error: {e}")
            ai_msg = None

    # metrics
    emit_metric("slippage_bps_est", slip_bps, {"symbol":symbol,"market":market})
    emit_metric("signal_quality", quality, {"symbol":symbol,"market":market})

    # include quality & peers in stats
    stats["signal_quality"] = float(quality)
    stats["peer_median"] = None if p50 is None else float(p50)
    stats["peer_rank_percentile"] = None if rank_percentile is None else float(rank_percentile)

    return feedback_text, chart_url, stats, style_type, rank_percentile, bench_ret, ai_msg


# =========================
# Endpoint wrapper (+ DLQ) — returns (fb, img, ai, stats)
# =========================
def auto_trade_feedback(
    trade_id: int,
    user_id: str,
    selected_tone: str = "friendly",
    use_llm: bool = False
) -> Tuple[str, Optional[str], Optional[str], Dict[str, Any]]:
    trade = fetch_trade(trade_id)
    if not trade:
        raise ValueError("trade not found")
    user = fetch_and_normalize_user(user_id)
    if not user:
        raise ValueError("user not found")

    m = (trade.get("market") or "").upper()
    if m in ["KRX", "KOSPI", "KOSDAQ"]:
        trade["market"] = "KR"
    elif m in ["NASDAQ", "NYSE", "AMEX", "US"]:
        trade["market"] = "US"
    else:
        trade["market"] = m

    logger.info("==== 입력값 확인 ====")
    logger.info(f"version: {VERSION}")
    logger.info(f"trade_id: {trade_id} user_id: {user_id}")
    logger.info(
        f"trade(m): {{'id': {trade.get('id')}, 'symbol': {trade.get('symbol')}, 'market': {trade.get('market')}, "
        f"'action': {trade.get('action')}, 'price': {trade.get('price')}, 'qty': {trade.get('qty')}, "
        f"'commission': {trade.get('commission')}, 'trade_time': {trade.get('trade_time')}}}"
    )
    logger.info(f"user: {_mask_user(user)}")

    fb, img, stats, stype, r, bench, ai = analyze_and_feedback(
        trade, user, service_config, selected_tone, use_llm
    )

    clean_stats = _sanitize_for_json(stats)
    rank_repr = None if r is None else f"~{int(round(r))}퍼센타일"
    payload = {
        "user_id": user_id, "trade_id": trade_id,
        "feedback_message": fb, "chart_url": img, "summary_stats": clean_stats,
        "style_type": stype, "rank_percentile": rank_repr, "benchmark_return": bench,
        "ai_coaching": ai, "selected_tone": selected_tone, "created_at": dt.datetime.now().isoformat()
    }

    try:
        supabase.table("trade_feedback").upsert(payload, on_conflict="trade_id").execute()
    except Exception as e:
        logger.warning(f"feedback upsert failed, fallback to insert: {e}")
        try:
            supabase.table("trade_feedback").insert(payload).execute()
        except Exception as e2:
            logger.error(f"feedback insert failed: {e2}")
            # Dead-letter queue
            try:
                supabase.table("feedback_dead_letter").insert({
                    "trade_id": trade_id, "user_id": user_id, "payload": payload, "error": str(e2),
                    "created_at": dt.datetime.now().isoformat()
                }).execute()
                logger.error("DLQ insert success.")
            except Exception as e3:
                logger.error(f"DLQ insert failed: {e3}")

    # Expanded return: (feedback, chart_url, ai_coaching, stats)
    return fb, img, ai, clean_stats


# =========== 사용 예 (로컬 테스트) ===========
# if __name__ == "__main__":
#     fb, url, coach, stats = auto_trade_feedback(101, "abcd1234", selected_tone="expert", use_llm=True)
#     print(fb, url, coach, json.dumps(stats, ensure_ascii=False, indent=2), sep="\n\n")
