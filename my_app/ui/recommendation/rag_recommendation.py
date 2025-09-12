import streamlit as st
import json
import os
import re
import yfinance as yf
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pydantic import BaseModel
from dotenv import load_dotenv
from supabase import create_client, Client
from pinecone import Pinecone

# LangChain 및 관련 라이브러리
from langchain_openai import OpenAIEmbeddings, ChatOpenAI

# --- Pydantic 모델 정의 ---

class PerformanceData(BaseModel):
    one_month: Optional[float] = None
    three_month: Optional[float] = None 
    six_month: Optional[float] = None

class Recommendation(BaseModel):
    ticker: Optional[str] = None
    symbol: Optional[str] = None  # ETF용
    name: str
    reason: str
    similarity_score: float
    performance: PerformanceData
    sexy_reason: str  # 자극적인 추천 이유
    current_price: float = 0.0  # 현재 가격
    keywords: List[str] = []  # 핵심 키워드 3개

# --- 유틸리티 함수 ---

@st.cache_data(ttl=300)  # 5분 캐시
def get_current_price(ticker: str) -> float:
    """현재 주식/ETF 가격을 가져옵니다."""
    try:
        if not ticker or ticker.strip() == '':
            return 0.0
            
        stock = yf.Ticker(ticker.strip().upper())
        hist = stock.history(period="1d")
        
        if hist.empty:
            return 0.0
            
        return round(hist['Close'].iloc[-1], 2)
    except:
        return 0.0

@st.cache_data(ttl=300)  # 5분 캐시
def calculate_historical_returns(ticker: str) -> PerformanceData:
    """주식/ETF의 과거 수익률을 계산합니다."""
    try:
        if not ticker or ticker.strip() == '':
            return PerformanceData()
            
        # yfinance에서 데이터 가져오기
        stock = yf.Ticker(ticker.strip().upper())
        
        # 과거 7개월 데이터 가져오기 (여유있게)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=220)
        
        hist = stock.history(start=start_date, end=end_date, auto_adjust=True, prepost=True)
        
        if hist.empty or len(hist) < 10:
            return PerformanceData()
            
        current_price = hist['Close'].iloc[-1]
        returns = {}
        periods = {'one_month': 22, 'three_month': 66, 'six_month': 132}  # 거래일 기준
        
        for period_name, days_back in periods.items():
            try:
                if len(hist) > days_back:
                    past_price = hist['Close'].iloc[-(days_back + 1)]
                    if past_price > 0:  # 0으로 나누기 방지
                        return_rate = (current_price / past_price - 1) * 100
                        returns[period_name] = round(return_rate, 2)
                    else:
                        returns[period_name] = None
                else:
                    returns[period_name] = None
            except:
                returns[period_name] = None
                
        return PerformanceData(**returns)
        
    except:
        return PerformanceData()

def normalize_similarity_score(score: float) -> float:
    """코사인 유사도를 사용자 친화적인 일치도(40-95%)로 변환합니다."""
    # 보통 코사인 유사도는 0.0 ~ 0.3 정도로 나옴
    # 이를 40% ~ 95% 범위로 매핑
    normalized = 40 + (score * 100 * 1.8)  # 0.3이면 약 94%가 됨
    return min(95, max(40, round(normalized)))

def create_donut_chart(similarity_percentage: float, user_name: str = "회원님") -> go.Figure:
    """일치도 도넛 차트를 생성합니다."""
    fig = go.Figure(data=[go.Pie(
        labels=['일치도', ''],
        values=[similarity_percentage, 100-similarity_percentage],
        hole=.7,
        marker_colors=['#FF6B6B', '#E8E8E8']
    )])
    
    fig.update_traces(
        textinfo='none',
        hovertemplate='<b>%{label}</b><br>%{value}%<extra></extra>'
    )
    
    fig.update_layout(
        showlegend=False,
        margin=dict(t=0, b=0, l=0, r=0),
        height=150,
        annotations=[dict(
            text=f"{user_name} 성향과<br><b>{similarity_percentage}%</b> 일치",
            x=0.5, y=0.5,
            font_size=12,
            showarrow=False,
            font_color="black"
        )]
    )
    
    return fig

def generate_sexy_reason(name: str, performance: PerformanceData, similarity: float) -> str:
    """자극적이고 매력적인 추천 이유를 생성합니다."""
    
    # 수익률 기반 메시지
    if performance.one_month and performance.one_month > 5:
        return f"🚀 {name}, 한 달 만에 +{performance.one_month}%. 지금 이 순간에도 돈이 불어나고 있습니다. 망설이는 사이 수익은 다른 사람 몫."
    elif performance.three_month and performance.three_month > 10:
        return f"💰 3개월 +{performance.three_month}% 수익률. 친구들이 주식 손실 투정할 때, 당신은 조용히 수익 인증샷. 이게 바로 스마트머니의 선택."
    elif performance.six_month and performance.six_month > 15:
        return f"🏆 반년 +{performance.six_month}% 달성한 {name}. 은행 적금 이자? 그건 옛날 얘기. 진짜 부자들은 이미 알고 있었습니다."
    
    # 유사도 기반 메시지
    if similarity > 85:
        return f"🎯 당신을 위해 태어난 종목, {name}. {similarity}% 일치도는 운명이 아니라 필연입니다. 지금이 아니면 언제?"
    elif similarity > 70:
        return f"✨ {name}에 투자하지 않는 이유가 있을까요? {similarity}% 일치하는 투자 성향. 데이터가 증명하는 당신의 선택."
    
    # 기본 자극적 메시지 풀
    sexy_messages = [
        f"🔥 {name}, 모든 사람이 알기 전에 먼저 들어가세요. 늦었다고 생각할 때가 가장 빠른 때입니다.",
        f"💎 {name}은 투자의 숨겨진 보석. 남들이 뒤늦게 깨달을 때, 당신은 이미 수익 중.",
        f"⚡ {name}에 투자하지 않는 건 기회비용의 낭비. 매일 망설이는 시간도 복리로 쌓입니다.",
        f"🎪 재미없어 보이는 {name}? 그게 바로 기회입니다. 화려한 건 이미 늦었어요.",
        f"🦅 {name}으로 시장을 앞서가세요. 남들이 따라올 때쯤엔 이미 정상에서 내려다보는 중."
    ]
    
    import random
    return random.choice(sexy_messages)

def extract_keywords_from_metadata(metadata: dict) -> List[str]:
    """Pinecone 메타데이터에서 핵심 키워드를 추출합니다."""
    keywords = []
    
    # 업종/섹터 정보
    if 'sector' in metadata:
        keywords.append(metadata['sector'])
    if 'industry' in metadata:
        keywords.append(metadata['industry'])
    
    # 기타 중요 태그들
    potential_keys = ['category', 'type', 'focus', 'theme', 'region', 'style']
    for key in potential_keys:
        if key in metadata and metadata[key]:
            keywords.append(str(metadata[key]))
    
    # 최대 3개만 반환
    return keywords[:3]

def translate_keywords_to_korean(keywords: List[str], llm) -> List[str]:
    """영어 키워드를 한국어로 번역합니다."""
    if not keywords:
        return []
    
    try:
        keywords_text = ', '.join(keywords)
        prompt = f"""
        다음 투자 관련 영어 키워드들을 한국어로 번역해주세요. 투자자가 이해하기 쉬운 한국어 단어로 변환해주세요.

        영어 키워드: {keywords_text}

        출력 형식: ["한국어1", "한국어2", "한국어3"]
        
        예시:
        - Technology → "기술주"
        - Healthcare → "헬스케어"  
        - Finance → "금융"
        - Real Estate → "부동산"
        - Consumer → "소비재"
        - Energy → "에너지"
        
        반드시 한국어로만 답해주세요.
        """
        
        response = llm.invoke(prompt)
        keywords_text = response.content.strip()
        
        # JSON 형태로 파싱 시도
        import re
        match = re.search(r'\[(.*?)\]', keywords_text)
        if match:
            keywords_str = match.group(1)
            korean_keywords = [k.strip().strip('"\'') for k in keywords_str.split(',')]
            return korean_keywords[:3]
        
        return keywords  # 번역 실패시 원본 반환
        
    except:
        return keywords  # 오류시 원본 반환

def generate_keywords_with_llm(name: str, reason: str, llm) -> List[str]:
    """LLM을 사용해서 핵심 키워드를 생성합니다."""
    try:
        prompt = f"""
        다음 투자 상품의 핵심 키워드 3개를 추출해주세요. 투자자가 한눈에 이해할 수 있는 간단한 한국어 단어로 답해주세요.

        상품명: {name}
        추천이유: {reason}

        출력 형식: ["키워드1", "키워드2", "키워드3"]
        예시: ["성장주", "기술주", "배당"]

        반드시 한국어로만 답해주세요. 영어 단어는 사용하지 마세요.
        """
        
        response = llm.invoke(prompt)
        keywords_text = response.content.strip()
        
        # JSON 형태로 파싱 시도
        import re
        match = re.search(r'\[(.*?)\]', keywords_text)
        if match:
            keywords_str = match.group(1)
            keywords = [k.strip().strip('"\'') for k in keywords_str.split(',')]
            return keywords[:3]
        
        # 실패시 기본 키워드 반환
        return ["투자", "추천", "성장"]
        
    except:
        return ["투자", "추천", "우량"]

# --- 초기 설정 및 클라이언트 초기화 (공통) ---

@st.cache_resource
def init_clients():
    """API 클라이언트 및 환경 변수를 초기화합니다."""
    dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', '.env')
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path)
    
    required_keys = ["OPENAI_API_KEY", "PINECONE_API_KEY", "SUPABASE_URL", "SUPABASE_KEY"]
    if not all(os.getenv(key) for key in required_keys):
        st.error("필수 환경 변수가 .env 파일에 설정되지 않았습니다.")
        st.stop()

    llm = ChatOpenAI(model_name="gpt-4o", temperature=0, openai_api_key=os.getenv("OPENAI_API_KEY"))
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small", openai_api_key=os.getenv("OPENAI_API_KEY"))
    supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
    pinecone = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    
    return llm, embeddings, supabase, pinecone

# --- 공통 유틸리티 함수 ---

def _extract_json_from_llm(text: str):
    """LLM 응답에서 JSON 배열만 안전하게 추출합니다. 마크다운 블록을 처리합니다."""
    # Case 1: Markdown code block ```json ... ```
    match = re.search(r"```json\s*(\[[\s\S]*\])\s*```", text)
    if match:
        json_str = match.group(1)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass

    # Case 2: Raw JSON array (fallback)
    match = re.search(r'\[[\s\S]*\]', text)
    if match:
        json_str = match.group(0)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            return None
            
    return None

# --- 인덱스 가져오기 함수 ---

@st.cache_resource
def get_pinecone_index(_pinecone_client, index_name: str):
    """지정된 이름의 Pinecone 인덱스를 가져옵니다."""
    if index_name not in _pinecone_client.list_indexes().names():
        st.error(f"Pinecone 인덱스 '{index_name}'을 찾을 수 없습니다.")
        return None
    return _pinecone_client.Index(index_name)

# --- 메인 렌더링 함수 ---

def render():
    st.title("🤖 AI 맞춤 상품 추천")
    
    llm, embeddings, supabase, pinecone = init_clients()
    user_id = st.session_state.user.id if "user" in st.session_state else None

    tab1, tab2 = st.tabs(["📈 주식 추천", "📊 ETF 추천"])

    with tab1:
        st.header("AI 주식 추천")
        st.info("회원님의 투자 성향에 맞는 주식을 추천해 드립니다.")
        
        # 시가총액 필터 옵션 추가
        col1, col2 = st.columns([1, 2])
        with col1:
            market_cap_filter = st.selectbox(
                "🏢 시가총액 필터", 
                ["전체 종목", "라지캡 이상 (100억$ 이상)", "메가캡 이상 (2000억$ 이상)"],
                key="stock_market_cap_filter"
            )
        with col2:
            st.info(f"선택: {market_cap_filter}")
        
        stock_index = get_pinecone_index(pinecone, "sp500-rag-pipeline")

        if 'stock_recommendations' not in st.session_state:
            st.session_state.stock_recommendations = None
        
        # 기존 추천 결과 초기화 (새로운 필드 호환성을 위해)
        if st.button("🔄 추천 결과 초기화", key="reset_stock_recommendations"):
            st.session_state.stock_recommendations = None
            st.success("추천 결과가 초기화되었습니다.")

        if st.button("🚀 내게 맞는 주식 추천받기", key="stock_recommend_button"):
            if not user_id:
                st.error("로그인 후 이용해주세요.")
            elif not stock_index:
                st.error("주식 추천 서비스를 현재 사용할 수 없습니다.")
            else:
                with st.spinner("AI가 회원님의 프로필에 맞는 주식을 분석 중입니다..."):
                    try:
                        response = supabase.table('profiles').select('user_summary').eq('id', user_id).single().execute()
                        user_profile = response.data.get('user_summary') if response.data else None
                        if not user_profile:
                            st.error("투자 성향 정보가 없습니다. 프로필을 먼저 설정해주세요.")
                            st.stop()

                        query_vector = embeddings.embed_query(user_profile)
                        
                        # 시가총액 필터 설정
                        pinecone_filter = {}
                        if market_cap_filter == "라지캡 이상 (100억$ 이상)":
                            pinecone_filter = {"marketCap": {"$gte": 10000000000}}  # 100억 달러 이상
                        elif market_cap_filter == "메가캡 이상 (2000억$ 이상)":
                            pinecone_filter = {"marketCap": {"$gte": 200000000000}}  # 2000억 달러 이상
                        
                        # 필터와 함께 검색
                        if pinecone_filter:
                            retrieval_results = stock_index.query(
                                vector=query_vector, 
                                top_k=15,  # 필터링 후에도 충분한 후보를 위해 더 많이 검색
                                include_metadata=True,
                                filter=pinecone_filter
                            )
                        else:
                            retrieval_results = stock_index.query(vector=query_vector, top_k=10, include_metadata=True)
                        
                        candidate_stocks = [res['metadata'] for res in retrieval_results['matches']]
                        
                        # 필터 결과 표시
                        if pinecone_filter:
                            st.success(f"🔍 {market_cap_filter} 조건으로 {len(candidate_stocks)}개 종목을 찾았습니다.")

                        prompt_text = f"""
                        당신은 최고의 금융 전문가입니다. 다음 [사용자 투자 성향]과 [후보 주식 정보]를 바탕으로, 사용자에게 가장 적합한 주식 3개를 추천하고, 그 이유를 명확하고 전문적으로 한국어로 설명해주세요.

                        [사용자 투자 성향]: {user_profile}
                        [후보 주식 정보]: {json.dumps(candidate_stocks, ensure_ascii=False, indent=2)}
                        
                        [출력 형식]: 반드시 다음 JSON 배열 형식으로만 응답해주세요:
                        [
                          {{
                            "ticker": "AAPL",
                            "name": "Apple Inc",
                            "reason": "이 회사를 추천하는 상세한 이유를 전문적이고 설득력 있게 작성"
                          }}
                        ]
                        """
                        
                        llm_response = llm.invoke(prompt_text)
                        basic_recommendations = _extract_json_from_llm(llm_response.content)
                        
                        # 추천 결과를 강화된 형태로 변환
                        if basic_recommendations:
                            enhanced_recommendations = []
                            for i, rec in enumerate(basic_recommendations):
                                ticker = rec.get('ticker', '')
                                name = rec.get('name', '')
                                reason = rec.get('reason', '')
                                
                                # 유사도 점수 (검색 결과에서 가져오기)
                                similarity_score = retrieval_results['matches'][i]['score'] if i < len(retrieval_results['matches']) else 0.1
                                
                                # 현재 가격 및 과거 수익률 계산
                                current_price = get_current_price(ticker)
                                performance = calculate_historical_returns(ticker)
                                
                                # 정규화된 유사도
                                normalized_similarity = normalize_similarity_score(similarity_score)
                                
                                # 자극적인 추천 이유
                                sexy_reason = generate_sexy_reason(name, performance, normalized_similarity)
                                
                                # 키워드 생성 (LLM 우선 사용, 실패 시 메타데이터 번역)
                                keywords = generate_keywords_with_llm(name, reason, llm)
                                
                                # LLM 실패 시 메타데이터에서 추출 후 번역
                                if not keywords or len([k for k in keywords if k.strip()]) == 0:
                                    metadata = retrieval_results['matches'][i]['metadata'] if i < len(retrieval_results['matches']) else {}
                                    eng_keywords = extract_keywords_from_metadata(metadata)
                                    if eng_keywords:
                                        keywords = translate_keywords_to_korean(eng_keywords, llm)
                                    else:
                                        keywords = ["투자", "추천", "우량"]
                                
                                enhanced_rec = Recommendation(
                                    ticker=ticker,
                                    name=name,
                                    reason=reason,
                                    similarity_score=normalized_similarity,
                                    performance=performance,
                                    sexy_reason=sexy_reason,
                                    current_price=current_price,
                                    keywords=keywords
                                )
                                
                                enhanced_recommendations.append(enhanced_rec)
                            
                            st.session_state.stock_recommendations = enhanced_recommendations

                    except Exception as e:
                        st.error(f"주식 추천 중 오류: {e}")

        if st.session_state.get('stock_recommendations'):
            st.subheader("✨ 맞춤 주식 포트폴리오 ✨", divider='rainbow')
            
            for idx, rec in enumerate(st.session_state.stock_recommendations):
                with st.container(border=True):
                    # 메인 레이아웃: 1:1 비율
                    left_col, right_col = st.columns([1, 1])
                    
                    with left_col:
                        # 왼쪽: 기본 정보
                        st.markdown(f"### {rec.name}")
                        st.markdown(f"**티커:** `{rec.ticker}`")
                        
                        # 핵심 키워드 (태그 형태로 표시)
                        keywords = getattr(rec, 'keywords', [])
                        if keywords:
                            st.markdown("**🏷️ 핵심 키워드**")
                            cols = st.columns(len(keywords))
                            for i, keyword in enumerate(keywords):
                                with cols[i]:
                                    st.markdown(f"<div style='background-color: #f0f0f5; padding: 4px 8px; border-radius: 12px; text-align: center; font-size: 0.8em; margin: 2px 0;'>{keyword}</div>", unsafe_allow_html=True)
                        
                        # 전문가 추천 이유
                        st.markdown("**💡 전문가 분석**")
                        st.write(rec.reason)
                        
                        # 추가 정보 링크
                        st.markdown(f"[📊 Yahoo Finance에서 더 알아보기](https://finance.yahoo.com/quote/{rec.ticker})")
                    
                    with right_col:
                        # 오른쪽: 새로운 기능들
                        
                        # 상단: 현재 가격 + 도넛 차트
                        chart_col1, chart_col2 = st.columns([1, 2])
                        
                        with chart_col1:
                            # 현재 가격
                            current_price = getattr(rec, 'current_price', 0.0)
                            if current_price > 0:
                                st.metric(
                                    label="💰 현재가", 
                                    value=f"${current_price:,.2f}"
                                )
                            else:
                                st.metric(
                                    label="💰 현재가", 
                                    value="N/A"
                                )
                        
                        with chart_col2:
                            # 일치도 도넛 차트
                            donut_fig = create_donut_chart(rec.similarity_score)
                            st.plotly_chart(donut_fig, use_container_width=True, key=f"stock_donut_{idx}")
                        
                        # 자극적인 추천 이유
                        st.markdown("**🔥 한 줄 요약**")
                        st.info(rec.sexy_reason)
                        
                        # 과거 수익률 표시
                        st.markdown("**📈 과거 수익률**")
                        perf_col1, perf_col2, perf_col3 = st.columns(3)
                        
                        with perf_col1:
                            if rec.performance.one_month is not None:
                                st.metric("1M", f"{rec.performance.one_month:+.1f}%")
                            else:
                                st.metric("1M", "N/A")
                        
                        with perf_col2:
                            if rec.performance.three_month is not None:
                                st.metric("3M", f"{rec.performance.three_month:+.1f}%")
                            else:
                                st.metric("3M", "N/A")
                        
                        with perf_col3:
                            if rec.performance.six_month is not None:
                                st.metric("6M", f"{rec.performance.six_month:+.1f}%")
                            else:
                                st.metric("6M", "N/A")
                
                if idx < len(st.session_state.stock_recommendations) - 1:
                    st.divider()

    with tab2:
        st.header("AI ETF 추천")
        st.info("회원님의 투자 성향에 맞는 ETF를 추천해 드립니다.")
        etf_index = get_pinecone_index(pinecone, "rag-etf")

        if 'etf_recommendations' not in st.session_state:
            st.session_state.etf_recommendations = None
        
        # 기존 추천 결과 초기화 (새로운 필드 호환성을 위해)
        if st.button("🔄 추천 결과 초기화", key="reset_etf_recommendations"):
            st.session_state.etf_recommendations = None
            st.success("ETF 추천 결과가 초기화되었습니다.")

        if st.button("🚀 내게 맞는 ETF 추천받기", key="etf_recommend_button"):
            if not user_id:
                st.error("로그인 후 이용해주세요.")
            elif not etf_index:
                st.error("ETF 추천 서비스를 현재 사용할 수 없습니다.")
            else:
                with st.spinner("AI가 회원님의 프로필에 맞는 ETF를 분석 중입니다..."):
                    try:
                        response = supabase.table('profiles').select('user_summary').eq('id', user_id).single().execute()
                        user_profile = response.data.get('user_summary') if response.data else None
                        if not user_profile:
                            st.error("투자 성향 정보가 없습니다. 프로필을 먼저 설정해주세요.")
                            st.stop()

                        query_vector = embeddings.embed_query(user_profile)
                        retrieval_results = etf_index.query(vector=query_vector, top_k=5, include_metadata=True)
                        candidate_etfs = [res['metadata'] for res in retrieval_results['matches']]

                        prompt_text = f"""
                        당신은 전문 ETF 투자 자문가입니다. 다음 [사용자 투자 프로필]과 [참고 ETF 정보]를 바탕으로, 사용자에게 가장 적합한 ETF 3개를 추천하고, 그 이유를 명확하고 전문적으로 한국어로 설명해주세요.

                        [사용자 투자 프로필]: {user_profile}
                        [참고 ETF 정보]: {json.dumps(candidate_etfs, ensure_ascii=False, indent=2)}
                        
                        [출력 형식]: 반드시 다음 JSON 배열 형식으로만 응답해주세요:
                        [
                          {{
                            "symbol": "SPY",
                            "name": "SPDR S&P 500 ETF",
                            "reason": "이 ETF를 추천하는 상세한 이유를 전문적이고 설득력 있게 작성"
                          }}
                        ]
                        """
                        
                        llm_response = llm.invoke(prompt_text)
                        basic_recommendations = _extract_json_from_llm(llm_response.content)
                        
                        # 추천 결과를 강화된 형태로 변환
                        if basic_recommendations:
                            enhanced_recommendations = []
                            for i, rec in enumerate(basic_recommendations):
                                symbol = rec.get('symbol', '')
                                name = rec.get('name', '')
                                reason = rec.get('reason', '')
                                
                                # 유사도 점수 (검색 결과에서 가져오기)
                                similarity_score = retrieval_results['matches'][i]['score'] if i < len(retrieval_results['matches']) else 0.1
                                
                                # 현재 가격 및 과거 수익률 계산
                                current_price = get_current_price(symbol)
                                performance = calculate_historical_returns(symbol)
                                
                                # 정규화된 유사도
                                normalized_similarity = normalize_similarity_score(similarity_score)
                                
                                # 자극적인 추천 이유
                                sexy_reason = generate_sexy_reason(name, performance, normalized_similarity)
                                
                                # 키워드 생성 (LLM 우선 사용, 실패 시 메타데이터 번역)
                                keywords = generate_keywords_with_llm(name, reason, llm)
                                
                                # LLM 실패 시 메타데이터에서 추출 후 번역
                                if not keywords or len([k for k in keywords if k.strip()]) == 0:
                                    metadata = retrieval_results['matches'][i]['metadata'] if i < len(retrieval_results['matches']) else {}
                                    eng_keywords = extract_keywords_from_metadata(metadata)
                                    if eng_keywords:
                                        keywords = translate_keywords_to_korean(eng_keywords, llm)
                                    else:
                                        keywords = ["투자", "추천", "우량"]
                                
                                enhanced_rec = Recommendation(
                                    symbol=symbol,
                                    name=name,
                                    reason=reason,
                                    similarity_score=normalized_similarity,
                                    performance=performance,
                                    sexy_reason=sexy_reason,
                                    current_price=current_price,
                                    keywords=keywords
                                )
                                
                                enhanced_recommendations.append(enhanced_rec)
                            
                            st.session_state.etf_recommendations = enhanced_recommendations

                    except Exception as e:
                        st.error(f"ETF 추천 중 오류: {e}")

        if st.session_state.get('etf_recommendations'):
            st.subheader("✨ 맞춤 ETF 포트폴리오 ✨", divider='rainbow')
            
            for idx, rec in enumerate(st.session_state.etf_recommendations):
                with st.container(border=True):
                    # 메인 레이아웃: 1:1 비율
                    left_col, right_col = st.columns([1, 1])
                    
                    with left_col:
                        # 왼쪽: 기본 정보
                        st.markdown(f"### {rec.name}")
                        st.markdown(f"**심볼:** `{rec.symbol}`")
                        
                        # 핵심 키워드 (태그 형태로 표시)
                        keywords = getattr(rec, 'keywords', [])
                        if keywords:
                            st.markdown("**🏷️ 핵심 키워드**")
                            cols = st.columns(len(keywords))
                            for i, keyword in enumerate(keywords):
                                with cols[i]:
                                    st.markdown(f"<div style='background-color: #f0f0f5; padding: 4px 8px; border-radius: 12px; text-align: center; font-size: 0.8em; margin: 2px 0;'>{keyword}</div>", unsafe_allow_html=True)
                        
                        # 전문가 추천 이유
                        st.markdown("**💡 전문가 분석**")
                        st.write(rec.reason)
                        
                        # 추가 정보 링크
                        st.markdown(f"[📊 Yahoo Finance에서 더 알아보기](https://finance.yahoo.com/quote/{rec.symbol})")
                    
                    with right_col:
                        # 오른쪽: 새로운 기능들
                        
                        # 상단: 현재 가격 + 도넛 차트
                        chart_col1, chart_col2 = st.columns([1, 2])
                        
                        with chart_col1:
                            # 현재 가격
                            current_price = getattr(rec, 'current_price', 0.0)
                            if current_price > 0:
                                st.metric(
                                    label="💰 현재가", 
                                    value=f"${current_price:,.2f}"
                                )
                            else:
                                st.metric(
                                    label="💰 현재가", 
                                    value="N/A"
                                )
                        
                        with chart_col2:
                            # 일치도 도넛 차트
                            donut_fig = create_donut_chart(rec.similarity_score)
                            st.plotly_chart(donut_fig, use_container_width=True, key=f"etf_donut_{idx}")
                        
                        # 자극적인 추천 이유
                        st.markdown("**🔥 한 줄 요약**")
                        st.info(rec.sexy_reason)
                        
                        # 과거 수익률 표시
                        st.markdown("**📈 과거 수익률**")
                        perf_col1, perf_col2, perf_col3 = st.columns(3)
                        
                        with perf_col1:
                            if rec.performance.one_month is not None:
                                st.metric("1M", f"{rec.performance.one_month:+.1f}%")
                            else:
                                st.metric("1M", "N/A")
                        
                        with perf_col2:
                            if rec.performance.three_month is not None:
                                st.metric("3M", f"{rec.performance.three_month:+.1f}%")
                            else:
                                st.metric("3M", "N/A")
                        
                        with perf_col3:
                            if rec.performance.six_month is not None:
                                st.metric("6M", f"{rec.performance.six_month:+.1f}%")
                            else:
                                st.metric("6M", "N/A")
                
                if idx < len(st.session_state.etf_recommendations) - 1:
                    st.divider()