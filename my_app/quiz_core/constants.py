import os
from pathlib import Path

# 경로들
COMMON_PATH = "my_app/ui/level_quiz/data/common_questions.json"
GENERATED_DIR = "my_app/ui/level_quiz/data/generated"

TOTAL_QUESTIONS = 10
COMMON_COUNT    = 3
MAX_CONTEXT_TURNS = 4           # 슬라이딩 윈도우 크기
ROLLING_SUMMARY_MAX_CHARS = 300 # 롤링 요약 길이 제한

TOPIC_KEYWORDS = {
    "예금/금리": [r"예금", r"금리", r"복리", r"단리"],
    "채권": [r"채권", r"듀레이션", r"표면이자", r"만기수익률", r"세후.?수익률"],
    "ETF/인덱스": [r"ETF", r"인덱스", r"지수", r"추적오차"],
    "세금": [r"세금", r"과세", r"배당소득", r"양도소득"],
    "신용/부채": [r"신용", r"신용점수", r"대출", r"DSR", r"원리금"],
    "FIRE/자산배분": [r"FIRE", r"자산배분", r"리밸런싱", r"비상금"],
}

os.makedirs(GENERATED_DIR, exist_ok=True)
