from typing import Any, Dict, Optional

import streamlit as st
from supabase import Client

from ui.chatbot.langgraph_core.state import OverallState


def get_supabase_client() -> Optional[Client]:
    return st.session_state.get("supabase")


def get_current_user_id() -> Optional[str]:
    user = st.session_state.get("user")
    return user.id if user else None


def update_user_profile_to_supabase(
    category: str, data: Any, user_id: Optional[str] = None
) -> bool:
    """
    특정 카테고리의 사용자 프로필 데이터를 Supabase에 업데이트합니다.

    Args:
        category: 업데이트할 카테고리 ('investment_goal', 'investment_emotions', etc.)
        data: 업데이트할 데이터
        user_id: 사용자 ID (None이면 현재 로그인 사용자)

    Returns:
        bool: 업데이트 성공 여부
    """
    try:
        supabase = get_supabase_client()
        if not supabase:
            st.error("Supabase 클라이언트를 찾을 수 없습니다.")
            return False

        if not user_id:
            user_id = get_current_user_id()
            if not user_id:
                st.error("사용자 정보를 찾을 수 없습니다.")
                return False

        # 데이터 업데이트
        result = (
            supabase.table("profiles")
            .update({category: data})
            .eq("id", user_id)
            .execute()
        )

        if result.data:
            # 세션 상태의 user_data도 동기화
            if "user_data" in st.session_state:
                st.session_state.user_data[category] = data
            return True
        else:
            st.error(f"프로필 업데이트 실패: {category}")
            return False

    except Exception as e:
        st.error(f"데이터베이스 업데이트 중 오류 발생: {e}")
        return False


def sync_langgraph_state_to_supabase(state: OverallState) -> Dict[str, bool]:
    """
    LangGraph 상태의 모든 프로필 데이터를 Supabase에 동기화합니다.

    Args:
        state: LangGraph의 OverallState

    Returns:
        Dict[str, bool]: 각 카테고리별 업데이트 성공 여부
    """
    results = {}

    # 각 카테고리별로 데이터가 있으면 업데이트
    categories_data = {
        "investment_goal": state.investment_goal,
        "investment_emotions": state.investment_emotions,
        "interests_categories": state.interests_categories,
        "investment_level": state.investment_level,
        "knowledge_level": state.knowledge_level,
    }

    for category, data in categories_data.items():
        # 데이터가 비어있지 않은 경우에만 업데이트
        if data and (
            isinstance(data, list)
            and len(data) > 0
            or isinstance(data, str)
            and data.strip()
        ):
            results[category] = update_user_profile_to_supabase(category, data)
        else:
            results[category] = True  # 빈 데이터는 스킵

    return results


def batch_update_profile_on_completion(state: OverallState) -> bool:
    """
    프로필이 완료되었을 때 전체 데이터를 한 번에 업데이트합니다.

    Args:
        state: LangGraph의 OverallState

    Returns:
        bool: 전체 업데이트 성공 여부
    """
    if state.profile_status != "completed":
        return False

    results = sync_langgraph_state_to_supabase(state)
    success_count = sum(1 for success in results.values() if success)
    total_count = len(results)

    if success_count == total_count:
        st.success("🎉 프로필이 성공적으로 저장되었습니다!")
        return True
    else:
        st.warning(f"⚠️ 프로필 저장 중 일부 오류 발생 ({success_count}/{total_count})")
        return False


# TODO(human): 실시간 업데이트 전략 구현
def realtime_update_on_answer(category: str, answers: list) -> bool:
    """
    사용자가 답변을 완료할 때마다 실시간으로 DB를 업데이트합니다.

    이 함수는 각 질문 카테고리가 완료될 때마다 호출되어야 합니다.
    답변 데이터를 적절한 형태로 변환하고 즉시 Supabase에 저장합니다.

    Args:
        category: 완료된 질문 카테고리 ('investment_goal', 'investment_emotions', etc.)
        answers: 사용자 답변 리스트 [(질문, 답변), (질문, 답변), ...]

    Returns:
        bool: 업데이트 성공 여부

    구현 고려사항:
    - 답변을 어떤 형태로 저장할지 결정 (JSON, 배열, 문자열 등)
    - 에러 처리 및 재시도 로직
    - 사용자 피드백 (저장 중 표시, 성공/실패 메시지)
    """
    # 여기에 실시간 업데이트 로직을 구현하세요
    pass
