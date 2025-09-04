import streamlit as st

def inject_home_styles():
    st.markdown("""
    <style>
      .home-hero {
        background: linear-gradient(135deg, rgba(99,102,241,.15), rgba(16,185,129,.15));
        border-radius: 20px;
        padding: 40px 30px;
        text-align: center;
        margin-bottom: 30px;
      }
      .home-hero h1 {
        font-size: 2.4rem;
        font-weight: 900;
        margin-bottom: .6rem;
      }
      .home-hero p {
        font-size: 1.1rem;
        opacity: .85;
        margin: 0;
      }
      .feature-card {
        border:1px solid rgba(148,163,184,.28);
        border-radius:16px;
        padding:24px;
        background:white;
        transition: all .2s ease;
        height:100%;
      }
      .feature-card:hover {
        box-shadow:0 4px 16px rgba(0,0,0,.08);
        transform: translateY(-2px);
      }
      .feature-title {
        font-weight:700;
        margin-top:10px;
        font-size:1.1rem;
      }
      .feature-desc {
        font-size:.95rem;
        opacity:.9;
        margin-top:6px;
      }
      .step-card {
        background: rgba(2,6,23,.02);
        border: 1px solid rgba(148,163,184,.28);
        border-radius: 14px;
        padding: 16px 20px;
        margin-bottom: 12px;
      }
      .step-card strong {
        font-size: 1.05rem;
      }
    </style>
    """, unsafe_allow_html=True)


def render():
    inject_home_styles()

    # Hero Section
    st.markdown("""
    <div class="home-hero">
      <h1>🚀 FIREGENERATOR</h1>
      <p>2030 세대를 위한 금융 지식 퀴즈, AI 챗봇 상담, 투자 시뮬레이션과 맞춤형 리포트</p>
    </div>
    """, unsafe_allow_html=True)

    # 프로젝트 소개
    st.subheader("📖 프로젝트 소개")
    st.markdown("""
    **FIREGENERATOR**는 단순한 퀴즈 앱이 아닙니다.  
    챗봇으로 투자 목표와 감정을 대화로 입력받고, 맞춤형 금융 퀴즈를 통해 학습하며,  
    개인화된 금융 지식과 상품 추천, 보유 주식에 대한 AI 코칭까지 제공합니다.  

    저희 목표는 **2030 세대가 자기 주도적으로 금융 지식을 쌓고, 자산을 성장시키는 것**입니다.
    """, unsafe_allow_html=True)

    st.divider()

    # 주요 기능
    st.subheader("✨ 주요 기능")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("""
        <div class="feature-card">
          <div style="font-size:2rem;">💬</div>
          <div class="feature-title">Chatbot</div>
          <div class="feature-desc">투자 목표, 감정, 관심사, 투자 수준을 입력하고 금융 상담을 시작하세요.</div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown("""
        <div class="feature-card">
          <div style="font-size:2rem;">🧠</div>
          <div class="feature-title">오늘의 퀴즈</div>
          <div class="feature-desc">관심 카테고리를 기반으로 맞춤형 퀴즈를 풀고 금융 지식을 점검하세요.</div>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        st.markdown("""
        <div class="feature-card">
          <div style="font-size:2rem;">📖</div>
          <div class="feature-title">맞춤형 금융 지식</div>
          <div class="feature-desc">퀴즈 결과와 관심사에 따라 개인화된 금융 정보를 확인할 수 있습니다.</div>
        </div>
        """, unsafe_allow_html=True)

    col4, col5, col6 = st.columns(3)
    with col4:
        st.markdown("""
        <div class="feature-card">
          <div style="font-size:2rem;">🎁</div>
          <div class="feature-title">맞춤형 상품 추천</div>
          <div class="feature-desc">투자 성향을 기반으로 주식 및 금융 상품을 추천받으세요.</div>
        </div>
        """, unsafe_allow_html=True)
    with col5:
        st.markdown("""
        <div class="feature-card">
          <div style="font-size:2rem;">📈</div>
          <div class="feature-title">보유 주식 AI 코칭</div>
          <div class="feature-desc">현재 보유 중인 주식을 등록하고 AI로부터 현황 분석과 코칭을 받으세요.</div>
        </div>
        """, unsafe_allow_html=True)
    with col6:
        st.markdown("""
        <div class="feature-card">
          <div style="font-size:2rem;">📊</div>
          <div class="feature-title">종목 피드백</div>
          <div class="feature-desc">관심 종목별로 세부 피드백을 받아 투자 전략을 개선하세요.</div>
        </div>
        """, unsafe_allow_html=True)

    st.divider()

    # 서비스 이용 순서
    st.subheader("이용 순서")
    st.markdown("""
    <div class="step-card">
      <strong>1단계: Chatbot 💬</strong><br/>
      투자 목표, 감정, 관심 카테고리, 투자 수준을 입력하며 나의 금융 프로필을 완성합니다.
    </div>
    <div class="step-card">
      <strong>2단계: 오늘의 퀴즈 ❓</strong><br/>
      관심 카테고리에 맞는 퀴즈를 풀고 금융 지식을 점검합니다.
    </div>
    <div class="step-card">
      <strong>3단계: 맞춤형 금융 지식 📖</strong><br/>
      퀴즈 결과와 관심사에 따라 추천된 금융 정보를 학습합니다.
    </div>
    <div class="step-card">
      <strong>4단계: 맞춤형 상품 추천 🎁</strong><br/>
      투자 성향 기반으로 나에게 맞는 주식·상품을 추천받습니다.
    </div>
    <div class="step-card">
      <strong>5단계: 보유 주식 AI 코칭 📈</strong><br/>
      내가 보유한 주식에 대한 분석과 코칭을 통해 전략을 보완합니다.
    </div>
    <div class="step-card">
      <strong>6단계: 종목 피드백 📊</strong><br/>
      개별 종목에 대해 AI 피드백을 받아 투자 결정을 정교화합니다.
    </div>
    """, unsafe_allow_html=True)

    st.divider()

