import streamlit as st
import pandas as pd
import json
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
from pathlib import Path

def load_evaluation_data():
    """평가 데이터 로드"""
    base_path = Path(__file__).parent / "final_result"
    
    # CSV 파일들 로드
    llm_summary = pd.read_csv(base_path / "llm_evaluation_summary_20250912_150744.csv")
    human_summary = pd.read_csv(base_path / "human_feedback_summary_20250913_195913.csv")
    
    # JSON 파일들 로드
    with open(base_path / "llm_evaluation_detailed_20250912_150744.json", 'r', encoding='utf-8') as f:
        llm_detailed = json.load(f)
    
    with open(base_path / "human_feedback_detailed_20250913_195913.json", 'r', encoding='utf-8') as f:
        human_detailed = json.load(f)
    
    return llm_summary, human_summary, llm_detailed, human_detailed

def create_overall_score_comparison(llm_summary, human_summary):
    """전체 점수 비교 차트"""
    merged_data = pd.merge(
        llm_summary[['user_name', 'average_llm_score']],
        human_summary[['user_name', 'human_overall_score']],
        on='user_name',
        how='inner'
    )
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=merged_data['user_name'],
        y=merged_data['average_llm_score'],
        mode='markers+lines',
        name='LLM 점수',
        line=dict(color='#FF6B6B', width=2),
        marker=dict(size=8, color='#FF6B6B')
    ))
    
    fig.add_trace(go.Scatter(
        x=merged_data['user_name'],
        y=merged_data['human_overall_score'],
        mode='markers+lines',
        name='Human 점수',
        line=dict(color='#4ECDC4', width=2),
        marker=dict(size=8, color='#4ECDC4')
    ))
    
    fig.update_layout(
        title="LLM vs Human 전체 점수 비교",
        xaxis_title="사용자",
        yaxis_title="점수",
        xaxis=dict(tickangle=45),
        height=500,
        hovermode='x unified',
        showlegend=True
    )
    
    return fig

def create_criteria_comparison(llm_summary, human_summary):
    """평가항목별 점수 비교"""
    criteria_korean = ['적합성', '관련성', '다양성', '일관성']
    
    llm_criteria = ['gpt-4o-mini_suitability', 'gpt-4o-mini_relevance', 'gpt-4o-mini_diversity', 'gpt-4o-mini_coherence']
    human_criteria = ['human_suitability_score', 'human_relevance_score', 'human_diversity_score', 'human_coherence_score']
    
    llm_avg = [llm_summary[col].mean() for col in llm_criteria]
    human_avg = [human_summary[col].mean() for col in human_criteria]
    
    fig = go.Figure()
    
    # LLM 막대 그래프
    fig.add_trace(go.Bar(
        x=criteria_korean,
        y=llm_avg,
        name='LLM 평가',
        marker_color='#FF6B6B',
        opacity=0.7,
        width=0.4,
        offset=-0.2
    ))
    
    # Human 막대 그래프
    fig.add_trace(go.Bar(
        x=criteria_korean,
        y=human_avg,
        name='Human 평가',
        marker_color='#4ECDC4',
        opacity=0.7,
        width=0.4,
        offset=0.2
    ))
    
    
    fig.update_layout(
        title="평가항목별 평균 점수 비교",
        xaxis_title="평가 항목",
        yaxis_title="평균 점수",
        barmode='group',
        height=450,
        xaxis=dict(
            tickmode='array',
            tickvals=list(range(len(criteria_korean))),
            ticktext=criteria_korean
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )
    
    return fig

def get_user_levels(detailed_data):
    """사용자별 레벨 정보 추출"""
    user_levels = {}
    for user_data in detailed_data:
        user_name = user_data['user_name']
        if user_data['real_recommendations']:
            level = user_data['real_recommendations'][0]['level']
            user_levels[user_name] = level
    return user_levels

def create_overall_score_by_level(llm_summary, human_summary, llm_detailed, human_detailed):
    """총합 점수 레벨별 비교"""
    user_levels = get_user_levels(llm_detailed)
    
    llm_summary_copy = llm_summary.copy()
    human_summary_copy = human_summary.copy()
    llm_summary_copy['level'] = llm_summary_copy['user_name'].map(user_levels)
    human_summary_copy['level'] = human_summary_copy['user_name'].map(user_levels)
    
    fig = make_subplots(
        rows=1, cols=3,
        subplot_titles=['Beginner', 'Intermediate', 'Advanced']
    )
    
    levels = ['Beginner', 'Intermediate', 'Advanced']
    criteria = ['총합점수', '적합성', '관련성', '다양성', '일관성']
    
    colors = {
        'LLM': '#FF6B6B',
        'Human': '#4ECDC4'
    }
    
    for i, level in enumerate(levels):
        col = i + 1
        
        llm_level_data = llm_summary_copy[llm_summary_copy['level'] == level]
        human_level_data = human_summary_copy[human_summary_copy['level'] == level]
        
        if llm_level_data.empty or human_level_data.empty:
            continue
        
        llm_scores = [
            llm_level_data['average_llm_score'].mean(),
            llm_level_data['gpt-4o-mini_suitability'].mean(),
            llm_level_data['gpt-4o-mini_relevance'].mean(),
            llm_level_data['gpt-4o-mini_diversity'].mean(),
            llm_level_data['gpt-4o-mini_coherence'].mean()
        ]
        
        human_scores = [
            human_level_data['human_overall_score'].mean(),
            human_level_data['human_suitability_score'].mean(),
            human_level_data['human_relevance_score'].mean(),
            human_level_data['human_diversity_score'].mean(),
            human_level_data['human_coherence_score'].mean()
        ]
        
        fig.add_trace(
            go.Bar(
                x=criteria,
                y=llm_scores,
                name='LLM' if i == 0 else None,
                marker_color=colors['LLM'],
                opacity=0.8,
                showlegend=(i == 0),
                legendgroup='LLM'
            ),
            row=1, col=col
        )
        
        fig.add_trace(
            go.Bar(
                x=criteria,
                y=human_scores,
                name='Human' if i == 0 else None,
                marker_color=colors['Human'],
                opacity=0.8,
                showlegend=(i == 0),
                legendgroup='Human'
            ),
            row=1, col=col
        )
        
        fig.update_xaxes(tickangle=45, row=1, col=col)
    
    fig.update_layout(
        title="레벨별 전체 평가항목 점수 비교",
        height=500,
        barmode='group',
        showlegend=True
    )
    
    return fig

def create_level_analysis(llm_summary, human_summary, llm_detailed, human_detailed):
    """레벨별 평가항목별 상세 분석"""
    user_levels = get_user_levels(llm_detailed)
    
    llm_summary_copy = llm_summary.copy()
    human_summary_copy = human_summary.copy()
    llm_summary_copy['level'] = llm_summary_copy['user_name'].map(user_levels)
    human_summary_copy['level'] = human_summary_copy['user_name'].map(user_levels)
    
    criteria = ['suitability', 'relevance', 'diversity', 'coherence']
    criteria_korean = ['적합성', '관련성', '다양성', '일관성']
    
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=criteria_korean
    )
    
    levels = ['Beginner', 'Intermediate', 'Advanced']
    colors = {
        'LLM': '#FF6B6B',
        'Human': '#4ECDC4'
    }
    
    for i, criterion in enumerate(criteria):
        row = i // 2 + 1
        col = i % 2 + 1
        
        llm_means = []
        human_means = []
        
        for level in levels:
            llm_level_data = llm_summary_copy[llm_summary_copy['level'] == level]
            human_level_data = human_summary_copy[human_summary_copy['level'] == level]
            
            llm_col = f'gpt-4o-mini_{criterion}'
            human_col = f'human_{criterion}_score'
            
            if not llm_level_data.empty:
                llm_means.append(llm_level_data[llm_col].mean())
            else:
                llm_means.append(0)
                
            if not human_level_data.empty:
                human_means.append(human_level_data[human_col].mean())
            else:
                human_means.append(0)
        
        fig.add_trace(
            go.Bar(
                x=levels,
                y=llm_means,
                name='LLM' if i == 0 else None,
                marker_color=colors['LLM'],
                opacity=0.8,
                showlegend=(i == 0),
                legendgroup='LLM'
            ),
            row=row, col=col
        )
        
        fig.add_trace(
            go.Bar(
                x=levels,
                y=human_means,
                name='Human' if i == 0 else None,
                marker_color=colors['Human'],
                opacity=0.8,
                showlegend=(i == 0),
                legendgroup='Human'
            ),
            row=row, col=col
        )
    
    fig.update_layout(
        title="평가항목별 레벨간 점수 비교",
        height=600,
        barmode='group',
        showlegend=True
    )
    
    return fig

def create_score_correlation(llm_summary, human_summary):
    """LLM vs Human 점수 상관관계"""
    merged_data = pd.merge(
        llm_summary[['user_name', 'average_llm_score']],
        human_summary[['user_name', 'human_overall_score']],
        on='user_name',
        how='inner'
    )
    
    fig = px.scatter(
        merged_data,
        x='average_llm_score',
        y='human_overall_score',
        hover_data=['user_name'],
        title="LLM vs Human 점수 상관관계",
        labels={
            'average_llm_score': 'LLM 점수',
            'human_overall_score': 'Human 점수'
        }
    )
    
    correlation = merged_data['average_llm_score'].corr(merged_data['human_overall_score'])
    
    z = np.polyfit(merged_data['average_llm_score'], merged_data['human_overall_score'], 1)
    p = np.poly1d(z)
    fig.add_trace(
        go.Scatter(
            x=merged_data['average_llm_score'],
            y=p(merged_data['average_llm_score']),
            mode='lines',
            name=f'회귀선 (r={correlation:.3f})',
            line=dict(color='red', dash='dash')
        )
    )
    
    fig.update_layout(height=500)
    return fig

def create_detailed_level_analysis(llm_summary, human_summary, llm_detailed):
    """레벨별 상세 분석"""
    user_levels = get_user_levels(llm_detailed)
    
    merged = pd.merge(
        llm_summary[['user_name', 'average_llm_score', 'gpt-4o-mini_suitability', 
                     'gpt-4o-mini_relevance', 'gpt-4o-mini_diversity', 'gpt-4o-mini_coherence']],
        human_summary[['user_name', 'human_overall_score', 'human_suitability_score',
                      'human_relevance_score', 'human_diversity_score', 'human_coherence_score']],
        on='user_name'
    )
    merged['level'] = merged['user_name'].map(user_levels)
    
    level_stats = merged.groupby('level').agg({
        'average_llm_score': 'mean',
        'human_overall_score': 'mean',
        'gpt-4o-mini_suitability': 'mean',
        'human_suitability_score': 'mean',
        'gpt-4o-mini_relevance': 'mean',
        'human_relevance_score': 'mean',
        'gpt-4o-mini_diversity': 'mean',
        'human_diversity_score': 'mean',
        'gpt-4o-mini_coherence': 'mean',
        'human_coherence_score': 'mean'
    }).round(2)
    
    return level_stats, merged

# 추천 시스템 분석 함수들
def analyze_recommendation_data(detailed_data):
    """추천 데이터 분석"""
    all_recommendations = []
    
    for user_data in detailed_data:
        user_name = user_data['user_name']
        level = user_data['real_recommendations'][0]['level'] if user_data['real_recommendations'] else 'Unknown'
        
        for rec in user_data['real_recommendations']:
            rec_info = {
                'user_name': user_name,
                'user_level': level,
                'title': rec.get('title', ''),
                'level': rec.get('level', ''),
                'category': rec.get('category', 'None'),
                'topic_id': rec.get('topic_id', 0),
                'style': rec.get('style', ''),
                'media_type': rec.get('media_type', ''),
                'recommendation_source': rec.get('recommendation_source', ''),
                'recommendation_rank': rec.get('recommendation_rank', 0),
                'vector_model': rec.get('vector_model', ''),
                'vector_score': rec.get('vector_score', 0),
                'llm_final_score': rec.get('llm_final_score', 0),
                'llm_reranked': rec.get('llm_reranked', False),
                'method': rec.get('recommendation_details', {}).get('method', ''),
                'model': rec.get('recommendation_details', {}).get('model', ''),
                'level_filtered': rec.get('recommendation_details', {}).get('level_filtered', False)
            }
            all_recommendations.append(rec_info)
    
    return pd.DataFrame(all_recommendations)

def create_recommendation_source_chart(rec_df):
    """추천 소스 분석 차트"""
    source_counts = rec_df['recommendation_source'].value_counts()
    
    fig = px.pie(
        values=source_counts.values,
        names=source_counts.index,
        title="추천 소스 분포",
        color_discrete_sequence=['#FFB3BA', '#B3D9FF', '#D4F4DD', '#F7E6FF', '#FFE6CC']
    )
    
    return fig

def create_vector_model_chart(rec_df):
    """벡터 모델 분석 차트"""
    model_counts = rec_df['vector_model'].value_counts()
    
    fig = px.bar(
        x=model_counts.index,
        y=model_counts.values,
        title="벡터 모델별 사용 빈도",
        labels={'x': '벡터 모델', 'y': '사용 횟수'},
        color=model_counts.index,
        color_discrete_sequence=['#FFB3BA', '#B3D9FF', '#D4F4DD', '#F7E6FF', '#FFE6CC']
    )
    
    return fig

def create_level_content_analysis(rec_df):
    """레벨별 콘텐츠 분석"""
    level_style = pd.crosstab(rec_df['user_level'], rec_df['style'])
    
    fig = px.imshow(
        level_style.values,
        x=level_style.columns,
        y=level_style.index,
        title="레벨별 콘텐츠 스타일 분포",
        labels={'x': '콘텐츠 스타일', 'y': '사용자 레벨', 'color': '빈도'},
        color_continuous_scale='Blues'
    )
    
    return fig

def create_topic_analysis(rec_df):
    """토픽별 분석"""
    topic_counts = rec_df['topic_id'].value_counts().head(10)
    
    fig = px.bar(
        x=topic_counts.index,
        y=topic_counts.values,
        title="상위 10개 토픽 ID 분포",
        labels={'x': '토픽 ID', 'y': '추천 횟수'}
    )
    
    return fig

def create_vector_score_distribution(rec_df):
    """벡터 스코어 분포"""
    fig = px.histogram(
        rec_df,
        x='vector_score',
        nbins=30,
        title="벡터 유사도 점수 분포",
        labels={'x': '벡터 점수', 'y': '빈도'},
        color_discrete_sequence=['#FFB3BA']
    )
    
    return fig

def create_recommendation_rank_analysis(rec_df):
    """추천 순위 분석"""
    rank_counts = rec_df['recommendation_rank'].value_counts().sort_index()
    
    fig = px.bar(
        x=rank_counts.index,
        y=rank_counts.values,
        title="추천 순위별 분포",
        labels={'x': '추천 순위', 'y': '횟수'},
        color_discrete_sequence=['#D4F4DD']
    )
    
    return fig

def main():
    st.set_page_config(
        page_title="평가 결과 대시보드",
        page_icon="📊",
        layout="wide"
    )
    
    # 사이드바 메뉴
    st.sidebar.title("📊 대시보드 메뉴")
    menu_option = st.sidebar.selectbox(
        "분석 메뉴 선택",
        ["LLM vs Human 평가 결과", "추천 시스템 분석"]
    )
    
    # 데이터 로드
    try:
        llm_summary, human_summary, llm_detailed, human_detailed = load_evaluation_data()
        st.success("평가 데이터가 성공적으로 로드되었습니다.")
    except Exception as e:
        st.error(f"데이터 로드 중 오류가 발생했습니다: {e}")
        return
    
    if menu_option == "LLM vs Human 평가 결과":
        show_evaluation_dashboard(llm_summary, human_summary, llm_detailed, human_detailed)
    else:
        show_recommendation_analysis(human_detailed)

def show_evaluation_dashboard(llm_summary, human_summary, llm_detailed, human_detailed):
    """기존 평가 결과 대시보드"""
    st.title("📊 LLM vs Human 평가 결과")
    st.markdown("---")
    
    # 기본 통계 정보
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("총 사용자 수", len(llm_summary))
    
    with col2:
        llm_avg = llm_summary['average_llm_score'].mean()
        st.metric("LLM 평균 점수", f"{llm_avg:.2f}")
    
    with col3:
        human_avg = human_summary['human_overall_score'].mean()
        st.metric("Human 평균 점수", f"{human_avg:.2f}")
    
    with col4:
        score_diff = human_avg - llm_avg
        st.metric("점수 차이 (H-L)", f"{score_diff:.2f}")
    
    st.markdown("---")
    
    # 탭 구성
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📈 전체 점수 비교", 
        "📊 평가항목별 비교", 
        "🎯 레벨별 분석", 
        "🔗 상관관계 분석",
        "📋 상세 데이터"
    ])
    
    with tab1:
        st.subheader("전체 점수 비교")
        st.plotly_chart(create_overall_score_comparison(llm_summary, human_summary), use_container_width=True)
        
        # 점수 차이가 큰 사용자들
        merged = pd.merge(
            llm_summary[['user_name', 'average_llm_score']],
            human_summary[['user_name', 'human_overall_score']],
            on='user_name'
        )
        merged['score_diff'] = merged['human_overall_score'] - merged['average_llm_score']
        
        st.subheader("점수 차이 분석")
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**Human 점수가 높은 상위 5명**")
            top_human = merged.nlargest(5, 'score_diff')[['user_name', 'score_diff']].round(2)
            st.dataframe(top_human)
        
        with col2:
            st.write("**LLM 점수가 높은 상위 5명**")
            top_llm = merged.nsmallest(5, 'score_diff')[['user_name', 'score_diff']].round(2)
            st.dataframe(top_llm)
    
    with tab2:
        st.subheader("평가항목별 평균 점수 비교")
        st.plotly_chart(create_criteria_comparison(llm_summary, human_summary), use_container_width=True)
        
        # 항목별 상세 분석
        criteria_analysis = pd.DataFrame({
            '평가항목': ['적합성', '관련성', '다양성', '일관성'],
            'LLM 평균': [
                llm_summary['gpt-4o-mini_suitability'].mean(),
                llm_summary['gpt-4o-mini_relevance'].mean(),
                llm_summary['gpt-4o-mini_diversity'].mean(),
                llm_summary['gpt-4o-mini_coherence'].mean()
            ],
            'Human 평균': [
                human_summary['human_suitability_score'].mean(),
                human_summary['human_relevance_score'].mean(),
                human_summary['human_diversity_score'].mean(),
                human_summary['human_coherence_score'].mean()
            ]
        })
        criteria_analysis['차이 (H-L)'] = criteria_analysis['Human 평균'] - criteria_analysis['LLM 평균']
        
        st.subheader("평가항목별 상세 분석")
        st.dataframe(criteria_analysis.round(3))
    
    with tab3:
        st.subheader("레벨별 전체 평가항목 점수 비교")
        st.plotly_chart(create_overall_score_by_level(llm_summary, human_summary, llm_detailed, human_detailed), use_container_width=True)
        
        st.subheader("평가항목별 상세 레벨 비교")
        st.plotly_chart(create_level_analysis(llm_summary, human_summary, llm_detailed, human_detailed), use_container_width=True)
        
        # 레벨별 요약 통계
        level_stats, merged_with_level = create_detailed_level_analysis(llm_summary, human_summary, llm_detailed)
        
        st.subheader("레벨별 평균 점수")
        st.dataframe(level_stats)
        
        # 레벨별 사용자 수
        level_counts = merged_with_level['level'].value_counts()
        st.subheader("레벨별 사용자 분포")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Beginner", level_counts.get('Beginner', 0))
        with col2:
            st.metric("Intermediate", level_counts.get('Intermediate', 0))
        with col3:
            st.metric("Advanced", level_counts.get('Advanced', 0))
    
    with tab4:
        st.subheader("LLM vs Human 점수 상관관계")
        st.plotly_chart(create_score_correlation(llm_summary, human_summary), use_container_width=True)
        
        # 상관관계 분석 표
        merged = pd.merge(
            llm_summary[['user_name', 'average_llm_score', 'gpt-4o-mini_suitability', 'gpt-4o-mini_relevance', 'gpt-4o-mini_diversity', 'gpt-4o-mini_coherence']],
            human_summary[['user_name', 'human_overall_score', 'human_suitability_score', 'human_relevance_score', 'human_diversity_score', 'human_coherence_score']],
            on='user_name'
        )
        
        correlations = pd.DataFrame({
            '항목': ['전체 점수', '적합성', '관련성', '다양성', '일관성'],
            '상관계수': [
                merged['average_llm_score'].corr(merged['human_overall_score']),
                merged['gpt-4o-mini_suitability'].corr(merged['human_suitability_score']),
                merged['gpt-4o-mini_relevance'].corr(merged['human_relevance_score']),
                merged['gpt-4o-mini_diversity'].corr(merged['human_diversity_score']),
                merged['gpt-4o-mini_coherence'].corr(merged['human_coherence_score'])
            ]
        })
        
        st.subheader("항목별 상관관계")
        st.dataframe(correlations.round(3))
    
    with tab5:
        st.subheader("상세 데이터 보기")
        
        # 데이터 선택
        data_type = st.selectbox("데이터 유형 선택", ["LLM 평가 요약", "Human 평가 요약", "전체 비교"])
        
        if data_type == "LLM 평가 요약":
            st.dataframe(llm_summary)
        elif data_type == "Human 평가 요약":
            st.dataframe(human_summary)
        else:
            merged_all = pd.merge(llm_summary, human_summary, on='user_name', suffixes=('_llm', '_human'))
            st.dataframe(merged_all)
        
        # 데이터 다운로드
        if st.button("데이터 다운로드"):
            merged_all = pd.merge(llm_summary, human_summary, on='user_name', suffixes=('_llm', '_human'))
            csv = merged_all.to_csv(index=False)
            st.download_button(
                label="CSV 파일 다운로드",
                data=csv,
                file_name="evaluation_comparison.csv",
                mime="text/csv"
            )

def show_recommendation_analysis(human_detailed):
    """추천 시스템 분석 대시보드"""
    st.title("🔍 추천 시스템 분석")
    st.markdown("---")
    
    # 추천 데이터 분석
    rec_df = analyze_recommendation_data(human_detailed)
    
    # 기본 통계
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("전체 추천 수", len(rec_df))
    
    with col2:
        avg_vector_score = rec_df['vector_score'].mean()
        st.metric("평균 벡터 점수", f"{avg_vector_score:.3f}")
    
    with col3:
        unique_models = rec_df['vector_model'].nunique()
        st.metric("사용된 벡터 모델 수", unique_models)
    
    with col4:
        reranked_rate = (rec_df['llm_reranked'].sum() / len(rec_df)) * 100
        st.metric("LLM 재순위율", f"{reranked_rate:.1f}%")
    
    st.markdown("---")
    
    # 탭 구성
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 추천 소스 분석",
        "🤖 벡터 모델 분석", 
        "📈 점수 분포 분석",
        "📋 상세 데이터"
    ])
    
    with tab1:
        st.subheader("추천 소스 및 순위 분석")
        
        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(create_recommendation_source_chart(rec_df), use_container_width=True)
        with col2:
            st.plotly_chart(create_recommendation_rank_analysis(rec_df), use_container_width=True)
        
        # 추천 소스별 통계
        st.subheader("추천 소스별 상세 통계")
        source_stats = rec_df.groupby('recommendation_source').agg({
            'vector_score': ['mean', 'std', 'count'],
            'llm_final_score': ['mean', 'std'],
            'llm_reranked': 'sum'
        }).round(3)
        st.dataframe(source_stats)
    
    with tab2:
        st.subheader("벡터 모델 성능 분석")
        
        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(create_vector_model_chart(rec_df), use_container_width=True)
        with col2:
            # 모델별 평균 점수
            model_scores = rec_df.groupby('vector_model')['vector_score'].mean().sort_values(ascending=False)
            fig = px.bar(
                x=model_scores.values,
                y=model_scores.index,
                orientation='h',
                title="벡터 모델별 평균 점수",
                labels={'x': '평균 벡터 점수', 'y': '모델명'},
                color=model_scores.index,
                color_discrete_sequence=['#FFB3BA', '#B3D9FF', '#D4F4DD', '#F7E6FF', '#FFE6CC']
            )
            st.plotly_chart(fig, use_container_width=True)
        
        # 모델별 상세 통계
        st.subheader("벡터 모델별 상세 통계")
        model_stats = rec_df.groupby('vector_model').agg({
            'vector_score': ['mean', 'std', 'min', 'max', 'count'],
            'llm_final_score': ['mean', 'std']
        }).round(3)
        st.dataframe(model_stats)
    
    with tab3:
        st.subheader("벡터 점수 분포")
        st.plotly_chart(create_vector_score_distribution(rec_df), use_container_width=True)
    
    with tab4:
        st.subheader("추천 상세 데이터")
        
        # 필터링 옵션
        col1, col2, col3 = st.columns(3)
        with col1:
            selected_level = st.selectbox("레벨 필터", ['전체'] + rec_df['user_level'].unique().tolist())
        with col2:
            selected_model = st.selectbox("벡터 모델 필터", ['전체'] + rec_df['vector_model'].unique().tolist())
        with col3:
            selected_source = st.selectbox("추천 소스 필터", ['전체'] + rec_df['recommendation_source'].unique().tolist())
        
        # 데이터 필터링
        filtered_df = rec_df.copy()
        if selected_level != '전체':
            filtered_df = filtered_df[filtered_df['user_level'] == selected_level]
        if selected_model != '전체':
            filtered_df = filtered_df[filtered_df['vector_model'] == selected_model]
        if selected_source != '전체':
            filtered_df = filtered_df[filtered_df['recommendation_source'] == selected_source]
        
        st.dataframe(filtered_df)
        
        # 데이터 다운로드
        if st.button("추천 데이터 다운로드"):
            csv = filtered_df.to_csv(index=False)
            st.download_button(
                label="CSV 파일 다운로드",
                data=csv,
                file_name="recommendation_analysis.csv",
                mime="text/csv"
            )

if __name__ == "__main__":
    main()