import streamlit as st
import json
from pathlib import Path
from datetime import datetime
import pandas as pd

RESULT_DIR = Path(__file__).parent / "final_result"
RESULT_DIR.mkdir(exist_ok=True)
PROFILE_CSV = Path(__file__).parent / "profiles_test_rows.csv"

# CSV 로드
if PROFILE_CSV.exists():
    profiles_df = pd.read_csv(PROFILE_CSV)
else:
    profiles_df = pd.DataFrame()

def get_user_profile(user_name):
    """사용자 이름으로 프로필 가져오기"""
    if profiles_df.empty:
        return None
    profile = profiles_df[profiles_df['name'] == user_name]
    if profile.empty:
        return None
    return profile.iloc[0].to_dict()

def load_latest_llm_results():
    json_files = list(RESULT_DIR.glob("llm_evaluation_detailed_*.json"))
    if not json_files:
        st.error("❌ LLM 평가 결과 파일이 없습니다. 먼저 llm_judge.py를 실행하세요.")
        return []
    latest_file = max(json_files, key=lambda x: x.stat().st_mtime)
    with open(latest_file, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_feedback_results(results):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # JSON 저장
    detailed_path = RESULT_DIR / f"human_feedback_detailed_{timestamp}.json"
    with open(detailed_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    # CSV 저장
    summary_data = []
    for r in results:
        row = {
            'user_name': r['user_name'],
            'human_overall_score': r['human_overall_score'],
            'average_llm_score': r['average_llm_score'],
            'score_difference': r['human_overall_score'] - r['average_llm_score'],
            'human_comment': r['human_comment'],
            'timestamp': r['timestamp']
        }
        # 세부 점수 추가
        if 'human_detailed_scores' in r:
            for key, score in r['human_detailed_scores'].items():
                row[f'human_{key}_score'] = score
        
        summary_data.append(row)
    df = pd.DataFrame(summary_data)
    csv_path = RESULT_DIR / f"human_feedback_summary_{timestamp}.csv"
    df.to_csv(csv_path, index=False, encoding='utf-8-sig')
    st.success(f"💾 저장 완료! 상세: {detailed_path}, 요약: {csv_path}")

def display_user_feedback(result, idx, total):
    st.header(f"평가 {idx+1}/{total}: {result['user_name']}")

    # 사용자 프로필 가져오기
    profile = get_user_profile(result['user_name'])
    
    st.subheader("👤 사용자 정보")
    st.write(f"이름: {result['user_name']}")
    if profile:
        st.write(f"나이: {profile.get('age', 'N/A')}")
        st.write(f"성별: {profile.get('gender', 'N/A')}")
        st.write(f"투자 목표: {profile.get('investment_goal', 'N/A')}")
        st.write(f"투자 성향: {profile.get('investment_emotions', 'N/A')}")
        st.write(f"관심 카테고리: {profile.get('interests_categories', 'N/A')}")
        st.write(f"투자 레벨: {profile.get('investment_level', 'N/A')}")
        st.write(f"지식 수준: {profile.get('knowledge_level', 'N/A')}")
        if pd.notna(profile.get('user_summary')):
            st.write(f"요약: {profile.get('user_summary')}")
    st.markdown("---")

    st.subheader("📋 추천 콘텐츠")
    for i, rec in enumerate(result['real_recommendations'], 1):
        st.markdown(f"**{i}. {rec['title']}**")
        st.write(f"내용: {rec['content']}")
        st.write(f"난이도: {rec['level']}, 태그: {', '.join(rec.get('tags', []))}")
        if rec.get('custom_explanation') and rec['custom_explanation'] != 'N/A':
            st.write(f"맞춤 설명: {rec['custom_explanation'][:300]}{'...' if len(rec['custom_explanation'])>300 else ''}")
    st.markdown("---")

    st.subheader("🤖 LLM 평가 점수")
    st.write(f"전체 평균: {result['average_llm_score']:.2f}/5.0")
    for model, score in result['llm_scores'].items():
        st.write(f"{model} 전체: {score:.2f}/5.0")
        if model in result.get('llm_detailed_scores', {}):
            st.write(result['llm_detailed_scores'][model])
    st.markdown("---")

    st.subheader("📝 Human Feedback 입력")
    overall_score = st.slider("전체 추천+설명 품질 점수 (1-5)", 1.0, 5.0, 3.0, 0.1, key=f"overall_{idx}")

    st.markdown("세부 평가 (선택)")
    criteria_scores = {}
    criteria = [
        ("suitability", "적합성 - 사용자 지식 수준에 적합한가?"),
        ("relevance", "관련성 - 사용자 관심사와 얼마나 관련있는 추천인가?"),
        ("diversity", "다양성 - 추천 콘텐츠들이 다양한 관점을 제공하는가?"),
        ("coherence", "일관성 - 콘텐츠와 맞춤 설명이 자연스럽고 논리적으로 연결되는가?")
    ]
    for key, label in criteria:
        criteria_scores[key] = st.slider(label, 1.0, 5.0, 3.0, 0.1, key=f"{key}_{idx}")
    
    comment = st.text_area("추가 코멘트", key=f"comment_{idx}")
    
    if st.button("✅ 평가 완료, 다음으로", key=f"submit_{idx}"):
        feedback = {
            "human_overall_score": overall_score,
            "human_detailed_scores": criteria_scores,
            "human_comment": comment or "없음",
            "timestamp": datetime.now().isoformat()
        }
        combined = {**result, **feedback}
        return combined
    return None

def main():
    st.title("👨‍👩‍👧‍👦 Human Feedback 수집기")
    
    llm_results = load_latest_llm_results()
    if not llm_results:
        return
    
    max_eval = st.sidebar.number_input("평가할 최대 개수", min_value=1, max_value=100, value=30)
    results_to_evaluate = llm_results[:max_eval]
    
    if 'current_idx' not in st.session_state:
        st.session_state.current_idx = 0
    if 'feedback_results' not in st.session_state:
        st.session_state.feedback_results = []
    
    if st.session_state.current_idx < len(results_to_evaluate):
        result = results_to_evaluate[st.session_state.current_idx]
        feedback = display_user_feedback(result, st.session_state.current_idx, len(results_to_evaluate))
        if feedback:
            st.session_state.feedback_results.append(feedback)
            st.session_state.current_idx += 1
            st.stop()
            
    else:
        st.success("🎉 모든 평가 완료!")
        if st.button("💾 모든 평가 저장"):
            save_feedback_results(st.session_state.feedback_results)

if __name__ == "__main__":
    main()