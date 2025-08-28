import os
import streamlit as st
import re
import datetime
from pinecone import Pinecone
from langchain_openai import OpenAIEmbeddings, OpenAI
from dotenv import load_dotenv
import json

@st.cache_resource
def init_clients():
    """API 클라이언트를 초기화하고 캐시합니다."""
    dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', '.env')
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path)
    
    if not os.getenv("PINECONE_API_KEY") or not os.getenv("OPENAI_API_KEY"):
        st.error("API 키가 설정되지 않았습니다. .env 파일을 확인해주세요.")
        st.stop()

    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small", openai_api_key=os.getenv("OPENAI_API_KEY"))
    llm = OpenAI(temperature=0, openai_api_key=os.getenv("OPENAI_API_KEY"), model_name="gpt-4o-mini")
    
    index_name = "sp500-rag-pipeline"
    if index_name not in pc.list_indexes().names():
        st.error(f"Pinecone 인덱스 '{index_name}'을 찾을 수 없습니다. 먼저 build_vector_db.py를 실행해주세요.")
        st.stop()
    pinecone_index = pc.Index(index_name)
    
    return pinecone_index, embeddings, llm

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

    pinecone_index, embeddings, llm = init_clients()

    st.info("💡 아래 텍스트 상자에 투자 성향, 목표, 관심 분야 등을 자유롭게 입력하고 추천 버튼을 누르세요.")

    user_context_example = "저는 20대 사회초년생으로, 기술 분야의 장기적인 성장에 투자하고 싶습니다. 어느 정도의 위험은 감수할 수 있으며, 혁신적인 기술을 가진 기업에 관심이 많습니다."
    user_query = st.text_area("**투자 성향을 입력하세요:**", value=user_context_example, height=150)

    if st.button("🚀 나만을 위한 주식 추천 받기", use_container_width=True):
        if not user_query.strip():
            st.warning("투자 성향을 입력해주세요.")
        else:
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

                    # 로그 저장
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
