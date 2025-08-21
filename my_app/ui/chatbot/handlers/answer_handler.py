"""
사용자 답변 처리를 위한 핸들러 모듈
복잡한 on_answer_change 로직을 역할별로 분리합니다.
"""
import streamlit as st
from typing import Tuple, List
from ui.chatbot.langgraph_core.state import OverallState
from ui.chatbot.services.profile_service import trigger_profile_update_from_state


class AnswerHandler:
    """사용자 답변 처리를 담당하는 클래스"""
    
    def __init__(self):
        self.config = st.session_state.config
        self.graph = st.session_state.graph
    
    def handle_answer_submission(
        self, 
        choice: str,
        question_text: str, 
        category_key: str,
        current_q_index: int,
        total_questions: int
    ) -> bool:
        """
        사용자 답변 제출을 처리합니다.
        
        Returns:
            bool: 처리 성공 여부
        """
        try:
            # 1. 답변을 세션 상태에 저장
            if not self._save_answer_to_session(question_text, choice, category_key):
                return False
            
            # 2. 마지막 질문인지 확인
            if current_q_index + 1 >= total_questions:
                return self._handle_category_completion(category_key)
            
            return True
            
        except Exception as e:
            st.error(f"답변 처리 중 오류 발생: {e}")
            return False
    
    def _save_answer_to_session(self, question: str, answer: str, category: str) -> bool:
        """답변을 세션 상태에 저장"""
        try:
            user_answers = st.session_state["user_answers"][category]
            user_answers.append((question, answer))
            return True
        except Exception as e:
            st.error(f"답변 저장 실패: {e}")
            return False
    
    def _handle_category_completion(self, category_key: str) -> bool:
        """카테고리 완료 시 처리"""
        try:
            # 현재 상태 조회
            state = self.graph.get_state(self.config)
            if not state:
                st.error("그래프 상태를 가져올 수 없습니다.")
                return False
            
            user_answers = st.session_state["user_answers"][category_key]
            
            # 워크플로우 단계에 따른 처리
            if state.workflow_stage == "generate_qa":
                return self._process_generate_qa_stage(category_key, user_answers)
            elif state.workflow_stage == "finished_qa":
                return self._process_finished_qa_stage(category_key, user_answers)
            else:
                st.warning(f"알 수 없는 워크플로우 단계: {state.workflow_stage}")
                return False
                
        except Exception as e:
            st.error(f"카테고리 완료 처리 실패: {e}")
            return False
    
    def _process_generate_qa_stage(self, category_key: str, user_answers: List[Tuple[str, str]]) -> bool:
        """generate_qa 단계 처리"""
        try:
            # LangGraph 상태 업데이트
            self.graph.graph.update_state(
                self.config,
                {
                    "answers_by_category": {
                        category_key: user_answers
                    }
                }
            )
            
            # 다음 단계 실행
            self.graph.invoke(None, config=self.config)
            return True
            
        except Exception as e:
            st.error(f"generate_qa 단계 처리 실패: {e}")
            return False
    
    def _process_finished_qa_stage(self, category_key: str, user_answers: List[Tuple[str, str]]) -> bool:
        """finished_qa 단계 처리"""
        try:
            # LangGraph 상태 업데이트
            self.graph.graph.update_state(
                self.config,
                {
                    "answers_by_category": {
                        category_key: user_answers
                    }
                }
            )
            
            # 최종 결과 저장
            result = self.graph.invoke(None, config=self.config)
            st.session_state["state_result"] = result
            
            # Profile Service를 통한 데이터 저장
            self._trigger_profile_update()
            
            return True
            
        except Exception as e:
            st.error(f"finished_qa 단계 처리 실패: {e}")
            return False
    
    def _trigger_profile_update(self):
        """프로필 업데이트 트리거"""
        try:
            # 최신 상태 가져오기
            state = self.graph.get_state(self.config)
            if state:
                # Profile Service를 통해 Supabase에 저장
                success = trigger_profile_update_from_state(state)
                if success:
                    st.info("✅ 프로필 데이터가 저장되었습니다.")
                else:
                    st.warning("⚠️ 프로필 저장 중 일부 문제가 발생했습니다.")
            else:
                st.error("상태 정보를 가져올 수 없어 프로필 저장을 건너뜁니다.")
                
        except Exception as e:
            st.error(f"프로필 업데이트 실패: {e}")


def create_answer_callback(
    question_text: str,
    total_questions: int,
    current_q_index: int,
    category_key: str,
    idx_key: str
):
    """
    답변 콜백 함수를 생성합니다.
    
    이 함수는 기존의 복잡한 on_answer_change를 대체합니다.
    """
    def on_answer_change():
        choice = st.session_state.get(idx_key)
        if choice:
            handler = AnswerHandler()
            success = handler.handle_answer_submission(
                choice=choice,
                question_text=question_text,
                category_key=category_key,
                current_q_index=current_q_index,
                total_questions=total_questions
            )
            
            if not success:
                st.error("답변 처리에 실패했습니다. 다시 시도해주세요.")
    
    return on_answer_change