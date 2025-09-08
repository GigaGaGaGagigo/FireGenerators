# ================== 
# 상수 및 설정값
# ================== 

# 감정 점수 분류 기준
EMOTION_RANGES = {
    "very_positive": {"min": 30, "emoji": "😊", "status": "매우 긍정적", "description": "투자에 대한 기대감이 높은 상태", "color": "#28a745"},
    "positive": {"min": 10, "emoji": "🙂", "status": "긍정적", "description": "투자에 대해 낙관적인 마음가짐", "color": "#20c997"},
    "neutral": {"min": -10, "emoji": "😐", "status": "중립적", "description": "평온하고 균형잡힌 투자 심리", "color": "#6c757d"},
    "anxious": {"min": -30, "emoji": "😟", "status": "다소 불안", "description": "투자에 대한 약간의 우려가 있는 상태", "color": "#fd7e14"},
    "very_anxious": {"min": -50, "emoji": "😔", "status": "불안감 높음", "description": "투자에 대한 걱정이 많은 상태", "color": "#dc3545"}
}

# 위험 허용도 분류 기준
RISK_TOLERANCE_RANGES = {
    "aggressive": {"min": 80, "emoji": "🚀", "status": "적극적 투자 성향", "description": "높은 수익을 위해 큰 위험도 감수할 수 있음", "color": "#dc3545"},
    "growth": {"min": 60, "emoji": "📈", "status": "공격적 투자 성향", "description": "적당한 위험을 감수하며 수익 추구", "color": "#fd7e14"},
    "balanced": {"min": 40, "emoji": "⚖️", "status": "균형 잡힌 투자 성향", "description": "안정성과 수익성의 적절한 균형 선호", "color": "#20c997"},
    "conservative": {"min": 20, "emoji": "🛡️", "status": "보수적 투자 성향", "description": "안정성을 중시하며 낮은 위험 선호", "color": "#6f42c1"},
    "very_conservative": {"min": 0, "emoji": "🏦", "status": "매우 보수적 투자 성향", "description": "원금 보장을 최우선으로 하는 안전 투자", "color": "#28a745"}
}

# 레벨 매핑
LEVEL_MAPPING = {
    'Beginner': '입문자',
    'Intermediate': '중급자', 
    'Advanced': '고급자'
}

# 토픽 ID 매핑
TOPIC_MAPPING = {
    2: "경제",
    4: "과학", 
    5: "금융",
    6: "사회"
}

# 피드백 매핑
FEEDBACK_EMOJI_MAP = {
    "positive": "👍", 
    "neutral": "😐", 
    "negative": "👎"
}

FEEDBACK_TEXT_MAP = {
    "positive": "도움됨", 
    "neutral": "보통", 
    "negative": "아쉬움"
}

# 컬러 팔레트
COLORS = {
    "primary": "#FE7743",
    "secondary": "#273F4F", 
    "success": "#28a745",
    "info": "#17a2b8",
    "warning": "#ffc107",
    "danger": "#dc3545",
    "light": "#f8f9fa",
    "dark": "#343a40"
}

# 차트 컬러 맵
CHART_COLORS = {
    "level_colors": {
        'Beginner': '#D0EBD1',  
        'Intermediate': '#7DC679', 
        'Advanced': '#249148'
    },
    "feedback_colors": {
        'positive': '#4CAF50',
        'neutral': '#FF9800', 
        'negative': '#F44336'
    }
}

# 기본 설정값
DEFAULT_CONFIG = {
    "top_n": 3,
    "use_llm_rerank": True,
    "emotion_score_range": (-50, 50),
    "risk_tolerance_range": (0, 100),
    "cache_ttl": 300,  # 5분
    "content_cache_ttl": 600,  # 10분
    "max_display_tags": 4,
    "max_title_length": 25
}

# Gemini API 설정
GEMINI_CONFIG = {
    "model_name": "gemini-1.5-flash",
    "temperature": 0.3,
    "max_tokens": 300,
    "top_p": 0.9
}