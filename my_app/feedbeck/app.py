import os
import json
import streamlit as st
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client, Client
import google.generativeai as genai
from google.generativeai import types

# 1) .env 로드
load_dotenv()

# 2) Supabase 초기화
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 3) Gemini 초기화
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
gemini_model = genai.GenerativeModel("gemini-1.5-flash")

# 4) 세션에 user_id 저장 (실제론 로그인/인증값을 쓰세요)
if "user_id" not in st.session_state:
    st.session_state.user_id = "0bfc599a-db77-49ef-8556-31d2be8ffdaf"
USER_ID = st.session_state.user_id


def get_trade_history(user_id: str) -> pd.DataFrame:
    res = (
        supabase
        .table("trade_history")
        .select("*")
        .eq("user_id", user_id)
        .order("trade_time", desc=True)
        .execute()
    )

    # 데이터가 아예 None 이면 에러로 보고 빈 DataFrame 반환
    if res.data is None:
        st.error("거래내역 조회 실패")
        return pd.DataFrame()

    # data 가 비어있으면 빈 DataFrame
    if len(res.data) == 0:
        return pd.DataFrame()

    # 정상적으로 data 가 들어왔으면 DataFrame 으로 변환
    return pd.DataFrame(res.data)

def get_past_feedbacks(user_id: str) -> list:
    """Supabase에서 과거 피드백 리스트 조회"""
    res = (
        supabase
        .table("trade_feedback")
        .select("id, created_at, chart_url, summary_stats, style_type, rank_in_group, benchmark_return")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )

    # 1) API 호출 자체가 실패해서 data 가 None 이면 에러 처리
    if res.data is None:
        st.error("과거 피드백 조회 실패")
        return []

    # 2) data 가 빈 리스트면 그대로 빈 리스트 반환
    if len(res.data) == 0:
        return []

    # 3) 정상적으로 리스트가 있으면 그대로 리턴
    return res.data


def build_prompt(name: str,
                 trades: pd.DataFrame,
                 feedbacks: list) -> str:
    """Gemini LLM 호출을 위한 프롬프트 문자열 생성"""
    lines = []
    lines.append(f"당신은 친절하고 논리적인 주식 투자 코치입니다.")
    lines.append(f"사용자 이름: {name}")
    lines.append("아래 최근 5건의 거래내역을 보고, 향후 매수·매도 타이밍과 위험 관리 전략을 제안해주세요.")
    lines.append("\n=== 최근 거래내역 ===")
    for _, t in trades.head(5).iterrows():
        dt = t["trade_time"][:10]
        lines.append(
            f"- {dt} {t['action'].upper()} {t['symbol']}/{t['market']} "
            f"{t['quantity']}주 @ {t['price']:.2f}"
        )

    if feedbacks:
        lines.append("\n=== 과거 피드백 요약 ===")
        for fb in feedbacks[:3]:
            dt = fb["created_at"][:10]
            stats = json.dumps(fb.get("summary_stats", {}), ensure_ascii=False)
            lines.append(f"- {dt} | 스타일: {fb.get('style_type')} | 지표: {stats}")

    lines.append("\n위 정보를 종합하여,")
    lines.append("1) 한 문장 요약 코칭 메시지")
    lines.append("2) 구체적인 3가지 추천 액션 리스트")
    lines.append("3) 간단한 지표 요약(JSON)")
    lines.append("4) 차트 URL (샘플이라 https://chart.example.com/?q=USER_ID 로 대체)")
    lines.append("형식은 반드시 아래 JSON 스키마를 준수해주세요:")
    lines.append(
        """
```json
{
  "message": "...",
  "recommendations": ["...", "...", "..."],
  "summary_stats": {"win_rate":0.6,"avg_profit":0.08,"max_drawdown":-0.05},
  "chart_url": "https://chart.example.com/?q=0bfc599a-..."
}
```"""
    )
    return "\n".join(lines)


def feedback_page():
    st.title("🤖 AI 거래 피드백 페이지")

    # 1) 프로필 이름 조회 (profiles 테이블에 name 컬럼이 있다고 가정)
    profile = (
        supabase
        .table("profiles")
        .select("name")
        .eq("id", USER_ID)
        .single()
        .execute()
    )
    user_name = profile.data.get("name") if profile.data else USER_ID[:8]

    # 2) 거래내역 & 과거 피드백 불러오기
    trades_df = get_trade_history(USER_ID)
    past_fb = get_past_feedbacks(USER_ID)

    if trades_df.empty:
        st.info("아직 거래 내역이 없습니다. 먼저 매수/매도 페이지에서 거래를 기록하세요.")
        return

    # 3) 최근 거래내역 테이블 표시
    st.subheader("📋 최근 거래내역 (최신 5건)")
    st.table(
        trades_df.head(5)[["trade_time", "action", "symbol", "market", "quantity", "price"]]
        .rename(columns={
            "trade_time": "거래일",
            "action": "행동",
            "symbol": "종목",
            "market": "시장",
            "quantity": "수량",
            "price": "단가"
        })
    )

    # 4) 과거 피드백(있으면) 표시
    st.subheader("📜 과거 피드백")
    if not past_fb:
        st.info("아직 생성된 피드백이 없습니다.")
    else:
        for fb in past_fb:
            with st.expander(f"생성일: {fb['created_at'][:10]}"):
                st.write("스타일:", fb.get("style_type"))
                st.json(fb.get("summary_stats", {}))
                st.markdown(f"[차트 보기]({fb.get('chart_url')})")
                st.write(f"벤치마크 수익률: {fb.get('benchmark_return')} | 순위: {fb.get('rank_in_group')}")

    # 5) 신규 피드백 생성
    if st.button("✨ 신규 AI 코칭 생성"):
        full_prompt = build_prompt(user_name, trades_df, past_fb)

        with st.spinner("Gemini LLM 호출 중..."):
            resp = gemini_model.generate_content(
            full_prompt,
            generation_config=types.GenerationConfig(
                temperature=0.7,
                max_output_tokens=400,
                candidate_count=1
            )
        )
        
        st.write("▶ LLM raw response:", repr(resp.text))

        # result = json.loads(resp.text)
        # LLM이 JSON만 반환했다고 가정
        try:
            result = json.loads(resp.text)
        except Exception as e:
            st.error("LLM 응답 JSON 파싱 실패:" + str(e))
            st.code(resp.text)
            return

        # 6) 결과 화면에 렌더링
        st.subheader("💬 코칭 메시지")
        st.write(result["message"])

        st.subheader("✅ 추천 액션")
        for idx, item in enumerate(result["recommendations"], 1):
            st.write(f"{idx}. {item}")

        st.subheader("📊 지표 요약")
        st.json(result["summary_stats"])

        st.subheader("📈 차트")
        st.markdown(f"[차트 보기]({result['chart_url']})")

        # 7) (선택) 새 피드백을 Supabase에 저장
        save_payload = {
            "user_id": USER_ID,
            "trade_id": trades_df.iloc[0]["id"],
            "chart_url": result["chart_url"],
            "summary_stats": result["summary_stats"],
            "style_type": None,
            "rank_in_group": None,
            "benchmark_return": None
        }
        supabase.table("trade_feedback").insert(save_payload).execute()
        st.success("✅ 새 피드백을 DB에 저장했습니다.")


def main():
    st.sidebar.title("Navigation")
    page = st.sidebar.radio("Go to", ["피드백 페이지"])
    if page == "피드백 페이지":
        feedback_page()


if __name__ == "__main__":
    main()