from datetime import datetime
import os
import math
import hashlib
import altair as alt
import streamlit as st
import pandas as pd 
import io, base64
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm, rcParams
from .utils import html, parse_listish, clean_text, clamp_pct
from .router import PAGE_KEYS
from home.db import get_supabase_client, fetch_profile_by_user_id, _get_user_id
from .styles import inject_home_styles

def set_korean_font():
    # 시스템에 있는 한글 폰트 중 첫 번째를 사용
    candidates = [
        "Malgun Gothic",             # Windows
        "Apple SD Gothic Neo",       # macOS
        "Noto Sans CJK KR",          # 리눅스
        "NanumGothic", "NanumSquare", "NanumBarunGothic"
    ]
    available = {f.name for f in fm.fontManager.ttflist}
    for name in candidates:
        if name in available:
            rcParams["font.family"] = name
            break
    rcParams["axes.unicode_minus"] = False

def _stable_emotion_score(label: str) -> float:
    """
    감정 라벨만 있어도 40~90 구간의 안정적인 점수 생성 (세션/런타임 바뀌어도 동일).
    추후 DB에 점수가 있으면 그 값을 사용.
    """
    h = hashlib.md5(label.encode("utf-8")).hexdigest()
    v = int(h[:4], 16) / 0xFFFF  # 0~1
    return 40 + v * 50           # 40~90

def _radar_df(emotions: list[str], scores: dict|None=None, max_r: float = 100.0) -> pd.DataFrame:
    """
    레이더 차트용 x,y 좌표를 미리 계산(극좌표 → 직교).
    scores 가 주어지면 그것을, 없으면 해시기반 점수 사용.
    """
    if not emotions:
        emotions = ["감정없음"]
    vals = []
    for e in emotions:
        if scores and e in scores:
            s = float(scores[e])
        else:
            s = _stable_emotion_score(e)
        s = max(0.0, min(max_r, s))
        vals.append({"emotion": e, "score": s})

    N = len(vals)
    rows = []
    for i, row in enumerate(vals):
        ang = 2 * math.pi * i / N
        r = row["score"] / max_r  # 0~1 정규화
        x = r * math.sin(ang)
        y = r * math.cos(ang)
        rows.append({"emotion": row["emotion"], "score": row["score"], "x": x, "y": y, "order": i})

    # 폴리곤 닫기 위해 첫 점 반복
    rows.append({**rows[0], "order": N})

    return pd.DataFrame(rows)

def render_missing_toast(missing_fields: list[str], auto_hide_sec: int = 12):
    items = ", ".join(missing_fields)
    # --auto CSS 변수로 자동 페이드 시간 주입
    html(f"""
    <div class="floating-wrap">
      <input id="ft-hide" type="checkbox" class="ft-hide">
      <div class="floating-toast" style="--auto: {max(0, int(auto_hide_sec))}s;">
        <label for="ft-hide" class="ft-close" title="닫기">×</label>
        <div class="ft-title">⚠️ 아직 정보가 부족합니다</div>
        <div class="ft-msg">{items}</div>
        <div class="ft-actions">
          <a class="ft-btn primary hash-nav" href="#nav=chatbot">Chatbot 열기</a>
          <a class="ft-btn hash-nav" href="#nav=quiz">오늘의 퀴즈</a>
          <a class="ft-btn hash-nav" href="#nav=content">맞춤형 금융 지식</a>
          <a class="ft-btn hash-nav" href="#nav=rag_recommendation">상품 추천</a>
        </div>
      </div>
    </div>
    """)

def render_emotion_card(emotions, score_map=None, size_in=4.0, scale=2):
    """
    감정분석 레이더 차트를 카드 안에 꽉 차게 렌더링
    """
    set_korean_font()

    axes = ["신중함","불안","아쉬움","혼란","자신감","욕심"]
    synonyms = {
        "신중함": {"신중함","침착함","차분함","현실성"},
        "불안": {"불안","불안감","초조","걱정"},
        "아쉬움": {"아쉬움","후회"},
        "혼란": {"혼란","동요","갈등"},
        "자신감": {"자신감","희망","기대감","도전","적극성"},
        "욕심": {"욕심","욕구","탐욕"},
    }

    def _norm(x):
        try: return max(0.0, min(1.0, float(x)))
        except: return 0.0

    emo_list = emotions or []
    scores = []
    for k in axes:
        if score_map and k in score_map:
            v = _norm(score_map[k])
        else:
            hit = sum(1 for e in emo_list for syn in synonyms[k] if syn in str(e))
            v = 0.35 + min(hit, 2) * 0.20
        scores.append(_norm(v))

    vals = scores + [scores[0]]
    angs = np.linspace(0, 2*np.pi, len(axes)+1)

    # === 카드에 꽉 차게 ===
    figsize = (size_in * scale, size_in * scale)
    fig = plt.figure(figsize=figsize, dpi=int(220 * scale))
    ax = fig.add_subplot(111, polar=True)

    # 여백 최소화
    fig.subplots_adjust(left=0.02, right=0.98, top=0.95, bottom=0.02)
    ax.set_position([0.0, 0.0, 1.0, 1.0])  # plot이 figure 전체를 채우게

    # 스타일
    lw = 2.0 * scale
    ax.plot(angs, vals, linewidth=lw)
    ax.fill(angs, vals, alpha=0.20)

    label_fs = int(40 * scale)
    ax.set_thetagrids(angs[:-1] * 180/np.pi, axes, fontsize=label_fs)
    ax.tick_params(axis="x", pad=int(22 * scale))
    ax.set_ylim(0, 1)

    # 그리드
    for gridline in ax.yaxis.get_gridlines() + ax.xaxis.get_gridlines():
        gridline.set_linestyle("--")
        gridline.set_alpha(0.35)
        gridline.set_linewidth(0.8 * scale)

    # r축 라벨 숨김
    ax.set_yticklabels([])

    buf = io.BytesIO()
    # pad_inches=0 으로 불필요한 바깥여백 제거
    fig.savefig(buf, format="png", dpi=int(200 * scale), bbox_inches="tight", pad_inches=0, facecolor="white")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


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

    # 상단 프로필 헤더 + p-grid 열기
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
        <div class="sq-row">
            <div class="square-card risk-card">
              <div class="card-head">리스크 허용도</div>
              <div class="sq-inner">
                <div class="ring"
                    style="--p:{risk};">
                  <div class="v">{risk}%</div>
                </div>
              </div>
            </div>
            <div class="square-card emotion-card">
              <div class="card-head">감정분석</div>
              <img class="radar-img"
                  src="data:image/png;base64,{render_emotion_card(
                        emotions,
                        score_map=profile.get('investment_emotions_score'),
                        size_in=5.2)}"
                  alt="감정분석"/>
            </div>
          </div>
      </div>     <!-- /.p-body -->
    </div>       <!-- /.profile-pro -->
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
