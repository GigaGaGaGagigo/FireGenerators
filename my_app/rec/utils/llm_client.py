# utils/llm_client.py

from __future__ import annotations
import os
import re
import json
from typing import List, Dict, Any
from openai import OpenAI

# OpenAI client (reads OPENAI_API_KEY from environment)
_client = OpenAI()


def _extract_json_array(text: str) -> list[dict] | None:
    """모델 응답에서 첫 번째 JSON 배열([ ... ])만 안전하게 추출합니다.

    우선적으로 ```json ... ``` 코드펜스 블록을 찾고, 없으면 첫 번째 대괄호 배열을 비탐욕(non-greedy)으로 추출합니다.
    """
    if not text:
        return None
    # ```json ... ``` 형태 우선 추출 (non-greedy)
    m = re.search(r"```json\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if m:
        body = m.group(1)
    else:
        # 코드펜스가 없으면, 첫 번째 대괄호 배열을 찾되 non-greedy로
        m = re.search(r"\[[\s\S]*?\]", text)
        if not m:
            return None
        body = m.group(0)
    try:
        return json.loads(body)
    except Exception:
        return None


def _tickers_from_table_markdown(table_md: str, top_n: int) -> list[str]:
    """pandas.DataFrame.to_markdown()로 만든 표에서 ticker 컬럼을 추출합니다.

    표는 보통 다음과 같은 형태입니다:
    | ticker | sector | currentPrice | ... |
    |--------|--------|--------------| ... |
    | AAPL   | Tech   | 170          | ... |
    """
    out: list[str] = []
    for line in table_md.splitlines():
        line = line.strip()
        if not line or line.startswith("| ticker") or set(line) == set("|- "):
            continue
        if line.startswith("|"):
            parts = [p.strip() for p in line.strip("|").split("|")]
            if parts:
                t = (parts[0] or "").upper()
                if t and t not in out:
                    out.append(t)
    return out[:top_n]


def recommend_stocks_via_llm(table_md: str, user_profile: Dict[str, Any], top_n: int = 3) -> List[Dict[str, str]]:
    """
    주식 추천을 OpenAI LLM으로 요청합니다.

    - table_md: pandas DataFrame.to_markdown() 형태의 문자열 (ticker 컬럼을 포함해야 함)
    - user_profile: 사용자 프로필 딕셔너리
    - top_n: 추천 개수

    반환값: [{"ticker":"AAPL","reason":"추천 이유(한국어)","url":"https://..."}, ...]
    실패 시 테이블 기반의 안전한 기본 fallback을 반환합니다.
    """
    system_msg = (
        "당신은 주식 추천 어시스턴트입니다. 반드시 한국어로 답하고, "
        "항상 JSON 배열만 출력하세요. 다른 텍스트, 코드펜스, 추가 설명은 출력하지 마세요."
    )

    user_msg = f"""
[사용자 프로필]
```json
{json.dumps(user_profile, ensure_ascii=False)}
```

[종목 재무 테이블]
{table_md}

위 정보를 참고하여 **반드시 JSON 배열**만 출력하세요. 형식 예시:
[
  {{"ticker":"AAPL","reason":"한글로 1~2문장 이유","url":"https://finance.yahoo.com/quote/AAPL"}},
  ...
]
- 총 {top_n}개
- ticker는 표에 있는 ticker 중에서 선택
- reason은 표의 지표/섹터를 근거로 1~2문장 한글로 작성
- url은 https://finance.yahoo.com/quote/<TICKER>
"""

    # 1) LLM 호출 (OpenAI)
    content = ""
    try:
        resp = _client.chat.completions.create(
            model=os.getenv("OPENAI_RECOMMENDER_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.2,
            max_tokens=600,
        )
        content = (resp.choices[0].message.content or "").strip()
    except Exception:
        content = ""

    # 2) JSON 파싱
    parsed = _extract_json_array(content)

    # 3) 실패이면 테이블 기반의 안전한 fallback
    def _fallback() -> List[Dict[str, str]]:
        tickers = _tickers_from_table_markdown(table_md, top_n)
        out: List[Dict[str, str]] = []
        for t in tickers:
            out.append({
                "ticker": t,
                "reason": "기본 추천: 표의 지표(가격/밸류/섹터)를 기초로 선정한 종목입니다.",
                "url": f"https://finance.yahoo.com/quote/{t}",
            })
        return out

    if not parsed or not isinstance(parsed, list):
        return _fallback()

    # 4) 정규화
    out: List[Dict[str, str]] = []
    for item in parsed[:top_n]:
        if not isinstance(item, dict):
            continue
        t = str(item.get("ticker", "")).strip().upper()
        if not t:
            continue
        reason = str(item.get("reason") or item.get("why") or item.get("추천이유") or "").strip()
        if not reason:
            reason = "추천 이유 미제공"
        url = str(item.get("url") or f"https://finance.yahoo.com/quote/{t}").strip()
        out.append({"ticker": t, "reason": reason, "url": url})

    if not out:
        return _fallback()

    return out


# 간단한 로컬 테스트용 (네트워크 호출 없이 파서 동작 확인)
if __name__ == "__main__":
    sample_text = '```json\n[{"ticker":"AAPL","reason":"성장성이 높아 보입니다.","url":"https://finance.yahoo.com/quote/AAPL"}]\n```'
    print(_extract_json_array(sample_text))