import streamlit as st
import json
import os
import re
from dotenv import load_dotenv
from supabase import create_client
from pinecone import Pinecone

# LangChain 및 관련 라이브러리
from langchain_openai import OpenAIEmbeddings, ChatOpenAI

# --- 초기 설정 및 클라이언트 초기화 ---

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

@st.cache_resource
def get_pinecone_index(_pinecone_client, index_name: str):
    """지정된 이름의 Pinecone 인덱스를 가져옵니다."""
    if index_name not in _pinecone_client.list_indexes().names():
        st.error(f"Pinecone 인덱스 '{index_name}'을 찾을 수 없습니다.")
        return None
    return _pinecone_client.Index(index_name)


# --- UI 렌더링 ---

def render():
    """페이지 전체를 렌더링합니다."""
    st.title("🤖 AI 기반 맞춤형 ETF 추천")
    st.info("회원님의 투자 성향을 분석하여 최적의 ETF 포트폴리오를 추천해 드립니다.")

    llm, embeddings, supabase, pinecone = init_clients()
    user_id = st.session_state.user.id if "user" in st.session_state else None

    etf_index = get_pinecone_index(pinecone, "rag-etf")

    if 'etf_recommendations' not in st.session_state:
        st.session_state.etf_recommendations = None

    if st.button("🚀 내 투자 성향에 맞는 ETF 추천받기", use_container_width=True, type="primary"):
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
                    당신은 전문 ETF 투자 자문가입니다. 다음 [사용자 투자 프로필]과 [참고 ETF 정보]를 바탕으로, 사용자에게 가장 적합한 ETF 3개를 추천하고, 그 이유를 명확하고 상세하게 한국어로 설명해주세요.
                    [사용자 투자 프로필]: {user_profile}
                    [참고 ETF 정보]: {json.dumps(candidate_etfs, ensure_ascii=False, indent=2)}
                    [출력 형식]: 반드시 JSON 배열 형식으로만 응답해주세요. (예: [{{"symbol": "SPY", "name": "SPDR S&P 500 ETF", "reason": "..."}}])
                    """
                    llm_response = llm.invoke(prompt_text)
                    st.session_state.etf_recommendations = _extract_json_from_llm(llm_response.content)

                except Exception as e:
                    st.error(f"ETF 추천 중 오류: {e}")

    if st.session_state.get('etf_recommendations'):
        st.subheader("✨ 맞춤 ETF 포트폴리오 ✨", divider='rainbow')
        for rec in st.session_state.etf_recommendations:
            with st.container(border=True):
                st.markdown(f"#### {rec.get('name')} ({rec.get('symbol')})")
                st.write(f"**💡 추천 이유:** {rec.get('reason')}")
                st.markdown(f"[Yahoo Finance에서 더 알아보기](https://finance.yahoo.com/quote/{rec.get('symbol')})")

