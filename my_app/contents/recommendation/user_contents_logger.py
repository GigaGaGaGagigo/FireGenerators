"""
사용자 콘텐츠 조회 로그 관리 모듈
- 사용자가 조회한 콘텐츠와 AI 설명을 실시간으로 기록
- 피드백 및 재추천을 위한 데이터 수집
- 사용자 행동 분석을 위한 로그 저장
"""

import os
from datetime import datetime
from typing import Dict, List, Optional, Any
from supabase import create_client, Client
import json


class UserContentsLogger:
    """사용자 콘텐츠 조회 로그 관리 클래스"""
    
    def __init__(self, supabase_client: Optional[Client] = None):
        """Supabase 클라이언트 초기화"""
        if supabase_client:
            self.supabase = supabase_client
        else:
            self.supabase_url = os.getenv("SUPABASE_URL")
            self.supabase_key = os.getenv("SUPABASE_KEY")
            
            if not self.supabase_url or not self.supabase_key:
                raise ValueError("SUPABASE_URL과 SUPABASE_KEY를 환경변수에 설정해주세요")
            
            self.supabase: Client = create_client(self.supabase_url, self.supabase_key)
    
    def log_content_view(self, 
                        user_id: str,
                        contents_id: str, 
                        content_title: str,
                        original_content: str,
                        ai_explanation: str,
                        user_level: str,
                        user_context: Dict[str, Any],
                        recommendation_source: str = "unknown",
                        recommendation_rank: Optional[int] = None) -> Optional[str]:
        """
        사용자 콘텐츠 조회 로그 저장
        
        Args:
            user_id: 사용자 ID
            contents_id: 콘텐츠 ID (contents 테이블의 id - uuid)
            content_title: 콘텐츠 제목
            original_content: 원본 콘텐츠 내용
            ai_explanation: AI 생성 맞춤 설명
            user_level: 사용자 레벨 (Beginner/Intermediate/Advanced)
            user_context: 사용자 컨텍스트 (감정, 관심사 등)
            recommendation_source: 추천 소스 (vector_search, emotion_rule, basic_rule)
            recommendation_rank: 추천 순위
            
        Returns:
            Optional[str]: 저장된 로그의 ID 또는 실패 시 None
        """
        try:
            log_data = {
                "user_id": user_id,
                "contents_id": contents_id,
                "content_title": content_title,
                "original_content": original_content,
                "ai_explanation": ai_explanation,
                "user_level": user_level,
                "user_context": user_context,  # JSONB로 직접 저장
                "recommendation_source": recommendation_source,
                "recommendation_rank": recommendation_rank,
                "viewed_at": datetime.now().isoformat()
                # explanation_length, original_content_length는 DB에서 자동 계산
            }
            
            response = self.supabase.table("user_contents_log").insert(log_data).execute()
            
            if response.data and len(response.data) > 0:
                return response.data[0].get('id')
            return None
            
        except Exception as e:
            print(f"[ERROR] 콘텐츠 조회 로그 저장 실패: {e}")
            return None

    def log_feedback(
                    self,
                    log_id: str,
                    feedback_type: str,  # positive, neutral, negative
                    feedback_details: Optional[Dict[str, Any]] = None) -> bool:
        """
        사용자 피드백 로그 저장
        
        Args:
            log_id: 피드백을 남길 로그의 ID (user_contents_log 테이블의 id)
            feedback_type: 피드백 유형
            feedback_details: 추가 피드백 정보
            
        Returns:
            bool: 저장 성공 여부
        """
        try:
            # 특정 로그에 피드백 업데이트
            response = (self.supabase.table("user_contents_log")
                        .update({
                            "feedback_type": feedback_type,
                            "feedback_details": feedback_details or {},  # JSONB로 직접 저장
                            "feedback_at": datetime.now().isoformat()
                        })
                        .eq("id", log_id)
                        .execute())
            
            return len(response.data) > 0
            
        except Exception as e:
            print(f"[ERROR] 피드백 로그 저장 실패: {e}")
            return False
    
    def get_user_content_history(self, 
                                user_id: str,
                                limit: int = 50,
                                contents_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        사용자의 콘텐츠 조회 히스토리 조회
        
        Args:
            user_id: 사용자 ID
            limit: 조회 개수 제한
            contents_id: 특정 콘텐츠 ID (선택사항)
            
        Returns:
            List[Dict]: 조회 히스토리 목록
        """
        try:
            query = (self.supabase.table("user_contents_log")
                .select("*")
                .eq("user_id", user_id)
                .order("viewed_at", desc=True)
                .limit(limit))
            
            if contents_id:
                query = query.eq("contents_id", contents_id)
            
            response = query.execute()
            
            # JSONB는 이미 딕셔너리로 반환되므로 별도 변환 불필요
            # user_context와 feedback_details는 JSONB 타입으로 자동 파싱됨
            
            return response.data
            
        except Exception as e:
            print(f"[ERROR] 사용자 히스토리 조회 실패: {e}")
            return []
    
    def get_content_analytics(self, 
                             contents_id: Optional[str] = None,
                             days: int = 30) -> Dict[str, Any]:
        """
        콘텐츠별 분석 데이터 조회
        
        Args:
            contents_id: 특정 콘텐츠 ID (None이면 전체)
            days: 조회 기간 (일)
            
        Returns:
            Dict: 분석 데이터
        """
        try:
            # 기간 계산
            from datetime import timedelta
            start_date = (datetime.now() - timedelta(days=days)).isoformat()
            
            query = (self.supabase.table("user_contents_log")
                .select("*")
                .gte("viewed_at", start_date))
            
            if contents_id:
                query = query.eq("contents_id", contents_id)
            
            response = query.execute()
            data = response.data
            
            if not data:
                return {
                    "total_views": 0,
                    "unique_users": 0,
                    "feedback_distribution": {},
                    "avg_explanation_length": 0,
                    "level_distribution": {},
                    "recommendation_source_distribution": {}
                }
            
            # 분석 계산
            total_views = len(data)
            unique_users = len(set(item["user_id"] for item in data))
            
            # 피드백 분포
            feedback_data = [item["feedback_type"] for item in data if item.get("feedback_type")]
            feedback_distribution = {}
            for feedback in feedback_data:
                feedback_distribution[feedback] = feedback_distribution.get(feedback, 0) + 1
            
            # 평균 설명 길이
            explanation_lengths = [item["explanation_length"] for item in data if item.get("explanation_length")]
            avg_explanation_length = sum(explanation_lengths) / len(explanation_lengths) if explanation_lengths else 0
            
            # 레벨 분포
            level_distribution = {}
            for item in data:
                level = item.get("user_level", "Unknown")
                level_distribution[level] = level_distribution.get(level, 0) + 1
            
            # 추천 소스 분포
            source_distribution = {}
            for item in data:
                source = item.get("recommendation_source", "unknown")
                source_distribution[source] = source_distribution.get(source, 0) + 1
            
            return {
                "total_views": total_views,
                "unique_users": unique_users,
                "feedback_distribution": feedback_distribution,
                "avg_explanation_length": round(avg_explanation_length, 1),
                "level_distribution": level_distribution,
                "recommendation_source_distribution": source_distribution,
                "period_days": days
            }
            
        except Exception as e:
            print(f"[ERROR] 콘텐츠 분석 데이터 조회 실패: {e}")
            return {}
    
    def get_user_behavior_analysis(self, user_id: str, days: int = 30) -> Dict[str, Any]:
        """
        특정 사용자의 행동 분석
        
        Args:
            user_id: 사용자 ID  
            days: 분석 기간 (일)
            
        Returns:
            Dict: 사용자 행동 분석 데이터
        """
        try:
            from datetime import timedelta
            start_date = (datetime.now() - timedelta(days=days)).isoformat()
            
            response = (self.supabase.table("user_contents_log")
                .select("*")
                .eq("user_id", user_id)
                .gte("viewed_at", start_date)
                .order("viewed_at", desc=True)
                .execute())
            
            data = response.data
            
            if not data:
                return {
                    "total_contents_viewed": 0,
                    "avg_daily_views": 0,
                    "favorite_topics": [],
                    "feedback_pattern": {},
                    "learning_progress": {},
                    "engagement_score": 0
                }
            
            total_views = len(data)
            avg_daily_views = round(total_views / days, 1)
            
            # 선호 토픽 분석 (콘텐츠 제목에서 키워드 추출)
            topics = {}
            for item in data:
                title = item.get("content_title", "")
                # 간단한 키워드 추출 (실제로는 더 정교한 분석 필요)
                for keyword in ["투자", "저축", "ETF", "주식", "경제", "금융", "부동산"]:
                    if keyword in title:
                        topics[keyword] = topics.get(keyword, 0) + 1
            
            favorite_topics = sorted(topics.items(), key=lambda x: x[1], reverse=True)[:5]
            
            # 피드백 패턴
            feedback_pattern = {}
            for item in data:
                feedback = item.get("feedback_type")
                if feedback:
                    feedback_pattern[feedback] = feedback_pattern.get(feedback, 0) + 1
            
            # 학습 진행도 (레벨별 조회 분포)
            learning_progress = {}
            for item in data:
                level = item.get("user_level", "Unknown")
                learning_progress[level] = learning_progress.get(level, 0) + 1
            
            # 참여도 점수 (피드백 비율 + 조회 빈도)
            feedback_rate = len([item for item in data if item.get("feedback_type")]) / total_views if total_views > 0 else 0
            engagement_score = round((feedback_rate * 50 + min(avg_daily_views * 10, 50)), 1)
            
            return {
                "total_contents_viewed": total_views,
                "avg_daily_views": avg_daily_views,
                "favorite_topics": favorite_topics,
                "feedback_pattern": feedback_pattern,
                "learning_progress": learning_progress,
                "engagement_score": engagement_score,
                "analysis_period_days": days
            }
            
        except Exception as e:
            print(f"[ERROR] 사용자 행동 분석 실패: {e}")
            return {}

    def get_cached_explanation(self, 
                               contents_id: str,
                               user_level: str) -> Optional[str]:
        """
        특정 콘텐츠와 사용자 레벨에 대해 캐시된 AI 설명을 조회합니다.

        Args:
            contents_id: 콘텐츠 ID (contents 테이블의 id - uuid)
            user_level: 사용자 레벨 (Beginner/Intermediate/Advanced)

        Returns:
            Optional[str]: 캐시된 AI 설명 또는 찾지 못한 경우 None
        """
        try:
            response = (self.supabase.table("user_contents_log")
                        .select("ai_explanation")
                        .eq("contents_id", contents_id)
                        .eq("user_level", user_level)
                        .not_.is_("ai_explanation", "null") # 설명이 비어있지 않은 것
                        .order("viewed_at", desc=True) # 가장 최근 것을 가져옴
                        .limit(1)
                        .execute())
            
            if response.data and response.data[0].get("ai_explanation"):
                print(f"[INFO] Found cached explanation for contents_id={contents_id}, level={user_level}")
                return response.data[0].get("ai_explanation")
            return None
            
        except Exception as e:
            print(f"[INFO] 캐시된 설명 조회 중 오류 발생 (무시하고 계속): {e}")
            return None


# 전역 인스턴스 생성
def get_logger(supabase_client: Optional[Client] = None) -> Optional[UserContentsLogger]:
    """UserContentsLogger 인스턴스 반환"""
    try:
        return UserContentsLogger(supabase_client)
    except Exception as e:
        print(f"[ERROR] UserContentsLogger 초기화 실패: {e}")
        return None