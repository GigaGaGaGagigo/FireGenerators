from typing import Optional, List
import os, requests
from .utils import html, clean_text

try:
    import feedparser
except Exception:
    feedparser = None

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
            params={"q": q or "markets OR stocks OR bonds", "language": "ko", "pageSize": limit, "sortBy": "publishedAt"},
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
        for f in ["https://feeds.reuters.com/reuters/businessNews",
                  "https://finance.yahoo.com/news/rssindex"]:
            d = feedparser.parse(f)
            for e in d.entries[: max(30, limit*2)]:
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
           [{"title":"(오프라인) 금융시장 요약 더미","source":"Local","url":"#","published_at":None}][:limit]

def render_news_list(tickers: Optional[List[str]] = None, query: Optional[str] = None):
    html('<div class="subcard"><h4>🗞️ 금융 뉴스</h4>')
    items = fetch_latest_news(limit=8, query=query, tickers=tickers)
    html('<div class="news-list">')
    for it in items:
        title = clean_text(it.get("title"), "제목 없음")
        src   = clean_text(it.get("source"), "News")
        url   = it.get("url") or "#"
        html(f"""
        <div class="news-item">
          <div>
            <div style="font-weight:700;color:var(--ink);">{title}</div>
            <div class="meta">{src}</div>
          </div>
          <a href="{url}" target="_blank" rel="noopener" class="tag">열기</a>
        </div>
        """)
    html('</div></div>')
