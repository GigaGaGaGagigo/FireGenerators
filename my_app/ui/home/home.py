import os
import streamlit as st
from .router import sync_nav_hash_bidirectional, PAGE_KEYS
from .styles import inject_home_styles,render_full_hero
from .utils import html
from .widgets import render_link_card
from .profile_panel import render_user_panel
from .portfolio_panel import render_portfolio_panel, render_fx_card, render_trades_timeline
from .news_panel import render_news_list
from home.db import _get_user_id, fetch_trades_by_user_id

def render():
    sync_nav_hash_bidirectional()
    inject_home_styles()

    # === FULL HERO ===
    rate = None
    try:
        from my_app.home.fx import fetch_usd_krw_rate  # 있으면 사용
        rate = fetch_usd_krw_rate() or None
    except Exception:
        pass
    render_full_hero(rate)

    # 히어로 아래로 스크롤될 위치(앵커)
    html('<div id="dash" class="anchor"></div>')

    # ===== 좌우 2단: 프로필 / 자산 =====

    # 레이아웃: 좌(프로필) / 우(포트폴리오+FX+체결+뉴스)
    user = st.session_state.get("user")
    user_id = (_get_user_id(user)
              or st.session_state.get("user_id")
              or (st.query_params.get("user_id",[None])[0] if hasattr(st,"query_params") else st.experimental_get_query_params().get("user_id",[None])[0])
              or os.getenv("USER_ID"))

    left, right = st.columns([1.15, 1.85], vertical_alignment="top")
    with left:
        render_user_panel()
    with right:
        try:
            from home.fx import fetch_usd_krw_rate
            default_rate = fetch_usd_krw_rate() or 1350.0
        except Exception:
            default_rate = 1350.0

        render_portfolio_panel(user_id)
        top1, top2 = st.columns([1, 1], vertical_alignment="top")
        with top1:
            render_fx_card(default_rate)     # ← 여기!
        with top2:
            render_trades_timeline(user_id)

        # 뉴스
        trades_for_news = fetch_trades_by_user_id(user_id)
        tickers = sorted({t["symbol"] for t in trades_for_news})[:10] if trades_for_news else None
        render_news_list(query="주식 OR 시장 OR 채권 OR 금리 OR 환율", tickers=tickers)

    st.divider()

    # 주요 기능 플로우
    st.subheader("✨ 주요 기능")
    try:
        row1 = st.columns([3,1,3,1,3], vertical_alignment="top")
    except TypeError:
        row1 = st.columns([3,1,3,1,3])
    with row1[0]:
        render_link_card("사용자 메타 분석", "투자 목표·감정·관심사·투자 수준을 입력하고 상담을 시작하세요.", "💬")
    with row1[1]:
        html('<div class="arrow-col">→</div>')
    with row1[2]:
        render_link_card("금융 레벨 테스트", "관심 카테고리에 맞춘 퀴즈로 지식을 점검하세요.", "🧠")
    with row1[3]:
        html('<div class="arrow-col">→</div>')
    with row1[4]:
        render_link_card("맞춤형 금융 지식", "퀴즈 결과와 관심사에 따라 개인화된 콘텐츠를 학습하세요.", "📖")

    down = st.columns([3,1,3,1,3])
    with down[4]:
        html('<div class="down-arrow">↓</div>')

    try:
        row2 = st.columns([3,1,3,1,3], vertical_alignment="top")
    except TypeError:
        row2 = st.columns([3,1,3,1,3])
    with row2[4]:
        render_link_card("주식·ETF 추천", "투자 성향을 반영한 주식·상품을 추천받으세요.", "🎁")
    with row2[3]:
        html('<div class="arrow-col">←</div>')
    with row2[2]:
        render_link_card("보유주식 AI 코칭", "보유 종목을 등록해 진단과 코칭을 받으세요.", "📈")
    with row2[1]:
        html('<div class="arrow-col">←</div>')
    with row2[0]:
        render_link_card("관심 종목 분석", "관심 종목별로 세부 피드백을 받아 전략을 개선하세요.", "📊")
