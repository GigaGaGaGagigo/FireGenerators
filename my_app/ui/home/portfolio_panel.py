import os, random
import pandas as pd
import streamlit as st
from .utils import html
from home.db import fetch_trades_by_user_id

def market_to_ccy(market: str) -> str:
    return "USD" if (market or "").upper() == "US" else "KRW"

def compute_positions_fifo(trades: list[dict]):
    lots = {}
    last_price = {}
    market_map = {}
    realized_by_ccy = {"USD": 0.0, "KRW": 0.0}
    for t in trades:
        sym = t["symbol"]; px = float(t["price"]); q = float(t["qty"]); act = t["action"].lower()
        market_map[sym] = (t.get("market") or "").upper() or "US"
        last_price[sym] = px
        if act == "buy":
            lots.setdefault(sym, []).append([q, px])
        elif act == "sell":
            remain = q
            for lot in lots.get(sym, []):
                if remain <= 0: break
                take = min(lot[0], remain)
                realized_by_ccy[market_to_ccy(market_map[sym])] += (px - lot[1]) * take
                lot[0] -= take
                remain -= take
            if sym in lots:
                lots[sym] = [l for l in lots[sym] if l[0] > 1e-12]
    positions = {}
    for sym, lst in lots.items():
        qty = sum(q for q, _ in lst)
        if qty <= 1e-12: continue
        cost = sum(q * p for q, p in lst)
        avg = cost / qty
        lp = last_price.get(sym, avg)
        ccy = market_to_ccy(market_map.get(sym, "US"))
        positions[sym] = {"market": market_map.get(sym, "US"), "currency": ccy,
                          "qty": qty, "avg_cost": avg, "last_price": lp,
                          "cost_native": cost, "mv_native": qty * lp}
    return positions, realized_by_ccy

def convert_amt(x: float, from_ccy: str, base_ccy: str, usdkrw: float) -> float:
    if from_ccy == base_ccy: return x
    if from_ccy == "USD" and base_ccy == "KRW": return x * usdkrw
    if from_ccy == "KRW" and base_ccy == "USD": return x / usdkrw
    return x

def make_usdkrw_series(days: int = 90, start: float = 1350.0):
    vals = [float(start)]
    for _ in range(days - 1):
        step = random.uniform(-7, 7)
        vals.append(max(900.0, min(2200.0, vals[-1] + step)))
    idx = pd.date_range(end=pd.Timestamp.today().normalize(), periods=days, freq="D")
    return pd.DataFrame({"USDKRW": vals}, index=idx)

def render_portfolio_panel(user_id: str):
    trades = fetch_trades_by_user_id(user_id)
    html(f'<div class="port-card"><div class="port-title">📊 현재 자산 <span class="badge-soft">user_id: {user_id or "—"}</span></div>')
    default_rate = float(os.getenv("FX_USDKRW") or os.getenv("USDKRW") or 1350)
    c1, c2, _ = st.columns([1, 1, 2])
    base_ccy = c1.selectbox("기준 통화", ["KRW", "USD"], index=0, key="base_ccy_home")
    usdkrw = c2.number_input("환율 (1 USD = KRW)", min_value=500.0, max_value=5000.0, value=default_rate, step=1.0, key="usdkrw_home")

    if not trades:
        html('<div class="empty">거래 내역이 없습니다. 보유 포지션이 없어요.</div></div>')
        return

    positions, realized_by_ccy = compute_positions_fifo(trades)
    invested = sum(convert_amt(p["cost_native"], p["currency"], base_ccy, usdkrw) for p in positions.values())
    mv = sum(convert_amt(p["mv_native"], p["currency"], base_ccy, usdkrw) for p in positions.values())
    realized = sum(convert_amt(v, k, base_ccy, usdkrw) for k, v in realized_by_ccy.items())
    unrealized = mv - invested

    html(f"""
    <div class="kpi-row">
      <div class="kpi"><small>투입 원금 ({base_ccy})</small><b>{invested:,.2f}</b></div>
      <div class="kpi"><small>평가 금액 ({base_ccy})</small><b>{mv:,.2f}</b></div>
      <div class="kpi"><small>실현 손익 ({base_ccy})</small><b class="{'pos' if realized>=0 else 'neg'}">{realized:+,.2f}</b></div>
      <div class="kpi"><small>평가 손익 ({base_ccy})</small><b class="{'pos' if unrealized>=0 else 'neg'}">{unrealized:+,.2f}</b></div>
    </div>
    """)

    rows = []
    for sym, p in positions.items():
        val = convert_amt(p["mv_native"], p["currency"], base_ccy, usdkrw)
        cost = convert_amt(p["cost_native"], p["currency"], base_ccy, usdkrw)
        unpp = ((val - cost) / cost * 100.0) if cost else 0.0
        rows.append({
            "Symbol": sym, "Market": p["market"], "Currency": p["currency"],
            "Qty": round(p["qty"], 4), "Avg Cost": round(p["avg_cost"], 4),
            "Last Px*": round(p["last_price"], 4),
            f"Cost ({base_ccy})": round(cost, 2),
            f"Value ({base_ccy})": round(val, 2),
            "Unreal P/L(%)": round(unpp, 2),
        })
    if rows:
        st.dataframe(pd.DataFrame(rows).sort_values(f"Value ({base_ccy})", ascending=False),
                     hide_index=True, use_container_width=True)
        html(f'<div class="table-hint">* Last Px: 마지막 체결가 기준 (실시간 연동 전).  환율: 1 USD = {usdkrw:,.2f} KRW</div>')
    else:
        html('<div class="empty" style="margin-top:8px;">보유 포지션이 없습니다.</div>')
    html('</div>')

def render_fx_card(default_rate: float):
    html('<div class="subcard"><h4>💱 환율 (USD/KRW)</h4>')
    df = make_usdkrw_series(90, default_rate)
    st.line_chart(df, height=160, use_container_width=True)
    html('</div>')

def render_trades_timeline(user_id: str):
    trades = fetch_trades_by_user_id(user_id)
    html('<div class="subcard"><h4>🧾 주식 체결 기록</h4>')
    if not trades:
        html('<div class="empty">체결 기록이 없습니다.</div></div>')
        return
    df = pd.DataFrame(trades)
    df["trade_time"] = pd.to_datetime(df["trade_time"])
    df["date"] = df["trade_time"].dt.date
    agg = df.pivot_table(index="date", columns="action", values="qty", aggfunc="sum").fillna(0)
    st.bar_chart(agg, height=160, use_container_width=True)
    df_show = (df.sort_values("trade_time", ascending=False)
                 .loc[:, ["trade_time","market","symbol","action","price","qty"]]
                 .rename(columns={"trade_time":"Time","market":"Mkt","symbol":"Sym","action":"Side","price":"Price","qty":"Qty"}))
    st.dataframe(df_show.head(10), hide_index=True, use_container_width=True)
    html('</div>')
