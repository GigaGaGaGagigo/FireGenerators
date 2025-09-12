import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.colors as pc
from pathlib import Path
import json

# Pastel 색상 팔레트
pastel = pc.qualitative.Pastel

st.set_page_config(page_title="FIREgenerator 추천 운영 분석", layout="wide")

# === CSS 스타일 ===
st.markdown("""
<style>
    .metric-container {
        background: white;
        border-radius: 8px;
        padding: 1rem;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        text-align: center;
        margin-bottom: 1rem;
    }
    .insight-box {
        background: #f8f4ff !important;
        border: 1px solid #a5b4fc !important;
        border-radius: 8px;
        padding: 1rem;
        margin: 1rem 0;
    }
    .warning-box {
        background: #fef3c7 !important;
        border: 1px solid #fbbf24 !important;
        border-radius: 8px;
        padding: 1rem;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

st.title("🔥 FIREgenerator 추천 시스템 운영 대시보드")
st.markdown("**실제 운영에 도움이 되는 인사이트 제공**")
st.markdown("---")

# === 데이터 로드 ===
@st.cache_data
def load_data():
    current_dir = Path(__file__).parent.resolve()
    data_file = current_dir / "human_feedback_detailed_20250911_223636.json"
    
    if not data_file.exists():
        st.error(f"JSON 파일을 찾을 수 없습니다: {data_file}")
        st.stop()
    
    with open(data_file, "r", encoding="utf-8") as f:
        raw = json.load(f)
    
    records = []
    for user in raw:
        user_name = user.get("user_name")
        for rec in user.get("real_recommendations", []):
            records.append({
                "user": user_name,
                "title": rec.get("title"),
                "source": rec.get("recommendation_source"),
                "model": rec.get("vector_model"),
                "vector_score": rec.get("vector_score"),
                "llm_score": rec.get("llm_final_score"),
                "rank": rec.get("recommendation_rank"),
                "reason": rec.get("recommendation_reason"),
                "content": rec.get("content", ""),
                "level": rec.get("level", ""),
                "tags": rec.get("tags", [])
            })
    
    return pd.DataFrame(records)

df = load_data()

# === 사이드바 필터 ===
st.sidebar.header("🔧 분석 필터")
selected_models = st.sidebar.multiselect(
    "임베딩 모델 선택", 
    options=sorted(df["model"].dropna().unique()),
    default=sorted(df["model"].dropna().unique())
)

selected_sources = st.sidebar.multiselect(
    "추천 소스 선택", 
    options=sorted(df["source"].dropna().unique()),
    default=sorted(df["source"].dropna().unique())
)

filtered_df = df[df["model"].isin(selected_models) & df["source"].isin(selected_sources)]

# === 탭 구성 ===
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 운영 현황", "🤖 모델 성능", "📈 추천 품질", "🎯 콘텐츠 분석", "🔍 상세 탐색"
])

# --- 함수 정의: metric 박스 ---
def metric_box(title, value, subtitle="", color="#3b82f6"):
    st.markdown(f"""
        <div class="metric-container">
            <h3 style="color: {color}; margin: 0;">{title}</h3>
            <h2 style="margin: 0.5rem 0;">{value}</h2>
            <p style="margin: 0; color: #6b7280;">{subtitle}</p>
        </div>
    """, unsafe_allow_html=True)

# === 탭1: 운영 현황 ===
with tab1:
    st.header("📊 시스템 운영 현황")
    
    col1, col2 = st.columns(2)
    
    total_users = df['user'].nunique()
    total_recs = len(df)
    avg_recs = total_recs / total_users
    
    with col1:
        metric_box("총 사용자", f"{total_users}명", color="#3b82f6")
    with col2:
        metric_box("총 추천", f"{total_recs}개", f"평균 {avg_recs:.1f}개/사용자", color="#10b981")
    
    st.markdown("---")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("임베딩 모델별 사용량")
        model_counts = df['model'].value_counts()
        fig_model = px.pie(
            values=model_counts.values,
            names=model_counts.index,
            title="모델별 추천 건수",
            color_discrete_sequence=pastel
        )
        st.plotly_chart(fig_model, use_container_width=True)
        
        st.markdown("**모델별 상세 통계:**")
        model_stats = df.groupby('model').agg({
            'llm_score': ['count', 'mean', 'std'],
            'user': 'nunique'
        }).round(3)
        model_stats.columns = ['추천수', '평균점수', '표준편차', '사용자수']
        st.dataframe(model_stats)
    
    with col2:
        st.subheader("추천 소스 분포")
        source_counts = df['source'].value_counts()
        fig_source = px.bar(
            x=source_counts.values,
            y=source_counts.index,
            orientation='h',
            title="소스별 추천 건수",
            labels={'x': '추천 건수', 'y': '소스'},
            color_discrete_sequence=pastel
        )
        st.plotly_chart(fig_source, use_container_width=True)
        
        st.markdown("**소스별 평균 품질:**")
        source_quality = df.groupby('source')['llm_score'].agg(['count', 'mean']).round(3)
        source_quality.columns = ['건수', '평균점수']
        source_quality = source_quality.sort_values('평균점수', ascending=False)
        st.dataframe(source_quality)

# === 탭2: 모델 성능 ===
with tab2:
    st.header("🤖 임베딩 모델 성능 비교")
    
    model_performance = filtered_df.groupby('model').agg({
        'llm_score': ['count', 'mean', 'median', 'std'],
        'user': 'nunique',
        'vector_score': 'mean'
    }).round(3)
    
    model_performance.columns = ['추천수', 'LLM평균', 'LLM중간값', 'LLM표준편차', '사용자수', 'Vector평균']
    model_performance = model_performance.sort_values('LLM평균', ascending=False)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("모델별 LLM 점수 비교")
        fig_model_score = px.bar(
            model_performance, x=model_performance.index, y='LLM평균',
            title="모델별 평균 LLM 점수",
            labels={'x': '모델', 'LLM평균': 'LLM 평균 점수'},
            color_discrete_sequence=pastel
        )
        fig_model_score.add_hline(y=df['llm_score'].mean(), line_dash="dash", annotation_text="전체 평균")
        st.plotly_chart(fig_model_score, use_container_width=True)
    
    with col2:
        st.subheader("모델별 점수 분포")
        fig_box = px.box(
            filtered_df, x='model', y='llm_score',
            title="모델별 LLM 점수 분포",
            color='model',
            color_discrete_sequence=pastel
        )
        st.plotly_chart(fig_box, use_container_width=True)
    
    st.subheader("모델별 상세 성능")
    st.dataframe(model_performance, use_container_width=True)
    
    best_model = model_performance['LLM평균'].idxmax()
    worst_model = model_performance['LLM평균'].idxmin()
    performance_gap = model_performance.loc[best_model, 'LLM평균'] - model_performance.loc[worst_model, 'LLM평균']
    
    if performance_gap > 0.3:
        st.markdown(f"""
        <div class="warning-box">
            <h4>⚠️ 모델 성능 격차 발견</h4>
            <p><strong>최고 성능:</strong> {best_model} ({model_performance.loc[best_model, 'LLM평균']:.2f}점)</p>
            <p><strong>최저 성능:</strong> {worst_model} ({model_performance.loc[worst_model, 'LLM평균']:.2f}점)</p>
            <p><strong>격차:</strong> {performance_gap:.2f}점 - 모델 교체를 고려해보세요.</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="insight-box">
            <h4>✅ 모델 성능 균등</h4>
            <p>모델간 성능 차이가 {performance_gap:.2f}점으로 적습니다. 현재 구성이 적절합니다.</p>
        </div>
        """, unsafe_allow_html=True)

# === 탭3: 추천 품질 분석 ===
with tab3:
    st.header("📈 추천 품질 분석")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("LLM 점수 분포")
        fig_hist = px.histogram(
            filtered_df, x='llm_score', nbins=20,
            title="LLM 점수 분포",
            labels={'llm_score': 'LLM 점수', 'count': '빈도'},
            color_discrete_sequence=pastel
        )
        fig_hist.add_vline(x=df['llm_score'].mean(), line_dash="dash", 
                          annotation_text=f"평균: {df['llm_score'].mean():.2f}")
        st.plotly_chart(fig_hist, use_container_width=True)
    
    with col2:
        st.subheader("순위별 품질")
        rank_quality = filtered_df.groupby('rank')['llm_score'].mean().reset_index()
        fig_rank = px.line(
            rank_quality, x='rank', y='llm_score',
            title="추천 순위별 평균 LLM 점수",
            labels={'rank': '추천 순위', 'llm_score': 'LLM 점수'},
            color_discrete_sequence=pastel
        )
        st.plotly_chart(fig_rank, use_container_width=True)


# === 탭4: 콘텐츠 분석 ===
with tab4:
    st.header("🎯 콘텐츠 분석")
    
    # 레벨별 분포
    if 'level' in filtered_df.columns and filtered_df['level'].notna().any():
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("콘텐츠 레벨 분포")
            level_counts = filtered_df['level'].value_counts()
            fig_level = px.bar(
                x=level_counts.index, y=level_counts.values,
                title="난이도별 추천 건수",
                labels={'x': '난이도', 'y': '건수'},
                color_discrete_sequence=pastel
            )
            st.plotly_chart(fig_level, use_container_width=True)
        
        with col2:
            st.subheader("레벨별 평균 품질")
            level_quality = filtered_df.groupby('level')['llm_score'].mean().sort_values(ascending=False)
            fig_level_quality = px.bar(
                x=level_quality.index, y=level_quality.values,
                title="난이도별 평균 LLM 점수",
                labels={'x': '난이도', 'y': 'LLM 점수'},
                color_discrete_sequence=pastel
            )
            st.plotly_chart(fig_level_quality, use_container_width=True)
    
    # 태그 분석 (상위 태그들)
    if 'tags' in filtered_df.columns:
        st.subheader("인기 태그 분석")
        all_tags = []
        for tags in filtered_df['tags'].dropna():
            if isinstance(tags, list):
                all_tags.extend(tags)
            elif isinstance(tags, str):
                all_tags.extend(tags.split(','))
        
        if all_tags:
            tag_counts = pd.Series(all_tags).value_counts().head(10)
            fig_tags = px.bar(
                x=tag_counts.values, y=tag_counts.index,
                orientation='h',
                title="상위 10개 태그",
                labels={'x': '빈도', 'y': '태그'},
                color_discrete_sequence=pastel
            )
            st.plotly_chart(fig_tags, use_container_width=True)
            
with tab5:
    st.header("🔍 상세 탐색")
    
    # 필터링 옵션
    col1, col2, col3 = st.columns(3)
    
    with col1:
        score_range = st.slider("LLM 점수 범위", 
                               float(df['llm_score'].min()), 
                               float(df['llm_score'].max()), 
                               (float(df['llm_score'].min()), float(df['llm_score'].max())),
                               step=0.1)
    
    with col2:
        rank_filter = st.multiselect("추천 순위", 
                                   options=sorted(df['rank'].unique()),
                                   default=sorted(df['rank'].unique()))
    
    with col3:
        search_term = st.text_input("제목 검색:", placeholder="검색어 입력...")
    
    # 필터 적용
    display_df = filtered_df[
        (filtered_df['llm_score'] >= score_range[0]) &
        (filtered_df['llm_score'] <= score_range[1]) &
        (filtered_df['rank'].isin(rank_filter))
    ]
    
    if search_term:
        display_df = display_df[display_df['title'].str.contains(search_term, case=False, na=False)]
    
    # 정렬 옵션
    sort_options = {
        "LLM 점수 (높음)": ('llm_score', False),
        "LLM 점수 (낮음)": ('llm_score', True),
        "Vector 점수 (높음)": ('vector_score', False),
        "사용자명": ('user', True),
        "추천 순위": ('rank', True)
    }
    
    sort_choice = st.selectbox("정렬 기준:", list(sort_options.keys()))
    sort_col, sort_asc = sort_options[sort_choice]
    display_df = display_df.sort_values(sort_col, ascending=sort_asc)
    
    # 결과 표시
    st.subheader(f"검색 결과: {len(display_df)}건")
    
    # 선택한 행들의 추가 정보 표시
    selected_columns = [
        'user', 'title', 'model', 'source', 'rank', 
        'llm_score', 'vector_score', 'level'
    ]
    
    # 존재하는 컬럼만 선택
    available_columns = [col for col in selected_columns if col in display_df.columns]
    
    st.dataframe(
        display_df[available_columns],
        use_container_width=True,
        height=400
    )
    
    # 상세 정보 버튼
    if st.button("상세 분석 보기"):
        if len(display_df) > 0:
            st.subheader("📊 선택된 데이터 요약")
            st.write(f"**평균 LLM 점수:** {display_df['llm_score'].mean():.2f}")
            st.write(f"**평균 Vector 점수:** {display_df['vector_score'].mean():.2f}")
            st.write(f"**가장 많이 사용된 모델:** {display_df['model'].mode().iloc[0]}")
            st.write(f"**가장 많이 사용된 소스:** {display_df['source'].mode().iloc[0]}")

# === 푸터 ===
st.markdown("---")
st.markdown("### 💡 대시보드 사용 팁")
st.markdown("""
- **운영 현황**: 전체적인 시스템 상태 파악
- **모델 성능**: 어떤 임베딩 모델이 좋은 추천을 만드는지 확인
- **추천 품질**: 실제 추천 품질 분포와 개선점 파악
- **콘텐츠 분석**: 어떤 난이도/태그의 콘텐츠가 인기있는지 확인
- **상세 탐색**: 특정 조건의 추천 결과 깊이 분석
""")