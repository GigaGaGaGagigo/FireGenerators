import os
from typing import Optional
import pandas as pd
import random

try:
    import yfinance as yf
except Exception:
    yf = None

def fetch_usd_krw_rate(default: float = None) -> float:
    """
    최근 USD/KRW 종가. 실패 시 .env( FX_USDKRW / USDKRW ) → default → 1350
    """
    if yf:
        try:
            df = yf.Ticker("KRW=X").history(period="1d")
            if not df.empty and "Close" in df:
                return float(df["Close"].iloc[-1])
        except Exception:
            pass
    # .env 폴백
    for k in ("FX_USDKRW", "USDKRW"):
        v = os.getenv(k)
        if v:
            try:
                return float(v)
            except Exception:
                pass
    return float(default if default is not None else 1350.0)

def fetch_usdkrw_series(days: int = 90, fallback_start: Optional[float] = None) -> pd.DataFrame:
    """
    최근 N일 USD/KRW 시계열. yfinance 실패 시 랜덤워크 대체.
    """
    if yf:
        try:
            df = yf.download("KRW=X", period=f"{max(days,7)}d", interval="1d",
                             auto_adjust=False, progress=False)
            if not df.empty and "Close" in df:
                s = df["Close"].tail(days)
                s.index = pd.to_datetime(s.index)
                return pd.DataFrame({"USDKRW": s})
        except Exception:
            pass
    # fallback synthetic
    start = fallback_start or fetch_usd_krw_rate()
    vals = [float(start)]
    for _ in range(days-1):
        step = random.uniform(-7, 7)
        vals.append(max(900.0, min(2200.0, vals[-1] + step)))
    idx = pd.date_range(end=pd.Timestamp.today().normalize(), periods=days, freq="D")
    return pd.DataFrame({"USDKRW": vals}, index=idx)
