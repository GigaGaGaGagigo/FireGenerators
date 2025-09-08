# ui/home/home.py
import json
import re
import os
from datetime import datetime
import streamlit as st
import streamlit.components.v1 as components
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
# ==============================
# 페이지 키 매핑
# ==============================
PAGE_KEYS = {
    "홈 화면": "home",
    "Chatbot": "chatbot",
    "오늘의 퀴즈": "quiz",
    "맞춤형 금융 지식": "content",
    "맞춤형 상품 추천": "rag_recommendation",
    "현재 보유주식 AI코칭": "simulation",
    "종목 피드백": "analysis",
    "Settings": "settings",
    "Logout": "logout",
}
ALLOWED_PAGES = set(PAGE_KEYS.values())


# ==============================
# 해시(nav) ←→ session_state 동기화 (로그인창 방지)
# ==============================
def sync_nav_hash_bidirectional():
    """
    - 브라우저 해시(#nav=...)를 읽어 session_state.current_page 로 반영
    - 카드 클릭 시 해시만 바꾸고, JS가 즉시 값을 넘겨 rerun (서버 쿼리 X → 로그인 리다이렉트 X)
    """
    if "current_page" not in st.session_state:
        st.session_state.current_page = "home"

    val = components.html(
        """
        <script>
        (function () {
          function getNavFromHash() {
            const h = window.location.hash || "";
            const m = h.match(/(?:^|#|&)nav=([^&]+)/);
            return m ? decodeURIComponent(m[1]) : "";
          }
          function setValue(v) {
            window.parent.postMessage(
              { isStreamlitMessage: true, type: "streamlit:setComponentValue", value: v },
              "*"
            );
          }
          // 초기 1회
          setValue(getNavFromHash());
          // 뒤/앞/직접편집 등 해시 변동 시
          window.addEventListener("hashchange", () => setValue(getNavFromHash()));
          // 카드(a.hash-nav) 클릭 시: 기본 이동 막고 해시만 바꾸고 즉시 전달
          document.addEventListener("click", function (e) {
            const a = e.target.closest && e.target.closest("a.hash-nav");
            if (!a) return;
            const href = a.getAttribute("href") || "";
            if (!href.startsWith("#nav=")) return;
            e.preventDefault();
            const v = decodeURIComponent(href.split("=").slice(1).join("="));
            window.location.hash = "nav=" + encodeURIComponent(v);
            setValue(v);
          });
        })();
        </script>
        """,
        height=0,
        scrolling=False,
    )

    if val and isinstance(val, str) and val in ALLOWED_PAGES:
        st.session_state.current_page = val


# ==============================
# 스타일
# ==============================
def inject_home_styles():
    st.markdown(
        """
        <style>
          :root {
            --ring: rgba(99,102,241,.25);
            --ink: #0f172a;
            --muted: #475569;
            --border: rgba(148,163,184,.28);
            --chip: #f1f5f9;
            --chip-text: #0f172a;
            --accent: #6366f1;
            --green: #10b981;
          }
          .home-hero {
            background: linear-gradient(135deg, rgba(99,102,241,.15), rgba(16,185,129,.15));
            border-radius: 20px;
            padding: 40px 30px;
            text-align: center;
            margin-bottom: 24px;
          }
          .home-hero h1 { font-size: 2.2rem; font-weight: 900; margin-bottom: .5rem; color: var(--ink); }
          .home-hero p  { font-size: 1.05rem; opacity: .85; margin: 0; color: var(--muted); }

          /* User snapshot */
          .user-card {
            border:1px solid var(--border);
            border-radius:18px;
            padding:18px 20px;
            background:#fff;
            display:flex; gap:16px; align-items:flex-start;
          }
          .avatar {
            width:56px; height:56px; border-radius:14px;
            background:linear-gradient(135deg, rgba(99,102,241,.25), rgba(16,185,129,.25));
            display:flex; align-items:center; justify-content:center;
            font-weight:800; font-size:1.2rem; color:#111827;
            border: 1px solid var(--border);
            flex: 0 0 auto;
          }
          .u-main { flex:1 1 auto; }
          .u-name { font-weight:800; font-size:1.1rem; }
          .u-email { font-size:.9rem; color:var(--muted); }
          .chips { display:flex; flex-wrap:wrap; gap:8px; margin-top:8px; }
          .chip {
            background:var(--chip);
            color:var(--chip-text);
            border:1px solid var(--border);
            border-radius:999px;
            padding:4px 10px; font-size:.85rem;
          }
          .badge {
            display:inline-flex; align-items:center; gap:6px;
            border:1px solid var(--border);
            background:#fff; border-radius:10px; padding:6px 10px;
            font-size:.85rem; color:#0f172a;
          }
          .stat-grid { display:grid; grid-template-columns: repeat(3, 1fr); gap:12px; margin-top:10px; }
          .stat {
            border:1px solid var(--border); border-radius:12px; padding:10px 12px; background:#fff;
          }
          .stat label { display:block; font-size:.8rem; color:var(--muted); margin-bottom:6px; }
          .bar {
            height:8px; border-radius:999px; background:#e2e8f0; position:relative; overflow:hidden;
          }
          .bar > i {
            position:absolute; inset:0;
            width: var(--pct, 0%); height:100%; display:block;
            background: linear-gradient(90deg, var(--accent), var(--green));
          }
          .sum {
            border:1px solid var(--border); border-radius:12px; padding:12px; background:#fff; font-size:.92rem; color:#0f172a;
          }
          .sum h4 { margin:0 0 6px 0; font-size:.95rem; }
          .hint {
            border:1px dashed var(--border);
            background: #f8fafc;
            border-radius: 12px; padding: 12px; color:#0f172a;
          }
          .hint ol { margin: 4px 0 0 18px; }
          .hint li { margin: 6px 0; }

          /* Feature cards */
          .feature-card {
            border:1px solid var(--border);
            border-radius:16px;
            padding:24px;
            background:white;
            transition: all .2s ease;
            height:100%;
          }
          .feature-card:hover { box-shadow:0 6px 18px rgba(0,0,0,.10); transform: translateY(-3px); }
          .feature-title { font-weight:700; margin-top:10px; font-size:1.1rem; }
          .feature-desc  { font-size:.95rem; opacity:.9; margin-top:6px; }

          /* hash-nav 링크 */
          .card-link,
          .card-link:link,
          .card-link:visited,
          .card-link:hover,
          .card-link:active {
            text-decoration: none !important;
            color: inherit !important;
            display: block !important;
          }
          .card-link .feature-card { cursor: pointer; }

          .arrow-col  { text-align:center; font-size:2rem; line-height:150px; opacity:.6; user-select:none; }
          .down-arrow { text-align:center; font-size:2rem; margin:10px 0;   opacity:.6; user-select:none; }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ==============================
# 유틸: 리스트/문자열 파싱
# ==============================
def parse_listish(val):
    """'{"a","b"}' 같은 PG 배열문자/JSON/리스트/공백을 안전하게 리스트로 변환"""
    if val is None:
        return []
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    s = str(val).strip()
    if s in ("", "{}", "[]", "None", "NULL"):
        return []
    # JSON 배열 시도
    try:
        arr = json.loads(s)
        if isinstance(arr, list):
            return [str(x).strip() for x in arr if str(x).strip()]
    except Exception:
        pass
    # PG 배열 형태 {a,b,c} or {"a","b"}
    if s.startswith("{") and s.endswith("}"):
        s2 = s[1:-1]
        # 따옴표 포함 분리
        parts = re.findall(r'"([^"]+)"|([^,]+)', s2)
        items = [p[0] or p[1] for p in parts]
        return [i.strip() for i in items if i and i.strip() and i.strip() not in ('NULL', 'None')]
    # 콤마 구분 텍스트
    if "," in s:
        return [x.strip() for x in s.split(",") if x.strip()]
    return [s]


def clean_text(val, default="—"):
    if val is None:
        return default
    s = str(val).strip()
    if s in ("", "{}", "[]", "None", "NULL"):
        return default
    return s


def clamp_pct(v):
    try:
        x = int(float(v))
    except Exception:
        return 0
    return max(0, min(100, x))


# ==============================
# Supabase 연동 (선택)
# ==============================

# ✅ 프로젝트 루트의 .env를 명시적으로 로드
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"
load_dotenv(ENV_PATH, override=True)  # <- .env 강제 로드

@st.cache_resource(show_spinner=False)
def _create_supabase_client(url: str, key: str):
    from supabase import create_client
    return create_client(url, key)

def get_supabase_client():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    # 환경변수 없으면 즉시 None (캐시 안 탑승)
    if not url or not key:
      return None
    # url/key 조합이 바뀌면 캐시 자동 무효화
    try:
        return _create_supabase_client(url, key)
    except Exception as e:
        print("Supabase 연결 실패:", e)
        return None


def fetch_profile_by_email(email: str):
    """
    profiles 테이블에서 한 명 조회. 없거나 에러면 None
    """
    sb = get_supabase_client()
    if not sb or not email:
        return None
    try:
        res = sb.table("profiles").select("*").eq("email", email).limit(1).execute()
        if res.data:
            return res.data[0]
    except Exception:
        return None
    return None

def _get_user_id(user):
    if not user:
        return None
    if isinstance(user, dict):
        return user.get("user_id") or user.get("id")
    return getattr(user, "user_id", None) or getattr(user, "id", None)

# ==============================
# 사용자 패널
# ==============================
def render_user_panel():
    # 1) 현재 사용자 user_id 결정
    supabase = get_supabase_client()
    user = st.session_state.get("user")  # 로그인 객체(딕트/오브젝트) 들어온다고 가정
    user_id = _get_user_id(user) or st.session_state.get("user_id")

    # (옵션) 쿼리/환경에서도 보조로 읽기
    if not user_id:
        try:
            qp = st.query_params if hasattr(st, "query_params") else st.experimental_get_query_params()
            user_id = (qp.get("user_id", [None])[0])
        except Exception:
            user_id = user_id or os.getenv("USER_ID")

    # 2) 프로필 로드 (user_id → DB)
    demo = False
    profile = None
    if supabase and user_id:
        try:
            res = (
                supabase
                .table("profiles")
                .select("id,email,name,role,knowledge_level,investment_level,risk_tolerance,interests_categories,investment_emotions,investment_goal,user_summary,knowledge_summary,updated_at")
                .eq("id", user_id)
                .single()                # v2: 단일행
                .execute()
            )
            profile = getattr(res, "data", None) or (res.get("data") if isinstance(res, dict) else None)
        except Exception as e:
            print("profiles 조회 실패:", e)

    # 3) 실패 시 데모
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
            "investment_goal": "초기에는 단기적 투자 기간에서 원금 보존과 최소 위험을 최우선으로 하는 낮은 위험 허용도를 가졌으나, 투자 목표를 10년 이상의 장기 투자로 전환…",
            "user_summary": "장기 고수익을 원하면서도 원금 손실을 피하고 싶은 신중한 성향",
            "knowledge_summary": "자산배분형/혼합형, 자동 리밸런싱, 로보어드바이저 등 심화 이해도 높음.",
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }


    # 3) 데이터 정리
    name = clean_text(profile.get("name"), "사용자")
    email_show = clean_text(profile.get("email"), "—")
    know = clean_text(profile.get("knowledge_level"), "—")
    invest = clean_text(profile.get("investment_level"), "—")
    risk = clamp_pct(profile.get("risk_tolerance"))
    interests = parse_listish(profile.get("interests_categories"))
    emotions = parse_listish(profile.get("investment_emotions"))
    goal = clean_text(profile.get("investment_goal"), "—")
    usum = clean_text(profile.get("user_summary"), "요약 없음")
    ksum = clean_text(profile.get("knowledge_summary"), "요약 없음")
    updated = clean_text(profile.get("updated_at"), "—")

    # 4) 프로필 카드
    cols = st.columns([2, 1])
    with cols[0]:
        st.markdown(
            f"""
            <div class="user-card">
              <div class="avatar">{(name or 'U')[:2]}</div>
              <div class="u-main">
                <div class="u-name">{name}</div>
                <div class="u-email">{email_show}</div>
                <div class="chips" style="margin-top:10px;">
                  <span class="badge">지식 레벨: <b>{know}</b></span>
                  <span class="badge">투자 레벨: <b>{invest}</b></span>
                </div>
                <div class="stat-grid">
                  <div class="stat">
                    <label>리스크 허용도</label>
                    <div class="bar" style="--pct:{risk}%"><i></i></div>
                  </div>
                  <div class="stat">
                    <label>관심 카테고리</label>
                    <div class="chips">
                      {''.join(f'<span class="chip">{x}</span>' for x in (interests[:4] or ["—"]))}
                    </div>
                  </div>
                  <div class="stat">
                    <label>투자 감정</label>
                    <div class="chips">
                      {''.join(f'<span class="chip">{x}</span>' for x in (emotions[:4] or ["—"]))}
                    </div>
                  </div>
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            f"""
            <div class="sum" style="margin-top:10px;">
              <h4>투자 목표</h4>
              <div>{goal}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with cols[1]:
        st.markdown(
            f"""
            <div class="sum">
              <h4>사용자 요약</h4>
              <div>{usum}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            f"""
            <div class="sum" style="margin-top:10px;">
              <h4>지식 요약</h4>
              <div>{ksum}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.caption(f"최근 업데이트: {updated}{' • (데모)' if demo else ''}")

    # 5) 누락 정보 가이드
    missing = []
    if goal == "—": missing.append("투자 목표")
    if not interests: missing.append("관심 카테고리")
    if not emotions: missing.append("투자 감정")
    if invest == "—": missing.append("투자 레벨")
    if know == "—": missing.append("지식 레벨")

    if missing and not demo:
        st.markdown(
            f"""
            <div class="hint" style="margin-top:10px;">
              <b>아직 정보가 부족합니다:</b> {', '.join(missing)}<br/>
              아래 순서대로 진행해 주세요.
              <ol>
                <li><a class="hash-nav" href="#nav={PAGE_KEYS['Chatbot']}">Chatbot</a>에서 투자 목표·감정·관심사를 입력</li>
                <li><a class="hash-nav" href="#nav={PAGE_KEYS['오늘의 퀴즈']}">오늘의 퀴즈</a>로 현재 지식 수준 파악</li>
                <li><a class="hash-nav" href="#nav={PAGE_KEYS['맞춤형 금융 지식']}">맞춤형 금융 지식</a>으로 빈틈 보완</li>
                <li><a class="hash-nav" href="#nav={PAGE_KEYS['맞춤형 상품 추천']}">맞춤형 상품 추천</a>으로 개인화 리밸런싱</li>
              </ol>
            </div>
            """,
            unsafe_allow_html=True,
        )
    elif demo:
        st.info("⚠️")


# ==============================
# 카드를 해시 링크로 (로그인창 X)
# ==============================
def render_link_card(title: str, desc: str, icon: str, page_key: str):
    st.markdown(
        f"""
        <a class="card-link hash-nav" href="#nav={page_key}">
          <div class="feature-card">
            <div style="font-size:2rem;">{icon}</div>
            <div class="feature-title">{title}</div>
            <div class="feature-desc">{desc}</div>
          </div>
        </a>
        """,
        unsafe_allow_html=True,
    )


# ==============================
# 홈 화면 렌더
# ==============================
def render():
    sync_nav_hash_bidirectional()   # ← 해시 기반 라우팅 (로그인창 X)
    inject_home_styles()

    # Hero
    st.markdown(
        """
        <div class="home-hero">
          <h1>🚀 FIREGENERATOR</h1>
          <p>2030 세대를 위한 금융 지식 퀴즈, AI 챗봇 상담, 투자 시뮬레이션과 맞춤형 리포트</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 사용자 정보 패널
    render_user_panel()
    st.divider()

    # 주요 기능 (지그재그 플로우)
    st.subheader("✨ 주요 기능")

    try:
        row1 = st.columns([3, 1, 3, 1, 3], vertical_alignment="top")
    except TypeError:
        row1 = st.columns([3, 1, 3, 1, 3])

    with row1[0]:
        render_link_card(
            "Chatbot",
            "투자 목표·감정·관심사·투자 수준을 입력하고 상담을 시작하세요.",
            "💬",
            PAGE_KEYS["Chatbot"],
        )
    with row1[1]:
        st.markdown('<div class="arrow-col">→</div>', unsafe_allow_html=True)
    with row1[2]:
        render_link_card(
            "오늘의 퀴즈",
            "관심 카테고리에 맞춘 퀴즈로 지식을 점검하세요.",
            "🧠",
            PAGE_KEYS["오늘의 퀴즈"],
        )
    with row1[3]:
        st.markdown('<div class="arrow-col">→</div>', unsafe_allow_html=True)
    with row1[4]:
        render_link_card(
            "맞춤형 금융 지식",
            "퀴즈 결과와 관심사에 따라 개인화된 콘텐츠를 학습하세요.",
            "📖",
            PAGE_KEYS["맞춤형 금융 지식"],
        )

    down = st.columns([3, 1, 3, 1, 3])
    with down[4]:
        st.markdown('<div class="down-arrow">↓</div>', unsafe_allow_html=True)

    try:
        row2 = st.columns([3, 1, 3, 1, 3], vertical_alignment="top")
    except TypeError:
        row2 = st.columns([3, 1, 3, 1, 3])

    with row2[4]:
        render_link_card(
            "맞춤형 상품 추천",
            "투자 성향을 반영한 주식·상품을 추천받으세요.",
            "🎁",
            PAGE_KEYS["맞춤형 상품 추천"],
        )
    with row2[3]:
        st.markdown('<div class="arrow-col">←</div>', unsafe_allow_html=True)
    with row2[2]:
        render_link_card(
            "현재 보유주식 AI코칭",
            "보유 종목을 등록해 진단과 코칭을 받으세요.",
            "📈",
            PAGE_KEYS["현재 보유주식 AI코칭"],
        )
    with row2[1]:
        st.markdown('<div class="arrow-col">←</div>', unsafe_allow_html=True)
    with row2[0]:
        render_link_card(
            "종목 피드백",
            "관심 종목별로 세부 피드백을 받아 전략을 개선하세요.",
            "📊",
            PAGE_KEYS["종목 피드백"],
        )

    st.divider()
