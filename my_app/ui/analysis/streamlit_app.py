# app.py
# -*- coding: utf-8 -*-
import os
from datetime import datetime, timedelta, date
from typing import Optional, List, Dict, Any, Tuple, Sequence, Union

import streamlit as st
from dotenv import load_dotenv
import pandas as pd
from supabase import create_client

# === 분석 모듈(기존 로직 유지) ===
from my_app.ui.analysis.auto_trade_feedback import (
    auto_trade_feedback,
    auto_trade_feedback_batch,
)

# === OpenAI (LLM 코칭을 여기서 직접 호출) ===
try:
    from openai import OpenAI
except Exception:
    OpenAI = None  # 라이브러리 미설치 시 우회

# ---------------------------------------
# 기본 설정
# ---------------------------------------
load_dotenv()
st.set_page_config(
    page_title="🔥 FIRE generator",
    page_icon="🔥",
    layout="wide"
)

# === 주황–노랑 테마 CSS (사이드바 제거 + 카드/버튼 컬러) ===
THEME_CSS = """
<style>

/* container width/padding */
main .block-container { padding-top: 1.2rem; padding-bottom: 3rem; max-width: 1400px; }

/* palette */
:root {
  --pri: #ff8a00;       /* 주황 */
  --pri-dark: #e07a00;  /* 어두운 주황 */
  --pri-soft: rgba(255, 178, 36, 0.15); /* 연노랑/오렌지 배경 */
  --accent: #ffd54d;    /* 노랑 포인트 */
}

/* headings accent underline */
h3, h4, h5 {
  position: relative;
}
h3:after, h4:after, h5:after {
  content: ""; position: absolute; left: 0; bottom: -6px; width: 48px; height: 4px;
  border-radius: 999px;
}

/* buttons (primary) */
button[kind="primary"] {
  background: var(--pri) !important;
  border: 1px solid var(--pri-dark) !important;
}
button[kind="primary"]:hover { filter: brightness(0.95); }

/* card */
.card {
  border: 1px solid rgba(255,138,0,0.25);
  border-radius: 16px;
  padding: 14px 16px;
  background: linear-gradient(180deg, #fff, var(--pri-soft));
  box-shadow: 0 6px 22px rgba(255,138,0,0.10);
}
.kpi   { font-size: 28px; font-weight: 800; line-height: 1; margin-bottom: 6px; color: #222; }
.kpi-sub { color: #7a6a4f; font-size: 12px; }

/* badge */
.badge {
  display:inline-block; padding: 2px 10px; border-radius: 999px; font-size: 11px; font-weight: 600;
  background: var(--accent); color: #4b3b00; margin-left: 8px; border: 1px solid rgba(0,0,0,0.08);
}

/* table header tint */
thead tr th { background: rgba(255,138,0,0.08); }
</style>
"""
st.markdown(THEME_CSS, unsafe_allow_html=True)

# ---------------------------------------
# Supabase
# ---------------------------------------
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("❗환경변수 SUPABASE_URL / SUPABASE_KEY 가 필요합니다.")
    st.stop()
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------------------------------------
# LLM 유틸
# ---------------------------------------
def _openai_client_or_none():
    """환경과 라이브러리가 갖춰진 경우 OpenAI 클라이언트 반환."""
    if OpenAI is None:
        return None, "openai-python 미설치"
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None, "OPENAI_API_KEY 미설정"
    try:
        client = OpenAI(api_key=api_key)
        return client, None
    except Exception as e:
        return None, f"OpenAI 초기화 실패: {e}"

def gen_ai_coaching_message(context: Dict[str, Any], tone: str = "friendly") -> Optional[str]:
    """
    context: 거래/요약 정보 등. (symbol, action, price, qty, stats 등 포함 가능)
    tone: friendly/expert/youth/serious
    """
    client, err = _openai_client_or_none()
    if client is None:
        # LLM 비활성화 사유를 로그/화면에 남기지 않고 None만 반환 (UI에서 fallback 처리)
        return None

    # 모델명은 존재하는 기본값으로. 필요시 환경변수로 덮어쓰세요.
    model = os.getenv("OPENAI_MODEL", "gpt-5")

    # 시스템 & 사용자 프롬프트(간결)
    sys = (
        "You are a trading coach. Provide concise, practical feedback for a single stock trade. "
        "Use bullet points, reflect risk management, entry context (trend/volatility), and next steps. "
        "Language: Korean."
    )
    user = (
        f"[코칭 톤] {tone}\n"
        f"[심볼] {context.get('symbol')}\n"
        f"[액션] {context.get('action')}\n"
        f"[가격/수량] {context.get('price')} / {context.get('qty')}\n"
        f"[거래시각] {context.get('trade_time')}\n"
        f"[요약] {context.get('feedback','')}\n"
        f"[통계] {context.get('stats','')}\n"
        "위 정보를 바탕으로 핵심만 짧게 피드백해줘."
    )

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": sys},
                {"role": "user", "content": user},
            ],     
            temperature=0.6,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception:
        # 모델명 오타/권한 문제 등 모든 예외는 UI에서 자연스럽게 룰-기반으로 대체
        return None

# ---------------------------------------
# 유틸 & 데이터 로더
# ---------------------------------------
@st.cache_data(ttl=60)
def fetch_user_profile(user_id: str) -> Optional[Dict[str, Any]]:
    try:
        return supabase.table("profiles").select("*").eq("id", user_id).single().execute().data
    except Exception:
        return None

@st.cache_data(ttl=120)
def fetch_user_traded_symbols(user_id: str) -> List[str]:
    try:
        res = supabase.table("trade_history").select("symbol").eq("user_id", user_id).execute()
        syms = sorted(set([r["symbol"] for r in (res.data or []) if r.get("symbol")]))
        return syms
    except Exception:
        return []

@st.cache_data(ttl=60)
def fetch_user_trades(user_id: str, start_iso: Optional[str]=None, end_iso: Optional[str]=None) -> pd.DataFrame:
    try:
        q = supabase.table("trade_history").select("*").eq("user_id", user_id).order("trade_time", desc=True)
        if start_iso: q = q.gte("trade_time", start_iso)
        if end_iso:   q = q.lte("trade_time", end_iso)
        rows = q.execute().data or []
        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame([])

def date_range_to_iso(dr: Sequence[Union[date, datetime]]) -> Tuple[Optional[str], Optional[str]]:
    """st.date_input이 (date, date) 튜플을 반환하므로 그 형태까지 허용."""
    if not dr or len(dr) != 2:
        return None, None
    s, e = dr
    if isinstance(s, datetime):
        s = s.date()
    if isinstance(e, datetime):
        e = e.date()
    return f"{s.isoformat()}T00:00:00", f"{e.isoformat()}T23:59:59"

def render():
    # ---------------------------------------
    # 상단 헤더
    # ---------------------------------------
    colL, colR = st.columns([0.65, 0.35])
    with colL:
        st.markdown("### 📊 관심 종목 분석")
        st.caption("분석 엔진 + LLM 코칭으로 거래를 더 명확하게 복기하세요.")
    with colR:
        PERIOD_PRESET = st.selectbox("기간 선택", ["최근 7일", "최근 30일", "사용자 지정"], index=1)
        if PERIOD_PRESET == "사용자 지정":
            default_start = (datetime.today() - timedelta(days=30)).date()
            default_end = datetime.today().date()
            user_range = st.date_input("분석 기간", (default_start, default_end))
        else:
            days = 7 if PERIOD_PRESET == "최근 7일" else 30
            user_range = ((datetime.today()-timedelta(days=days)).date(), datetime.today().date())
        tone_global = st.selectbox("코칭 톤", ["friendly", "expert", "youth", "serious"], index=0)
        # use_llm_global = st.toggle("LLM 코칭 활성화", value=True, help="키/환경이 없으면 자동 스킵")

    user_id = st.session_state.user.id
    # user_id = st.text_input("User ID", value=os.getenv("FIXED_USER_ID",""), help="프로필·거래를 이 ID로 조회합니다.")
    # if not user_id:
    #     st.info("먼저 User ID 를 입력하세요.")
    #     st.stop()
    # profile = fetch_user_profile(user_id)
    # if not profile:
    #     st.error("해당 User ID의 프로필을 찾을 수 없습니다.")
    #     st.stop()

    # ---------------------------------------
    # 탭
    # ---------------------------------------
    tab1, tab2, tab3 = st.tabs(["개별 종목 피드백", "기간별 전체 피드백", "단일 거래 피드백"])

    # =========================================================
    # 탭 1: 개별 종목 피드백
    # =========================================================
    with tab1:
        st.markdown("#### 개별 종목 피드백 <span class='badge'>Symbol-wise</span>", unsafe_allow_html=True)
        syms = fetch_user_traded_symbols(user_id)
        if not syms:
            st.warning("해당 사용자 거래 종목이 없습니다.")
        else:
            c1, c2, c3 = st.columns([0.4, 0.3, 0.3])
            with c1:
                symbol = st.selectbox("종목 선택", syms)
            with c2:
                action_filter = st.multiselect("액션", ["buy","sell"], default=["buy","sell"])
            with c3:
                st.write("")
                run_btn = st.button("분석 실행", type="primary", use_container_width=True)

            start_iso, end_iso = date_range_to_iso(user_range)
            st.caption(f"분석 기간: {start_iso[:10]} ~ {end_iso[:10]}")

            if run_btn:
                with st.spinner("AI가 회원님의 프로필에 맞는 관심 종목을 분석중입니다..."):
                    try:
                        batch = auto_trade_feedback_batch(
                            user_id=user_id,
                            start_iso=start_iso,
                            end_iso=end_iso,
                            markets=None,
                            symbols=[symbol],
                            actions=action_filter or None,
                            group_by="symbol",
                            fast=False  # 차트/LLM 허용 (배치 결과에는 ai_text가 없음을 감안)
                        )
                    except Exception as e:
                        st.error(f"분석 실패: {e}")
                        batch = None

                if batch and batch.get("per_trade"):
                    summary = batch.get("summary", {}).get("overview", {})
                    k1, k2, k3, k4 = st.columns(4)
                    with k1: st.markdown(f'<div class="card"><div class="kpi">{int(summary.get("num_trades",0))}</div><div class="kpi-sub">거래 건수</div></div>', unsafe_allow_html=True)
                    with k2: st.markdown(f'<div class="card"><div class="kpi">{summary.get("sum_pnl",0.0):.0f}</div><div class="kpi-sub">합계 P&L</div></div>', unsafe_allow_html=True)
                    with k3: st.markdown(f'<div class="card"><div class="kpi">{summary.get("avg_pnl",0.0):.0f}</div><div class="kpi-sub">평균 P&L</div></div>', unsafe_allow_html=True)
                    with k4: st.markdown(f'<div class="card"><div class="kpi">{summary.get("winrate",0.0):.0%}</div><div class="kpi-sub">승률</div></div>', unsafe_allow_html=True)

                    st.markdown("##### 거래 목록")
                    df = pd.DataFrame(batch["per_trade"])
                    disp_cols = ["trade_id","trade_time","symbol","action","price","qty","benchmark_return_pct","rank_percentile","chart_url","style_type"]
                    st.dataframe(df[disp_cols], use_container_width=True, hide_index=True)

                    # ---- 최근 거래 LLM 코칭: app.py에서 직접 생성(모델명 오류 방지) ----
                    latest = batch["per_trade"][-1]
                    st.markdown("##### AI 코칭(최근 거래)")
                    co1, co2 = st.columns([0.55, 0.45])

                    # 기존 함수가 반환하는 ai_text2는 무시하고, 여기서 재생성
                    fb_text2, chart2, _ai_text2_ignored, stats2 = None, None, None, {}
                    try:
                        fb_text2, chart2, _ai_text2_ignored, stats2 = auto_trade_feedback(
                            trade_id=int(latest["trade_id"]),
                            user_id=user_id,
                            selected_tone=tone_global,
                            use_llm=False  # 내부 LLM 비활성 (모델명 문제 회피)
                        )
                    except Exception as e:
                        st.warning(f"기본 피드백/차트 생성 중 오류: {e}")

                    with co1:
                        ai_text2 = None
                        if True:
                            ctx = {
                                **latest,
                                "stats": stats2,
                            }
                            ai_text2 = gen_ai_coaching_message(ctx, tone=tone_global)

                        if ai_text2:
                            st.markdown(f'<div class="card">{ai_text2}</div>', unsafe_allow_html=True)
                            st.success("✅ LLM 코칭 메시지 생성이 완료되었습니다.")
                            st.toast("✅ LLM 코칭 메시지 생성 완료", icon="✅")
                        else:
                            # LLM 실패/비활성 시 룰 기반 피드백으로 대체
                            fb_fallback = (latest.get("feedback") or fb_text2 or "피드백이 없습니다.")
                            st.markdown(f'<div class="card">{fb_fallback}</div>', unsafe_allow_html=True)

                    with co2:
                        img = latest.get("chart_url") or chart2
                        if img:
                            st.image(img, caption="분석 차트", use_column_width=True)
                        else:
                            st.info("차트 이미지가 없습니다.")
                else:
                    st.info("분석 결과가 없습니다.")

    # =========================================================
    # 탭 2: 기간별 전체 피드백
    # =========================================================
    with tab2:
        st.markdown("#### 기간별 전체 피드백 <span class='badge'>Portfolio</span>", unsafe_allow_html=True)
        c1, c2 = st.columns([0.75, 0.25])
        with c2:
            run_all = st.button("전체 분석 실행", type="primary", use_container_width=True)
        with c1:
            st.caption("기간 내 모든 거래에 대한 요약/히스토/누적 P&L")

        start_iso, end_iso = date_range_to_iso(user_range)

        if run_all:
            with st.spinner("AI가 회원님의 프로필에 맞는 관심 종목을 분석중입니다..."):
                try:
                    batch = auto_trade_feedback_batch(
                        user_id=user_id,
                        start_iso=start_iso,
                        end_iso=end_iso,
                        markets=None,
                        symbols=None,
                        actions=None,
                        group_by="symbol",
                        fast=True  # 빠르게
                    )
                except Exception as e:
                    st.error(f"분석 실패: {e}")
                    batch = None

            if batch:
                overview = batch.get("summary",{}).get("overview",{})
                by_group = batch.get("summary",{}).get("by_group",{})
                hist = batch.get("summary",{}).get("histogram",{})
                per_trade = pd.DataFrame(batch.get("per_trade",[]))

                k1, k2, k3, k4 = st.columns(4)
                with k1: st.markdown(f'<div class="card"><div class="kpi">{int(overview.get("num_trades",0))}</div><div class="kpi-sub">거래 건수</div></div>', unsafe_allow_html=True)
                with k2: st.markdown(f'<div class="card"><div class="kpi">{overview.get("sum_pnl",0.0):.0f}</div><div class="kpi-sub">합계 P&L</div></div>', unsafe_allow_html=True)
                with k3: st.markdown(f'<div class="card"><div class="kpi">{overview.get("avg_pnl",0.0):.0f}</div><div class="kpi-sub">평균 P&L</div></div>', unsafe_allow_html=True)
                with k4: st.markdown(f'<div class="card"><div class="kpi">{overview.get("winrate",0.0):.0%}</div><div class="kpi-sub">승률</div></div>', unsafe_allow_html=True)

                cA, cB = st.columns([0.6, 0.4])
                with cA:
                    st.markdown("##### 종목별 요약")
                    if by_group:
                        df_by = pd.DataFrame.from_dict(by_group, orient="index").reset_index(names=["symbol"])
                        st.dataframe(df_by, use_container_width=True, hide_index=True)
                    else:
                        st.info("그룹 요약이 없습니다.")
                with cB:
                    st.markdown("##### 피어 퍼센타일 히스토")
                    if hist:
                        dfh = pd.DataFrame({"bin": list(hist.keys()), "count": list(hist.values())})
                        st.bar_chart(dfh.set_index("bin"))
                    else:
                        st.info("히스토그램 데이터가 없습니다.")

                with st.expander("거래 상세 목록", expanded=False):
                    if not per_trade.empty:
                        keep = ["trade_id","trade_time","symbol","market","action","price","qty","benchmark_return_pct","rank_percentile","style_type"]
                        st.dataframe(per_trade[keep], use_container_width=True, hide_index=True)
                    else:
                        st.info("표시할 거래가 없습니다.")
            else:
                st.info("분석 결과가 없습니다.")

    # =========================================================
    # 탭 3: 단일 거래 피드백
    # =========================================================
    with tab3:
        st.markdown("#### 단일 거래 피드백 <span class='badge'>Single Trade</span>", unsafe_allow_html=True)
        start_iso, end_iso = date_range_to_iso(user_range)
        trades_df = fetch_user_trades(user_id, start_iso, end_iso)
        if trades_df.empty:
            st.info("해당 기간에 거래가 없습니다.")
        else:
            trades_df["trade_time"] = pd.to_datetime(trades_df["trade_time"])
            show = trades_df[["id","trade_time","symbol","market","action","price","qty","commission"]].sort_values("trade_time", ascending=False)
            st.dataframe(show, use_container_width=True, hide_index=True, height=280)
            trade_id = st.number_input("분석할 trade_id 입력", min_value=int(show["id"].min()), max_value=int(show["id"].max()))
            c1, c2, c3 = st.columns([0.35, 0.35, 0.3])
            with c1:
                btn = st.button("선택 거래 분석", type="primary", use_container_width=True)
            with c2:
                tone3 = st.selectbox("코칭 톤(이 탭 전용)", ["friendly","expert","youth","serious"], index=0)
            with c3:
                llm3 = st.toggle("LLM 코칭", value=True)

            if btn:
                with st.spinner("AI가 회원님의 프로필에 맞는 관심 종목을 분석중입니다..."):
                    try:
                        # 내부 LLM은 끄고, 아래에서 app.py가 직접 코칭 생성
                        fb_text, chart_url, _ai_text_ignored, stats = auto_trade_feedback(
                            trade_id=int(trade_id),
                            user_id=user_id,
                            selected_tone=tone3,
                            use_llm=False
                        )
                    except Exception as e:
                        st.error(f"분석 실패: {e}")
                        fb_text, chart_url, _ai_text_ignored, stats = None, None, None, {}
                        
                st.markdown("##### 규칙 기반 피드백")
                if fb_text:
                    st.markdown(f'<div class="card">{fb_text}</div>', unsafe_allow_html=True)
                else:
                    st.info("피드백이 없습니다.")
                if stats:
                    s_keys = ["stop_price","tp1_price","tp2_price","tp3_price","recommended_size_capped","slippage_bps_est","peer_rank_percentile","signal_quality"]
                    s_view = {k: stats.get(k) for k in s_keys}
                    st.json(s_view)

                # colA, colB = st.columns([0.55, 0.45])
                # with colA:
                #     st.markdown("##### 규칙 기반 피드백")
                #     if fb_text:
                #         st.markdown(f'<div class="card">{fb_text}</div>', unsafe_allow_html=True)
                #     else:
                #         st.info("피드백이 없습니다.")
                #     if stats:
                #         s_keys = ["stop_price","tp1_price","tp2_price","tp3_price","recommended_size_capped","slippage_bps_est","peer_rank_percentile","signal_quality"]
                #         s_view = {k: stats.get(k) for k in s_keys}
                #         st.json(s_view)
                # with colB:
                #     st.markdown("##### 차트")
                #     if chart_url:
                #         st.image(chart_url, use_column_width=True)
                #     else:
                #         st.info("차트 이미지가 없습니다.")
                #     st.markdown("##### AI 코칭")
                #     ai_text = None
                #     if llm3:
                #         # trades_df에서 해당 trade_id 레코드 가져와 컨텍스트 구성
                #         row = trades_df.loc[trades_df["id"] == int(trade_id)]
                #         base_ctx = row.iloc[0].to_dict() if not row.empty else {}
                #         base_ctx.update({"stats": stats, "feedback": fb_text})
                #         ai_text = gen_ai_coaching_message(base_ctx, tone=tone3)

                #     if ai_text:
                #         st.markdown(f'<div class="card">{ai_text}</div>', unsafe_allow_html=True)
                #         st.success("✅ LLM 코칭 메시지 생성이 완료되었습니다.")
                #         st.toast("✅ LLM 코칭 메시지 생성 완료", icon="✅")
                #     else:
                #         if llm3:
                #             st.caption("⚠️ AI 코칭이 제공되지 않았습니다. (OpenAI 키/모델 확인 필요)")
                #         else:
                #             st.caption("LLM 코칭 비활성화 상태입니다.")

# ---------------------------------------
# 앱 실행
# ---------------------------------------
if __name__ == "__main__":
    render()
