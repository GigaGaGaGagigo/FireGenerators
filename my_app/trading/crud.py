from sqlalchemy.ext.asyncio import AsyncSession
from my_app.trading.models import Quiz
from datetime import date

async def create_quiz(
    session: AsyncSession,
    user_id: int,
    security_id: str,
    quiz_date: date,
    p0: float,
    p1: float,
    actual_pct: float,
    options: list[float]
) -> Quiz:
    q = Quiz(
        user_id=user_id,
        security_id=security_id,
        quiz_date=quiz_date,
        p0=p0, p1=p1, actual_pct=actual_pct,
        option_a=options[0], option_b=options[1],
        option_c=options[2], option_d=options[3]
    )
    session.add(q)
    await session.commit()
    await session.refresh(q)
    return q

async def update_quiz_answer(
    session: AsyncSession,
    quiz_id: int,
    selected_pct: float,
    error_pct: float,
    skill_score: float,
    is_correct: bool
) -> Quiz:
    q = await session.get(Quiz, quiz_id)
    q.selected_pct = selected_pct
    q.error_pct = error_pct
    q.skill_score = skill_score
    q.is_correct = 1 if is_correct else 0
    await session.commit()
    await session.refresh(q)
    return q