# utils/data_loader.py
import os, time, json, logging, pandas as pd, yfinance as yf, feedparser
import urllib.parse, re

logger = logging.getLogger(__name__)
DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data'))
os.makedirs(DATA_DIR, exist_ok=True)

def fetch_sp500_list():
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    try:
        tables = pd.read_html(url)
        df = tables[0]
        df.to_csv(os.path.join(DATA_DIR, 'sp500_list.csv'), index=False)
        return df
    except Exception as e:
        logger.exception('Failed to fetch S&P500 list: %s', e)
        csv_path = os.path.join(DATA_DIR, 'sp500_list.csv')
        if os.path.exists(csv_path):
            return pd.read_csv(csv_path)
        raise

def _normalize_link(link: str) -> str:
    if not link:
        return link
    try:
        p = urllib.parse.urlsplit(link)
        # 쿼리/프래그먼트 제거(구글뉴스 리다이렉트 매개변수 제거 효과)
        return urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, "", ""))
    except Exception:
        return link

def _normalize_title(title: str) -> str:
    t = (title or "").strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t

def fetch_company_news_rss(company_name, top_n=5, hl='en', gl='US'):
    """
    Google News RSS 에서 회사 관련 뉴스 수집
    - 회사명은 URL 인코딩
    - 제목+정규화된 링크 기준으로 중복 제거
    """
    try:
        q = urllib.parse.quote_plus(str(company_name))
        url = f'https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={gl}:{hl}'
        feed = feedparser.parse(url)

        items, seen = [], set()
        for entry in feed.entries:
            title = entry.get('title') or ''
            link = _normalize_link(entry.get('link') or '')
            key = (_normalize_title(title), link)

            if key in seen:
                continue
            seen.add(key)

            items.append({
                'title': title,
                'link': link,
                'published': entry.get('published'),
                'summary': entry.get('summary')
            })
            if len(items) >= int(top_n):
                break
        return items
    except Exception as e:
        logger.exception('RSS fetch failed for %s: %s', company_name, e)
        return []

def fetch_financial_summary(ticker: str):
    try:
        t = yf.Ticker(ticker)
        info = t.info if hasattr(t, 'info') else {}
        try:
            hist = t.history(period='2d')
        except Exception:
            hist = None
        last_price = change_pct = None
        if hist is not None and len(hist) >= 2:
            prev = hist['Close'].iloc[-2]
            last_price = hist['Close'].iloc[-1]
            change_pct = ((last_price - prev) / prev) * 100 if prev else None
        else:
            last_price = info.get('regularMarketPrice')
        return {
            'ticker': ticker,
            'longName': info.get('longName'),
            'sector': info.get('sector'),
            'industry': info.get('industry'),
            'marketCap': info.get('marketCap'),
            'trailingPE': info.get('trailingPE'),
            'forwardPE': info.get('forwardPE'),
            'dividendYield': info.get('dividendYield'),
            'shortRatio': info.get('shortRatio'),
            'lastPrice': last_price,
            'changePct': change_pct,
        }
    except Exception as e:
        logger.exception('Financial fetch failed for %s: %s', ticker, e)
        return {'ticker': ticker}