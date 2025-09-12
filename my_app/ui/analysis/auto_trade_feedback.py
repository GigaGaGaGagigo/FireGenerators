# -*- coding: utf-8 -*-
"""
Auto Trade Feedback — PRO++ (Expert-Grade FINAL, Fix-Before-Use applied)
- Snapshot-safe indicators (no leakage), strict rolling(min_periods), ddof=0
- Data layer: KR(pykrx→FDR fallback), US(yfinance→Stooq fallback), minute-data hook (optional)
- VWAP policy: true session VWAP only with intraday source; otherwise hidden (no pseudo)
- Cost/Tax/FX externalized: (market × broker × account_type) tables; trade-date FX snapshot
- Slippage model: per-(market|symbol) calibrated params from DB; robust fallback
- Peer engine: same-session + ±timebox + half-life + tick-equality + robust outlier filter(IQR/MAD)
  + peer quality weighting (winrate/Sharpe from peer_stats) + reliability flags
- Backtest engine: rule-based stop/TP simulation (gap-aware next-bar execution; fees/slippage)
- Risk: ATR-based stops, 1R/2R/3R, hard portfolio caps (per-symbol/sector/beta/DDL), KR int shares; US fractional opt-in
- Observability: structured logs, metrics stubs, DLQ table on write failure
- LLM coaching (optional) with strict, quantified context block + disclaimer
- Supabase storage upload (public URL) + upsert-safe feedback write
- Backward-compat return: (feedback, chart_url, ai_text, stats)

Note:
- Optional deps are guarded (pandas_market_calendars, FinanceDataReader, pandas_datareader, pydantic)
- Minute data provider is a hook; disabled by default
"""

from __future__ import annotations

import os
from pathlib import Path
import io
import json
import datetime as dt
from functools import lru_cache
from typing import Dict, Any, Tuple, Optional, List

import math
import time
import logging

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

try:
    import pandas_ta as ta            # 공식 패키지(파이썬 3.12+)
except ModuleNotFoundError:
    import pandas_ta_classic as ta    # 포크(파이썬 3.10/3.11 호환)

from dotenv import load_dotenv

from supabase import create_client
from pykrx import stock
import yfinance as yf

# ---------- Optional deps ----------
try:
    import pandas_market_calendars as mcal  # business sessions, half-days
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
    from pydantic import BaseModel, Field, ValidationError  # config schema
except Exception:
    BaseModel = None
    Field = None
    ValidationError = Exception

try:
     # OpenAI SDK (optional)
     from openai import OpenAI
except Exception:
     OpenAI = None
# -----------------------------------

try:
    from zoneinfo import ZoneInfo  # py>=3.9
except Exception:
    ZoneInfo = None


# =========================================================
# Logging & environment
# =========================================================
load_dotenv()

logger = logging.getLogger("auto_trade_feedback_pro")
_stream = logging.StreamHandler()
_stream.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s"))
logger.addHandler(_stream)
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

# =========================================================
# Config schema (pydantic if available) — expert-grade knobs
# =========================================================
if BaseModel:
    class IntradayCfg(BaseModel):
        enabled: bool = False
        provider: str = "none"         # e.g., "alpaca|polygon|ibkr|kite|none"
        tz_policy: str = "exchange"    # "exchange"|"local"

    class CostRow(BaseModel):
        market: str = Field(..., pattern="^(KR|US)$")
        broker: str = "generic"
        account_type: str = "cash"     # "cash"|"margin"|"retirement"|...
        fee_buy: float = 0.0
        fee_sell: float = 0.0
        tax_sell: float = 0.0
        min_fee: float = 0.0
        currency: str = "KRW"          # currency of commissions/taxes

    class ExecCfg(BaseModel):
        slippage_bps_default: float = 5.0
        account_risk_per_trade: float = 0.01
        account_size: float = 10_000_000
        stop_atr_mult: float = 1.2
        tp1_atr_mult: float = 2.0
        allow_fractional: Dict[str, bool] = {"KR": False, "US": True}
        kr_tick_table: Optional[List[List[float]]] = None  # [[lo,hi,step], ...]
        static_cost_table: List[CostRow] = []

    class FeedbackCfg(BaseModel):
        analysis_mode: str = "backtest"  # or "realtime"
        peer_group_size: int = 120
        min_data_period_days: int = 60
        analysis_window_days: int = 7
        peer_min_samples: int = 60
        peer_window_days: int = 3
        peer_same_session: bool = True
        peer_timebox_minutes: int = 60
        peer_halflife_minutes: int = 60
        outlier_filter: str = "iqr"      # "iqr"|"mad"|"none"
        outlier_k: float = 1.5
        min_effective_peers: int = 25

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
        model: str = "gpt-5"

    class PortfolioCaps(BaseModel):
        per_trade_risk: float = 0.0025
        daily_drawdown_limit: float = 0.005
        symbol_cap: float = 0.05
        sector_cap: float = 0.20
        beta_expo_cap: float = 0.50
        cash_buffer: float = 0.02

    class ServiceConfig(BaseModel):
        version: str = "unknown"
        intraday: IntradayCfg = IntradayCfg()
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
        logger.warning(f"[CFG] validation failed; use raw config. Detail: {ve}")
        service_config = _raw_cfg
else:
    service_config = _raw_cfg

# ---- Bind config values ----
VERSION = service_config.get("version", "unknown")

INTRADAY = service_config.get("intraday", {"enabled": False, "provider": "none", "tz_policy": "exchange"})

FEEDBACK = service_config.get("feedback_policy", {})
ANALYSIS_MODE: str = FEEDBACK.get("analysis_mode", "backtest")
PEER_GROUP_SIZE: int = int(FEEDBACK.get("peer_group_size", 120))
MIN_DATA_DAYS: int = int(FEEDBACK.get("min_data_period_days", 60))
ANALYSIS_WINDOW_DAYS: int = int(FEEDBACK.get("analysis_window_days", 7))
PEER_MIN_SAMPLES: int = int(FEEDBACK.get("peer_min_samples", 60))
PEER_WINDOW_DAYS: int = int(FEEDBACK.get("peer_window_days", 3))
PEER_SAME_SESSION: bool = bool(FEEDBACK.get("peer_same_session", True))
PEER_TIMEBOX_MIN: int = int(FEEDBACK.get("peer_timebox_minutes", 60))
PEER_HALFLIFE_MIN: int = int(FEEDBACK.get("peer_halflife_minutes", 60))
OUTLIER_FILTER: str = FEEDBACK.get("outlier_filter", "iqr").lower()
OUTLIER_K: float = float(FEEDBACK.get("outlier_k", 1.5))
MIN_EFFECTIVE_PEERS: int = int(FEEDBACK.get("min_effective_peers", 25))

EXEC_CFG = service_config.get("execution", {})
SLIPPAGE_BPS_DEFAULT: float = float(EXEC_CFG.get("slippage_bps_default", 5))
ACCOUNT_RISK: float = float(EXEC_CFG.get("account_risk_per_trade", 0.01))
ACCOUNT_SIZE: float = float(EXEC_CFG.get("account_size", 10_000_000))
STOP_ATR_MULT: float = float(EXEC_CFG.get("stop_atr_mult", 1.2))
TP1_ATR_MULT: float = float(EXEC_CFG.get("tp1_atr_mult", 2.0))
ALLOW_FRACTIONAL: Dict[str, bool] = EXEC_CFG.get("allow_fractional", {"KR": False, "US": True})
KR_TICK_TABLE = EXEC_CFG.get("kr_tick_table", None)
STATIC_COST_TABLE = EXEC_CFG.get("static_cost_table", [])

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
LLM_MODEL_NAME: str = LLM_CFG.get("model", "gpt-5")

PORT_CAPS = service_config.get("portfolio_caps", {
    "per_trade_risk": 0.0025,
    "daily_drawdown_limit": 0.005,
    "symbol_cap": 0.05,
    "sector_cap": 0.20,
    "beta_expo_cap": 0.50,
    "cash_buffer": 0.02
})

# =========================================================
# Supabase init
# =========================================================
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_ANON_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Supabase URL/KEY가 설정되지 않았습니다. (SUPABASE_URL, SUPABASE_KEY|SUPABASE_ANON_KEY)")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
STORAGE_BUCKET_NAME = os.environ.get("CHARTS_BUCKET", "charts")
np.seterr(all="ignore")

# =========================================================
# Observability helpers
# =========================================================
def emit_metric(name: str, value: float, labels: Optional[Dict[str, str]] = None):
    """Stub for metrics export; replace with Prometheus/OTel as needed."""
    try:
        labels = labels or {}
        logger.info(f"[metric] {name}={value} | {labels}")
    except Exception:
        pass

# =========================================================
# Market / TZ / Calendar
# =========================================================
def market_tz(market: str) -> str:
    m = (market or "").upper()
    if m == "KR": return "Asia/Seoul"
    return "America/New_York"

def _calendar_code(market: str) -> Optional[str]:
    if (mcal is None) or (not USE_MCAL): return None
    return EXCHANGE_CODES.get((market or "").upper(), None)

def _tz_localize(ts: pd.Timestamp, tzname: str) -> pd.Timestamp:
    tz = ZoneInfo(tzname) if ZoneInfo else None
    if tz is None: return ts
    return ts.tz_convert(tz) if ts.tzinfo else ts.tz_localize(tz)

def snap_to_session_close(ts_local: pd.Timestamp, market: str) -> Optional[pd.Timestamp]:
    """
    Returns session close time (naive, local) if ts_local is within a session; else None.
    Handles half-days via mcal schedule.
    """
    code = _calendar_code(market)
    if not code: return None
    try:
        cal = mcal.get_calendar(code)
        sched = cal.schedule(
            start_date=ts_local.date() - dt.timedelta(days=60),
            end_date=ts_local.date() + dt.timedelta(days=60),
        ).copy()
        local_tz = ts_local.tz
        open_local = sched["market_open"].dt.tz_convert(local_tz)
        close_local = sched["market_close"].dt.tz_convert(local_tz)
        in_sess = (open_local <= ts_local) & (ts_local <= close_local)
        if in_sess.any():
            close_l = close_local.loc[in_sess].iloc[0]
            return close_l.tz_localize(None)
        return None
    except Exception as e:
        logger.debug(f"snap_to_session_close failed: {e}")
        return None

def parse_trade_date_for_market(trade_time_iso: str, market: str) -> pd.Timestamp:
    """Convert to local exchange tz and return session close (if in-session) else local midnight (naive)."""
    tz = ZoneInfo(market_tz(market)) if ZoneInfo else None
    ts = pd.to_datetime(trade_time_iso)
    ts_local = ts.tz_convert(tz) if (tz and ts.tzinfo) else (ts.tz_localize(tz) if tz else ts)
    close_ts = snap_to_session_close(ts_local, market)
    if close_ts is not None:
        return close_ts
    return ts_local.normalize().tz_localize(None) if ts_local.tzinfo else pd.to_datetime(str(ts_local.date()))

def business_window_utc(trade_time_iso: str, market: str, n_days: int) -> Optional[Tuple[str, str]]:
    """Return (open_utc, close_utc) spanning ±n business days around trade date."""
    code = _calendar_code(market)
    if not code: return None
    try:
        tz = ZoneInfo(market_tz(market)) if ZoneInfo else None
        cal = mcal.get_calendar(code)
        ts = pd.to_datetime(trade_time_iso)
        ts_local = ts.tz_convert(tz) if (tz and ts.tzinfo) else (ts.tz_localize(tz) if tz else ts)
        sched = cal.schedule(
            start_date=ts_local.date() - dt.timedelta(days=120),
            end_date=ts_local.date() + dt.timedelta(days=120)
        ).sort_index()
        mask = (sched["market_open"].dt.tz_convert(ts_local.tz) <= ts_local) & \
               (ts_local <= sched["market_close"].dt.tz_convert(ts_local.tz))
        if mask.any():
            idx = sched.index.get_loc(sched.index[mask][0])
        else:
            idx = sched.index.get_indexer([ts_local.date()], method="backfill")[0]
            if idx < 0: idx = 0
        lo = max(0, idx - n_days)
        hi = min(len(sched) - 1, idx + n_days)
        start_utc = sched["market_open"].iloc[lo].tz_convert("UTC").isoformat()
        end_utc   = sched["market_close"].iloc[hi].tz_convert("UTC").isoformat()
        return start_utc, end_utc
    except Exception as e:
        logger.debug(f"business_window_utc failed: {e}")
        return None

def snap_to_index_or_next(idx: pd.DatetimeIndex, t: pd.Timestamp) -> pd.Timestamp:
    if t in idx: return t
    m = idx >= t
    return idx[m][0] if m.any() else idx[-1]

def snap_to_index_or_prev(idx: pd.DatetimeIndex, t: pd.Timestamp) -> pd.Timestamp:
    """가장 가까운 과거(<=t) 인덱스 반환; 없으면 첫 인덱스."""
    if t in idx: return t
    m = idx <= t
    return idx[m][-1] if m.any() else idx[0]

def event_cutoff_for_daily(trade_time_iso: str, market: str) -> pd.Timestamp:
    """
    장중 체결이면 '직전 거래일 종가'를 컷오프로 사용해 스냅샷 누수 차단.
    장마감 이후 체결(또는 장외/야간 기록)이면 해당 '당일 종가'까지 허용.
    mcal 없을 때는 보수적으로 '전일'로 처리.
    """
    tz = ZoneInfo(market_tz(market)) if ZoneInfo else None
    ts = pd.to_datetime(trade_time_iso)
    ts_local = ts.tz_convert(tz) if (tz and ts.tzinfo) else (ts.tz_localize(tz) if tz else ts)
    code = _calendar_code(market)
    if not code:
        return (ts_local.normalize() - pd.Timedelta(days=1)).tz_localize(None) if ts_local.tzinfo else (pd.to_datetime(ts_local.date()) - pd.Timedelta(days=1))
    try:
        cal = mcal.get_calendar(code)
        sched = cal.schedule(
            start_date=ts_local.date() - dt.timedelta(days=120),
            end_date=ts_local.date() + dt.timedelta(days=120)
        ).copy()
        cl = sched["market_close"].dt.tz_convert(ts_local.tz)
        before = cl[cl < ts_local]
        if len(before):
            cutoff = before.iloc[-1]
        else:
            cutoff = cl.iloc[0]
        return cutoff.tz_localize(None)
    except Exception:
        return (ts_local.normalize() - pd.Timedelta(days=1)).tz_localize(None) if ts_local.tzinfo else (pd.to_datetime(ts_local.date()) - pd.Timedelta(days=1))

# =========================================================
# Tables: Cost/Tax, FX rate, Slippage params (DB-first)
# =========================================================
def _cost_row_from_static(market: str, broker: str, account_type: str) -> Optional[Dict[str, Any]]:
    # fallback to static cost table from config if DB missing
    for r in STATIC_COST_TABLE:
        try:
            if (r.get("market") == market and
                r.get("broker", "generic") == broker and
                r.get("account_type", "cash") == account_type):
                return r
        except Exception:
            continue
    return None

def fetch_cost_model(market: str, broker: str = "generic", account_type: str = "cash") -> Dict[str, float]:
    """
    Loads fees/taxes/min_fee for (market, broker, account_type) from DB table 'cost_model'.
    Columns expected: market, broker, account_type, fee_buy, fee_sell, tax_sell, min_fee, currency
    Fallback to STATIC_COST_TABLE, else zeros.
    """
    try:
        res = (supabase.table("cost_model")
               .select("*")
               .eq("market", market)
               .eq("broker", broker)
               .eq("account_type", account_type)
               .single()
               .execute())
        row = res.data
        if row:
            return {
                "fee_buy": float(row.get("fee_buy", 0.0)),
                "fee_sell": float(row.get("fee_sell", 0.0)),
                "tax_sell": float(row.get("tax_sell", 0.0)),
                "min_fee": float(row.get("min_fee", 0.0)),
                "currency": (row.get("currency") or ("KRW" if market=="KR" else "USD"))
            }
    except Exception:
        pass
    st = _cost_row_from_static(market, broker, account_type) or {}
    return {
        "fee_buy": float(st.get("fee_buy", 0.0)),
        "fee_sell": float(st.get("fee_sell", 0.0)),
        "tax_sell": float(st.get("tax_sell", 0.0)),
        "min_fee": float(st.get("min_fee", 0.0)),
        "currency": st.get("currency", ("KRW" if market=="KR" else "USD"))
    }

def fetch_fx_rate(base_ccy: str, quote_ccy: str, trade_date: dt.date) -> float:
    """
    Fetches FX rate base/quote at (or nearest before) trade_date from 'fx_rates' table.
    Columns: base, quote, date(YYYY-MM-DD), rate
    Fallbacks:
      - identity if base==quote
      - last known rate before trade_date
      - else 1.0 with reliability flag (tracked in stats later)
    """
    if base_ccy == quote_ccy:
        return 1.0
    try:
        res = (supabase.table("fx_rates")
               .select("rate,date")
               .eq("base", base_ccy)
               .eq("quote", quote_ccy)
               .lte("date", trade_date.isoformat())
               .order("date", desc=True)
               .limit(1)
               .execute())
        if res.data:
            return float(res.data[0].get("rate", 1.0))
        # fallback: allow future date within small buffer if needed
        res2 = (supabase.table("fx_rates")
                .select("rate,date")
                .eq("base", base_ccy)
                .eq("quote", quote_ccy)
                .order("date", asc=True)
                .limit(1)
                .execute())
        if res2.data:
            return float(res2.data[0].get("rate", 1.0))
    except Exception:
        pass
    return 1.0  # will mark low_reliability later

def fetch_slippage_params(symbol: Optional[str], market: str) -> Dict[str, float]:
    """
    Loads slippage regression-like params from 'slippage_params'.
    Columns: symbol (nullable), market, a, b, c, d, updated_at
    Priority: (symbol,market) -> (NULL,market) -> defaults
    """
    try:
        if symbol:
            res = (supabase.table("slippage_params")
                   .select("a,b,c,d")
                   .eq("market", market)
                   .eq("symbol", symbol)
                   .single()
                   .execute())
            if res.data:
                r = res.data
                return {"a": float(r["a"]), "b": float(r["b"]), "c": float(r["c"]), "d": float(r["d"])}
        res2 = (supabase.table("slippage_params")
                .select("a,b,c,d")
                .eq("market", market)
                .is_("symbol", None)
                .single()
                .execute())
        if res2.data:
            r = res2.data
            return {"a": float(r["a"]), "b": float(r["b"]), "c": float(r["c"]), "d": float(r["d"])}
    except Exception:
        pass
    return {"a": SLIPPAGE_BPS_DEFAULT, "b": 0.0, "c": 0.0, "d": 0.0}

# =========================================================
# Tick rules & rounding
# =========================================================
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
    if not np.isfinite(px): return px
    t = tick_size_kr(px) if (market or "").upper() == "KR" else tick_size_us(px)
    return round(px / t) * t

def round_to_tick_side(px: float, market: str, side: str, level: str) -> float:
    """
    side: 'buy'|'sell', level: 'entry'|'stop'|'tp'
    매수는 유리하게 위/아래 반올림이 다름. (손절·익절 방향성 반영)
    """
    if not np.isfinite(px): return px
    t = tick_size_kr(px) if (market or "").upper() == "KR" else tick_size_us(px)
    q = px / t
    if side == "buy":
        if level == "entry": q = math.ceil(q)
        elif level == "stop": q = math.floor(q)
        else: q = math.ceil(q)  # tp
    else:
        if level == "entry": q = math.floor(q)
        elif level == "stop": q = math.ceil(q)
        else: q = math.floor(q)  # tp
    return q * t

def _tick_equalize(series: pd.Series, market: str) -> pd.Series:
    if series is None or len(series) == 0: return series
    return series.apply(lambda v: round_to_tick(float(v), market) if np.isfinite(v) else v)

# =========================================================
# JSON/PII utilities
# =========================================================
def _sanitize_for_json(obj: Any) -> Any:
    import numpy as np
    import pandas as pd
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        x = float(obj)
        if math.isnan(x) or math.isinf(x): return None
        return x
    if isinstance(obj, (pd.Timestamp, dt.datetime)):
        # ISO 문자열로
        return pd.Timestamp(obj).to_pydatetime().isoformat()
    if isinstance(obj, (pd.Timedelta,)):
        return obj.total_seconds()
    if isinstance(obj, dict):
        return {str(k): _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_sanitize_for_json(v) for v in obj]
    # NaN/Inf 처리
    try:
        if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
            return None
    except Exception:
        pass
    return obj

def _mask_user(u: Dict[str, Any]) -> Dict[str, Any]:
    if not u: return u
    v = dict(u)
    if "email" in v and isinstance(v["email"], str):
        parts = v["email"].split("@")
        v["email"] = (parts[0][:2] + "***@" + parts[1]) if len(parts) == 2 else "***"
    keys = ["id", "investor_level", "preferred_tone", "risk_profile", "last_emotion"]
    return {k: v.get(k) for k in keys}

# =========================================================
# Required lookback estimation (no leakage)
# =========================================================
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

# =========================================================
# Data layer (daily + intraday hook) & harmonize
# =========================================================
def _normalize_index(df: pd.DataFrame) -> pd.DataFrame:
    """
    Robust index normalization:
    - ensure DatetimeIndex
    - drop timezone (tz-naive)
    - normalize to midnight (for daily series)
    """
    if df is None or df.empty:
        return pd.DataFrame()
    idx = pd.to_datetime(df.index)
    try:
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
    """
    Harmonize to columns: ['종가','고가','저가','거래량']
    Accepts various vendor column names (case-insensitive).
    """
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    df = _normalize_index(df)

    cols_map = {c.lower(): c for c in df.columns}

    def _pick(*names) -> Optional[pd.Series]:
        for n in names:
            key = n.lower()
            if key in cols_map:
                return pd.to_numeric(df[cols_map[key]], errors="coerce")
        return None

    base_index = df.index

    def _series_or_nan(s: Optional[pd.Series]) -> pd.Series:
        if s is None:
            return pd.Series(np.nan, index=base_index)
        return s

    open_ = _series_or_nan(_pick("open", "시가"))
    close = _series_or_nan(_pick("close", "adj close", "adjclose", "종가"))
    high  = _series_or_nan(_pick("high", "고가"))
    low   = _series_or_nan(_pick("low", "저가"))
    vol   = _series_or_nan(_pick("volume", "거래량")).fillna(0.0)

    out = pd.DataFrame(index=base_index)
    out["시가"]   = open_
    out["종가"]   = close
    out["고가"]   = high
    out["저가"]   = low
    out["거래량"] = vol

    for c in ["시가","종가","고가","저가","거래량"]:
        out[c] = pd.to_numeric(out[c], errors="coerce").astype("float64")

    out = out.dropna(subset=["종가","고가","저가"])

    return out

def _kr_primary(symbol: str, start: str, end: str) -> pd.DataFrame:
    """
    Primary KR daily source: pykrx
    """
    try:
        df = stock.get_market_ohlcv_by_date(start, end, symbol)
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.rename(columns={
             "시가":"Open", "종가":"Close","고가":"High","저가":"Low","거래량":"Volume"
         })
        return _harmonize(df)
    except Exception:
        return pd.DataFrame()

def _kr_secondary(symbol: str, start: str, end: str) -> pd.DataFrame:
    """
    Secondary KR daily source: FinanceDataReader (if available)
    """
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
    """
    Primary US daily source: yfinance (auto_adjust=True)
    """
    try:
        df = yf.download(symbol, start=start, end=end, progress=False, auto_adjust=True)
        return _harmonize(df)
    except Exception:
        return pd.DataFrame()

def _us_secondary(symbol: str, start: str, end: str) -> pd.DataFrame:
    """
    Secondary US daily source: Stooq via pandas_datareader (if available)
    """
    if pdr is None:
        return pd.DataFrame()
    try:
        df = pdr.DataReader(symbol, "stooq", start=start, end=end).sort_index()
        return _harmonize(df)
    except Exception:
        return pd.DataFrame()

@lru_cache(maxsize=256)
def get_stock_price_cached(symbol: str, market: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    Daily price loader with KR/US primary/secondary fallbacks.
    """
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
    """
    Public wrapper returning a copy (to avoid mutability surprises).
    """
    return get_stock_price_cached(symbol, market, str(start), str(end)).copy()

# ------------------ Intraday hook (optional) ------------------
def get_intraday_prices(symbol: str, market: str, start_dt: pd.Timestamp, end_dt: pd.Timestamp) -> pd.DataFrame:
    """
    Intraday (minute) data hook.
    Contract:
      - returns tz-naive DatetimeIndex at minute granularity
      - columns: ['종가','고가','저가','거래량']
    Implementation is provider-specific and intentionally left as a stub.
    """
    cfg = INTRADAY or {}
    if not cfg.get("enabled", False) or cfg.get("provider", "none") == "none":
        return pd.DataFrame()  # disabled
    # TODO: implement specific providers (alpaca/polygon/ibkr/etc.)
    logger.info(f"[INTRADAY] provider '{cfg.get('provider')}' not implemented; fallback to daily-only.")
    return pd.DataFrame()

def _session_vwap_from_intraday(df_min: pd.DataFrame) -> pd.Series:
    """
    Build per-day session VWAP from minute bars:
    VWAP_day_close = sum(TP*V)/sum(V) over each trading day, reported as a daily series.
    """
    if df_min is None or df_min.empty:
        return pd.Series(dtype="float64")
    # Ensure minute index (tz-naive); group by date
    idx = pd.to_datetime(df_min.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    dfm = df_min.copy()
    dfm.index = idx
    tp = (dfm["고가"] + dfm["저가"] + dfm["종가"]) / 3.0
    grp = dfm.index.normalize()
    pv = (tp * dfm["거래량"]).groupby(grp).sum()
    vv = dfm["거래량"].groupby(grp).sum().replace(0, np.nan)
    vwap_daily = (pv / vv).astype("float64")
    vwap_daily.name = "VWAP"
    return vwap_daily

# =========================================================
# Indicators (snapshot, no leakage) with true session VWAP policy
# =========================================================
def compute_indicators_snapshot(
    df_hist: pd.DataFrame,
    cfg: Dict[str, Any],
    intraday_vwap_daily: Optional[pd.Series] = None
) -> Tuple[Dict[str, Optional[float]], pd.DataFrame]:
    """
    df_hist: daily data up to (and including) event date.
    intraday_vwap_daily: if provided, true per-day session VWAP (end-of-day).
      - If None/empty: 'VWAP' (session VWAP) will be omitted (NaN), not pseudo-estimated.
    Returns:
      snap: dict of last-bar indicator values (NaN->None sanitized)
      df_enriched: df_hist with indicator columns attached
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

    df = df_hist.copy()
    df.ffill(inplace=True)

    # EMA / RSI
    df["EMA_FAST"] = _as_float_series(ta.ema(df["종가"], length=ema_fast), df.index)
    df["EMA_MID"]  = _as_float_series(ta.ema(df["종가"], length=ema_mid),  df.index)
    df["EMA_SLOW"] = _as_float_series(ta.ema(df["종가"], length=ema_slow), df.index)
    df["RSI"]      = _as_float_series(ta.rsi(df["종가"], length=rsi_len),   df.index)

    # MACD (+ histogram)
    macd = ta.macd(df["종가"], fast=macd_cfg["fast"], slow=macd_cfg["slow"], signal=macd_cfg["signal"])
    if macd is None:
        df["MACD"] = df["MACD_SIGNAL"] = df["MACD_HIST"] = pd.Series(np.nan, index=df.index, dtype="float64")
    else:
        base = f"{macd_cfg['fast']}_{macd_cfg['slow']}_{macd_cfg['signal']}"
        df["MACD"]        = _as_float_series(macd.get(f"MACD_{base}"),  df.index)
        df["MACD_SIGNAL"] = _as_float_series(macd.get(f"MACDs_{base}"), df.index)
        df["MACD_HIST"]   = _as_float_series(macd.get(f"MACDh_{base}"), df.index)

    # STOCH
    stoch = ta.stoch(df["고가"], df["저가"], df["종가"], k=stoch_cfg["k"], d=stoch_cfg["d"], smooth_k=stoch_cfg["smooth"])
    if stoch is None:
        df["STOCH_K"] = pd.Series(np.nan, index=df.index, dtype="float64")
        df["STOCH_D"] = pd.Series(np.nan, index=df.index, dtype="float64")
    else:
        k_key = f"STOCHk_{stoch_cfg['k']}_{stoch_cfg['d']}_{stoch_cfg['smooth']}"
        d_key = f"STOCHd_{stoch_cfg['k']}_{stoch_cfg['d']}_{stoch_cfg['smooth']}"
        df["STOCH_K"] = _as_float_series(stoch.get(k_key), df.index)
        df["STOCH_D"] = _as_float_series(stoch.get(d_key), df.index)

    # === BBANDS (EWMA volatility, center=Close) ===
    ewvar = df["종가"].pct_change().ewm(alpha=1 - EWMA_LAM, min_periods=bb_cfg["period"]).var()
    sigma_price = (np.sqrt(ewvar) * df["종가"]).rename("SIGMA_PRICE")
    k = float(bb_cfg.get("stddev", 2.0))
    center = df["종가"]
    df["BB_UPPER"] = _as_float_series(center + k * sigma_price, df.index)
    df["BB_LOWER"] = _as_float_series(center - k * sigma_price, df.index)
    df["BB_MID"]   = _as_float_series(center, df.index)

    # Keltner & SQUEEZE
    ema_kc  = _as_float_series(ta.ema(df["종가"], length=kel_cfg["period"]), df.index)
    atr_kc  = _as_float_series(ta.atr(df["고가"], df["저가"], df["종가"], length=kel_cfg["period"]), df.index)
    df["KC_UPPER"] = ema_kc + atr_kc * kel_cfg["mult"]
    df["KC_LOWER"] = ema_kc - atr_kc * kel_cfg["mult"]
    with np.errstate(divide='ignore', invalid='ignore'):
        bbw = (df["BB_UPPER"] - df["BB_LOWER"]) / ema_kc
        kcw = (df["KC_UPPER"] - df["KC_LOWER"]) / ema_kc
        df["SQUEEZE"] = (bbw / kcw).replace([np.inf, -np.inf], np.nan)

    # ATR / ADX / MFI / CMF
    df["ATR"] = _as_float_series(ta.atr(df["고가"], df["저가"], df["종가"], length=14), df.index)
    adxout = ta.adx(df["고가"], df["저가"], df["종가"], length=14)
    df["ADX"] = _as_float_series(adxout.get("ADX_14") if adxout is not None else None, df.index)
    df["MFI"] = _as_float_series(ta.mfi(df["고가"], df["저가"], df["종가"], df["거래량"], length=14), df.index)
    try:
        df["CMF"] = _as_float_series(ta.cmf(df["고가"], df["저가"], df["종가"], df["거래량"], length=20), df.index)
    except Exception:
        df["CMF"] = pd.Series(np.nan, index=df.index, dtype="float64")

    # OBV Z, VOL Z (winsorized)
    df["OBV"] = _as_float_series(ta.obv(df["종가"], df["거래량"]), df.index)
    mu_obv  = df["OBV"].rolling(OBV_Z_WINDOW, min_periods=OBV_Z_WINDOW).mean()
    sd_obv  = df["OBV"].rolling(OBV_Z_WINDOW, min_periods=OBV_Z_WINDOW).std(ddof=0).replace(0, np.nan)
    df["OBV_Z"] = ((df["OBV"] - mu_obv) / sd_obv).clip(lower=-WINSOR_SIGMA, upper=WINSOR_SIGMA)
    vol_ma  = df["거래량"].rolling(VOL_Z_WINDOW, min_periods=VOL_Z_WINDOW).mean()
    vol_sd  = df["거래량"].rolling(VOL_Z_WINDOW, min_periods=VOL_Z_WINDOW).std(ddof=0).replace(0, np.nan)
    df["VOL_Z"] = ((df["거래량"] - vol_ma) / vol_sd).clip(lower=-WINSOR_SIGMA, upper=WINSOR_SIGMA)

    # VWAP policy:
    # - True session VWAP (per-day) ONLY if intraday series provided
    # - Otherwise hide (leave NaN)
    if intraday_vwap_daily is not None and not intraday_vwap_daily.empty:
        df["VWAP"] = _as_float_series(intraday_vwap_daily, df.index)
    else:
        df["VWAP"] = pd.Series(np.nan, index=df.index, dtype="float64")

    # Cumulative VWAP (daily cumulative) — legitimate with daily bars
    tp_daily = (df["고가"] + df["저가"] + df["종가"]) / 3.0
    df["VWAP_CUM"] = (tp_daily.mul(df["거래량"]).cumsum() / df["거래량"].cumsum().replace(0, np.nan)).astype("float64")

    # Anchored VWAP — YTD / MTD
    def _anchored(freq: str) -> pd.Series:
        grp = df.index.to_period('Y' if freq == 'Y' else 'M')
        pv = (tp_daily * df["거래량"]).groupby(grp).cumsum()
        vv = df["거래량"].groupby(grp).cumsum().replace(0, np.nan)
        return (pv / vv).astype("float64")

    try:
        df["AVWAP_YTD"] = _anchored('Y')
    except Exception:
        df["AVWAP_YTD"] = pd.Series(np.nan, index=df.index, dtype="float64")
    try:
        df["AVWAP_MTD"] = _anchored('M')
    except Exception:
        df["AVWAP_MTD"] = pd.Series(np.nan, index=df.index, dtype="float64")

    # Donchian & market structure
    df["DONCH_H"] = df["고가"].rolling(DONCHIAN_N, min_periods=DONCHIAN_N).max()
    df["DONCH_L"] = df["저가"].rolling(DONCHIAN_N, min_periods=DONCHIAN_N).min()
    sw_high = df["고가"].rolling(SWING_W, center=True, min_periods=1).max()
    sw_low  = df["저가"].rolling(SWING_W, center=True, min_periods=1).min()
    df["HH_HL"] = ((sw_high > sw_high.shift(1)) & (sw_low > sw_low.shift(1))).astype(int)  # trend up
    df["LH_LL"] = ((sw_high < sw_high.shift(1)) & (sw_low < sw_low.shift(1))).astype(int)  # trend down

    # Regime flags
    df["REGIME_TREND"] = ((df["ADX"] > REGIME_ADX) & ((df["ATR"] / df["종가"]) > REGIME_ATR_PCT)).astype(int)
    df["REGIME_MEAN"]  = (1 - df["REGIME_TREND"]).astype(int)

    # Snapshot dict at last index
    cols = ["EMA_FAST","EMA_MID","EMA_SLOW","RSI","MACD","MACD_SIGNAL","MACD_HIST",
            "STOCH_K","STOCH_D","BB_UPPER","BB_LOWER","BB_MID","KC_UPPER","KC_LOWER",
            "SQUEEZE","ATR","ADX","OBV","OBV_Z","MFI","CMF","VOL_Z","AVWAP_YTD","AVWAP_MTD",
            "VWAP","VWAP_CUM","DONCH_H","DONCH_L","HH_HL","LH_LL","REGIME_TREND","REGIME_MEAN"]
    snap = {}
    for c in cols:
        val = df[c].iloc[-1] if c in df.columns and len(df[c]) else np.nan
        snap[c] = None if (val is None or pd.isna(val)) else float(val)

    return snap, df

# =========================================================
# Multi-timeframe helper
# =========================================================
def weekly_trend_confluence(df_hist: pd.DataFrame) -> float:
    """
    Confluence between weekly and daily EMA(20) trend directions.
    Returns 0.0 or 1.0 for simplicity.
    """
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

# =========================================================
# Peer sampling (timebox + decay + tick-equality + robust outlier filter + quality weighting)
# =========================================================
def fetch_peer_trades(
    symbol: str,
    market: str,
    trade_time_iso: str,
    action: str,
    group_size: Optional[int] = None,
    user_id_exclude: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Sample peers around trade_time within ±N business days (calendar-aware if available).
    """
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

def fetch_peer_quality_map(user_ids: List[str]) -> Dict[str, float]:
    """
    Fetch per-user quality weights from 'peer_stats' table.
    Expected columns: user_id, winrate (0~1), sharpe (float)
    Weight formula example (bounded):
        wq = 0.5 + 0.5*clip(winrate,0,1) + 0.1*clip(sharpe/2, -0.5, 1.0)
    Final weights will be clipped to [0.25, 2.0].
    """
    if not user_ids:
        return {}
    try:
        res = (supabase.table("peer_stats")
               .select("user_id, winrate, sharpe")
               .in_("user_id", list(set(user_ids)))
               .execute())
        rows = res.data or []
    except Exception:
        rows = []
    out: Dict[str, float] = {}
    for r in rows:
        uid = r.get("user_id")
        wr = r.get("winrate", 0.5) or 0.5
        sh = r.get("sharpe", 0.0) or 0.0
        wq = 0.5 + 0.5*float(np.clip(wr, 0, 1)) + 0.1*float(np.clip(sh/2.0, -0.5, 1.0))
        out[uid] = float(np.clip(wq, 0.25, 2.0))
    return out

def _to_local(ts_iso: str, market: str) -> pd.Timestamp:
    tz = ZoneInfo(market_tz(market)) if ZoneInfo else None
    t = pd.to_datetime(ts_iso)
    return t.tz_convert(tz) if (tz and t.tzinfo) else (t.tz_localize(tz) if tz else t)

def _same_session_local(trade_ts_local: pd.Timestamp, other_ts_local: pd.Timestamp) -> bool:
    return trade_ts_local.date() == other_ts_local.date()

def _robust_filter_prices(x: pd.Series, method: str = "iqr", k: float = 1.5) -> pd.Series:
    """
    Returns a boolean mask for inliers (True means keep).
    method: "iqr" or "mad" or "none"
    """
    if x is None or x.empty:
        return pd.Series(dtype=bool)
    xv = x.astype("float64")
    if method == "none":
        return pd.Series(True, index=x.index)

    if method == "iqr":
        q1, q3 = np.nanpercentile(xv, [25, 75])
        iqr = q3 - q1
        lo = q1 - k * iqr
        hi = q3 + k * iqr
        return (xv >= lo) & (xv <= hi)
    # MAD
    med = np.nanmedian(xv)
    mad = np.nanmedian(np.abs(xv - med)) + 1e-12
    z = 0.6745 * (xv - med) / mad
    return np.abs(z) <= k

def user_weighted_peer_prices_timeboxed(
    peers: List[Dict[str, Any]],
    trade_time_iso: str,
    market: str,
    same_session: bool = True,
    timebox_min: Optional[int] = None,
    halflife_min: int = 60,
    outlier_method: str = "iqr",
    outlier_k: float = 1.5,
    apply_quality_weight: bool = True
) -> Tuple[pd.Series, pd.Series, Dict[str, Any]]:
    """
    Aggregate peer prices user-wise with qty*time-decay*(quality) weights.
    Steps:
      - filter same session & ±timebox minutes
      - time decay by half-life
      - aggregate per user (price-weighted by qty)
      - robust outlier filter on resulting user-level prices
      - optional quality weighting using peer_stats
      - tick equality rounding (later, at rank stage)
    Returns:
      prices_series, weights_series, info_dict{count, eff_count, removed_outliers, quality_used}
    """
    if not peers:
        return pd.Series(dtype="float64"), pd.Series(dtype="float64"), {"count": 0, "eff_count": 0, "removed_outliers": 0, "quality_used": False}

    t0_local = _to_local(trade_time_iso, market)

    # First pass: accumulate per user
    from collections import defaultdict
    acc_pv = defaultdict(float)   # sum(price * weight)
    acc_w  = defaultdict(float)   # sum(weight)

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

    # Build user-level price & weight
    prices, weights, user_ids = [], [], []
    for uid, w in acc_w.items():
        if w > 0:
            prices.append(acc_pv[uid]/w)
            weights.append(w)
            user_ids.append(uid)

    if not prices:
        return pd.Series(dtype="float64"), pd.Series(dtype="float64"), {"count": 0, "eff_count": 0, "removed_outliers": 0, "quality_used": False}

    s_prices = pd.Series(prices, index=user_ids, dtype="float64")
    s_weights = pd.Series(weights, index=user_ids, dtype="float64")

    # Robust outlier filter at user-level
    keep_mask = _robust_filter_prices(s_prices, method=outlier_method, k=outlier_k)
    removed = int((~keep_mask).sum())
    s_prices = s_prices[keep_mask]
    s_weights = s_weights[keep_mask]

    # Optional quality weighting
    quality_used = False
    if apply_quality_weight and len(s_prices) > 0:
        qmap = fetch_peer_quality_map(list(s_prices.index))
        if qmap:
            qweights = s_prices.index.to_series().map(lambda u: qmap.get(u, 1.0)).astype("float64")
            s_weights = s_weights * qweights.values
            quality_used = True

    # Effective sample size
    wsum = float(np.sum(s_weights)) if len(s_weights) else 0.0
    w2sum = float(np.sum(np.square(s_weights))) if len(s_weights) else 0.0
    eff = int(round((wsum**2 / w2sum))) if w2sum > 0 else 0

    info = {"count": int(len(s_prices)), "eff_count": eff, "removed_outliers": removed, "quality_used": quality_used}
    return s_prices, s_weights, info

def weighted_median(x: pd.Series, w: pd.Series) -> Optional[float]:
    """
    Weighted median of user-level prices.
    """
    if x.empty or w.empty or len(x) != len(w):
        return None
    order = np.argsort(x.values)
    xv = x.values[order]; wv = w.values[order]
    cdf = np.cumsum(wv) / np.sum(wv)
    idx = np.searchsorted(cdf, 0.5)
    idx = np.clip(idx, 0, len(xv)-1)
    return float(xv[idx])

def weighted_percentile_rank_by_action(
    action: str,
    peer_prices: pd.Series,
    weights: pd.Series,
    my_price: float,
    market: Optional[str] = None
) -> Optional[float]:
    """
    Weighted percentile:
      - buy: share of weights at prices <= my_price
      - sell: share of weights at prices >= my_price
    Tick equality rounding applied if market provided.
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

# =========================================================
# Cost model / FX / Slippage (per-order min fee + effective px)
# =========================================================
def per_order_min_fee(notional_ccy: float, market: str, side: str,
                      broker: str = "generic", account_type: str = "cash",
                      trade_ccy: str = None, trade_date: Optional[dt.date] = None) -> Tuple[float, str]:
    """
    Returns (min_fee_amount_in_trade_ccy, fee_currency)

      퍼센트 수수료를 섞지 않습니다. 오직 '최소 수수료' 금액만
       브로커 통화 → 거래 통화로 환산해서 반환합니다.
    """
    cm = fetch_cost_model((market or "US").upper(), broker, account_type)
    base_ccy = cm.get("currency", "KRW" if market == "KR" else "USD")
    trade_ccy = trade_ccy or base_ccy

    rate = 1.0
    if trade_date and base_ccy != trade_ccy:
        rate = fetch_fx_rate(base_ccy, trade_ccy, trade_date)

    min_fee = float(cm.get("min_fee", 0.0))
    fee_in_trade = min_fee * rate
    return float(fee_in_trade), trade_ccy

def _percent_fee_rate_for_side(cm: Dict[str, float], action: str) -> float:
    if action == "buy":
        return float(cm.get("fee_buy", 0.0))
    else:
        return float(cm.get("fee_sell", 0.0))

def compute_fee_ps_and_apply_flag(price: float, qty: float, action: str, market: str,
                                  broker: str, account_type: str, trade_ccy: str,
                                  trade_date: dt.date) -> Tuple[float, bool]:
    """
    반환: (per_share_fee_extra, apply_percent)
      - 퍼센트 총액(price * pct * qty)과 '최소 수수료 총액'을 비교.
      - 최소 수수료가 더 크면: per-share fee extra 를 (min_fee_total/qty)로 지급,
        퍼센트는 비활성화(apply_percent=False).
      - 퍼센트가 더 크면: per-share extra=0, 퍼센트 활성화(apply_percent=True).
    """
    cm = fetch_cost_model((market or "US").upper(), broker, account_type)
    pct = _percent_fee_rate_for_side(cm, action)

    # 퍼센트 수수료 총액
    percent_total = max(0.0, price) * max(0.0, pct) * max(1.0, qty)

    # 최소 수수료 총액 (오직 최소 수수료만 환산)
    min_fee_total, _ = per_order_min_fee(price * max(1.0, qty), market, action,
                                         broker=broker, account_type=account_type,
                                         trade_ccy=trade_ccy, trade_date=trade_date)

    if min_fee_total > percent_total:
        # 최소 수수료 우세 → per-share extra로 분배, 퍼센트는 끔
        return float(min_fee_total / max(1.0, qty)), False
    else:
        # 퍼센트 우세 → per-share extra 없음, 퍼센트만 적용
        return 0.0, True

def adaptive_slippage_bps(symbol: str, market: str, df_hist: pd.DataFrame) -> float:
    """
    a + 1e4*(b*intraday_spread_pct + c*avg_abs_ret + d*last_abs_ret)
    - Parameters a,b,c,d loaded from DB with symbol override and market fallback.
    - Uses last up-to-10 daily bars.
    """
    params = fetch_slippage_params(symbol, (market or "US").upper())
    a = float(params.get("a", SLIPPAGE_BPS_DEFAULT))
    b = float(params.get("b", 0.0))
    c = float(params.get("c", 0.0))
    d = float(params.get("d", 0.0))
    try:
        win = min(10, len(df_hist))
        if win <= 0:
            return max(0.0, a)
        close = df_hist["종가"].iloc[-win:]
        high = df_hist["고가"].iloc[-win:]
        low  = df_hist["저가"].iloc[-win:]
        spread_pct = float(np.nanmean((high - low) / np.clip(close, 1e-12, None)))
        vol_term   = float(np.nanmean(close.pct_change().abs())) if win > 1 else 0.0
        abs_ret    = float(abs(close.pct_change().iloc[-1])) if win > 1 else 0.0
        slip = a + 1e4*(b*spread_pct + c*vol_term + d*abs_ret)
        return float(max(0.0, slip))
    except Exception:
        return float(max(0.0, a))

def effective_unit_price(px: float, action: str, market: str, slippage_bps: float,
                         broker: str = "generic", account_type: str = "cash",
                         trade_ccy: str = None, trade_date: Optional[dt.date] = None,
                         per_share_fee_extra: float = 0.0, apply_percent: bool = True) -> float:
    """
    실효단가 = (가격 ± 슬리피지) × (1 + 수수료% + (매도시)세금%)
             + per_share_fee_extra

    - apply_percent: '퍼센트 수수료(commission %)'만 토글.
    - 매도세(tax_sell)는 최소수수료 여부와 무관하게 항상 적용.
    """
    cm = fetch_cost_model((market or "US").upper(), broker, account_type)
    fee_buy  = float(cm.get("fee_buy", 0.0))
    fee_sell = float(cm.get("fee_sell", 0.0))
    tax_sell = float(cm.get("tax_sell", 0.0))

    # 슬리피지 적용
    slip = px * (slippage_bps / 1e4)
    eff = px + (slip if action == "buy" else -slip)

    if action == "buy":
        # 매수: 커미션 퍼센트만 flag로
        if apply_percent:
            eff *= (1 + fee_buy)
    else:
        # 매도: 세금은 항상, 커미션 퍼센트는 flag로
        comm_part = fee_sell if apply_percent else 0.0
        eff *= (1 + comm_part + tax_sell)

    return float(eff + per_share_fee_extra)

# =========================================================
# Portfolio context & caps / sizing
# =========================================================
def fetch_positions_and_meta(user_id: str) -> Dict[str, Any]:
    """
    Loads user's portfolio context. Expected optional tables:
      - positions(user_id, symbol, qty, price, sector, beta)
      - daily_drawdown(user_id, date, value)
      - cash(user_id, available)
    Falls back to EXEC account_size if no data.
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
            sec = r.get("sector") or "OTHER"
            beta = float(r.get("beta", 1.0) or 1.0)
            notional = q * p
            eq += notional
            by_sym[s] = by_sym.get(s, 0.0) + notional
            by_sec[sec] = by_sec.get(sec, 0.0) + notional
            beta_exp += beta * (notional / max(1.0, ACCOUNT_SIZE))
        equity_est = eq if eq > 0 else ACCOUNT_SIZE
        out.update({"equity": equity_est, "by_symbol": by_sym, "by_sector": by_sec, "beta_exposure": beta_exp})

        # daily drawdown
        dd = supabase.table("daily_drawdown").select("value").eq("user_id", user_id)\
             .order("date", desc=True).limit(1).execute()
        if dd.data:
            out["ddl_today"] = float(dd.data[0].get("value", 0.0) or 0.0)

        # cash
        cash = supabase.table("cash").select("available").eq("user_id", user_id).single().execute().data
        if cash:
            out["cash_avail"] = float(cash.get("available", ACCOUNT_SIZE))
    except Exception:
        pass
    return out

def cap_position_sizing(req_qty: int, symbol: str, price: float,
                        market: str, stop_dist: float, user_ctx: Dict[str, Any]) -> int:
    """
    Applies hard caps and cash/risk caps. KR enforces integer shares if ALLOW_FRACTIONAL['KR']=False.
    """
    caps = PORT_CAPS
    equity = float(user_ctx.get("equity", ACCOUNT_SIZE))
    cash_avail = float(user_ctx.get("cash_avail", ACCOUNT_SIZE))
    ddl_today = float(user_ctx.get("ddl_today", 0.0))
    by_sym = user_ctx.get("by_symbol", {})
    by_sec = user_ctx.get("by_sector", {})
    beta_expo = float(user_ctx.get("beta_exposure", 0.0))

    # sector lookup lightweight
    try:
        sm = supabase.table("sector_map").select("sector").eq("symbol", symbol).single().execute().data
        sector = sm["sector"] if sm and sm.get("sector") else "OTHER"
    except Exception:
        sector = "OTHER"

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

    qty = max(0, min(req_qty, max_qty_cash, max_qty_risk))

    # Market-specific integer/fractional rule
    m = (market or "").upper()
    if not ALLOW_FRACTIONAL.get(m, False):
        qty = int(qty)  # enforce integer
    return qty

# =========================================================
# Rule-based benchmark simulator (gap-aware next-bar execution)
# =========================================================
def _exec_price_next_bar(entry_side: str, trigger_price: float,
                         next_open: float, next_high: float, next_low: float,
                         slippage_bps: float, market: str,
                         broker: str, account_type: str,
                         trade_ccy: str, trade_date: dt.date,
                         qty: float,
                         level: str  # "stop" | "tp"
                         ) -> float:
    # gap-through 판정
    if entry_side == "buy":
        crossed_gap = (next_open < trigger_price) if level == "stop" else (next_open > trigger_price)
    else:  # entry_side == "sell"
        crossed_gap = (next_open > trigger_price) if level == "stop" else (next_open < trigger_price)

    base = next_open if crossed_gap else trigger_price

    exit_side = "sell" if entry_side == "buy" else "buy"
    ps_extra, apply_pct = compute_fee_ps_and_apply_flag(
        base, max(1.0, qty), exit_side, market, broker, account_type, trade_ccy, trade_date
    )
    eff = effective_unit_price(
        base, exit_side, market, slippage_bps,
        broker=broker, account_type=account_type, trade_ccy=trade_ccy, trade_date=trade_date,
        per_share_fee_extra=ps_extra, apply_percent=apply_pct
    )
    return float(eff)

def simulate_trade_path(
    df_after: pd.DataFrame,
    action: str,
    entry_price: float,
    stop_price: float,
    tp1_price: float,
    max_holding_days: int,
    market: str,
    broker: str,
    account_type: str,
    trade_ccy: str,
    trade_date: dt.date,
    slippage_bps: float,
    qty: float
) -> Dict[str, Any]:
    """
    Rule-based path over the analysis window:
      - entry assumed at time 0 (already executed at entry_price)
      - For each next day bar: if stop or TP touched (by high/low), we simulate fill at the first touch with next-bar logic.
      - If neither hits within holding window, exit at last close with slippage+fees.
    Returns: dict with realized_return_pct, exit_reason, exit_day_index, exit_price
    """
    if df_after is None or df_after.empty:
        return {"realized_return_pct": None, "exit_reason": "no_data", "exit_day_index": None, "exit_price": None}

    # Iterate day by day (skip the entry day as it's already executed)
    for i in range(1, min(max_holding_days, len(df_after))):
        row = df_after.iloc[i]
        hi = float(row["고가"]); lo = float(row["저가"])
        op = float(row["시가"]) if "시가" in row.index and pd.notna(row["시가"]) else float(row["종가"])
        # '시가' 우선 사용. 없으면 보수적으로 종가 대체.

        if action == "buy":
            # stop first, then tp ordering uncertain: assume worst-case for trader (touch adverse first if both in range)
            hit_stop = lo <= stop_price
            hit_tp   = hi >= tp1_price
            if hit_stop or hit_tp:
                # next bar execution from this day's "open" proxy
                level = "stop" if hit_stop else "tp"

                # long(=buy) 포지션 청산 → entry_side는 "buy"로 넘겨야 함
                fill = _exec_price_next_bar(
                    "buy",  # ← 진입 방향
                    stop_price if hit_stop else tp1_price,
                    op, hi, lo,
                    slippage_bps, market, broker, account_type, trade_ccy, trade_date, qty,
                    level=level
                )

                pnl_pct = (fill - entry_price) / max(entry_price, 1e-9) * 100.0
                return {"realized_return_pct": float(pnl_pct),
                        "exit_reason": "stop" if hit_stop else "tp1",
                        "exit_day_index": i, "exit_price": float(fill)}

        else:
            # sell entry → buy to cover
            hit_stop = hi >= stop_price
            hit_tp   = lo <= tp1_price
            if hit_stop or hit_tp:
                level = "stop" if hit_stop else "tp"

                # 숏 포지션의 진입 방향은 "sell" (청산은 "buy"가 맞지만,
                # _exec_price_next_bar에서 entry_side는 진입 방향을 넣도록 설계됨)
                fill = _exec_price_next_bar(
                    entry_side="sell",
                    trigger_price=(stop_price if hit_stop else tp1_price),
                    next_open=op, next_high=hi, next_low=lo,
                    slippage_bps=slippage_bps, market=market,
                    broker=broker, account_type=account_type,
                    trade_ccy=trade_ccy, trade_date=trade_date,
                    qty=qty, level=level
                )

                pnl_pct = (entry_price - fill) / max(entry_price, 1e-9) * 100.0
                return {
                       "realized_return_pct": float(pnl_pct),
                       "exit_reason": ("stop" if hit_stop else "tp1"),
                       "exit_day_index": i,
                       "exit_price": float(fill)
                       }

    # If not exited within window, close at last available price
    last = df_after.iloc[min(max_holding_days-1, len(df_after)-1)]
    px = float(last["종가"])
    exit_side = "sell" if action == "buy" else "buy"

    ps_extra_last, apply_pct_last = compute_fee_ps_and_apply_flag(
        px, max(1.0, qty), exit_side, market, broker, account_type, trade_ccy, trade_date
    )

    fill_last = effective_unit_price(
        px, exit_side, market, slippage_bps,
        broker=broker, account_type=account_type, trade_ccy=trade_ccy, trade_date=trade_date,
        per_share_fee_extra=ps_extra_last, apply_percent=apply_pct_last
    )

    if action == "buy":
        pnl_pct = (fill_last - entry_price) / max(entry_price, 1e-9) * 100.0
    else:
        pnl_pct = (entry_price - fill_last) / max(entry_price, 1e-9) * 100.0
    return {"realized_return_pct": float(pnl_pct),
            "exit_reason": "time_expiry", "exit_day_index": int(min(max_holding_days-1, len(df_after)-1)),
            "exit_price": float(fill_last)}

# =========================================================
# Charting
# =========================================================
def make_trade_chart(
    df: pd.DataFrame,
    xpt: pd.Timestamp,
    trade_price: float,
    action: str,
    peer_median: Optional[float] = None,
    bench_price: Optional[float] = None,
    show_vwap: bool = True
) -> io.BytesIO:
    """
    Builds a PNG chart in memory; session VWAP line is shown only if df['VWAP'] has non-NaNs and show_vwap=True.
    """
    plt.figure(figsize=(14, 8))
    plt.plot(df.index, df["종가"], label="종가", color="black", linewidth=1.3)

    for key, style in [("EMA_FAST","--"),("EMA_MID",":"),("EMA_SLOW","-.")]:
        if key in df.columns: plt.plot(df.index, df[key], style, label=key)

    # Envelope bands
    for key in ["BB_UPPER","BB_LOWER","KC_UPPER","KC_LOWER",
                "AVWAP_YTD","AVWAP_MTD","VWAP_CUM","DONCH_H","DONCH_L"]:
        if key in df.columns:
            plt.plot(df.index, df[key], alpha=0.5, label=key)

    # Session VWAP (only when truly available)
    if show_vwap and "VWAP" in df.columns and df["VWAP"].notna().any():
        plt.plot(df.index, df["VWAP"], alpha=0.7, label="VWAP")

    if "BB_UPPER" in df.columns and "BB_LOWER" in df.columns:
        plt.fill_between(df.index, df["BB_LOWER"], df["BB_UPPER"], alpha=0.08)

    # Trade marker
    plt.axvline(xpt, color=("red" if action == "sell" else "green"), linestyle="--")
    plt.scatter([xpt], [trade_price], color=("red" if action == "sell" else "green"), s=140, zorder=5)

    if peer_median is not None:
        plt.hlines(peer_median, df.index[0], df.index[-1], alpha=0.35, label="Peer Median")
    if bench_price is not None:
        plt.hlines(bench_price, df.index[0], df.index[-1], alpha=0.45, label="Benchmark Px")

    plt.title("Auto Trade Analysis (Expert-Grade)")
    plt.legend()
    plt.grid(True)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close()
    buf.seek(0)
    return buf

# =========================================================
# LLM context builder (quantified blocks + disclaimer)
# =========================================================
def build_llm_context(
    user: Dict[str, Any],
    trade: Dict[str, Any],
    feedback_text: str,
    stats: Dict[str, Any],
    config: Dict[str, Any],
    selected_tone: str
) -> str:
    """
    Produces a precise prompt for the LLM with explicit numerical blocks:
      - Position/Risk block
      - Cost/Slippage block
      - Peer block
      - Safety disclaimer
    """
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

    safety = (
        "※ 유의: 본 코칭은 교육 목적이며 수익을 보장하지 않습니다. 최종 투자 결정과 책임은 사용자에게 있습니다. "
        "과도한 레버리지·집중투자를 지양하고, 손실 가능성을 충분히 고려하세요."
    )

    sym = trade.get("symbol"); px = trade.get("price"); qty = trade.get("qty")
    act = trade.get("action"); tt = trade.get("trade_time")

    stop_price = stats.get("stop_price")
    tp1_price  = stats.get("tp1_price")
    tp2_price  = stats.get("tp2_price")
    tp3_price  = stats.get("tp3_price")
    size_base  = stats.get("recommended_size_base")
    size_cap   = stats.get("recommended_size_capped")

    eff_buy  = stats.get("effective_unit_buy")
    eff_sell = stats.get("effective_unit_sell")
    slip_bps = stats.get("slippage_bps_est")
    comm_tot = stats.get("commission_total")
    sig_q    = stats.get("signal_quality")
    peer_pct = stats.get("peer_rank_percentile")
    peer_med = stats.get("peer_median")

    acct_sz  = stats.get("account_size")
    acct_src = stats.get("account_size_source", "config")
    base_ccy = trade.get("currency", "USD")
    acct_label = "추정" if acct_src == "equity" else "설정값"
    acct_rpt = stats.get("account_risk_per_trade")
    atr_mult = stats.get("atr_stop_mult")
    tp1_mult = stats.get("tp1_atr_mult")

    sizing_block = f"""
[포지션/리스크]
- 체결 수량(qty): {qty}
- 신호 품질(score 0~1): {sig_q}
- 권장 수량: {size_cap} (캡 전 {size_base})
- 손절가: {stop_price} | 익절 1R: {tp1_price} / 2R: {tp2_price} / 3R: {tp3_price}
- 계정 크기({acct_label}): {acct_sz} {base_ccy} | 거래당 계정 리스크 비율: {acct_rpt}
- ATR 기반 Stop 배수: {atr_mult} | TP1 배수: {tp1_mult}
""".strip()

    cost_block = f"""
[비용/슬리피지]
- 슬리피지 추정(bps): {slip_bps}
- 실효단가(매수): {eff_buy} | 실효단가(매도): {eff_sell}
- 총 수수료/세금(있다면): {comm_tot}
""".strip()

    peer_block = f"""
[피어 비교]
- 가중 중앙값(가격): {peer_med}
- 가중 퍼센타일(내 체결가 기준): {peer_pct}
""".strip()

    ctx = f"""
[시스템]
- 코드 버전: {VERSION}

[사용자정보]
- 투자레벨: {user.get('investor_level','beginner')} ({inv_msg})
- 선택 톤: {tone_msg}
- 최근감정: {user.get('last_emotion','')}

[트레이드]
- 종목: {sym}
- 가격: {px}
- 수량: {qty}
- 날짜: {str(tt)[:19]}
- 액션: {act}

{peer_block}

{sizing_block}

{cost_block}

[규칙 기반 피드백 요약]
{feedback_text}

[주요지표 (요약 JSON)]
{json.dumps(stats, ensure_ascii=False, indent=2)}

[AI코칭목표]
사용자의 실제 수량/실효단가/리스크 한도를 고려해
- 포지션 크기, 손절·익절 실행 기준(가격/퍼센트/리스크금액),
- 분할 청산/추가 진입 조건,
- 반대 방향 움직임·급변동 시 대안 시나리오와 액션 플랜을
정량적으로 제시하시오. 톤/투자등급 가이드를 준수할 것.

[안전고지]
{safety}
""".strip()

    return ctx

# ===== OpenAI 기반 LLM 코멘터리 (Responses API) =====
def ai_commentary(context: str, tries: int = 2, timeout: int = 60) -> Optional[str]:
    """
    OpenAI Responses API로 코멘트 생성.
    - 환경변수: OPENAI_API_KEY
    """
    if OpenAI is None:
        logger.info("[LLM] openai SDK not installed; skipping.")
        return None
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.info("[LLM] OPENAI_API_KEY not set; skipping.")
        return None
    try:
        client = OpenAI(api_key=api_key, timeout=timeout)
    except Exception as e:
        logger.warning(f"[LLM] openai init failed: {type(e).__name__}: {e}")
        return None

    last_err = None
    for _ in range(max(1, tries)):
        try:
            resp = client.responses.create(
                model=LLM_MODEL_NAME or "gpt-5",
                input=context,
            )
            # 표준 속성 (SDK 버전에 따라 없을 수 있어 안전 추출)
            text = getattr(resp, "output_text", None)
            if not text:
                try:
                    # 보강: content 트리를 순회해 텍스트 조합
                    parts = []
                    for item in getattr(resp, "output", []) or []:
                        for c in getattr(item, "content", []) or []:
                            t = getattr(c, "text", None)
                            if t: parts.append(t)
                    text = "\n".join(parts) if parts else None
                except Exception:
                    text = None
            return text
        except Exception as e:
            last_err = e
            time.sleep(0.6)
    logger.warning(f"[LLM] openai commentary failed after retries: {last_err}")
    return None

# =========================================================
# Main analysis & feedback (expert-grade)
# =========================================================
def analyze_and_feedback(
    trade: Dict[str, Any],
    user: Dict[str, Any],
    cfg: Dict[str, Any],
    selected_tone: str = "friendly",
    use_llm: bool = False,
    generate_chart: bool = True,
) -> Tuple[str, Optional[str], Dict[str, Any], str, Optional[float], Optional[float], Optional[str]]:
    """
    Returns:
      feedback_text, chart_url, stats(dict), style_type, rank_percentile, bench_ret_pct, ai_msg
    """
    # ---------- Normalize inputs ----------
    symbol = trade["symbol"]
    market_raw = (trade.get("market") or "").upper()
    if market_raw in ["KRX", "KOSPI", "KOSDAQ"]:
        market = "KR"
    elif market_raw in ["NASDAQ", "NYSE", "AMEX", "US"]:
        market = "US"
    else:
        market = market_raw or "US"

    action = (trade.get("action") or "").lower()
    if action not in ("buy", "sell"):
        logger.warning(f"[input] Unknown action '{action}', fallback to 'buy'")
        action = "buy"

    price = float(trade.get("price", 0) or 0.0)
    trade_time_iso = str(trade.get("trade_time"))
    qty_raw = trade.get("qty", 0)
    commission_raw = trade.get("commission", 0)

    broker = (trade.get("broker") or "generic")
    account_type = (trade.get("account_type") or "cash")
    trade_ccy = trade.get("currency") or ("KRW" if market == "KR" else "USD")
    t_parsed = pd.to_datetime(trade_time_iso)
    t_date = t_parsed.date()

    # Sanitize qty/commission
    try:
        qty = float(qty_raw or 0.0)
        if not np.isfinite(qty) or qty < 0:
            qty = 0.0
    except Exception:
        qty = 0.0

    try:
        commission = float(commission_raw or 0.0)
        if not np.isfinite(commission) or commission < 0:
            commission = 0.0
    except Exception:
        commission = 0.0

    # ---------- Data window ----------
    lookback_days = required_lookback_days(cfg)
    fwd = 1 if ANALYSIS_MODE == "realtime" else (ANALYSIS_WINDOW_DAYS + 7)

    if market == "KR":
        start_dt = (t_parsed - pd.Timedelta(days=lookback_days)).strftime("%Y%m%d")
        end_dt   = (t_parsed + pd.Timedelta(days=fwd)).strftime("%Y%m%d")
    else:
        start_dt = (t_parsed - pd.Timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        end_dt   = (t_parsed + pd.Timedelta(days=fwd)).strftime("%Y-%m-%d")

    df = get_stock_price(symbol, market, start_dt, end_dt)
    if df.empty:
        logger.warning(f"[data] Empty price data: {symbol} {market} {start_dt}~{end_dt}")
        return "데이터가 부족해 분석을 진행할 수 없습니다.", None, {}, "중립", None, None, None

    if len(df) < MIN_CONSEC_BARS:
        logger.warning(f"[data] Insufficient bars ({len(df)} < {MIN_CONSEC_BARS}) for stable indicators.")
        emit_metric("insufficient_bars", 1, {"symbol": symbol, "market": market})

    # ---------- Determine event cutoff (leak-free) ----------
    df.index = pd.to_datetime(df.index).tz_localize(None)
    cutoff = event_cutoff_for_daily(trade_time_iso, market)
    cutoff_date = pd.to_datetime(cutoff).normalize()
    xpt = snap_to_index_or_prev(df.index, cutoff_date)
    df_hist = df.loc[:xpt].copy()

    # ---------- Intraday VWAP policy ----------
    intraday_used = False
    intraday_vwap_daily = pd.Series(dtype="float64")
    try:
        if INTRADAY.get("enabled", False):
            # Pull minute data in a small window to build session VWAP up to event date
            i_start = pd.to_datetime(xpt) - pd.Timedelta(days=10)
            i_end   = pd.to_datetime(xpt) + pd.Timedelta(days=1)
            df_min = get_intraday_prices(symbol, market, i_start, i_end)
            if df_min is not None and not df_min.empty:
                intraday_vwap_daily = _session_vwap_from_intraday(df_min)
                intraday_used = intraday_vwap_daily.notna().any()
    except Exception as e:
        logger.info(f"[intraday] minute hook failed: {e}")
        intraday_used = False

    # ---------- Indicators snapshot ----------
    snap, df_enriched_hist = compute_indicators_snapshot(df_hist, cfg, intraday_vwap_daily)
    vwap_session_available = (
        "VWAP" in df_enriched_hist.columns and df_enriched_hist["VWAP"].notna().any()
    )

    # ---------- Weekly confluence ----------
    mtf_conf = weekly_trend_confluence(df_enriched_hist)
    snap["WEEKLY_CONFLUENCE"] = mtf_conf

    # ---------- Peer sampling & ranks ----------
    peers_raw = fetch_peer_trades(symbol, market, trade_time_iso, action, user_id_exclude=user.get("id"))
    peer_prices, peer_w, pinfo = user_weighted_peer_prices_timeboxed(
        peers_raw, trade_time_iso, market,
        same_session=PEER_SAME_SESSION,
        timebox_min=PEER_TIMEBOX_MIN,
        halflife_min=PEER_HALFLIFE_MIN,
        outlier_method=OUTLIER_FILTER,
        outlier_k=OUTLIER_K,
        apply_quality_weight=True
    )
    p50 = weighted_median(peer_prices, peer_w)
    rank_percentile = weighted_percentile_rank_by_action(action, peer_prices, peer_w, price, market=market)
    peer_reliability = "high" if pinfo.get("eff_count", 0) >= MIN_EFFECTIVE_PEERS else "low"

    # ---------- After window for simulator (backtest mode) ----------
    df_after = pd.DataFrame()
    if ANALYSIS_MODE != "realtime":
        df_after = df.loc[xpt:].copy()  # includes entry bar at index 0
        if len(df_after) > (ANALYSIS_WINDOW_DAYS + 1):
            df_after = df_after.iloc[:(ANALYSIS_WINDOW_DAYS + 1)]

    # ---------- Slippage & fees ----------
    slip_bps = adaptive_slippage_bps(symbol, market, df_enriched_hist)

    # Fee application (mutually exclusive: percent vs min-fee)
    commission_total = 0.0
    if qty > 0 and commission > 0:
        # 사용자가 명시한 커미션은 per-share extra 로 간주(퍼센트도 유지)
        per_share_fee_buy  = commission / qty if action == "buy" else 0.0
        per_share_fee_sell = commission / qty if action == "sell" else 0.0
        apply_percent_buy, apply_percent_sell = True, True
        commission_total = commission
    else:
        per_share_fee_buy,  apply_percent_buy  = compute_fee_ps_and_apply_flag(price, max(1.0, qty), "buy",
                                                                               market, broker, account_type, trade_ccy, t_date)
        per_share_fee_sell, apply_percent_sell = compute_fee_ps_and_apply_flag(price, max(1.0, qty), "sell",
                                                                               market, broker, account_type, trade_ccy, t_date)
        commission_total = (per_share_fee_buy if action=="buy" else per_share_fee_sell) * max(1.0, qty)

    eff_buy  = effective_unit_price(price, "buy",  market, slip_bps, broker=broker, account_type=account_type,
                                    trade_ccy=trade_ccy, trade_date=t_date,
                                    per_share_fee_extra=per_share_fee_buy, apply_percent=apply_percent_buy)
    eff_sell = effective_unit_price(price, "sell", market, slip_bps, broker=broker, account_type=account_type,
                                    trade_ccy=trade_ccy, trade_date=t_date,
                                    per_share_fee_extra=per_share_fee_sell, apply_percent=apply_percent_sell)

    # ---------- Risk: ATR stop & targets ----------
    atr = snap.get("ATR")
    stop_dist = (atr or 0.0) * STOP_ATR_MULT if atr is not None else 0.0
    if not np.isfinite(stop_dist) or stop_dist <= 0:  # fallback
        stop_dist = max(price * 0.005, 1e-3)

    stop_raw = price - stop_dist if action == "buy" else price + stop_dist
    tp1_raw  = price + (atr or 0.0) * TP1_ATR_MULT if action == "buy" else price - (atr or 0.0) * TP1_ATR_MULT

    stop = round_to_tick_side(stop_raw, market, action, "stop")
    tp1  = round_to_tick_side(tp1_raw,  market, action, "tp")

    # 2R/3R based on distance from entry to TP1
    r1 = (tp1_raw - price) if action == "buy" else (price - tp1_raw)
    tp2  = round_to_tick(price + (r1 * 2.0) if action == "buy" else price - (r1 * 2.0), market)
    tp3  = round_to_tick(price + (r1 * 3.0) if action == "buy" else price - (r1 * 3.0), market)

    # ---------- Sizing & caps ----------
    risk_cash = ACCOUNT_SIZE * ACCOUNT_RISK
    denom = max(abs(price - stop), 1e-6)
    size_by_risk = int(max(risk_cash // denom, 0))
    size_by_cash = int(max(ACCOUNT_SIZE // max(price, 1e-9), 0))
    base_size = max(1, min(size_by_risk, size_by_cash))

    user_ctx = fetch_positions_and_meta(user.get("id"))
    acct_sz_val = float(user_ctx.get("equity", ACCOUNT_SIZE))
    acct_src = "equity" if user_ctx.get("equity") is not None else "config"
    size_capped = cap_position_sizing(base_size, symbol, price, market, abs(price - stop), user_ctx)

    if not ALLOW_FRACTIONAL.get(market, False):  # KR 등 정수주 강제
        size_capped = int(size_capped)

    # ---------- Simulator (gap-aware) ----------
    bench_ret = None
    bench_exit_px = None
    bench_reason = None
    if ANALYSIS_MODE != "realtime" and not df_after.empty:
        sim = simulate_trade_path(
            df_after=df_after,
            action=action,
            entry_price=(eff_buy if action == "buy" else eff_sell),
            stop_price=stop,
            tp1_price=tp1,
            max_holding_days=ANALYSIS_WINDOW_DAYS,
            market=market,
            broker=broker,
            account_type=account_type,
            trade_ccy=trade_ccy,
            trade_date=t_date,
            slippage_bps=slip_bps,
            qty=qty
        )
        bench_ret = sim.get("realized_return_pct")
        bench_exit_px = sim.get("exit_price")
        bench_reason = sim.get("exit_reason")

    # ---------- Feedback text (concise, quantified) ----------
    parts: List[str] = []
    ef, em, es = snap.get("EMA_FAST"), snap.get("EMA_MID"), snap.get("EMA_SLOW")
    rsi = snap.get("RSI"); adx = snap.get("ADX")
    macd, macds = snap.get("MACD"), snap.get("MACD_SIGNAL")
    vwap = snap.get("VWAP"); vwap_cum = snap.get("VWAP_CUM")
    avwap_y = snap.get("AVWAP_YTD", np.nan); squeeze = snap.get("SQUEEZE", np.nan); volz = snap.get("VOL_Z", np.nan)
    donch_h, donch_l = snap.get("DONCH_H", np.nan), snap.get("DONCH_L", np.nan)
    hh_hl, lh_ll = snap.get("HH_HL", 0), snap.get("LH_LL", 0)
    regime_trend = snap.get("REGIME_TREND", 0)

    if action == "buy":
        if all(x is not None for x in [ef, em, es]) and ef > em > es: parts.append("상승 추세.")
        if adx is not None and adx >= 20: parts.append(f"추세강도(ADX={adx:.1f}) 양호.")
        if regime_trend: parts.append("레짐: 추세 우세.")
        if rsi is not None and rsi < 30: parts.append("과매도 반등 가능성.")
        if rsi is not None and rsi > 70: parts.append("과매수 위험.")
        if None not in (macd, macds) and macd > macds: parts.append("MACD 매수 신호.")
        if np.isfinite(avwap_y) and price >= avwap_y: parts.append("연초 AVWAP 이상.")
        if vwap_session_available and np.isfinite(vwap) and price < vwap: parts.append("세션 VWAP 아래 매수.")
        if np.isfinite(vwap_cum) and price < vwap_cum: parts.append("누적 VWAP 아래 매수.")
        if np.isfinite(donch_h) and price > donch_h: parts.append("Donchian 상단 돌파.")
        if int(hh_hl) == 1: parts.append("시장 구조: HH/HL (상향).")
        if np.isfinite(volz) and abs(volz) >= 2: parts.append("이례적 거래량.")
        if np.isfinite(squeeze) and squeeze < 1.0: parts.append("변동성 수축 구간.")
    else:
        if rsi is not None and rsi > 70: parts.append("과매수 매도.")
        if adx is not None and adx >= 20 and None not in (macd, macds) and macd < macds: parts.append("MACD 매도 신호.")
        if vwap_session_available and np.isfinite(vwap) and price > vwap: parts.append("세션 VWAP 상단 매도.")
        if np.isfinite(vwap_cum) and price > vwap_cum: parts.append("누적 VWAP 상단 매도.")
        if np.isfinite(donch_l) and price < donch_l: parts.append("Donchian 하단 이탈.")
        if int(lh_ll) == 1: parts.append("시장 구조: LH/LL (하향).")

    # Peer relation
    if p50 is not None:
        rel = ("저렴" if price <= p50 else "비싸게") if action == "buy" else ("고점" if price >= p50 else "저점")
        parts.append(f"Peer 중앙({p50:.2f}) 대비 {rel}.")
        if rank_percentile is not None:
            parts.append(f"피어 유효표본 {pinfo.get('eff_count',0)}명 기준 ~{int(round(rank_percentile))}퍼센타일.")
    else:
        parts.append(f"피어 표본 부족(유효 {pinfo.get('eff_count',0)}명)으로 신뢰도 제한.")

    if not vwap_session_available:
        parts.append("세션 VWAP 데이터 없음(분봉 미연결).")

    if bench_ret is not None:
        parts.append(f"룰-기반 시뮬 결과(비용·슬리피지 반영): {bench_ret:.2f}% ({bench_reason}).")

    if commission_total > 0:
        parts.append(f"수수료/최소수수료 반영: 총 {commission_total:.2f} {trade_ccy}.")

    parts.append(
        f"손절 {round(stop, 4)}, 익절 1R {round(tp1, 4)} / 2R {round(tp2, 4)} / 3R {round(tp3, 4)}, "
        f"권장수량 {size_capped} (캡 전 {base_size})."
    )

    # Signal quality score
    quality = 0.0
    quality += min(1.0, pinfo.get("eff_count",0) / max(1.0, PEER_MIN_SAMPLES)) * 0.25
    quality += (1.0 if regime_trend else 0.5) * 0.20
    quality += mtf_conf * 0.20
    quality += (min(1.0, max(0.0, abs(volz or 0.0) / 2.0))) * 0.15
    q_struct = 0.1 if ((hh_hl and action == "buy") or (lh_ll and action == "sell")) else 0.0
    q_donch  = 0.1 if ((np.isfinite(donch_h) and price > donch_h and action == "buy") or
                       (np.isfinite(donch_l) and price < donch_l and action == "sell")) else 0.0
    quality += (q_struct + q_donch)
    quality = float(max(0.0, min(1.0, quality)))
    parts.append(f"신호 품질 스코어: {round(quality, 2)}")

    # Reliability flags
    flags = {
        "vwap_session_available": vwap_session_available,
        "intraday_used": bool(intraday_used),
        "peer_reliability": peer_reliability,
        "data_bars": int(len(df)),
        "analysis_mode": ANALYSIS_MODE
    }
    if peer_reliability == "low":
        parts.append("※ 피어 신뢰도 낮음: 유효 표본이 제한적입니다.")

    feedback_text = " ".join([p for p in parts if p]).strip()

    # ---------- Stats payload ----------
    acct_sz_val = float(user_ctx.get("equity", ACCOUNT_SIZE))
    has_pos = False
    try:
        by_sym = user_ctx.get("by_symbol", {}) or {}
        has_pos = (sum(by_sym.values()) > 0)
    except Exception:
        pass
    acct_src = "positions_equity" if (has_pos and acct_sz_val > 0) else "config_default"

    acct_ccy = trade_ccy
    per_share_fee_effective = per_share_fee_buy if action == "buy" else per_share_fee_sell

    stats: Dict[str, Any] = dict(snap)
    stats.update({
        "stop_price": float(stop) if np.isfinite(stop) else None,
        "tp1_price": float(tp1) if np.isfinite(tp1) else None,
        "tp2_price": float(tp2) if np.isfinite(tp2) else None,
        "tp3_price": float(tp3) if np.isfinite(tp3) else None,
        "recommended_size_base": int(base_size),
        "recommended_size_capped": int(size_capped),
        "account_size": float(acct_sz_val),
        "account_size_source": acct_src,
        "account_currency": acct_ccy,
        "account_risk_per_trade": float(ACCOUNT_RISK),
        "atr_stop_mult": float(STOP_ATR_MULT),
        "tp1_atr_mult": float(TP1_ATR_MULT),
        "slippage_bps_est": float(slip_bps),
        "effective_unit_buy": float(eff_buy) if np.isfinite(eff_buy) else None,
        "effective_unit_sell": float(eff_sell) if np.isfinite(eff_sell) else None,
        "commission_total": float(commission_total) if np.isfinite(commission_total) else None,
        "trade_qty": float(qty) if np.isfinite(qty) else None,
        "per_share_fee": (
            float(per_share_fee_effective)
            if np.isfinite(per_share_fee_effective) and per_share_fee_effective > 0
            else None
        ),
        "apply_percent_flags": {"buy": bool(apply_percent_buy), "sell": bool(apply_percent_sell)},
        "risk_cash_amount": float(acct_sz_val * ACCOUNT_RISK),
        "stop_distance": float(abs(price - stop)) if np.isfinite(stop) else None,
        "peer_count": int(pinfo.get("count", 0)),
        "peer_eff_count": int(pinfo.get("eff_count", 0)),
        "peer_median": None if p50 is None else float(p50),
        "peer_rank_percentile": None if rank_percentile is None else float(rank_percentile),
        "signal_quality": quality,
        "flags": flags
    })

    # ---------- Chart upload ----------
    chart_url = None
    if generate_chart:
        try:
            df_plot = df.copy()
            for col in ["EMA_FAST","EMA_MID","EMA_SLOW","BB_UPPER","BB_LOWER","KC_UPPER","KC_LOWER",
                        "AVWAP_YTD","AVWAP_MTD","VWAP","VWAP_CUM","DONCH_H","DONCH_L"]:
                if col in df_enriched_hist.columns:
                    df_plot[col] = df_enriched_hist[col]

            buf = make_trade_chart(df_plot, xpt, price, action,
                                   peer_median=p50,
                                   bench_price=bench_exit_px,
                                   show_vwap=vwap_session_available)
            filename = f"{trade.get('id','trade')}.png"
            # 업로드 (SDK 버전 차이 대비)
            try:
                supabase.storage.from_(STORAGE_BUCKET_NAME).upload(
                    path=filename,
                    file=buf.getvalue(),
                    file_options={"contentType":"image/png", "upsert":"true"}
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
            logger.warning(f"[chart] upload failed: {e}")
            chart_url = None

    # ---------- Style label ----------
    style_type = "중립"
    try:
        if (stats.get("tp1_price") and stats.get("stop_price") and rsi is not None):
            if (snap.get("HH_HL", 0) == 1 and (rsi or 0) < 30):
                style_type = "단타추세"
            elif (snap.get("LH_LL", 0) == 1 and (rsi or 0) > 70):
                style_type = "고점방어"
    except Exception:
        pass

    # ---------- LLM coaching (optional) ----------
    ai_msg: Optional[str] = None
    _use_llm = bool(use_llm or LLM_ENABLED_DEFAULT)
    logger.info(f"[LLM] enabled={_use_llm} provider=openai model={LLM_MODEL_NAME} openai_sdk={OpenAI is not None}")
    if _use_llm:
        try:
            stats_for_llm = _sanitize_for_json(stats)
            ctx = build_llm_context(user, trade, feedback_text, stats_for_llm, cfg, selected_tone)
            ai_msg = ai_commentary(ctx)
        except Exception as e:
            logger.warning(f"[LLM] commentary error: {e}")
            ai_msg = None

    # ---------- Metrics ----------
    emit_metric("slippage_bps_est", float(slip_bps), {"symbol": symbol, "market": market})
    emit_metric("signal_quality", float(quality), {"symbol": symbol, "market": market})
    emit_metric("peer_eff_count", float(pinfo.get("eff_count", 0)), {"symbol": symbol, "market": market})

    return feedback_text, chart_url, stats, style_type, rank_percentile, bench_ret, ai_msg

# =========================================================
# Endpoint wrapper with storage/upsert & DLQ
# =========================================================
def fetch_trade(trade_id: int) -> Optional[Dict[str, Any]]:
    """
    Simple fetch wrapper from trade_history.
    """
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

def auto_trade_feedback(
    trade_id: int,
    user_id: str,
    selected_tone: str = "friendly",
    use_llm: bool = False
) -> Tuple[str, Optional[str], Optional[str], Dict[str, Any]]:
    """
    Top-level callable:
      returns (feedback_text, chart_url, ai_text, summary_stats)
    Side effects:
      - Uploads chart to storage bucket (public URL)
      - Upserts summary to 'trade_feedback' table; DLQ on persistent failure
    """
    trade = fetch_trade(trade_id)
    if not trade:
        raise ValueError("trade not found")
    user = fetch_and_normalize_user(user_id)
    if not user:
        raise ValueError("user not found")

    # Normalize market just in case
    m = (trade.get("market") or "").upper()
    if m in ["KRX", "KOSPI", "KOSDAQ"]:
        trade["market"] = "KR"
    elif m in ["NASDAQ", "NYSE", "AMEX", "US"]:
        trade["market"] = "US"
    else:
        trade["market"] = m or "US"

    logger.info("==== 입력값 확인 ====")
    logger.info(f"version: {VERSION}")
    logger.info(f"trade_id: {trade_id} user_id: {user_id}")
    logger.info(
        f"trade(m): {{'id': {trade.get('id')}, 'symbol': {trade.get('symbol')}, 'market': {trade.get('market')}, "
        f"'action': {trade.get('action')}, 'price': {trade.get('price')}, 'qty': {trade.get('qty')}, "
        f"'commission': {trade.get('commission')}, 'trade_time': {trade.get('trade_time')}, "
        f"'broker': {trade.get('broker')}, 'account_type': {trade.get('account_type')}, 'currency': {trade.get('currency')}}}"
    )
    logger.info(f"user: {_mask_user(user)}")

    fb, img, stats, stype, r, bench, ai = analyze_and_feedback(
        trade, user, service_config, selected_tone, use_llm
    )

    clean_stats = _sanitize_for_json(stats)
    payload = _sanitize_for_json({
        "user_id": user_id,
        "trade_id": trade_id,
        "feedback_message": fb,
        "chart_url": img,
        "summary_stats": clean_stats,
        "style_type": stype,
        "rank_percentile": None if r is None else f"~{int(round(r))}퍼센타일",
        "benchmark_return": bench,
        "ai_coaching": ai,
        "selected_tone": selected_tone,
        "created_at": dt.datetime.now().isoformat(),
    })

    # Persist feedback with upsert; DLQ on failure
    try:
        supabase.table("trade_feedback").upsert(payload, on_conflict="trade_id").execute()
    except Exception as e:
        logger.warning(f"[store] feedback upsert failed, fallback to insert: {e}")
        try:
            supabase.table("trade_feedback").insert(payload).execute()
        except Exception as e2:
            logger.error(f"[store] feedback insert failed: {e2}")
            try:
                supabase.table("feedback_dead_letter").insert({
                    "trade_id": trade_id, "user_id": user_id, "payload": payload, "error": str(e2),
                    "created_at": dt.datetime.now().isoformat()
                }).execute()
                logger.error("[store] DLQ insert success.")
            except Exception as e3:
                logger.error(f"[store] DLQ insert failed: {e3}")

    return fb, img, ai, clean_stats

# =========================================================
# Batch feedback extensions (a~e)
# =========================================================
def _attach_virtual_product(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    (a) 가상 product 필드 부여: DB 스키마 변경 없이 런타임에서 라우팅용 분류를 추가.
    """
    out = []
    for r in rows:
        sym = (r.get("symbol") or "").upper()
        mkt = (r.get("market") or "").upper()
        product = None
        if mkt == "KR":
            product = "KR_STOCK"
        elif mkt == "US":
            if any(sym.endswith(suf) for suf in (".P", "-P")):
                product = "US_PREFERRED"
            elif sym.endswith("W"):
                product = "US_WARRANT"
            else:
                product = "US_STOCK"
        else:
            product = "OTHER"

        r2 = dict(r)
        r2["product"] = product
        out.append(r2)
    return out

def fetch_trades_by_filter(
    user_id: str,
    start_iso: Optional[str] = None,
    end_iso: Optional[str] = None,
    markets: Optional[List[str]] = None,
    symbols: Optional[List[str]] = None,
    actions: Optional[List[str]] = None,
    limit: int = 2000,
) -> List[Dict[str, Any]]:
    """
    (b) 필터형 조회. trade_history만 사용 (새 테이블/컬럼 없이).
    """
    try:
        q = supabase.table("trade_history").select("*").eq("user_id", user_id).order("trade_time", desc=False)

        if start_iso:
            q = q.gte("trade_time", start_iso)
        if end_iso:
            q = q.lte("trade_time", end_iso)
        if markets:
            mk = []
            for m in markets:
                mm = (m or "").upper()
                if mm in ("KRX", "KOSPI", "KOSDAQ"): mm = "KR"
                elif mm in ("NASDAQ","NYSE","AMEX","US"): mm = "US"
                mk.append(mm)
            q = q.in_("market", list(set(mk)))
        if symbols:
            q = q.in_("symbol", symbols)
        if actions:
            acts = [a.lower() for a in actions]
            q = q.in_("action", acts)

        if limit:
            q = q.limit(limit)

        res = q.execute()
        return res.data or []
    except Exception as e:
        logger.error(f"fetch_trades_by_filter failed: {e}")
        return []

def analyze_many(
    rows: List[Dict[str, Any]],
    user: Dict[str, Any],
    cfg: Dict[str, Any],
    fast: bool = True
) -> List[Dict[str, Any]]:
    """
    (c) 다건 분석 래퍼: 기존 analyze_and_feedback을 그대로 호출하되,
        fast=True이면 LLM/차트 비활성화해 경량화.
    반환: per-trade 요약 리스트
    """
    results = []
    for r in rows:
        try:
            m = (r.get("market") or "").upper()
            if m in ["KRX", "KOSPI", "KOSDAQ"]:
                r["market"] = "KR"
            elif m in ["NASDAQ", "NYSE", "AMEX", "US"]:
                r["market"] = "US"
            else:
                r["market"] = m or "US"

            fb, img, stats, stype, rank, bench_ret, ai = analyze_and_feedback(
                trade=r,
                user=user,
                cfg=cfg,
                selected_tone=user.get("preferred_tone","friendly"),
                use_llm=(False if fast else LLM_ENABLED_DEFAULT),
                generate_chart=(False if fast else True),
            )
            results.append({
                "trade_id": r.get("id"),
                "symbol": r.get("symbol"),
                "market": r.get("market"),
                "action": r.get("action"),
                "price": r.get("price"),
                "qty": r.get("qty"),
                "trade_time": r.get("trade_time"),
                "feedback": fb,
                "rank_percentile": rank,
                "benchmark_return_pct": bench_ret,
                "chart_url": (img if not fast else None),
                "style_type": stype,
                "stats": _sanitize_for_json(stats),
            })
        except Exception as e:
            logger.warning(f"[batch] analyze fail trade_id={r.get('id')}: {e}")
    return results

def aggregate_batch_results(
    rows: List[Dict[str, Any]],
    group_by: str = "none"  # "none"|"day"|"symbol"|"product"|"period"
) -> Dict[str, Any]:
    """
    (d) 종합 요약 생성. 메모리 내 계산만.
    - P&L은 benchmark_return_pct(%)를 price*qty에 곱해 금액으로 근사.
    - 히스토그램은 rank_percentile을 사용 (피어 대비 체결가 분포).
    """
    if not rows:
        return {"overview": {}, "by_group": {}, "histogram": {}}

    df = pd.DataFrame(rows)
    for col in ["price","qty","benchmark_return_pct","rank_percentile"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    notional = (df["price"] * df["qty"]).fillna(0.0)
    pnl_amt = (notional * (df["benchmark_return_pct"].fillna(0.0) / 100.0)).rename("pnl_amt")
    df["pnl_amt"] = pnl_amt

    overview = {
        "num_trades": int(len(df)),
        "sum_pnl": float(df["pnl_amt"].sum()),
        "avg_pnl": float(df["pnl_amt"].mean()) if len(df) else 0.0,
        "winrate": float((df["pnl_amt"] > 0).mean()) if len(df) else 0.0,
        "expectancy": float(df["pnl_amt"].mean()) if len(df) else 0.0,
        "median_peer_percentile": float(df["rank_percentile"].median()) if "rank_percentile" in df.columns else None,
    }

    # 그룹 키
    gb_key = None
    if group_by == "day":
        df["day"] = pd.to_datetime(df["trade_time"]).dt.date
        gb_key = "day"
    elif group_by == "symbol":
        gb_key = "symbol"
    elif group_by == "product":
        gb_key = "product"
    elif group_by == "period":
        df["period"] = pd.to_datetime(df["trade_time"]).dt.to_period("W").astype(str)
        gb_key = "period"

    by_group = {}
    if gb_key and gb_key in df.columns:
        g = df.groupby(gb_key, dropna=False)
        agg = g.agg(
            num_trades=("trade_id","count"),
            sum_pnl=("pnl_amt","sum"),
            avg_pnl=("pnl_amt","mean"),
            winrate=("pnl_amt", lambda s: float((s>0).mean())),
            median_peer_percentile=("rank_percentile","median")
        ).reset_index()
        by_group = {str(row[gb_key]): {
                        "num_trades": int(row["num_trades"]),
                        "sum_pnl": float(row["sum_pnl"]),
                        "avg_pnl": float(row["avg_pnl"]),
                        "winrate": float(row["winrate"]),
                        "median_peer_percentile": (None if pd.isna(row["median_peer_percentile"]) else float(row["median_peer_percentile"]))
                    }
                    for _, row in agg.iterrows()}

    # 퍼센타일 히스토그램 (0~100)
    hist = {}
    if "rank_percentile" in df.columns:
        bins = list(range(0, 101, 10))
        cut = pd.cut(df["rank_percentile"].dropna(), bins=bins, include_lowest=True, right=True)
        hist = cut.value_counts().sort_index().to_dict()
        hist = {f"{interval.left:.0f}-{interval.right:.0f}": int(cnt) for interval, cnt in hist.items()}

    return {"overview": overview, "by_group": by_group, "histogram": hist}

def build_cum_pnl_series(rows: List[Dict[str, Any]]) -> List[Tuple[str, float]]:
    """
    (e) 시뮬 누적 P&L 시리즈 (시간순). 차트 파일은 만들지 않고 데이터만 반환.
    """
    if not rows:
        return []
    df = pd.DataFrame(rows)
    for col in ["price","qty","benchmark_return_pct"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["trade_time"] = pd.to_datetime(df["trade_time"])
    df = df.sort_values("trade_time")
    df["pnl_amt"] = (df["price"] * df["qty"]).fillna(0.0) * (df["benchmark_return_pct"].fillna(0.0)/100.0)
    df["cum_pnl"] = df["pnl_amt"].cumsum()
    return [(ts.isoformat(), float(v)) for ts, v in zip(df["trade_time"], df["cum_pnl"])]

def auto_trade_feedback_batch(
    user_id: str,
    start_iso: Optional[str] = None,
    end_iso: Optional[str] = None,
    markets: Optional[List[str]] = None,
    symbols: Optional[List[str]] = None,
    actions: Optional[List[str]] = None,
    group_by: str = "none",          # "none"|"day"|"symbol"|"product"|"period"
    fast: bool = True
) -> Dict[str, Any]:
    """
    최상위 배치 엔드포인트.
    - 입력 필터로 trade_history 조회 → 가상 product 부여 → analyze_many(fast 모드) → 집계/히스토그램/누적P&L
    - DB 스키마 변경 없음.
    """
    user = fetch_and_normalize_user(user_id)
    if not user:
        raise ValueError("user not found")

    rows = fetch_trades_by_filter(
        user_id=user_id,
        start_iso=start_iso,
        end_iso=end_iso,
        markets=markets,
        symbols=symbols,
        actions=actions,
        limit=5000,
    )
    rows = _attach_virtual_product(rows)
    per_trade = analyze_many(rows, user, service_config, fast=fast)
    summary  = aggregate_batch_results(per_trade, group_by=group_by)
    cum_line = build_cum_pnl_series(per_trade)

    return {
        "filter": {
            "user_id": user_id, "start": start_iso, "end": end_iso,
            "markets": markets, "symbols": symbols, "actions": actions, "group_by": group_by, "fast": fast
        },
        "per_trade": per_trade,         # 각 트레이드 요약 리스트
        "summary": summary,             # overview/by_group/histogram
        "cum_pnl_series": cum_line,     # (iso_time, cum_pnl) 리스트
    }
