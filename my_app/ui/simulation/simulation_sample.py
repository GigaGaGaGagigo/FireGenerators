import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

def create_sample_data():
    """샘플 데이터 생성"""
    dates = pd.date_range(start='2023-01-01', end='2024-12-31', freq='M')
    
    # 포트폴리오 성장 데이터
    portfolio_data = {
        'date': dates,
        'portfolio_value': [1000000 + i * 150000 + (i * 50000 if i % 3 == 0 else 0) for i in range(len(dates))],
        'invested_amount': [1000000 + i * 100000 for i in range(len(dates))],
        'profit_loss': [i * 50000 + (i * 50000 if i % 3 == 0 else 0) for i in range(len(dates))]
    }
    
    # 자산 배분 데이터
    asset_allocation = {
        'asset_type': ['국내 주식', '해외 주식', '채권', '현금'],
        'percentage': [40, 35, 20, 5],
        'amount': [8000000, 7000000, 4000000, 1000000]
    }
    
    return pd.DataFrame(portfolio_data), pd.DataFrame(asset_allocation)

def render_portfolio_overview():
    """포트폴리오 개요 카드"""
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="총 자산",
            value="20,000,000원",
            delta="1,500,000원 (8.1%)",
            delta_color="normal"
        )
    
    with col2:
        st.metric(
            label="투자원금",
            value="15,000,000원",
            delta="500,000원",
            delta_color="off" # 투자원금 증가는 중립적으로 표시
        )
    
    with col3:
        st.metric(
            label="수익률",
            value="33.3%",
            delta="2.5%",
            delta_color="normal"
        )
    
    with col4:
        st.metric(
            label="FIRE 달성률",
            value="20%",
            delta="1.5%",
            delta_color="normal"
        )

def render_portfolio_growth_chart(portfolio_df):
    """포트폴리오 성장 차트"""
    fig = go.Figure()
    
    # 포트폴리오 가치
    fig.add_trace(go.Scatter(
        x=portfolio_df['date'],
        y=portfolio_df['portfolio_value'],
        mode='lines',
        name='포트폴리오 가치',
        line=dict(color='#FE7743', width=3)
    ))
    
    # 투자원금
    fig.add_trace(go.Scatter(
        x=portfolio_df['date'],
        y=portfolio_df['invested_amount'],
        mode='lines',
        name='투자원금',
        line=dict(color='#273F4F', width=2, dash='dash')
    ))
    
    fig.update_layout(
        title='포트폴리오 성장 추이',
        xaxis_title='날짜',
        yaxis_title='금액 (원)',
        hovermode='x unified',
        plot_bgcolor='white',
        paper_bgcolor='white',
        legend=dict(x=0.01, y=0.99)
    )
    
    return fig

def render_asset_allocation_chart(asset_df):
    """자산 배분 차트"""
    fig = px.pie(
        asset_df,
        values='percentage',
        names='asset_type',
        title='자산 배분',
        color_discrete_sequence=['#FE7743', '#FEA07A', '#FEB795', '#FED4B0']
    )
    
    fig.update_traces(textposition='inside', textinfo='percent+label', hole=.3)
    fig.update_layout(
        paper_bgcolor='white',
        plot_bgcolor='white',
        showlegend=False
    )
    
    return fig

def render_fire_progress():
    """FIRE 달성 진행률"""
    target_amount = 100000000  # 1억원 목표
    current_amount = 20000000  # 현재 2천만원
    progress = (current_amount / target_amount)
    
    st.subheader("🎯 FIRE 달성 목표")
    st.progress(progress)
    st.write(f"**목표**: {target_amount:,}원 | **현재**: {current_amount:,}원 ({progress:.1%})")
    
    # 목표 달성까지 남은 기간 계산
    monthly_saving = 500000  # 월 50만원 저축 가정
    remaining_amount = target_amount - current_amount
    
    # 월 저축액이 0보다 클 때만 계산
    if monthly_saving > 0:
        months_to_goal = remaining_amount / monthly_saving
        years_to_goal = months_to_goal / 12
        
        col1, col2 = st.columns(2)
        with col1:
            st.info(f"예상 달성 기간: {years_to_goal:.1f}년")
        with col2:
            st.info(f"월 저축액: {monthly_saving:,}원")
    else:
        st.warning("월 저축액을 설정해야 예상 달성 기간을 계산할 수 있습니다.")


def render():
    """대시보드 페이지 렌더링"""
    st.set_page_config(layout="wide")
    st.title("📊 투자 대시보드")
    
    # 샘플 데이터 생성
    portfolio_df, asset_df = create_sample_data()
    
    # 포트폴리오 개요
    render_portfolio_overview()
    
    st.divider()
    
    # 차트 영역
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # 포트폴리오 성장 차트
        portfolio_chart = render_portfolio_growth_chart(portfolio_df)
        st.plotly_chart(portfolio_chart, use_container_width=True)
        
    with col2:
        # 자산 배분 차트
        allocation_chart = render_asset_allocation_chart(asset_df)
        st.plotly_chart(allocation_chart, use_container_width=True)
    
    st.divider()
    
    # FIRE 진행률
    render_fire_progress()

# 이 스크립트를 직접 실행할 때 render() 함수를 호출합니다.
if __name__ == "__main__":
    render()
