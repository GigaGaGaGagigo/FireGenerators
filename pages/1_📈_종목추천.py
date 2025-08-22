import streamlit as st
import pandas as pd
import yfinance as yf
import json

from utils.llm_client import recommend_stocks_via_llm

# 카드 스타일(원하는대로 조정 가능)
_CARD_CSS = """
<style>
.stock-card{
  border:1px solid #333; border-radius:12px; padding:16px; margin-bottom:16px;
  background: rgba(255,255,255,0.03);
}
.stock-card h3{margin:0 0 8px 0;}
.stock-card a{font-weight:600; text-decoration:none;}
</style>
"""

def _to_table_md(df: pd.DataFrame) -> str:
    cols = ["ticker","sector","currentPrice","trailingPE","priceToBook"]
    safe = df[cols].copy().fillna("")
    return safe.to_markdown(index=False)

def _normalize_recs(recs, fallback):
    """LLM 응답을 일관된 형태로 정규화"""
    norm = []
    for r in (recs or []):
        if isinstance(r, dict):
            t = (r.get("ticker") or r.get("symbol") or "").strip().upper()
            reason = r.get("reason") or r.get("why") or r.get("추천이유") or "추천 이유 없음"
            url = r.get("url")
        else:
            t = str(r).strip().upper()
            reason = "추천 이유 없음"
            url = None
        if t:
            norm.append({"ticker": t, "reason": reason, "url": url})
    if not norm:
        norm = [{"ticker": t, "reason": "기본 추천", "url": None} for t in fallback]
    return norm[:3]

def main():
    st.set_page_config(page_title="내 맞춤 주식 추천", layout="wide")
    st.markdown(_CARD_CSS, unsafe_allow_html=True)
    st.title("📈 내 맞춤 주식 추천")

    # 1) 사용자 프로필: secrets.toml의 USER_PROFILE_JSON에서 바로 로드
    user_profile = json.loads(st.secrets["USER_PROFILE_JSON"])
    st.sidebar.subheader("👤 투자자 프로필 (fixed)")
    st.sidebar.json(user_profile)

    # 2) 예시용 재무 메타 (yfinance)
    demo_tickers = ["AAPL","MSFT","GOOGL","AMZN","TSLA"]
    meta_rows = []
    for t in demo_tickers:
        try:
            info = getattr(yf.Ticker(t), "info", {}) or {}
        except Exception:
            info = {}
        meta_rows.append({
            "ticker": t,
            "sector": info.get("sector",""),
            "currentPrice": info.get("currentPrice") or info.get("regularMarketPrice"),
            "trailingPE": info.get("trailingPE"),
            "priceToBook": info.get("priceToBook"),
        })
    fin_df = pd.DataFrame(meta_rows)
    st.subheader("투자에 참조될 종목 재무정보 샘플")
    st.dataframe(fin_df, use_container_width=True)

    # RAG/LLM에 줄 테이블(마크다운) 준비
    table_md = _to_table_md(fin_df)

    # 3) 추천하기 버튼 → LLM 호출 → 카드 3개 렌더
    if st.button("🚀 추천하기"):
        with st.spinner("추천 생성 중…"):
            try:
                recs = recommend_stocks_via_llm(table_md, user_profile, top_n=3)
            except Exception as e:
                st.error(f"LLM 추천 호출 실패: {e}")
                recs = []

        norm_recs = _normalize_recs(recs, fallback=demo_tickers[:3])

        cols = st.columns(3, gap="large")
        for i, item in enumerate(norm_recs):
            t = item["ticker"]
            try:
                info = getattr(yf.Ticker(t), "info", {}) or {}
            except Exception:
                info = {}
            longName = info.get("longName") or t
            sector = info.get("sector") or "-"
            price  = info.get("currentPrice") or info.get("regularMarketPrice")
            url    = item["url"] or f"https://finance.yahoo.com/quote/{t}"

            with cols[i]:
                st.markdown(f"""
<div class="stock-card">
  <h3>{longName} ({t})</h3>
  <p>섹터: {sector} | 현재가: {price if price is not None else 'N/A'}</p>
  <p>{item["reason"]}</p>
  <a href="{url}" target="_blank">상세 정보 보기 →</a>
</div>
""", unsafe_allow_html=True)

if __name__ == "__main__":
    main()