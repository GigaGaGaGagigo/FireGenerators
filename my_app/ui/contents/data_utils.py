# ================== 
# 데이터 처리 유틸리티 함수들
# ================== 
import streamlit as st
import datetime
import re
import os
import pandas as pd
from typing import Dict, List, Any, Optional
from ui.contents.constants import (
    EMOTION_RANGES, RISK_TOLERANCE_RANGES, LEVEL_MAPPING, 
    TOPIC_MAPPING, FEEDBACK_EMOJI_MAP, FEEDBACK_TEXT_MAP,
    DEFAULT_CONFIG, GEMINI_CONFIG
)

try:
    import google.generativeai as genai
except ImportError:
    genai = None


def safe_tags(tags) -> List[str]:
    """태그를 안전하게 처리하여 리스트로 반환"""
    if tags is None: 
        return []
    if isinstance(tags, list): 
        return [str(t) for t in tags if t]
    if isinstance(tags, str): 
        return [t.strip() for t in tags.split(",") if t.strip()]
    return [str(tags)]


def get_emotion_status(emotion_score: int) -> Dict[str, str]:
    """감정 점수를 사용자 친화적인 표현으로 변환"""
    for key, config in EMOTION_RANGES.items():
        if emotion_score >= config["min"]:
            return {
                "status": config["status"],
                "emoji": config["emoji"],
                "description": config["description"],
                "color": config["color"],
                "range": f"{config['min']}점 이상" if config['min'] >= 0 else f"{config['min']}점 미만"
            }
    
    # 기본값 (최하위)
    return {
        "status": "불안감 높음",
        "emoji": "😔",
        "description": "투자에 대한 걱정이 많은 상태",
        "color": "#dc3545",
        "range": "-30점 미만"
    }


def get_risk_tolerance_status(risk_score: int) -> Dict[str, str]:
    """위험 허용도를 사용자 친화적인 표현으로 변환"""
    for key, config in RISK_TOLERANCE_RANGES.items():
        if risk_score >= config["min"]:
            return {
                "status": config["status"],
                "emoji": config["emoji"],
                "description": config["description"],
                "color": config["color"],
                "range": f"{config['min']}점 이상" if key != "very_conservative" else f"{config['min']}점 미만"
            }
    
    # 기본값 (최하위)
    return {
        "status": "매우 보수적 투자 성향",
        "emoji": "🏦",
        "description": "원금 보장을 최우선으로 하는 안전 투자",
        "color": "#28a745",
        "range": "20점 미만"
    }


@st.cache_data(ttl=DEFAULT_CONFIG["cache_ttl"])
def analyze_emotion_score_with_gemini(emotions_text: str) -> int:
    """Gemini를 사용해서 감정 텍스트를 점수로 변환 (-50 ~ +50)"""
    if not emotions_text or emotions_text in ['[]', '{}', 'null']:
        return 0
    
    try:
        # Gemini API 초기화
        if not genai:
            return 0
            
        api_key = os.getenv('GOOGLE_API_KEY')
        if not api_key:
            return 0
            
        try:
            if genai and hasattr(genai, 'configure') and hasattr(genai, 'GenerativeModel'):
                configure_func = getattr(genai, 'configure')
                model_class = getattr(genai, 'GenerativeModel')
                configure_func(api_key=api_key)
                model = model_class(GEMINI_CONFIG["model_name"])
            else:
                return 0
        except (AttributeError, Exception):
            return 0
        
        prompt = f"""
        다음은 사용자의 투자 관련 감정 상태입니다: {emotions_text}
        
        이 감정들을 분석해서 전체적인 감정 점수를 -50부터 +50 사이의 숫자로 평가해주세요.
        
        평가 기준:
        - 긍정적 감정 (기대감, 설렘, 자신감, 희망 등): +점수
        - 부정적 감정 (불안감, 걱정, 두려움 등): -점수
        - 중립적 감정 (평범함, 보통 등): 0 근처
        
        결과는 숫자만 답해주세요. 예: 15 또는 -20
        """
        
        response = model.generate_content(prompt)
        score_text = response.text.strip()
        
        # 숫자 추출
        numbers = re.findall(r'-?\d+', score_text)
        if numbers:
            score = int(numbers[0])
            return max(-50, min(50, score))  # -50~50 범위로 제한
        return 0
        
    except Exception as e:
        st.warning(f"감정 분석 중 오류: {e}")
        return 0


def parse_user_profile_data() -> Dict[str, Any]:
    """Supabase profiles 테이블 데이터를 파싱해서 UI용 데이터로 변환"""
    user_data = st.session_state.get('user_data', {})
    
    # 사용자 이름 추출
    user_name = user_data.get('name', '사용자님')
    
    # knowledge_level 변환
    knowledge_level = user_data.get('knowledge_level', 'Beginner')
    user_level = LEVEL_MAPPING.get(knowledge_level, '입문자')
    
    # investment_emotions를 Gemini로 분석
    investment_emotions_raw = user_data.get('investment_emotions', '[]')
    emotions_score = analyze_emotion_score_with_gemini(str(investment_emotions_raw))
    
    # interests_categories 파싱
    interests_categories = user_data.get('interests_categories', '[]')
    if isinstance(interests_categories, str):
        try:
            import json
            interests_categories = json.loads(interests_categories)
        except:
            interests_categories = []
    
    # user_summary와 knowledge_summary 추출
    user_summary = user_data.get('user_summary', '').strip()
    knowledge_summary = user_data.get('knowledge_summary', '').strip()
    
    return {
        'user_name': user_name,
        'user_level': user_level,
        'knowledge_level': knowledge_level,
        'emotions': emotions_score,
        'interest_tags': interests_categories,
        'user_summary': user_summary,
        'knowledge_summary': knowledge_summary,
        'risk_tolerance': user_data.get('risk_tolerance', 50),
        'investment_goal': user_data.get('investment_goal', ''),
        'investment_level': user_data.get('investment_level', 'None')
    }


@st.cache_data(ttl=DEFAULT_CONFIG["content_cache_ttl"])
def load_and_analyze_contents() -> Optional[Dict[str, Any]]:
    """Supabase에서 콘텐츠 데이터를 로드하고 분석"""
    try:
        # 경로 설정 및 직접 import
        import os
        from pathlib import Path
        import importlib.util
        
        current_file = Path(__file__).resolve()
        project_root = current_file.parent.parent.parent
        contents_rec_path = os.path.join(str(project_root), "contents", "recommendation")
        
        # 직접 파일을 import하는 방식
        hybrid_spec = importlib.util.spec_from_file_location(
            "hybrid_recommender_v2", 
            os.path.join(contents_rec_path, "hybrid_recommender_v2.py")
        )
        if hybrid_spec is None or hybrid_spec.loader is None:
            raise ImportError("hybrid_recommender_v2 모듈을 찾을 수 없습니다")
        
        hybrid_module = importlib.util.module_from_spec(hybrid_spec)
        hybrid_spec.loader.exec_module(hybrid_module)
        
        all_contents = hybrid_module.load_contents_from_supabase()
        
        # topic_id를 카테고리명으로 변환
        for content in all_contents:
            topic_id = content.get('topic_id')
            if topic_id in TOPIC_MAPPING:
                content['category_name'] = TOPIC_MAPPING[topic_id]
            else:
                content['category_name'] = content.get('category', '기타')
        
        # 데이터 분석
        df = pd.DataFrame(all_contents)
        
        analysis = {
            'total_contents': len(all_contents),
            'level_distribution': df['level'].value_counts().to_dict() if 'level' in df.columns else {},
            'category_distribution': df['category_name'].value_counts().to_dict() if 'category_name' in df.columns else {},
            'contents_df': df,
            'raw_contents': all_contents
        }
        
        return analysis
    except Exception as e:
        st.error(f"콘텐츠 데이터 로드 실패: {e}")
        return None


def format_datetime_string(datetime_str: str) -> str:
    """Supabase 날짜 형식을 파싱하여 표시용 문자열로 변환"""
    try:
        # Supabase 날짜 형식 파싱 (microseconds 자리수 문제 해결)
        viewed_at_str = datetime_str.replace('Z', '+00:00')
        # microseconds가 5자리인 경우 6자리로 패딩
        viewed_at_str = re.sub(r'\.(\d{5})\+', r'.\g<1>0+', viewed_at_str)
        viewed_at = datetime.datetime.fromisoformat(viewed_at_str)
        return viewed_at.strftime('%m/%d %H:%M')
    except ValueError:
        # 파싱 실패시 현재 시간 사용
        return datetime.datetime.now().strftime('%m/%d %H:%M')


def calculate_completion_rate(results: List[Dict], session_state: Dict) -> tuple[int, int, int]:
    """학습 완료율 계산"""
    total_contents = len(results)
    explained_count = 0
    
    # 설명 완료 개수 계산
    for i, content in enumerate(results, 1):
        explanation_key = f"explanation_{content.get('card_id', i)}"
        if explanation_key in session_state:
            explained_count += 1
    
    completion_rate = int((explained_count / total_contents) * 100) if total_contents > 0 else 0
    return total_contents, explained_count, completion_rate


def process_feedback_for_reranking(previous_results: List[Dict], session_state: Dict) -> Dict[str, List]:
    """이전 결과에서 피드백 정보 추출"""
    feedback = {'liked': [], 'disliked': []}
    
    for content in previous_results:
        card_identifier = content.get('card_id', content.get('id'))
        feedback_key = f"feedback_recorded_{card_identifier}"
        
        if feedback_key in session_state:
            if session_state[feedback_key] == 'positive':
                feedback['liked'].append(content)
            elif session_state[feedback_key] == 'negative':
                feedback['disliked'].append(content)
    
    return feedback


def adjust_scores_by_feedback(
    base_scores: Dict[str, float], 
    all_candidates: List[str], 
    card_map: Dict[str, Dict],
    feedback: Dict[str, List]
) -> Dict[str, float]:
    """피드백을 바탕으로 점수 조정"""
    scores_to_sort = base_scores.copy()
    
    if not (feedback['liked'] or feedback['disliked']):
        return scores_to_sort
    
    # 선호 태그와 비선호 태그 수집
    boost_tags = set()
    for item in feedback['liked']:
        boost_tags.update(safe_tags(item.get('tags', [])))

    penalize_tags = set()
    for item in feedback['disliked']:
        penalize_tags.update(safe_tags(item.get('tags', [])))

    # 점수 조정
    for cid in all_candidates:
        if cid not in card_map: 
            continue
        content_tags = set(safe_tags(card_map[cid].get('tags', [])))
        
        if boost_tags.intersection(content_tags):
            scores_to_sort[cid] = scores_to_sort.get(cid, 0.0) + 0.2
        if penalize_tags.intersection(content_tags):
            scores_to_sort[cid] = scores_to_sort.get(cid, 0.0) - 0.3
    
    return scores_to_sort


def get_feedback_display_info(log_item: Dict) -> tuple[str, str]:
    """피드백 정보를 표시용으로 변환"""
    feedback_type = log_item.get('feedback_type')
    if feedback_type:
        emoji = FEEDBACK_EMOJI_MAP.get(feedback_type, '❓')
        text = FEEDBACK_TEXT_MAP.get(feedback_type, '알 수 없음')
        return emoji, text
    return '❓', '알 수 없음'