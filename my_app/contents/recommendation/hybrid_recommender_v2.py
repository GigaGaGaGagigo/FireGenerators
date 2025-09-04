"""
개선된 하이브리드 추천 시스템 - Streamlit 최적화 버전
- ko-sroberta + bge-m3 모델 지원 (upstage 제외)
- 레벨/태그/card_id 정규화로 안전성 강화
"""

from typing import List, Dict, Tuple, Set, Optional
import time
import random
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client, Client

# 경로 설정 - 현재 파일의 위치를 기준으로 프로젝트 루트까지
current_file = Path(__file__).resolve()
contents_rec_path = current_file.parent  # contents/recommendation/
project_root = contents_rec_path.parent.parent  # my_app/

# sys.path에 경로 추가
if str(contents_rec_path) not in sys.path:
    sys.path.insert(0, str(contents_rec_path))
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from data_access import load_all_cards  # JSON 파일용 (백업)
from context_builder import build_user_context_text
from vector_search import vector_candidates

# ========================================
# 0. 유틸: 정규화 함수들
# ========================================

VALID_LEVELS = ["Beginner", "Intermediate", "Advanced"]

def normalize_level(level_val) -> str:
    """레벨을 항상 'Beginner/Intermediate/Advanced' 중 하나의 문자열로 변환"""
    if not isinstance(level_val, str):
        return "Beginner"
    val = level_val.strip().title()
    return val if val in VALID_LEVELS else "Beginner"

def normalize_tags(tags) -> List[str]:
    """태그를 항상 문자열 리스트로 변환"""
    if tags is None:
        return []
    if isinstance(tags, list):
        return [str(t) for t in tags]
    if isinstance(tags, (int, float)):
        return [str(tags)]
    if isinstance(tags, str):
        # 콤마/세미콜론 구분 모두 허용
        parts = [p.strip() for p in tags.replace(";", ",").split(",")]
        return [p for p in parts if p]
    # dict/tuple 등 기타 타입 방지
    return [str(tags)]

def normalize_card(raw: Dict) -> Dict:
    """콘텐츠 한 건을 안전한 표준 스키마로 정규화"""
    card_id = raw.get("card_id") or raw.get("id")
    # card_id는 반드시 문자열로
    card_id = str(card_id) if card_id is not None else ""

    level = normalize_level(raw.get("level", "Beginner"))
    tags = normalize_tags(raw.get("tags", []))

    normalized = {
        "id": raw.get("id"),
        "card_id": card_id,
        "title": raw.get("title"),
        "content": raw.get("content"),
        "level": level,
        "tags": tags,
        "category": raw.get("category"),
        "topic_id": raw.get("topic_id"),
        # 선택 필드들 그대로 보존
        "style": raw.get("style"),
        "media_type": raw.get("media_type"),
        "created_at": raw.get("created_at"),
        "updated_at": raw.get("updated_at"),
    }
    return normalized

# ========================================
# 1. 설정 및 상수
# ========================================

# 환경변수 로드
load_dotenv()

# Supabase 클라이언트 (전역)
_supabase_client = None

def get_supabase_client():
    """Supabase 클라이언트 싱글톤"""
    global _supabase_client
    if _supabase_client is None:
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY")
        if not supabase_url or not supabase_key:
            raise ValueError("SUPABASE_URL과 SUPABASE_KEY를 환경변수에 설정해주세요")
        _supabase_client = create_client(supabase_url, supabase_key)
    return _supabase_client

# 선택된 임베딩 모델들
SELECTED_MODELS = ["ko-sroberta", "bge-m3"]

# 기본 파라미터
DEFAULT_PARAMS = {
    "top_n": 3,
    "k_vec": 10,
    "k_rule": 10,
    "alpha": 0.6,
    "beta": 0.3,
    "gamma": 0.1,
    "sim_threshold": 0.15,
    "level_strict": True,
    "use_llm_rerank": True  # LLM 컨텍스트 리랭킹 사용 여부
}

# ========================================
# 2. Supabase DB 콘텐츠 접근 함수들
# ========================================

def load_contents_from_supabase() -> List[Dict]:
    """Supabase DB에서 모든 콘텐츠 로드 (정규화 포함)"""
    try:
        supabase = get_supabase_client()
        response = supabase.table("contents").select("*").execute()
        contents = [normalize_card(item) for item in response.data]
        return contents
    except Exception as e:
        print(f"[ERROR] Supabase 콘텐츠 로드 실패: {e}")
        # 백업: JSON 파일에서 로드 (정규화 적용)
        print("[INFO] JSON 파일 백업 사용")
        backup = load_all_cards()
        return [normalize_card(c) for c in backup]

def query_contents_by_level_and_tags(user_level: str, interest_tags: List[str],
                                     emotions: int = 0, limit: int = 10) -> Tuple[List[Dict], Dict]:
    """
    Supabase DB에서 레벨과 태그 기반으로 콘텐츠 쿼리 (감정 기반 레벨 조정 포함)
    Returns: (콘텐츠 리스트, 쿼리 상세 정보)
    """
    try:
        adjusted_level, level_reason = adjust_level_by_emotion(user_level, emotions)
        supabase = get_supabase_client()

        # Advanced 레벨의 경우 Intermediate와 Advanced 모두 조회
        if adjusted_level == "Advanced":
            query = supabase.table("contents").select("*").or_("level.eq.intermediate,level.eq.advanced")
            query_levels = ["intermediate", "advanced"]
        else:
            query = supabase.table("contents").select("*").eq("level", adjusted_level.lower())
            query_levels = [adjusted_level.lower()]

        # 태그 필터 (가능하면 or-contains)
        if interest_tags:
            # interest_tags가 숫자/공백 포함 가능성 → 문자열로 정규화
            safe_interest = [str(t).strip() for t in interest_tags if str(t).strip()]
            for tag in safe_interest:
                query = query.or_(f"tags.cs.{{{tag}}}")

        response = query.limit(limit * 2).execute()

        # 없으면 태그 완화
        if not response.data:
            if adjusted_level == "Advanced":
                response = supabase.table("contents").select("*").or_("level.eq.intermediate,level.eq.advanced").limit(limit).execute()
            else:
                response = supabase.table("contents").select("*").eq("level", adjusted_level.lower()).limit(limit).execute()

        # 정규화
        contents = [normalize_card(item) for item in response.data]

        # 태그 점수 계산 (클라 사이드)
        safe_interest_set = set([str(t) for t in (interest_tags or []) if str(t).strip()])
        def calculate_tag_score(content):
            content_tags = set(normalize_tags(content.get("tags", [])))
            return sum((tag in content_tags) for tag in safe_interest_set)

        scored_contents = [(c, calculate_tag_score(c)) for c in contents]
        scored_contents.sort(key=lambda x: x[1], reverse=True)

        final_contents = [c for c, _ in scored_contents[:limit]]
        max_tag_score = max([score for _, score in scored_contents]) if scored_contents else 0

        query_details = {
            "method": "supabase_query",
            "original_level": user_level,
            "adjusted_level": adjusted_level,
            "level_adjustment": level_reason,
            "queried_levels": query_levels,
            "interest_tags": list(safe_interest_set),
            "total_found": len(contents),
            "max_tag_score": max_tag_score,
            "final_selected": len(final_contents),
            "reason": f"Supabase DB에서 레벨 {query_levels} 필터링 후 태그 매칭 점수 기준 정렬"
        }
        return final_contents, query_details

    except Exception as e:
        print(f"[ERROR] Supabase 쿼리 실패: {e}")
        # 백업 로직
        all_contents = load_contents_from_supabase()
        return emotion_based_rule_recommend(all_contents, user_level, interest_tags, emotions, limit)

# ========================================
# 3. 감정 기반 레벨 조정 (UI 추천 시스템 로직)
# ========================================

def adjust_level_by_emotion(knowledge_level: str, emotions: int) -> Tuple[str, str]:
    level_order = ["Beginner", "Intermediate", "Advanced"]
    try:
        idx = level_order.index(normalize_level(knowledge_level))
    except ValueError:
        idx = 0

    original_level = level_order[idx]
    if emotions <= -30:
        new_idx = max(0, idx - 1)
        adjusted_level = level_order[new_idx]
        reason = f"부정적 감정({emotions})으로 인해 {original_level} → {adjusted_level}로 하향 조정" if new_idx != idx else f"부정적 감정({emotions})이지만 이미 최하위 레벨"
    elif emotions >= 30:
        new_idx = min(len(level_order) - 1, idx + 1)
        adjusted_level = level_order[new_idx]
        reason = f"긍정적 감정({emotions})으로 인해 {original_level} → {adjusted_level}로 상향 조정" if new_idx != idx else f"긍정적 감정({emotions})이지만 이미 최상위 레벨"
    else:
        adjusted_level = original_level
        reason = f"중립적 감정({emotions})으로 레벨 유지: {original_level}"
    return adjusted_level, reason

def emotion_based_rule_recommend(contents: List[Dict], knowledge_level: str,
                                 interests_categories: List[str], emotions: int,
                                 top_k: int = 10) -> Tuple[List[str], Dict]:
    adjusted_level, level_reason = adjust_level_by_emotion(knowledge_level, emotions)

    # 정규화 보장
    contents = [normalize_card(c) for c in contents]

    # Advanced 레벨의 경우 Intermediate와 Advanced 모두 포함
    if adjusted_level == "Advanced":
        candidates = [c for c in contents if c.get("level") in ["Intermediate", "Advanced"]]
        allowed_levels = ["Intermediate", "Advanced"]
    else:
        candidates = [c for c in contents if c.get("level") == adjusted_level]
        allowed_levels = [adjusted_level]

    safe_interest = set([str(t).strip() for t in (interests_categories or []) if str(t).strip()])

    def calculate_tag_score(content):
        content_tags = set(normalize_tags(content.get("tags", [])))
        return sum((t in content_tags) for t in safe_interest)

    scored = [(c, calculate_tag_score(c)) for c in candidates]
    if not scored:
        return [], {
            "method": "emotion_rule",
            "level_adjustment": level_reason,
            "candidates_found": 0,
            "max_tag_score": 0,
            "allowed_levels": allowed_levels,
            "reason": f"조정된 레벨 {allowed_levels}에 해당하는 콘텐츠가 없음"
        }

    max_score = max(score for _, score in scored)
    best = [c for c, score in scored if score == max_score]

    if len(best) >= top_k:
        selected = random.sample(best, top_k)
    else:
        scored.sort(key=lambda x: x[1], reverse=True)
        selected = [c for c, _ in scored][:top_k]

    result_ids = [c["card_id"] for c in selected]
    details = {
        "method": "emotion_rule",
        "level_adjustment": level_reason,
        "original_level": normalize_level(knowledge_level),
        "adjusted_level": adjusted_level,
        "allowed_levels": allowed_levels,
        "candidates_found": len(candidates),
        "max_tag_score": max_score,
        "selected_count": len(selected),
        "reason": f"감정 기반 레벨 조정 후 레벨 {allowed_levels}에서 태그 매칭 점수 {max_score}점 기준 선별"
    }
    return result_ids, details

# ========================================
# 4. 후보·리랭킹 (기존 + LLM 컨텍스트 리랭킹)
# ========================================

def get_level_compatible_contents(cards: List[Dict], user_level: str, strict: bool = True) -> List[Dict]:
    level_order = ["Beginner", "Intermediate", "Advanced"]
    user_level = normalize_level(user_level)

    # 입력 카드 정규화
    cards = [normalize_card(c) for c in cards]

    if not strict:
        try:
            user_idx = level_order.index(user_level)
            allowed_levels = level_order[:user_idx + 1]
        except ValueError:
            allowed_levels = [user_level]
    else:
        # Advanced 레벨의 경우 Intermediate 콘텐츠도 포함
        if user_level == "Advanced":
            allowed_levels = ["Intermediate", "Advanced"]
        else:
            allowed_levels = [user_level]

    filtered = [c for c in cards if c.get("level") in allowed_levels]
    return filtered

def rule_candidates_v2(cards: List[Dict], user_level: str, interest_tags: List[str],
                       k: int = 10, exclude_ids: Set[str] = None, level_strict: bool = True) -> List[str]:
    exclude_ids = exclude_ids or set()
    user_level = normalize_level(user_level)
    itags = set([str(t).strip() for t in (interest_tags or []) if str(t).strip()])

    # 정규화
    cards = [normalize_card(c) for c in cards]
    level_filtered_cards = get_level_compatible_contents(cards, user_level, strict=level_strict)

    scored: List[Tuple[float, str]] = []
    for c in level_filtered_cards:
        if c["card_id"] in exclude_ids:
            continue

        level_bonus = 1.0 if str(c.get("level")) == user_level else 0.5

        content_tags = set(normalize_tags(c.get("tags")))
        overlap = len(itags.intersection(content_tags))
        tag_bonus = min(overlap / max(1, len(itags)), 1.0) if itags else 0.0

        score = 0.6 * level_bonus + 0.4 * tag_bonus
        if score > 0:
            scored.append((score, c["card_id"]))

    scored.sort(reverse=True)
    return [cid for _, cid in scored[:k]]

def multi_model_vector_search(ctx_text: str, level_filtered_cards: List[Dict] = None,
                              models: List[str] = None, k: int = 10,
                              sim_threshold: float = 0.15) -> Tuple[List[str], Dict[str, float], Dict[str, str]]:
    if models is None:
        models = SELECTED_MODELS
    level_filtered_cards = [normalize_card(c) for c in (level_filtered_cards or [])]

    level_filtered_ids = set(card["card_id"] for card in level_filtered_cards)

    all_results: Dict[str, float] = {}
    all_scores: Dict[str, float] = {}
    model_sources: Dict[str, str] = {}

    for model_key in models:
        try:
            results = vector_candidates(ctx_text, k=k * 2, model_key=model_key)
            for result in results:
                card_id = str(result["card_id"])
                score = float(result["score"])
                if card_id not in level_filtered_ids:
                    continue
                if score >= sim_threshold:
                    if card_id not in all_results or score > all_results[card_id]:
                        all_results[card_id] = score
                        all_scores[card_id] = score
                        model_sources[card_id] = model_key
        except Exception as e:
            print(f"[WARN] {model_key} 벡터 검색 실패: {e}")
            continue

    sorted_ids = sorted(all_results.keys(), key=lambda x: all_results[x], reverse=True)
    return sorted_ids, all_scores, model_sources

def rerank_v2(candidates: List[str], user: Dict, cards: List[Dict],
              faiss_scores: Dict[str, float], top_n: int = 3,
              alpha: float = 0.6, beta: float = 0.3, gamma: float = 0.1) -> List[str]:
    itags = set([str(t).strip() for t in (user.get("interest_tags") or []) if str(t).strip()])
    seen = set([str(s) for s in (user.get("recent_seen_card_ids") or [])])
    liked_tags = set([str(t).strip() for t in (user.get("liked_tags") or []) if str(t).strip()])
    user_level = normalize_level(user.get("level", "Beginner"))

    cards = [normalize_card(c) for c in cards]
    card_map = {c["card_id"]: c for c in cards}

    scored: List[Tuple[float, str]] = []
    for cid in candidates:
        cid = str(cid)
        c = card_map.get(cid)
        if not c:
            continue

        vec_score = float(faiss_scores.get(cid, 0.0))

        content_level = normalize_level(c.get("level", "Beginner"))
        if content_level == user_level:
            level_score = 1.0
        else:
            level_order = ["Beginner", "Intermediate", "Advanced"]
            try:
                user_idx = level_order.index(user_level)
                content_idx = level_order.index(content_level)
                level_diff = abs(user_idx - content_idx)
                level_score = max(0.0, 1.0 - 0.3 * level_diff)
            except ValueError:
                level_score = 0.5

        content_tags = set(normalize_tags(c.get("tags")))
        overlap = len(itags.intersection(content_tags))
        tag_score = (overlap / max(1, len(itags))) if itags else 0.0

        final_score = alpha * vec_score + beta * level_score + gamma * tag_score

        if cid in seen:
            final_score -= 0.2
        if liked_tags.intersection(content_tags):
            final_score += 0.1

        scored.append((final_score, cid))

    scored.sort(reverse=True)
    return [cid for _, cid in scored[:top_n]]

def llm_context_rerank(candidates: List[str], user: Dict, cards: List[Dict],
                      base_scores: Dict[str, float], top_n: int = 3,
                      use_llm_rerank: bool = True) -> Tuple[List[str], Dict]:
    """
    LLM을 활용한 컨텍스트 기반 리랭킹
    기존 수치 기반 점수를 사용자 맥락을 고려해 LLM이 재조정
    """
    if not use_llm_rerank or not candidates:
        # LLM 리랭킹을 사용하지 않으면 기존 점수 기준으로 정렬
        scored = [(base_scores.get(cid, 0.0), cid) for cid in candidates]
        scored.sort(reverse=True)
        return [cid for _, cid in scored[:top_n]], {"method": "numeric_only", "llm_used": False}

    try:
        from openai import OpenAI
        
        # OpenAI API 초기화
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found")
        
        client = OpenAI(api_key=api_key)
        
        # 카드 매핑
        cards = [normalize_card(c) for c in cards]
        card_map = {c["card_id"]: c for c in cards}
        
        # 사용자 컨텍스트 추출 
        user_summary = user.get("user_summary", "")
        knowledge_summary = user.get("knowledge_summary", "")
        user_level = normalize_level(user.get("level", "Beginner"))
        emotions = int(user.get("emotions", 0)) if isinstance(user.get("emotions", 0), (int, float, str)) else 0
        interest_tags = user.get("interest_tags", [])
        
        # 후보 정보 구성 (상위 5-7개만 LLM으로 처리)
        llm_candidates = candidates[:min(7, len(candidates))]
        candidate_info = []
        
        for i, cid in enumerate(llm_candidates, 1):
            card = card_map.get(cid)
            if not card:
                continue
                
            base_score = base_scores.get(cid, 0.0)
            title = card.get('title', 'Unknown')
            card_level = card.get('level', 'Beginner')
            tags = ', '.join(normalize_tags(card.get('tags', [])))
            content_preview = str(card.get('content', ''))[:100] + "..." if card.get('content') else ""
            
            candidate_info.append(
                f"후보 {i}: 제목='{title}', 레벨={card_level}, 태그=[{tags}], "
                f"내용미리보기='{content_preview}', 기존점수={base_score:.3f}"
            )
        
        # LLM 프롬프트 구성 (GPT-4o-mini 최적화)
        prompt = f"""다음 정보를 기반으로 사용자에게 가장 적합한 금융 콘텐츠 순위를 매겨주세요.

👤 사용자 정보:
- 지식 수준: {user_level}
- 감정 점수: {emotions}점 (-50~+50, 부정적일수록 쉬운 내용 선호)
- 관심 분야: {', '.join(interest_tags) if interest_tags else '미설정'}
- 투자 성향: {user_summary if user_summary and user_summary.strip() else '미분석'}
- 지식 특성: {knowledge_summary if knowledge_summary and knowledge_summary.strip() else '미분석'}

📝 평가 후보:
{chr(10).join(candidate_info)}

🎯 평가 기준:
- 지식 수준 일치도 (가장 중요)
- 감정 상태 적합도 (부정적이면 쉬운 내용 우선)
- 관심사 연관성
- 학습 효과성

⚠️ 중요: 기존점수가 높아도 사용자에게 맞지 않으면 낮은 점수를 줘야 합니다.

출력 형식 (반드시 이 형식):
후보 1: context_score=0.XX
후보 2: context_score=0.YY
후보 3: context_score=0.ZZ

점수 범위: 0.0~1.0 (1.0이 완벽 적합)"""

        # LLM 호출 (GPT-4o-mini)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "당신은 금융 맞춤 추천 전문가입니다. 사용자 프로필과 콘텐츠를 분석하여 정확한 컨텍스트 점수를 제공해주세요."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,  # 일관성을 위해 낮은 temperature
            max_tokens=300,   # 리랭킹이므로 짧은 응답 충분
            top_p=0.9
        )
        llm_result = response.choices[0].message.content.strip()
        
        # LLM 결과 파싱
        context_scores = {}
        lines = llm_result.split('\n')
        
        for line in lines:
            line = line.strip()
            if '후보' in line and 'context_score=' in line:
                try:
                    # "후보 1: context_score=0.85" 형태에서 번호와 점수 추출
                    parts = line.split(':')
                    if len(parts) >= 2:
                        candidate_num = int(''.join(filter(str.isdigit, parts[0])))
                        score_part = parts[1].strip()
                        if 'context_score=' in score_part:
                            score = float(score_part.split('context_score=')[1].strip())
                            score = max(0.0, min(1.0, score))  # 0~1 범위로 제한
                            
                            # 후보 번호를 실제 card_id로 매핑
                            if 1 <= candidate_num <= len(llm_candidates):
                                card_id = llm_candidates[candidate_num - 1]
                                context_scores[card_id] = score
                except (ValueError, IndexError) as e:
                    continue
        
        # LLM 점수와 기존 점수를 결합 (7:3 비율)
        final_scores = {}
        for cid in candidates:
            base_score = base_scores.get(cid, 0.0)
            llm_score = context_scores.get(cid, 0.5)  # LLM이 평가하지 않은 항목은 중간값
            
            # LLM 컨텍스트 점수가 있으면 70% 반영, 없으면 기존 점수 100%
            if cid in context_scores:
                final_score = 0.7 * llm_score + 0.3 * base_score
            else:
                final_score = base_score
                
            final_scores[cid] = final_score
        
        # 최종 점수로 정렬
        scored_final = [(final_scores[cid], cid) for cid in candidates]
        scored_final.sort(reverse=True)
        final_ranking = [cid for _, cid in scored_final[:top_n]]
        
        # 메타데이터 구성
        metadata = {
            "method": "llm_context_rerank",
            "llm_used": True,
            "llm_model": "gpt-4o-mini",
            "total_candidates": len(candidates),
            "llm_evaluated_candidates": len(llm_candidates),
            "context_scores": context_scores,
            "final_scores": {cid: final_scores[cid] for cid in final_ranking},
            "llm_raw_response": llm_result,
            "score_combination": "70% LLM context + 30% base score",
            "llm_settings": {
                "temperature": 0.3,
                "max_tokens": 300,
                "top_p": 0.9
            }
        }
        
        return final_ranking, metadata
        
    except Exception as e:
        # 실패 시 기존 점수 기준으로 폴백
        scored = [(base_scores.get(cid, 0.0), cid) for cid in candidates]
        scored.sort(reverse=True)
        return [cid for _, cid in scored[:top_n]], {
            "method": "numeric_fallback", 
            "llm_used": False, 
            "error": str(e)
        }

# ========================================
# 5. 메인 추천 함수 (Streamlit용)
# ========================================

def get_hybrid_recommendations(user: Dict, **kwargs) -> Dict:
    params = {**DEFAULT_PARAMS, **kwargs}

    start_time = time.time()
    result = {"success": False, "results": [], "metadata": {}, "error": None}

    try:
        # 1) 사용자 컨텍스트
        ctx_text = build_user_context_text(user, logs=None)

        # 2) 감정 기반 룰 (Supabase 쿼리)
        emotions = int(user.get("emotions", 0)) if isinstance(user.get("emotions", 0), (int, float, str)) else 0
        user_level = normalize_level(user.get("level", "Beginner"))
        interest_tags = [str(t) for t in (user.get("interest_tags", []))]

        emotion_rule_contents, emotion_rule_details = query_contents_by_level_and_tags(
            user_level, interest_tags, emotions, limit=params["k_rule"]
        )
        # 정규화 보장
        emotion_rule_contents = [normalize_card(c) for c in emotion_rule_contents]
        emotion_rule_ids = [c["card_id"] for c in emotion_rule_contents]

        # 3) 전체 콘텐츠 로드 (정규화)
        all_contents = load_contents_from_supabase()
        all_contents = [normalize_card(c) for c in all_contents]

        # 4) 레벨 필터
        level_filtered_cards = get_level_compatible_contents(
            all_contents, user_level, strict=params["level_strict"]
        )

        # 5) 멀티 모델 벡터 검색
        vec_ids, vec_scores, model_sources = multi_model_vector_search(
            ctx_text,
            level_filtered_cards=level_filtered_cards,
            models=SELECTED_MODELS,
            k=params["k_vec"],
            sim_threshold=params["sim_threshold"]
        )

        # 6) 기본 룰 후보
        basic_rule_ids = rule_candidates_v2(
            all_contents,
            user_level,
            interest_tags,
            k=params["k_rule"],
            exclude_ids=set([str(s) for s in user.get("recent_seen_card_ids", [])]),
            level_strict=params["level_strict"]
        )

        # 7) 후보 통합
        all_candidates: List[str] = []
        seen_ids: Set[str] = set()
        candidate_sources: Dict[str, str] = {}
        candidate_details: Dict[str, Dict] = {}

        # 감정 기반 룰
        for cid in emotion_rule_ids:
            if cid not in seen_ids:
                all_candidates.append(cid)
                seen_ids.add(cid)
                candidate_sources[cid] = "emotion_rule"
                candidate_details[cid] = {
                    "method": "감정 기반 룰",
                    "level_adjustment": emotion_rule_details.get("level_adjustment", ""),
                    "tag_score": emotion_rule_details.get("max_tag_score", 0),
                }

        # 벡터 검색
        for cid in vec_ids:
            if cid not in seen_ids:
                all_candidates.append(cid)
                seen_ids.add(cid)
                candidate_sources[cid] = "vector_search"
                candidate_details[cid] = {
                    "method": "벡터 검색",
                    "model": model_sources.get(cid, "unknown"),
                    "score": float(vec_scores.get(cid, 0.0)),
                    "level_filtered": True,
                }

        # 기본 룰
        for cid in basic_rule_ids:
            if cid not in seen_ids:
                all_candidates.append(cid)
                seen_ids.add(cid)
                candidate_sources[cid] = "basic_rule"
                candidate_details[cid] = {
                    "method": "기본 룰",
                    "level_matched": True,
                    "tag_matched": True,
                }

        # 8) 기존 수치 기반 점수 계산 (LLM 리랭킹의 base_score로 사용)
        base_scores = {}
        card_map = {c["card_id"]: c for c in all_contents}
        
        itags = set([str(t).strip() for t in (user.get("interest_tags") or []) if str(t).strip()])
        seen = set([str(s) for s in (user.get("recent_seen_card_ids") or [])])
        liked_tags = set([str(t).strip() for t in (user.get("liked_tags") or []) if str(t).strip()])
        user_level = normalize_level(user.get("level", "Beginner"))
        
        # 모든 후보에 대해 기존 방식의 점수 계산
        for cid in all_candidates:
            cid = str(cid)
            c = card_map.get(cid)
            if not c:
                continue

            vec_score = float(vec_scores.get(cid, 0.0))
            
            content_level = normalize_level(c.get("level", "Beginner"))
            if content_level == user_level:
                level_score = 1.0
            else:
                level_order = ["Beginner", "Intermediate", "Advanced"]
                try:
                    user_idx = level_order.index(user_level)
                    content_idx = level_order.index(content_level)
                    level_diff = abs(user_idx - content_idx)
                    level_score = max(0.0, 1.0 - 0.3 * level_diff)
                except ValueError:
                    level_score = 0.5

            content_tags = set(normalize_tags(c.get("tags")))
            overlap = len(itags.intersection(content_tags))
            tag_score = (overlap / max(1, len(itags))) if itags else 0.0

            final_score = params["alpha"] * vec_score + params["beta"] * level_score + params["gamma"] * tag_score

            if cid in seen:
                final_score -= 0.2
            if liked_tags.intersection(content_tags):
                final_score += 0.1

            base_scores[cid] = final_score
        
        # 9) LLM 컨텍스트 리랭킹 (옵션)
        final_ids, rerank_metadata = llm_context_rerank(
            all_candidates, user, all_contents, base_scores,
            top_n=params["top_n"], use_llm_rerank=params["use_llm_rerank"]
        )

        # 10) 결과 구성
        recommended_contents = [card_map[cid] for cid in final_ids if cid in card_map]

        # 11) 상세 사유 추가 (LLM 리랭킹 정보 포함)
        for i, content in enumerate(recommended_contents):
            cid = content["card_id"]
            source = candidate_sources.get(cid, "unknown")
            details = candidate_details.get(cid, {})
            
            # 기본 추천 사유
            if source == "emotion_rule":
                base_reason = f"[감정 기반 룰] {details.get('level_adjustment', '')} (태그 점수: {details.get('tag_score', 0)})"
            elif source == "vector_search":
                model_name = details.get("model", "unknown")
                vec_score = float(details.get("score", 0.0))
                base_reason = f"[벡터 검색 - {model_name}] 유사도 {vec_score:.3f} (레벨 필터링 적용)"
            elif source == "basic_rule":
                base_reason = f"[기본 룰] 레벨 및 관심사 태그 매칭"
            else:
                base_reason = f"[하이브리드] 알 수 없는 출처"
            
            # LLM 리랭킹 정보 추가
            if rerank_metadata.get("llm_used", False):
                context_score = rerank_metadata.get("context_scores", {}).get(cid, None)
                final_score = rerank_metadata.get("final_scores", {}).get(cid, None)
                if context_score is not None:
                    llm_info = f" → LLM 컨텍스트 점수: {context_score:.3f}, 최종점수: {final_score:.3f}"
                    reason = f"{base_reason}{llm_info}"
                else:
                    reason = f"{base_reason} → LLM 평가 없음 (기존 점수 유지)"
            else:
                reason = f"{base_reason} → 수치 기반 리랭킹"
            
            content["recommendation_reason"] = f"순위 {i+1}: {reason}"
            content["recommendation_source"] = source
            content["recommendation_rank"] = i + 1
            content["recommendation_details"] = details

            # 벡터 검색 관련 정보
            if source == "vector_search":
                content["vector_model"] = details.get("model", "unknown")
                content["vector_score"] = float(details.get("score", 0.0))
            
            # LLM 리랭킹 관련 정보
            if rerank_metadata.get("llm_used", False):
                content["llm_context_score"] = rerank_metadata.get("context_scores", {}).get(cid, None)
                content["llm_final_score"] = rerank_metadata.get("final_scores", {}).get(cid, None)
                content["llm_reranked"] = cid in rerank_metadata.get("context_scores", {})

            if source == "emotion_rule":
                content["emotion_adjustment"] = emotion_rule_details

        processing_time = time.time() - start_time
        metadata = {
            "processing_time": processing_time,
            "context_text": ctx_text,
            "data_sources": {
                "rule_based": "Supabase DB",
                "vector_search": "FAISS Index"
            },
            "level_filtering_applied": True,
            "level_filtered_count": len(level_filtered_cards),
            "emotion_rule_candidates": len(emotion_rule_ids),
            "vector_candidates_count": len(vec_ids),
            "basic_rule_candidates": len(basic_rule_ids),
            "total_candidates": len(all_candidates),
            "final_recommendations": len(recommended_contents),
            "models_used": SELECTED_MODELS,
            "model_sources": model_sources,
            "parameters": params,
            "user_level": user_level,
            "user_emotions": emotions,
            "user_interests": interest_tags,
            "emotion_rule_details": emotion_rule_details,
            "candidate_sources_distribution": {
                "emotion_rule_supabase": len(emotion_rule_ids),
                "vector_search_faiss": len(vec_ids),
                "basic_rule_supabase": len(basic_rule_ids),
            },
            "recommendation_sources": [candidate_sources.get(cid, "unknown") for cid in final_ids],
            "llm_rerank_info": rerank_metadata,  # LLM 리랭킹 메타데이터 포함
            "optimization_info": {
                "level_filtering_first": True,
                "vector_search_on_filtered": True,
                "supabase_query_used": True,
                "llm_context_rerank_used": params["use_llm_rerank"],
                "efficiency_improvement": f"벡터 검색 범위를 {len(level_filtered_cards)}/{len(all_contents)} 콘텐츠로 제한"
            },
        }

        result.update({"success": True, "results": recommended_contents, "metadata": metadata})

    except Exception as e:
        result["error"] = f"추천 시스템 오류: {str(e)}"

    return result

# ========================================
# 6. 유효성 검사 & 요약
# ========================================

def validate_user_input(user: Dict) -> Tuple[bool, str]:
    required_fields = ["level", "interest_tags"]
    for field in required_fields:
        if field not in user:
            return False, f"필수 필드 누락: {field}"

    if normalize_level(user["level"]) not in VALID_LEVELS:
        return False, f"유효하지 않은 레벨: {user['level']}"

    if not user["interest_tags"] or len(user["interest_tags"]) == 0:
        return False, "최소 하나 이상의 관심 태그가 필요합니다."
    return True, ""

def get_recommendation_summary(recommendation_result: Dict) -> str:
    if not recommendation_result["success"]:
        return f"❌ 추천 실패: {recommendation_result.get('error', '알 수 없는 오류')}"
    metadata = recommendation_result["metadata"]
    results_count = len(recommendation_result["results"])
    models = ", ".join([str(m) for m in metadata.get("models_used", [])])
    summary = f"""
    ✅ 추천 완료: {results_count}개 콘텐츠
    ⚡ 처리 시간: {metadata['processing_time']:.3f}초
    🎯 사용 모델: {models}
    📊 후보 수: 감정룰 {metadata['emotion_rule_candidates']}개 + 벡터 {metadata['vector_candidates_count']}개 + 기본룰 {metadata['basic_rule_candidates']}개
    👤 사용자 레벨: {metadata['user_level']}
    """
    return summary.strip()

# ========================================
# 7. 테스트용
# ========================================

def test_hybrid_recommendation():
    test_user = {
        "user_id": "test_user",
        "level": "Beginner",
        "emotions": -10,  # 약간 부정적
        "interest_tags": ["ETF", "투자", "경제"],
        "user_summary": "투자에 관심이 많지만 아직 경험이 부족한 초보자",
        "knowledge_summary": "기본적인 금융 용어는 알고 있으나 실제 투자 경험은 없음",
        "recent_seen_card_ids": [],
        "liked_tags": []
    }
    print("🧪 하이브리드 추천 시스템 테스트 (GPT-4o-mini LLM 리랭킹)")
    print("=" * 60)
    result = get_hybrid_recommendations(test_user, use_llm_rerank=True)
    if result["success"]:
        print("✅ 추천 성공!")
        print(get_recommendation_summary(result))
        
        # LLM 리랭킹 정보
        llm_info = result.get("metadata", {}).get("llm_rerank_info", {})
        if llm_info.get("llm_used"):
            print(f"\n🤖 LLM 리랭킹: {llm_info.get('llm_model')} 사용")
            print(f"   평가 후보 수: {llm_info.get('llm_evaluated_candidates', 0)}")
            context_scores = llm_info.get("context_scores", {})
            if context_scores:
                print("   컨텍스트 점수:")
                for cid, score in context_scores.items():
                    print(f"   - {cid[:8]}: {score:.3f}")
        
        print("\n📚 추천 콘텐츠:")
        for i, content in enumerate(result["results"], 1):
            print(f"{i}. {content.get('title', 'Unknown')}")
            print(f"   레벨: {content.get('level')}")
            print(f"   태그: {content.get('tags', [])}")
            if content.get('llm_reranked'):
                ctx_score = content.get('llm_context_score', 0)
                print(f"   🤖 LLM 컨텍스트 점수: {ctx_score:.3f}")
            print()
    else:
        print(f"❌ 추천 실패: {result['error']}")

if __name__ == "__main__":
    test_hybrid_recommendation()
