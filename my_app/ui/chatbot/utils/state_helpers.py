"""
LangGraph 상태 관리를 위한 헬퍼 함수들
타입 안전성과 에러 처리를 개선합니다.
"""
import streamlit as st
from typing import Dict, List, Optional, Any
from ui.chatbot.langgraph_core.state import OverallState


def get_quiz_content_safely(state: OverallState, category: str) -> Dict[str, List]:
    """
    안전하게 퀴즈 컨텐츠를 가져옵니다.
    
    Args:
        state: LangGraph 상태
        category: 카테고리 키
    
    Returns:
        Dict[str, List]: 퀴즈 데이터 (questions, options)
    """
    try:
        if hasattr(state, 'quiz_content_by_category'):
            quiz_contents = state.quiz_content_by_category
            if isinstance(quiz_contents, dict) and category in quiz_contents:
                return quiz_contents[category]
        
        # 기본값 반환
        return {"questions": [], "options": []}
        
    except Exception as e:
        st.error(f"퀴즈 컨텐츠 조회 실패: {e}")
        return {"questions": [], "options": []}


def get_current_state_safely() -> Optional[OverallState]:
    """
    안전하게 현재 LangGraph 상태를 가져옵니다.
    
    Returns:
        Optional[OverallState]: 상태 객체 또는 None
    """
    try:
        if "graph" not in st.session_state or "config" not in st.session_state:
            st.error("그래프 또는 설정이 초기화되지 않았습니다.")
            return None
        
        graph = st.session_state.graph
        config = st.session_state.config
        
        state = graph.get_state(config)
        return state
        
    except Exception as e:
        st.error(f"상태 조회 실패: {e}")
        return None


def sync_quiz_data_to_session(state: OverallState, category: str) -> bool:
    """
    LangGraph 상태의 퀴즈 데이터를 세션 상태로 동기화합니다.
    
    Args:
        state: LangGraph 상태
        category: 카테고리 키
    
    Returns:
        bool: 동기화 성공 여부
    """
    try:
        quiz_data = get_quiz_content_safely(state, category)
        
        if category not in st.session_state["quiz"]:
            st.session_state["quiz"][category] = {"questions": [], "options": []}
        
        st.session_state["quiz"][category]["questions"] = quiz_data.get("questions", [])
        st.session_state["quiz"][category]["options"] = quiz_data.get("options", [])
        
        return True
        
    except Exception as e:
        st.error(f"퀴즈 데이터 동기화 실패: {e}")
        return False


def get_current_question_info(category: str) -> Optional[Dict[str, Any]]:
    """
    현재 표시할 질문 정보를 가져옵니다.
    
    Args:
        category: 카테고리 키
    
    Returns:
        Optional[Dict]: 질문 정보 또는 None
    """
    try:
        if category not in st.session_state["quiz"]:
            return None
        
        questions = st.session_state["quiz"][category].get("questions", [])
        options = st.session_state["quiz"][category].get("options", [])
        
        if not questions:
            return None
        
        # 현재 질문 인덱스 계산
        answered_count = len(st.session_state["user_answers"].get(category, []))
        
        if answered_count >= len(questions):
            return None  # 모든 질문 완료
        
        current_question = questions[answered_count]
        current_options = options[answered_count] if answered_count < len(options) else []
        
        return {
            "question": current_question,
            "options": current_options,
            "index": answered_count,
            "total": len(questions)
        }
        
    except Exception as e:
        st.error(f"질문 정보 조회 실패: {e}")
        return None


def validate_session_state() -> bool:
    """
    필수 세션 상태가 올바르게 초기화되었는지 확인합니다.
    
    Returns:
        bool: 검증 성공 여부
    """
    required_keys = ["graph", "config", "ai", "quiz", "user_answers"]
    
    for key in required_keys:
        if key not in st.session_state:
            st.error(f"필수 세션 상태 '{key}'가 초기화되지 않았습니다.")
            return False
    
    return True


def debug_state_info() -> Dict[str, Any]:
    """
    디버깅을 위한 상태 정보를 수집합니다.
    
    Returns:
        Dict[str, Any]: 디버그 정보
    """
    try:
        state = get_current_state_safely()
        if not state:
            return {"error": "상태 조회 실패"}
        
        return {
            "target_profile_category": getattr(state, "target_profile_category", []),
            "profile_status": getattr(state, "profile_status", None),
            "workflow_stage": getattr(state, "workflow_stage", None),
            "evaluation_results": getattr(state, "evaluation_results", {}),
            "investment_goal": getattr(state, "investment_goal", []),
            "investment_emotions": getattr(state, "investment_emotions", []),
            "interests_categories": getattr(state, "interests_categories", []),
            "investment_level": getattr(state, "investment_level", ""),
            "knowledge_level": getattr(state, "knowledge_level", ""),
            "evaluation_results_logs": getattr(state, "evaluation_results_logs", {}),
        }
        
    except Exception as e:
        return {"error": f"디버그 정보 수집 실패: {e}"}