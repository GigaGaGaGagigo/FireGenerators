from typing import Optional, List, Dict, Any
import os, requests, json, re
from .utils import html, clean_text
from .router import PAGE_KEYS
from home.db import get_supabase_client, _get_user_id
import streamlit as st
from urllib.parse import urlparse
try:
    import feedparser
except Exception:
    feedparser = None

# ------------------------------
# (1) 개인화: Supabase user_news_logs
# ------------------------------
def _parse_array(val) -> List[str]:
    """text[] / JSON / 콤마문자 → 리스트"""
    if val is None:
        return []
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    s = str(val).strip()
    if not s:
        return []
    # JSON 배열
    try:
        arr = json.loads(s)
        if isinstance(arr, list):
            return [str(x).strip() for x in arr if str(x).strip()]
    except Exception:
        pass
    # PG 배열 {"a","b"}
    if s.startswith("{") and s.endswith("}"):
        body = s[1:-1]
        parts = re.findall(r'"([^"]+)"|([^,]+)', body)
        return [(p[0] or p[1]).strip() for p in parts if (p[0] or p[1]).strip()]
    # 콤마 분리
    if "," in s:
        return [x.strip() for x in s.split(",") if x.strip()]
    return [s]

def _parse_links(val) -> List[Dict[str, str]]:
    """[{url,title}] JSON → [{'url','title'}]"""
    if val is None:
        return []
    if isinstance(val, list):
        return [{"url": d.get("url"), "title": d.get("title") or d.get("url")}
                for d in val if isinstance(d, dict) and d.get("url")]
    try:
        arr = json.loads(str(val))
        out = []
        for d in arr:
            if isinstance(d, dict) and d.get("url"):
                out.append({"url": d["url"], "title": d.get("title") or d["url"]})
        return out
    except Exception:
        return []

# --- NEW: user_id 해석 + 개인화 뉴스 조회 ---
from home.db import get_supabase_client, _get_user_id
import streamlit as st
import os

def _effective_user_id() -> str | None:
    """세션/객체/쿼리스트링/환경변수 순서로 user_id를 안정적으로 획득."""
    # 1) 세션에 명시적으로 저장된 값
    cand = st.session_state.get("user_id")
    if cand:
        return str(cand).strip().strip('"').strip("'")

    # 2) 세션의 user 객체에서 추출
    user = st.session_state.get("user")
    cand = _get_user_id(user)
    if cand:
        return str(cand).strip().strip('"').strip("'")

    # 3) 쿼리스트링
    try:
        qp = st.query_params if hasattr(st, "query_params") else st.experimental_get_query_params()
        cand = (qp.get("user_id", [None])[0])
        if cand:
            return str(cand).strip().strip('"').strip("'")
    except Exception:
        pass

    # 4) 환경변수(개발용)
    cand = os.getenv("USER_ID")
    if cand:
        return str(cand).strip().strip('"').strip("'")

    return None

def fetch_news_by_user_id(user_id: str | None, limit: int = 3):
    """
    user_news_logs에서 개인화 뉴스 요약을 가져와 파싱해서 반환.
    (원래 _supabase_user_news와 동일 역할, 이름만 네가 쓰기 편하게)
    """
    if not user_id:
        return []

    sb = get_supabase_client()
    if not sb:
        return []

    try:
        res = (
            sb.table("user_news_logs")
              .select("summary,key_opportunities,potential_risks,analyst_take,links,created_at")
              .eq("user_id", str(user_id).strip().strip('"').strip("'"))
              .order("created_at", desc=True)
              .limit(limit)
              .execute()
        )
        rows = getattr(res, "data", None) or (res.get("data") if isinstance(res, dict) else []) or []
    except Exception as e:
        print("user_news_logs 조회 실패:", e)
        rows = []

    out = []
    for r in rows:
        out.append({
            "summary": r.get("summary") or "",
            "opportunities": _parse_array(r.get("key_opportunities")),
            "risks": _parse_array(r.get("potential_risks")),
            "analyst_take": r.get("analyst_take") or "",
            "links": _parse_links(r.get("links")),
            "created_at": r.get("created_at") or "",
        })
    return out


# ------------------------------
# (2) 기존 공개 뉴스(폴백)
# ------------------------------
def _newsapi_fetch(limit: int, query: Optional[str], tickers: Optional[List[str]]):
    key = os.getenv("NEWSAPI_KEY")
    if not key:
        return None
    q = query or ""
    if tickers:
        q = f"({q}) " + " OR ".join([f'"{t}"' for t in tickers if t])
    try:
        r = requests.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": q or "markets OR stocks OR bonds",
                "language": "ko",
                "pageSize": limit,
                "sortBy": "publishedAt",
            },
            headers={"X-Api-Key": key}, timeout=6,
        )
        if r.status_code != 200:
            return None
        data = r.json().get("articles", [])
        out = []
        for a in data:
            out.append({
                "title": a.get("title"),
                "source": (a.get("source") or {}).get("name"),
                "url": a.get("url"),
                "published_at": a.get("publishedAt"),
            })
        return out
    except Exception:
        return None

def _rss_fallback(limit: int):
    out = []
    if not feedparser:
        return out
    try:
        for f in [
            "https://feeds.reuters.com/reuters/businessNews",
            "https://finance.yahoo.com/news/rssindex",
        ]:
            d = feedparser.parse(f)
            for e in d.entries[: max(30, limit * 2)]:
                out.append({
                    "title": e.get("title"),
                    "source": (getattr(d, "feed", {}) or {}).get("title", "RSS"),
                    "url": e.get("link"),
                    "published_at": e.get("published") or None,
                })
    except Exception:
        pass
    return out[:limit]

def fetch_latest_news(limit: int = 8, query: Optional[str] = None, tickers: Optional[List[str]] = None):
    return _newsapi_fetch(limit, query, tickers) or _rss_fallback(limit) or \
           [{"title": "(오프라인) 금융시장 요약 더미", "source": "Local", "url": "#", "published_at": None}][:limit]

# ------------------------------
# (3) 렌더: 개인화 우선, 없으면 안내 → (선택) 공개 뉴스 폴백
# ------------------------------
def _date_badge(s: str | None) -> str:
    return (str(s)[:10]) if s else ""

def _source_from_url(url: str) -> str:
    try:
        netloc = urlparse(url).netloc
        return netloc.replace("www.","")
    except Exception:
        return "link"

def _flatten_personal_links(logs: List[Dict], limit_cards: int) -> List[Dict]:
    """
    user_news_logs 로우들에서 links만 뽑아 카드 리스트로 평탄화 + URL 중복 제거
    반환: [{title,url,source,created,kind}]
    """
    seen = set()
    cards = []
    for r in logs:
        created = r.get("created_at")
        for l in (r.get("links") or []):
            url = l.get("url") or ""
            if not url or url in seen:
                continue
            seen.add(url)
            title = clean_text(l.get("title") or url, url)
            cards.append({
                "title": title,
                "url": url,
                "source": _source_from_url(url),
                "created": _date_badge(created),
                "kind": "personal",
            })
            if len(cards) >= limit_cards:
                return cards
    return cards

def render_news_list(user_id: Optional[str] = None,
                     limit: int = 8,                 # ← 카드 개수
                     query: Optional[str] = None,
                     tickers: Optional[List[str]] = None):
    html('<div class="subcard"><h4>🗞️ 맞춤 뉴스 추천</h4>')

    # user_id 자동 획득 (실패해도 조용히 진행)
    if not user_id:
        try:
            user_id = _effective_user_id()
        except Exception:
            user_id = None

    # 개인화 케이스
    personal_cards: List[Dict] = []
    if user_id:
        try:
            logs = fetch_news_by_user_id(user_id, limit=3)
            personal_cards = _flatten_personal_links(logs, limit_cards=limit)
        except Exception:
            personal_cards = []

    # 1) 개인화 카드가 있으면 그것만 보여주기
    if personal_cards:
        html('<div class="news-grid">')
        for c in personal_cards:
            html(f'''
            <a class="news-card" href="{c["url"]}" target="_blank" rel="noopener">
              <div class="news-tag">맞춤</div>
              <div class="news-title">{c["title"]}</div>
              <div class="news-meta">{c["source"]}{' · ' + c["created"] if c["created"] else ''}</div>
            </a>
            ''')
        html('</div></div>')
        return

    # 2) user_id 없거나 개인화 데이터 없음 → 안내 + 일반 뉴스 폴백 카드
    if not user_id:
        html(f"""
        <div class="empty" style="margin-top:8px;">
          개인화된 뉴스 데이터를 볼 수 없습니다. <b>사용자 메타 분석</b>을 먼저 실행해 주세요.
          <div style="margin-top:8px;display:flex;gap:8px;flex-wrap:wrap;">
            <a class="ft-btn primary hash-nav" href="#nav={PAGE_KEYS['Chatbot']}">메타 분석 실행</a>
          </div>
        </div>
        """)

    # 폴백 뉴스 불러오기 (NewsAPI → RSS)
    try:
        items = fetch_latest_news(limit=limit, query=query, tickers=tickers)
    except Exception:
        items = []

    # 카드 출력
    if items:
        html('<div class="news-grid" style="margin-top:10px;">')
        for it in items:
            title = clean_text(it.get("title"), "제목 없음")
            url   = it.get("url") or "#"
            src   = clean_text(it.get("source"), _source_from_url(url))
            date  = _date_badge(it.get("published_at"))
            html(f'''
            <a class="news-card" href="{url}" target="_blank" rel="noopener">
              <div class="news-tag">일반</div>
              <div class="news-title">{title}</div>
              <div class="news-meta">{src}{' · ' + date if date else ''}</div>
            </a>
            ''')
        html('</div>')
    else:
        html('<div class="empty" style="margin-top:8px;">표시할 뉴스가 없습니다.</div>')

    html('</div>')  # .subcard