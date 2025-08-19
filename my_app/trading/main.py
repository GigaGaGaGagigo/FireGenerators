# main.py
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from datetime import date, timedelta

from my_app.trading.trading_config import settings
from my_app.trading.services import (
    get_price_from_supabase,
    get_news_summaries_from_supabase,
    make_options,
    calc_skill_score,
    create_quiz_supabase,
    update_quiz_supabase,
    update_economic_data_in_background  # ✅ 경제 데이터 업데이트 함수 추가
)
from my_app.trading.schemas import QuizResponse, SubmitRequest, SubmitResponse

app = FastAPI(
    title="모의 투자 & 시뮬레이션 퀴즈",
    debug=False
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ 앱 시작 시 경제 데이터 업데이트
@app.on_event("startup")
async def on_startup():
    print("⏳ 서비스 시작 시 경제 데이터 수집을 실행합니다...")
    try:
        await update_economic_data_in_background()
        print("✅ 초기 경제 데이터 수집 완료")
    except Exception as e:
        print(f"❌ 경제 데이터 수집 중 오류: {e}")

@app.get("/quiz/{security_id}", response_model=QuizResponse)
def get_quiz(security_id: str, user_id: int = 1):
    today = date.today()
    three_months_ago = today - timedelta(days=90)

    p0 = get_price_from_supabase(security_id, three_months_ago)
    p1 = get_price_from_supabase(security_id, today)
    actual_pct = (p1 - p0) / p0 * 100

    options = make_options(actual_pct)
    news = get_news_summaries_from_supabase(security_id, n=2)

    quiz_row = create_quiz_supabase(
        user_id, security_id, today, p0, p1, actual_pct, options
    )

    return QuizResponse(
        quiz_id=quiz_row["id"],
        quiz_date=quiz_row["quiz_date"],
        p0=quiz_row["p0"],
        p1=quiz_row["p1"],
        actual_pct=quiz_row["actual_pct"],
        options=[quiz_row["option_a"], quiz_row["option_b"], quiz_row["option_c"], quiz_row["option_d"]],
        news=news
    )

@app.post("/quiz/{quiz_id}/submit", response_model=SubmitResponse)
def submit_quiz(quiz_id: int, body: SubmitRequest):
    original = (
        supabase
        .table("quizzes")
        .select("actual_pct")
        .eq("id", quiz_id)
        .single()
        .execute()
    ).data

    if not original:
        raise HTTPException(status_code=404, detail="Quiz not found")

    actual_pct = float(original["actual_pct"])
    error_pct = abs(body.selected_pct - actual_pct)
    skill = calc_skill_score(error_pct, k=2.0)
    is_corr = error_pct <= 5.0

    updated = update_quiz_supabase(
        quiz_id, body.selected_pct, error_pct, skill, is_corr
    )

    return SubmitResponse(
        actual_pct=updated["actual_pct"],
        error_pct=updated["error_pct"],
        skill_score=updated["skill_score"],
        is_correct=bool(updated["is_correct"])
    )

if __name__ == "__main__":
    uvicorn.run("my_app.trading.main:app", host="0.0.0.0", port=8000, reload=True)
