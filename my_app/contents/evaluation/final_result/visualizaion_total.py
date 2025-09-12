import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np

# 페이지 설정
st.set_page_config(
    page_title="FIREgenerator 성능평가 대시보드",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 커스텀 CSS
st.markdown("""
<style>
    .main-header {
        font-size: 3rem;
        font-weight: bold;
        color: #1f2937;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #6b7280;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: white;
        padding: 1.5rem;
        border-radius: 0.75rem;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        border: 1px solid #e5e7eb;
        text-align: center;
        margin-bottom: 1rem;
    }
    .insight-box {
        padding: 1.5rem;
        border-radius: 0.75rem;
        margin: 1rem 0;
    }
    .improvement-box {
        background: #fef2f2;
        border-left: 4px solid #ef4444;
    }
    .strength-box {
        background: #f0fdf4;
        border-left: 4px solid #22c55e;
    }
    .strategy-box {
        padding: 1.5rem;
        border-radius: 0.75rem;
        margin: 1rem 0;
    }
    .strategy-short {
        background: #eff6ff;
    }
    .strategy-medium {
        background: #fefce8;
    }
    .strategy-long {
        background: #f0fdf4;
    }
</style>
""", unsafe_allow_html=True)

# 데이터 준비
@st.cache_data
def load_data():
    # 전체 점수 비교 데이터
    overall_scores = pd.DataFrame({
        'metric': ['관련성 (Relevance)', '적합성 (Suitability)', '다양성 (Diversity)', '실용성 (Practicality)'],
        'gpt': [4.2, 4.6, 3.5, 4.3],
        'human': [4.2, 4.1, 3.4, 3.9],
        'category': ['content', 'content', 'content', 'content']
    })
    
    # 설명 관련 점수 (GPT만)
    explanation_scores = pd.DataFrame({
        'metric': ['정확성 (Accuracy)', '완결성 (Completeness)', '일관성 (Coherence)', '안전성 (Safety)', '어조/스타일 (Tone)'],
        'gpt': [5.0, 4.5, 4.7, 5.0, 4.6]
    })
    
    # 사용자 레벨별 분포
    user_distribution = pd.DataFrame({
        'level': ['Beginner', 'Intermediate', 'Advanced'],
        'knowledge': [9, 11, 10],
        'investment': [10, 10, 10]
    })
    
    # 카테고리별 평균 점수
    category_averages = pd.DataFrame({
        'category': ['콘텐츠 추천', '맞춤 설명'],
        'score': [4.15, 4.76]
    })
    
    # 개선 우선순위 데이터
    improvement_priority = pd.DataFrame({
        'area': ['다양성', '실용성', '관련성', '적합성'],
        'current_score': [3.5, 4.1, 4.2, 4.35],
        'target_score': [4.5, 4.8, 4.7, 4.8],
        'impact': ['High', 'High', 'Medium', 'Medium'],
        'effort': ['Medium', 'High', 'Low', 'Medium']
    })
    
    return overall_scores, explanation_scores, user_distribution, category_averages, improvement_priority

# 데이터 로드
overall_scores, explanation_scores, user_distribution, category_averages, improvement_priority = load_data()

# 헤더
st.markdown('<div class="main-header">FIREgenerator 성능평가 대시보드</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">LLM as a Judge vs Human Feedback 비교 분석</div>', unsafe_allow_html=True)

# 탭 생성
tab1, tab2, tab3, tab4 = st.tabs(["📊 전체 개요", "🔄 GPT vs Human", "💡 인사이트 & 개선", "🎯 전략 방향"])

with tab1:
    st.header("전체 개요")
    
    # 주요 지표 카드
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown("""
        <div class="metric-card">
            <h3 style="color: #3b82f6; margin-bottom: 0.5rem;">전체 평균 (GPT)</h3>
            <div style="font-size: 2rem; font-weight: bold; color: #1f2937;">4.5/5.0</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div class="metric-card">
            <h3 style="color: #22c55e; margin-bottom: 0.5rem;">전체 평균 (Human)</h3>
            <div style="font-size: 2rem; font-weight: bold; color: #1f2937;">4.2/5.0</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown("""
        <div class="metric-card">
            <h3 style="color: #a855f7; margin-bottom: 0.5rem;">평가 대상 사용자</h3>
            <div style="font-size: 2rem; font-weight: bold; color: #1f2937;">30명</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        st.markdown("""
        <div class="metric-card">
            <h3 style="color: #f97316; margin-bottom: 0.5rem;">평가 지표</h3>
            <div style="font-size: 2rem; font-weight: bold; color: #1f2937;">9개 항목</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # 차트 섹션
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("사용자 레벨 분포")
        fig_user = px.bar(
            user_distribution, 
            x='level', 
            y=['knowledge', 'investment'],
            title="",
            labels={'value': '사용자 수', 'variable': '구분', 'level': '레벨'},
            color_discrete_map={'knowledge': '#8884d8', 'investment': '#82ca9d'}
        )
        fig_user.update_layout(
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font=dict(size=12),
            height=400
        )
        st.plotly_chart(fig_user, use_container_width=True)
    
    with col2:
        st.subheader("카테고리별 평균 점수")
        fig_category = px.pie(
            category_averages, 
            values='score', 
            names='category',
            title="",
            color_discrete_map={'콘텐츠 추천': '#8884d8', '맞춤 설명': '#82ca9d'}
        )
        fig_category.update_layout(
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font=dict(size=12),
            height=400,
            showlegend=True
        )
        fig_category.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig_category, use_container_width=True)

with tab2:
    st.header("GPT vs Human 평가 비교")
    
    # GPT vs Human 비교 차트
    st.subheader("GPT vs Human 평가 비교")
    fig_comparison = px.bar(
        overall_scores, 
        x='metric', 
        y=['gpt', 'human'],
        title="",
        labels={'value': '점수', 'variable': '평가자', 'metric': '평가 지표'},
        color_discrete_map={'gpt': '#8884d8', 'human': '#82ca9d'},
        barmode='group'
    )
    fig_comparison.update_layout(
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        font=dict(size=12),
        height=500,
        xaxis={'tickangle': 45},
        yaxis={'range': [0, 5]}
    )
    st.plotly_chart(fig_comparison, use_container_width=True)
    
    # 레이더 차트
    st.subheader("평가 지표 레이더 차트")
    categories = overall_scores['metric'].tolist()
    categories += [categories[0]]  # 닫힌 도형을 위해 첫 번째 항목 추가
    
    gpt_values = overall_scores['gpt'].tolist()
    gpt_values += [gpt_values[0]]
    
    human_values = overall_scores['human'].tolist()
    human_values += [human_values[0]]
    
    fig_radar = go.Figure()
    
    fig_radar.add_trace(go.Scatterpolar(
        r=gpt_values,
        theta=categories,
        fill='toself',
        name='GPT 평가',
        line_color='#8884d8',
        fillcolor='rgba(136, 132, 216, 0.3)'
    ))
    
    fig_radar.add_trace(go.Scatterpolar(
        r=human_values,
        theta=categories,
        fill='toself',
        name='Human 평가',
        line_color='#82ca9d',
        fillcolor='rgba(130, 202, 157, 0.3)'
    ))
    
    fig_radar.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 5]
            )),
        showlegend=True,
        height=500,
        font=dict(size=12)
    )
    
    st.plotly_chart(fig_radar, use_container_width=True)
    
    # 평가 격차 분석
    st.subheader("평가 격차 분석")
    gaps = overall_scores.copy()
    gaps['gap'] = gaps['human'] - gaps['gpt']
    
    for _, row in gaps.iterrows():
        gap = row['gap']
        gap_color = "#ef4444" if gap < 0 else "#22c55e" if gap > 0 else "#6b7280"
        gap_text = f"{gap:+.1f}" if gap != 0 else "0.0"
        
        col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
        with col1:
            st.write(f"**{row['metric']}**")
        with col2:
            st.write(f"GPT: {row['gpt']}")
        with col3:
            st.write(f"Human: {row['human']}")
        with col4:
            st.markdown(f"<span style='color: {gap_color}; font-weight: bold;'>{gap_text}</span>", unsafe_allow_html=True)

with tab3:
    st.header("인사이트 & 개선")
    
    # 개선 우선순위 매트릭스
    st.subheader("개선 우선순위 매트릭스")
    
    # Impact에 따른 색상 매핑
    color_map = {'High': '#ff4444', 'Medium': '#ffaa00', 'Low': '#00aa00'}
    colors = [color_map[impact] for impact in improvement_priority['impact']]
    
    fig_scatter = px.scatter(
        improvement_priority, 
        x='current_score', 
        y='target_score',
        text='area',
        title="",
        labels={'current_score': '현재 점수', 'target_score': '목표 점수'},
        color='impact',
        color_discrete_map=color_map,
        size_max=15
    )
    
    fig_scatter.update_traces(textposition="middle center", textfont_size=12)
    fig_scatter.update_layout(
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        font=dict(size=12),
        height=500,
        xaxis={'range': [3, 5]},
        yaxis={'range': [4, 5]}
    )
    
    st.plotly_chart(fig_scatter, use_container_width=True)
    
    # 주요 인사이트
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        <div class="insight-box improvement-box">
            <h4 style="color: #991b1b; font-size: 1.2rem; margin-bottom: 1rem;">🚨 주요 개선 필요 영역</h4>
            <ul style="color: #b91c1c; list-style-type: none; padding-left: 0;">
                <li style="margin-bottom: 0.5rem;">• <strong>다양성 (3.5점)</strong>: 콘텐츠 주제 범위 확대 필요</li>
                <li style="margin-bottom: 0.5rem;">• <strong>실용성 (4.1점)</strong>: 실전 투자 전략, 사례 부족</li>
                <li style="margin-bottom: 0.5rem;">• <strong>고급 사용자 만족도</strong>: 심화 콘텐츠 부족</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div class="insight-box strength-box">
            <h4 style="color: #166534; font-size: 1.2rem; margin-bottom: 1rem;">✅ 강점 영역</h4>
            <ul style="color: #15803d; list-style-type: none; padding-left: 0;">
                <li style="margin-bottom: 0.5rem;">• <strong>정확성 & 안전성 (5.0점)</strong>: 완벽한 사실 검증</li>
                <li style="margin-bottom: 0.5rem;">• <strong>초보자 친화성</strong>: 설명 품질과 톤 우수</li>
                <li style="margin-bottom: 0.5rem;">• <strong>레벨 매칭</strong>: 사용자 수준별 적합성 양호</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)

with tab4:
    st.header("전략 방향")
    
    # 전략 로드맵
    st.subheader("개선 전략 로드맵")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("""
        <div class="strategy-box strategy-short">
            <h4 style="color: #1e40af; font-size: 1.2rem; margin-bottom: 1rem;">1️⃣ 단기 (1-2개월)</h4>
            <ul style="color: #1d4ed8; font-size: 0.9rem; list-style-type: none; padding-left: 0;">
                <li style="margin-bottom: 0.5rem;">• 초보자 맞춤 콘텐츠 강화</li>
                <li style="margin-bottom: 0.5rem;">• 다양성 개선 프롬프트 수정</li>
                <li style="margin-bottom: 0.5rem;">• 추천 후보군 2-3배 확대</li>
                <li style="margin-bottom: 0.5rem;">• 실용성 예시 추가</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div class="strategy-box strategy-medium">
            <h4 style="color: #92400e; font-size: 1.2rem; margin-bottom: 1rem;">2️⃣ 중기 (3-6개월)</h4>
            <ul style="color: #a16207; font-size: 0.9rem; list-style-type: none; padding-left: 0;">
                <li style="margin-bottom: 0.5rem;">• 고급 콘텐츠 풀 확장</li>
                <li style="margin-bottom: 0.5rem;">• 레벨별 세분화 강화</li>
                <li style="margin-bottom: 0.5rem;">• 정서 기반 큐레이션 도입</li>
                <li style="margin-bottom: 0.5rem;">• 참여형 학습 기능 개발</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown("""
        <div class="strategy-box strategy-long">
            <h4 style="color: #166534; font-size: 1.2rem; margin-bottom: 1rem;">3️⃣ 장기 (6개월+)</h4>
            <ul style="color: #15803d; font-size: 0.9rem; list-style-type: none; padding-left: 0;">
                <li style="margin-bottom: 0.5rem;">• 프리미엄 리포트 제공</li>
                <li style="margin-bottom: 0.5rem;">• 전문가 레벨 콘텐츠</li>
                <li style="margin-bottom: 0.5rem;">• 성장 파이프라인 완성</li>
                <li style="margin-bottom: 0.5rem;">• 브랜드 확장성 확보</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
    
    # 타겟 사용자별 전략
    st.subheader("타겟 사용자별 전략")
    
    user_strategies = [
        {
            "level": "Beginner (초보자)",
            "description": "기초 금융 시리즈, 친근한 튜토리얼형 지식 제공으로 빠른 신뢰 구축",
            "color": "#eff6ff",
            "text_color": "#1e40af"
        },
        {
            "level": "Intermediate (중급자)",
            "description": "사례·숫자 기반 심화 설명, 참여형 학습으로 Engagement 강화",
            "color": "#fefce8",
            "text_color": "#92400e"
        },
        {
            "level": "Advanced (고급자)",
            "description": "데이터·차트·전문전략 제공, 프리미엄 콘텐츠로 자연스러운 업그레이드",
            "color": "#f0fdf4",
            "text_color": "#166534"
        }
    ]
    
    for strategy in user_strategies:
        st.markdown(f"""
        <div style="background: {strategy['color']}; padding: 1rem; border-radius: 0.5rem; margin: 0.5rem 0; display: flex; align-items: center;">
            <div style="width: 2rem; height: 2rem; background: {strategy['text_color']}; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; margin-right: 1rem;">
                {strategy['level'][0]}
            </div>
            <div>
                <h4 style="color: {strategy['text_color']}; margin: 0; font-size: 1.1rem;">{strategy['level']}</h4>
                <p style="color: {strategy['text_color']}; margin: 0.25rem 0 0 0; font-size: 0.9rem;">{strategy['description']}</p>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    # 기대 효과
    st.subheader("🎯 기대 효과")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("고객 충성도 향상", "85%+")
    
    with col2:
        st.metric("Human 평가 목표", "4.5+")
    
    with col3:
        st.metric("재방문률 증가", "70%+")