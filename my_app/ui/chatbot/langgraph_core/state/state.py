"""
WRITER: Kang Joseph
DATE: 2025-08-01
DESCRIPTION:
This file defines the state structure used throughout the chat workflow.

TODO: Add variables after adding functions.
"""

from typing import Annotated, TypedDict


class UserState(TypedDict):
    user_email: Annotated[str, "사용자 이메일"]
    name: Annotated[str, "사용자 이름"]
    age: Annotated[int, "사용자 나이"]
    gender: Annotated[str, "사용자 성별"]
    investment_goal: Annotated[list, "투자 목표"]
    emotions: Annotated[list, "사용자 감정"]
    interests_categories: Annotated[list, "사용자 관심분야"]
    investment_level: Annotated[str, "투자 레벨"]
    knowledge_level: Annotated[int, "지식 레벨"]


class ChatState(TypedDict):
    user_messages: Annotated[list, "사용자 메시지"]
    ai_messages: Annotated[list, "AI 메시지"]
    is_analysis_required: Annotated[str, "분석 필요 여부"]
