# 콜드스타트 대응 
from typing import List, Dict, Optional

def build_user_context_text(profile: Dict, logs: Optional[List[Dict]] = None) -> str:
    """
    profile 예시:
      {
        "user_id": "u001",
        "level": "Beginner",
        "interest_tags": ["ETF","저위험","반도체"],
        "style": "쉬운 언어와 비유 중심"
      }
    logs 예시(없어도 OK):
      [
        {"contents_id":"card_001","feedback":"like","tags":["ETF"],"context":{"emotion":"positive"}},
        {"contents_id":"card_021","feedback":"dislike","tags":["채권"],"context":{"emotion":"confused"}},
      ]
    """
    level = str(profile.get("level") or "알 수 없음")
    itags = profile.get("interest_tags") or []
    interests = ", ".join(itags) if itags else "아직 없음"
    style = str(profile.get("style") or "미정")

    if logs and len(logs) > 0:
        likes = [l for l in logs if l.get("feedback") == "like"]
        dislikes = [l for l in logs if l.get("feedback") == "dislike"]

        likes_ids = ", ".join([f"'{l.get('contents_id')}'" for l in likes]) if likes else "없음"
        dislikes_ids = ", ".join([f"'{l.get('contents_id')}'" for l in dislikes]) if dislikes else "없음"

        text = (
            f"이 사용자는 {level} 수준의 투자자이며, 관심사는 {interests}입니다. "
            f"최근 좋아한 콘텐츠: {likes_ids}. 어려워한 주제: {dislikes_ids}. "
            f"선호 스타일: {style}."
        )
    else:
        # 콜드 스타트: 로그가 전혀 없을 때
        text = (
            f"이 사용자는 {level} 수준의 투자자이며, 관심사는 {interests}입니다. "
            f"아직 콘텐츠 학습 기록은 없습니다. 선호 스타일: {style}."
        )
    return text