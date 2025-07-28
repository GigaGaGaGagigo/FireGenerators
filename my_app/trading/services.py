# my_app/trading/services.py

from supabase import create_client, Client
from datetime import date, datetime, timedelta
from datetime import date
from fastapi import BackgroundTasks
import pandas as pd
import openai
import pytz

from my_app.trading.trading_config import settings
from my_app.trading.stock import collect_economic_data

# Supabase 클라이언트 싱글톤
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)

# OpenAI 키 셋팅
openai.api_key = settings.KIS_BASE_URL

def make_options(actual_pct: float) -> list[float]:
    base = round(actual_pct, 1)
    return [
        round(base - 20, 1),
        round(base - 10, 1),
        base,
        round(base + 10, 1),
    ]

def calc_skill_score(error_pct: float, k: float = 2.0) -> float:
    return max(0.0, 100.0 - k * error_pct)

def get_price_from_supabase(security_id: str, target_date: date) -> float:
    resp = (
        supabase
        .table("prices")
        .select("close, date")
        .eq("security_id", security_id)
        .lte("date", target_date.isoformat())
        .order("date", desc=True)
        .limit(1)
        .execute()
    )
    data = resp.data or []
    if not data:
        raise ValueError(f"No price for {security_id} at {target_date}")
    return float(data[0]["close"])

def get_news_summaries_from_supabase(security_id: str, n: int = 2) -> list[dict]:
    resp = (
        supabase
        .table("news_articles")
        .select("id, title, summary")
        .eq("security_id", security_id)
        .order("published_at", desc=True)
        .limit(n)
        .execute()
    )
    return resp.data or []

def create_quiz_supabase(
    user_id: int,
    security_id: str,
    quiz_date: date,
    p0: float,
    p1: float,
    actual_pct: float,
    options: list[float],
) -> dict:
    payload = {
        "user_id": user_id,
        "security_id": security_id,
        "quiz_date": quiz_date.isoformat(),
        "p0": p0,
        "p1": p1,
        "actual_pct": actual_pct,
        "option_a": options[0],
        "option_b": options[1],
        "option_c": options[2],
        "option_d": options[3],
    }
    resp = supabase.table("quizzes").insert(payload).execute()
    data = resp.data or []
    if not data:
        raise RuntimeError("Quiz insert failed")
    return data[0]

def update_quiz_supabase(
    quiz_id: int,
    selected_pct: float,
    error_pct: float,
    skill_score: float,
    is_correct: bool,
) -> dict:
    update_payload = {
        "selected_pct": selected_pct,
        "error_pct": error_pct,
        "skill_score": skill_score,
        "is_correct": is_correct,
    }
    resp = (
        supabase
        .table("quizzes")
        .update(update_payload)
        .eq("id", quiz_id)
        .execute()
    )
    data = resp.data or []
    if not data:
        raise RuntimeError("Quiz update failed")
    return data[0]

def get_last_updated_date() -> str:
    try:
        response = supabase.table("economic_and_stock_data").select("날짜").order("날짜", desc=True).limit(1).execute()
        if response.data:
            last_date = datetime.fromisoformat(response.data[0]["날짜"].replace('Z', '+00:00'))
            return (last_date + timedelta(days=1)).strftime('%Y-%m-%d')
        return "2006-01-01"
    except Exception:
        return "2006-01-01"

async def update_economic_data():
    try:
        now = datetime.now()
        hour, minute = now.hour, now.minute
        if (hour == 22 and minute >= 30) or (22 < hour or hour < 6):
            print("미국 장 시간입니다. 수집 중단.")
            return

        start_date = get_last_updated_date()
        today = datetime.now().strftime('%Y-%m-%d')
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

        if start_date > yesterday:
            print("수집할 데이터가 없습니다.")
            return

        new_data = collect_economic_data(start_date=start_date, end_date=today)
        if new_data is None or new_data.empty:
            print("수집된 데이터 없음")
            return

        all_dates = pd.date_range(start=start_date, end=yesterday)
        for date_obj in all_dates:
            date_str = date_obj.strftime('%Y-%m-%d')
            row = new_data.loc[date_obj] if date_obj in new_data.index else pd.Series(dtype='object')
            prev_date = (date_obj - timedelta(days=1)).strftime('%Y-%m-%d')
            prev = supabase.table("economic_and_stock_data").select("*").eq("날짜", prev_date).execute().data
            prev_data = prev[0] if prev else {}
            
            data_dict = {k: v for k, v in row.items() if not pd.isna(v)}
            for k, v in prev_data.items():
                if k != "날짜" and k not in data_dict and v is not None:
                    data_dict[k] = v

            exists = supabase.table("economic_and_stock_data").select("*").eq("날짜", date_str).execute().data
            if exists:
                update_dict = {k: v for k, v in data_dict.items() if exists[0].get(k) is None}
                if update_dict:
                    supabase.table("economic_and_stock_data").update(update_dict).eq("날짜", date_str).execute()
            else:
                record = {"날짜": date_str, **data_dict}
                supabase.table("economic_and_stock_data").insert(record).execute()

        print("경제 데이터 업데이트 완료")
    except Exception as e:
        print(f"업데이트 오류: {str(e)}")


def update_economic_data_in_background(background_tasks: BackgroundTasks):
    background_tasks.add_task(update_us_indicators, date.today())
    background_tasks.add_task(update_etf_prices, date.today())