"""
사용자 프로필 관리를 위한 서비스 레이어
LangGraph와 Streamlit/Supabase 간의 깔끔한 분리를 제공합니다.
"""

from typing import Any, Callable, Dict, Optional

import streamlit as st
from supabase import Client

from ui.chatbot.langgraph_core.state import OverallState


class ProfileService:
    """프로필 데이터 관리를 담당하는 서비스 클래스"""

    def __init__(self):
        self._update_callbacks: list[Callable[[str, Any], bool]] = []
        self._completion_callbacks: list[Callable[[Dict[str, Any]], bool]] = []

    def add_update_callback(self, callback: Callable[[str, Any], bool]):
        """카테고리별 업데이트 콜백 등록"""
        self._update_callbacks.append(callback)

    def add_completion_callback(self, callback: Callable[[Dict[str, Any]], bool]):
        """프로필 완성 콜백 등록"""
        self._completion_callbacks.append(callback)

    def notify_category_update(self, category: str, data: Any) -> bool:
        """카테고리 업데이트 알림"""
        results = []
        for callback in self._update_callbacks:
            try:
                results.append(callback(category, data))
            except Exception as e:
                st.error(f"업데이트 콜백 실행 오류: {e}")
                results.append(False)
        return all(results)

    def notify_profile_completion(self, profile_data: Dict[str, Any]) -> bool:
        """프로필 완성 알림"""
        results = []
        for callback in self._completion_callbacks:
            try:
                results.append(callback(profile_data))
            except Exception as e:
                st.error(f"완성 콜백 실행 오류: {e}")
                results.append(False)
        return all(results)


# 전역 서비스 인스턴스 (Streamlit 세션에서 관리)
def get_profile_service() -> ProfileService:
    """프로필 서비스 인스턴스를 가져옵니다 (세션별 싱글톤)"""
    if "profile_service" not in st.session_state:
        st.session_state.profile_service = ProfileService()

        # Supabase 업데이트 콜백 등록
        st.session_state.profile_service.add_update_callback(supabase_update_callback)
        st.session_state.profile_service.add_completion_callback(
            supabase_completion_callback
        )

    return st.session_state.profile_service


# Supabase 연동 콜백 함수들
def supabase_update_callback(category: str, data: Any) -> bool:
    """Supabase에 카테고리별 데이터 업데이트"""
    try:
        supabase: Client = st.session_state.get("supabase")
        user_id = st.session_state.get("user", {}).id

        if not supabase or not user_id:
            return False

        result = (
            supabase.table("profiles")
            .update({category: data})
            .eq("id", user_id)
            .execute()
        )

        # 세션 상태도 동기화
        if "user_data" in st.session_state:
            st.session_state.user_data[category] = data

        return bool(result.data)

    except Exception as e:
        st.error(f"Supabase 업데이트 실패: {e}")
        return False


def supabase_completion_callback(profile_data: Dict[str, Any]) -> bool:
    """프로필 완성 시 전체 데이터 저장"""
    try:
        supabase: Client = st.session_state.get("supabase")
        user_id = st.session_state.get("user", {}).id

        if not supabase or not user_id:
            return False

        result = (
            supabase.table("profiles").update(profile_data).eq("id", user_id).execute()
        )

        if result.data:
            st.success("🎉 프로필이 성공적으로 저장되었습니다!")

            # 세션 상태 전체 동기화
            if "user_data" in st.session_state:
                st.session_state.user_data.update(profile_data)
            return True

        return False

    except Exception as e:
        st.error(f"프로필 완성 저장 실패: {e}")
        return False


# LangGraph에서 사용할 헬퍼 함수
def trigger_profile_update_from_state(state: OverallState) -> bool:
    """
    LangGraph 상태에서 프로필 서비스로 업데이트 알림
    이 함수는 Streamlit UI 레이어에서 호출됩니다.
    """
    service = get_profile_service()

    # 현재 완료된 카테고리 찾기
    if hasattr(state, "target_profile_category") and state.target_profile_category:
        # 가장 최근에 완료된 카테고리 데이터 전송
        categories_data = {
            "investment_goal": state.investment_goal,
            "investment_emotions": state.investment_emotions,
            "interests_categories": state.interests_categories,
            "investment_level": state.investment_level,
            "knowledge_level": state.knowledge_level,
        }

        # 변경된 데이터만 업데이트
        success = True
        for category, data in categories_data.items():
            if data and (
                isinstance(data, list)
                and len(data) > 0
                or isinstance(data, str)
                and data.strip()
            ):
                if not service.notify_category_update(category, data):
                    success = False

        # 프로필이 완성되었다면 완성 알림도 전송
        if state.profile_status == "completed":
            service.notify_profile_completion(categories_data)

        return success

    return False
