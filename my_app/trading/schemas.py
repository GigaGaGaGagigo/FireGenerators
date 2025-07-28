from pydantic import BaseModel
from datetime import date
from typing import List

class NewsSummary(BaseModel):
    id: int
    title: str
    summary: str

class QuizResponse(BaseModel):
    quiz_id: int
    quiz_date: date
    p0: float
    p1: float
    actual_pct: float
    options: List[float]
    news: List[NewsSummary]

class SubmitRequest(BaseModel):
    user_id: int
    selected_pct: float

class SubmitResponse(BaseModel):
    actual_pct: float
    error_pct: float
    skill_score: float
    is_correct: bool