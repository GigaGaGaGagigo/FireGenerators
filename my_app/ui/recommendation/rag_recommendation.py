import os
import streamlit as st
import re
import datetime
from pinecone import Pinecone
from langchain_openai import OpenAIEmbeddings, OpenAI
from dotenv import load_dotenv
import json
from supabase import create_client, Client

@st.cache_resource
def init_clients():
    """API 클라이언트를 초기화하고 캐시합니다."""
    dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', '.env')
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path)
    
    # API 키 및 Supabase URL/Key 확인
    api_keys_missing = not os.getenv("PINECONE_API_KEY") or not os.getenv("OPENAI_API_KEY")
    supabase_creds_missing = not st.secrets.get("supabase") or not st.secrets["supabase"].get("url") or not st.secrets["supabase"].get("key")

    if api_keys_missing:
        st.error("API 키가 설정되지 않았습니다. .env 파일을 확인해주세요.")
        st.stop()
    if supabase_creds_missing:
        st.error("Supabase 설정이 누락되었습니다. Streamlit secrets를 확인해주세요.")
        st.stop()

    # 클라이언트 초기화
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small", openai_api_key=os.getenv("OPENAI_API_KEY"))
    llm = OpenAI(temperature=0, openai_api_key=os.getenv("OPENAI_API_KEY"), model_name="gpt-4o-mini")
    supabase_client = create_client(st.secrets["supabase"]["url"], st.secrets["supabase"]["key"])

    # Pinecone 인덱스 연결
    index_name = "sp500-rag-pipeline"
    if index_name not in pc.list_indexes().names():
        st.error(f"Pinecone 인덱스 '{index_name}'을 찾을 수 없습니다. 먼저 build_vector_db.py를 실행해주세요.")
        st.stop()
    pinecone_index = pc.Index(index_name)
    
    return pinecone_index, embeddings, llm, supabase_client

def _extract_json_array(text: str):
    """LLM 응답에서 JSON 배열만 안전하게 추출합니다."""
    match = re.search(r"```json\n(\[.*?\])\n```", text, re.DOTALL)
    if match:
        json_str = match.group(1)
    else:
        match = re.search(r"(\[.*?\])", text, re.DOTALL)
        if match:
            json_str = match.group(1)
        else:
            return None
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return None

def _save_log(user_query, candidate_stocks, final_recommendations):
    """추천 결과를 로그 파일에 저장합니다."""
    log_dir = os.path.join(os.path.dirname(__file__), 'data')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "recommendation_logs.jsonl")
    log_entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "user_query": user_query,
        "candidate_stocks": candidate_stocks,
        "final_recommendations": final_recommendations
    }
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

def render():
    """메인 앱에서 호출될 페이지 렌더링 함수"""
    st.title("🤖 RAG 기반 맞춤형 주식 추천")

    pinecone_index, embeddings, llm, supabase = init_clients()

    st.info("저장된 회원님의 투자 성향을 기반으로 맞춤형 주식 추천을 제공합니다.")

    if st.button("🚀 나만을 위한 주식 추천 받기", use_container_width=True):
        # 1. 사용자 정보 가져오기
        if "user" not in st.session_state or not hasattr(st.session_state.user, 'id'):
            st.error("로그인 정보가 없습니다. 로그인 후 다시 시도해주세요.")
            st.stop()
        
        user_id = st.session_state.user.id

        with st.spinner("회원님의 투자 성향을 불러오는 중..."):
            try:
                # 2. Supabase에서 투자 성향 조회
                # 여기에서 'user_context'는 투자 성향 정보가 담긴 컬럼명입니다. 실제 DB 스키마에 맞게 변경해야 할 수 있습니다.
                response = supabase.table('profiles').select('user_summary').eq('id', user_id).single().execute()
                
                if not response.data or 'user_summary' not in response.data or not response.data['user_summary']:
                    st.error("투자 성향 정보가 등록되지 않았습니다. 먼저 프로필을 설정해주세요.")
                    st.error(f"(Supabase `profiles_test` 테이블의 `id`={user_id} 행에 `user_summary` 값이 비어있습니다.)")
                    st.stop()
                
                user_query = response.data['user_summary']
                st.success("투자 성향 정보를 성공적으로 불러왔습니다.")

            except Exception as e:
                st.error(f"Supabase에서 데이터를 가져오는 중 오류가 발생했습니다: {e}")
                st.warning("Supabase에 `profiles_test` 테이블이 존재하는지, `user_context` 컬럼이 있는지 확인해주세요.")
                st.stop()

        with st.expander("나의 투자 성향 정보 보기"):
            st.write(user_query)

        # 3. RAG 파이프라인 실행
        with st.spinner("RAG 파이프라인을 통해 맞춤형 주식을 찾고 있습니다..."):
            try:
                st.write("**1단계: 투자 성향 벡터화 및 유사 종목 검색**")
                query_vector = embeddings.embed_query(user_query)
                retrieval_results = pinecone_index.query(vector=query_vector, top_k=10, include_metadata=True)
                candidate_stocks = [res['metadata'] for res in retrieval_results['matches']]
                st.success(f"{len(candidate_stocks)}개의 유사한 종목을 후보로 선택했습니다.")
                with st.expander("검색된 후보 종목 보기"):
                    st.json(candidate_stocks)

                st.write("**2단계: LLM을 통해 후보 종목 분석 및 최종 추천**")
                prompt_template = f"""
                당신은 최고의 금융 전문가입니다. 아래의 [사용자 투자 성향]과 [후보 주식 정보]를 바탕으로, 사용자에게 가장 적합한 주식 3개를 추천하고, 그 이유를 명확하고 이해하기 쉽게 한국어로 설명해주세요.

                [사용자 투자 성향]:
                {user_query}

                [후보 주식 정보]:
                {json.dumps(candidate_stocks, ensure_ascii=False, indent=2)}

                [출력 형식]:
                반드시 아래와 같은 JSON 배열 형식으로만 응답해주세요. 다른 설명은 절대 추가하지 마세요.
                [ 
                    {{"ticker": "종목 티커", "name": "종목명", "reason": "추천하는 이유 (2-3문장으로 상세히)"}},
                    {{"ticker": "종목 티커", "name": "종목명", "reason": "추천하는 이유 (2-3문장으로 상세히)"}},
                    {{"ticker": "종목 티커", "name": "종목명", "reason": "추천하는 이유 (2-3문장으로 상세히)"}}
                ]
                """
                
                llm_response = llm(prompt_template)
                final_recommendations = _extract_json_array(llm_response)

                if final_recommendations is None:
                    st.error("LLM의 응답에서 유효한 JSON을 찾지 못했습니다. 다시 시도해주세요.")
                    st.code(llm_response)
                    st.stop()

                _save_log(user_query, candidate_stocks, final_recommendations)
                st.success("최종 3개 종목 추천 완료!")

                st.subheader("✨ 당신만을 위한 맞춤 주식 추천 결과 ✨")
                for rec in final_recommendations:
                    with st.container(border=True):
                        st.markdown(f"#### {rec['name']} ({rec['ticker']})")
                        st.write(rec['reason'])
                        st.markdown(f"[Yahoo Finance에서 더 알아보기](https://finance.yahoo.com/quote/{rec['ticker']})")

            except Exception as e:
                st.error(f"추천 과정에서 오류가 발생했습니다: {e}")
