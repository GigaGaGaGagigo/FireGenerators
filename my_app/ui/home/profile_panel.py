from datetime import datetime
import os
import streamlit as st
from .utils import html, parse_listish, clean_text, clamp_pct
from .router import PAGE_KEYS
from home.db import get_supabase_client, fetch_profile_by_user_id, _get_user_id

def render_missing_toast(missing_fields, auto_hide_sec: int = 12):
    items = ", ".join(missing_fields)
    html(f"""
    <div class="floating-wrap">
      <input id="ft-hide" type="checkbox" class="ft-hide">
      <div class="floating-toast" style="--auto:{max(0,int(auto_hide_sec))}s;">
        <label for="ft-hide" class="ft-close" title="닫기">×</label>
        <div class="ft-title">⚠️ 아직 정보가 부족합니다</div>
        <div class="ft-msg">{items}</div>
        <div class="ft-actions">
          <a class="ft-btn primary hash-nav" href="#nav={PAGE_KEYS['Chatbot']}">Chatbot 열기</a>
          <a class="ft-btn hash-nav" href="#nav={PAGE_KEYS['오늘의 퀴즈']}">오늘의 퀴즈</a>
          <a class="ft-btn hash-nav" href="#nav={PAGE_KEYS['맞춤형 금융 지식']}">금융 지식</a>
          <a class="ft-btn hash-nav" href="#nav={PAGE_KEYS['맞춤형 상품 추천']}">상품 추천</a>
        </div>
      </div>
    </div>
    """)

def render_user_panel():
    sb = get_supabase_client()
    user = st.session_state.get("user")
    user_id = _get_user_id(user) or st.session_state.get("user_id")
    if not user_id:
        try:
            qp = st.query_params if hasattr(st, "query_params") else st.experimental_get_query_params()
            user_id = qp.get("user_id", [None])[0]
        except Exception:
            user_id = os.getenv("USER_ID")

    demo = False
    profile = fetch_profile_by_user_id(user_id) if user_id else None
    if not profile:
        demo = True
        profile = {
            "name": "Sohee An",
            "email": "soheean1370@gmail.com",
            "knowledge_level": "Advanced",
            "investment_level": "Intermediate",
            "risk_tolerance": "25",
            "interests_categories": '{"혼합형 자산배분 펀드","주식·채권 혼합 펀드","자산배분 펀드","밸런스드 펀드","자산배분형 ETF","ETF","로보어드바이저","자동 리밸런싱","분산 투자","자동화 투자","퀀트 투자","알고리즘 투자","채권","국채","투자등급 회사채","인플레이션 연동채권","단기채","단기채 펀드","현금성 자산","현금대체 자산"}',
            "investment_emotions": '{"아쉬움","불안","혼란","신중함","손실회피","안전욕구"}',
            "investment_goal": "초기에는 단기적 투자 기간에서 원금 보존과 최소 위험을 최우선으로...",
            "user_summary": "장기 고수익을 원하면서도 원금 손실 회피 성향",
            "knowledge_summary": "자산배분형/로보어드바이저 이해도 높음",
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }

    name = clean_text(profile.get("name"), "사용자")
    email = clean_text(profile.get("email"), "—")
    know = clean_text(profile.get("knowledge_level"), "—")
    invest = clean_text(profile.get("investment_level"), "—")
    risk = clamp_pct(profile.get("risk_tolerance"))
    interests = parse_listish(profile.get("interests_categories"))
    emotions = parse_listish(profile.get("investment_emotions"))
    goal = clean_text(profile.get("investment_goal"), "—")
    usum = clean_text(profile.get("user_summary"), "요약 없음")
    ksum = clean_text(profile.get("knowledge_summary"), "요약 없음")
    updated = clean_text(profile.get("updated_at"), "—")

    html(f"""
    <div class="profile-pro">
      <div class="profile-cover">
        <div class="p-head">
          <div class="ava">{(name or 'U')[:2]}</div>
          <div>
            <div class="p-name">{name}</div>
            <div class="p-email">{email}</div>
            <div class="p-pills"><span class="pill">지식 레벨 <b>{know}</b></span></div>
          </div>
        </div>
      </div>
      <div class="p-body">
        <div class="p-grid">
          <div class="card" style="display:grid;grid-template-columns:auto 1fr;gap:12px;align-items:center;">
            <div class="ring" style="--p:{risk};"><div class="v">{risk}%</div></div>
            <div><div style="font-weight:700;margin-bottom:6px;">리스크 허용도</div>
                <div style="color:var(--muted);font-size:.92rem;">현재 설정된 위험 허용 수준입니다.</div></div>
          </div>
          <div class="card">
            <label>관심 카테고리</label>
            <div class="chips">
              {''.join(f'<span class="chip">{x}</span>' for x in (interests[:8] or ['—']))}
            </div>
          </div>
          <div class="card">
            <label>투자 감정</label>
            <div class="chips">
              {''.join(f'<span class="chip">{x}</span>' for x in (emotions[:8] or ['—']))}
            </div>
          </div>
        </div>
      </div>
    </div>
    """)

    html(f"""
    <div class="mini-grid">
      <div class="sum"><h4>🧑‍💼 사용자 요약</h4><div>{usum}</div></div>
      <div class="sum"><h4>📖 지식 요약</h4><div>{ksum}</div></div>
    </div>
    <div class="sum" style="margin-top:12px;">
      <h4>🎯 투자 목표</h4>
      <div>{goal}</div>
      <div style="color:var(--muted);font-size:.85rem;margin-top:8px;">최근 업데이트: {updated}{' • (데모)' if demo else ''}</div>
    </div>
    """)

    missing = []
    if goal == "—": missing.append("투자 목표")
    if not interests: missing.append("관심 카테고리")
    if not emotions: missing.append("투자 감정")
    if know == "—": missing.append("지식 레벨")

    if missing and not demo:
        render_missing_toast(missing, 12)
