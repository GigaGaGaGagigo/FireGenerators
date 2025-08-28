# RAG 주식 추천 시스템 구현 가이드

이 문서는 피드백 받은 S&P 500 기반 RAG(Retrieval-Augmented Generation) 주식 추천 파이프라인을 현재 프로젝트에 구현하는 방법을 안내합니다.

## 1. 구현 가능성 검토

**결론: 현재 프로젝트 구조에서 충분히 구현 가능합니다.**

-   **Streamlit 기반**: `app.py`를 중심으로 한 현재 구조는 새로운 추천 페이지를 통합하기에 적합합니다.
-   **API 키 관리**: `my_app/.streamlit/secrets.toml` 파일에 OpenAI API 키가 이미 설정되어 있어, Pinecone 키만 추가하면 됩니다.
-   **외부 라이브러리 사용**: `stocks_held_gpt.py`에서 `yfinance`, `openai` 등을 이미 사용하고 있어, `langchain`, `pinecone-client` 등을 추가하는 것은 간단합니다.

## 2. 사전 준비: 라이브러리 및 API 키 설정

### 단계 1: 필수 라이브러리 설치

터미널을 열고 프로젝트 폴더(`FireGenerators`)에서 아래 명령어를 실행하여 필요한 라이브러리를 설치합니다.

```bash
pip install langchain langchain_openai langchain_pinecone pinecone-client yfinance pandas "tiktoken<0.7.0"
```
> `tiktoken` 버전을 명시하는 것은 LangChain과의 호환성 문제를 예방하기 위함입니다.

### 단계 2: Pinecone API 키 발급 및 설정

1.  [Pinecone 웹사이트](https://www.pinecone.io/)에 가입하고 로그인합니다.
2.  로그인 후 왼쪽 메뉴에서 **API Keys**로 이동하여 `API Key`와 `Environment` 값을 복사합니다.
3.  `my_app/.streamlit/secrets.toml` 파일을 열고, 복사한 키를 아래와 같이 추가합니다.

    ```toml
    # my_app/.streamlit/secrets.toml

    # ... 기존 supabase, OPENAI_API_KEY 등 ...

    # Pinecone Vector DB 정보
    [pinecone]
    api_key = "YOUR_PINECONE_API_KEY"
    environment = "YOUR_PINECONE_ENVIRONMENT"
    ```

## 3. RAG 파이프라인 구현 (코드 예시)

이제 "맞춤형 상품 추천" 페이지를 담당할 파일을 수정합니다. 이전에 `rec/recommendation.py` 경로를 사용하기로 했으므로, 해당 파일을 아래 내용으로 채우거나 새로 생성합니다.

-   **파일 경로**: `/Users/min/Desktop/FireGenerators/rec/recommendation.py`

아래 코드는 RAG 파이프라인의 전체 흐름을 담고 있으며, 실제 데이터 수집 및 DB 구축 부분은 비용과 시간이 발생하므로 **샘플 데이터로 시뮬레이션**하는 형태로 작성되었습니다.

```python
# filepath: /Users/min/Desktop/FireGenerators/rec/recommendation.py

import streamlit as st
import pandas as pd
import os
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_pinecone import PineconeVectorStore
from langchain.prompts import PromptTemplate
from langchain.schema.runnable import RunnablePassthrough
from langchain.schema.output_parser import StrOutputParser

# --- 1. 초기 설정 및 환경 변수 로드 ---

# Streamlit secrets에서 API 키 로드
try:
    PINECONE_API_KEY = st.secrets["pinecone"]["api_key"]
    PINECONE_ENVIRONMENT = st.secrets["pinecone"]["environment"]
    OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
    
    # LangChain에서 사용할 수 있도록 환경변수 설정
    os.environ["PINECONE_API_KEY"] = PINECONE_API_KEY
    os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

except KeyError as e:
    st.error(f"필수 API 키가 secrets.toml 파일에 없습니다: {e}")
    st.stop()

# Pinecone 인덱스 이름 (원하는 이름으로 변경 가능)
INDEX_NAME = "sp500-stock-recommendations"

# --- 2. RAG 파이프라인의 핵심 함수들 ---

@st.cache_resource
def get_vectorstore():
    """ Pinecone VectorStore 객체를 초기화하고 반환합니다. """
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    try:
        vectorstore = PineconeVectorStore.from_existing_index(
            index_name=INDEX_NAME, 
            embedding=embeddings
        )
        return vectorstore
    except Exception as e:
        # 실제 운영 시에는 여기서 인덱스가 없으면 생성하는 로직을 추가해야 합니다.
        st.error(f"Pinecone 인덱스 '{INDEX_NAME}'에 연결할 수 없습니다. Pinecone에서 인덱스를 먼저 생성해주세요. 오류: {e}")
        st.info("이 데모에서는 Pinecone 연결 없이 가상 데이터를 사용합니다.")
        return None # 데모용으로 None 반환

def format_docs(docs):
    """ 검색된 문서(주식 정보)를 LLM 프롬프트에 맞게 포맷팅합니다. """
    return "\n\n".join(
        f"Ticker: {doc.metadata.get('ticker', 'N/A')}\n"
        f"Name: {doc.metadata.get('name', 'N/A')}\n"
        f"Sector: {doc.metadata.get('sector', 'N/A')}\n"
        f"Summary: {doc.page_content}"
        for doc in docs
    )

# --- 3. Streamlit UI 렌더링 ---

def render():
    st.title("📈 AI 기반 S&P 500 종목 추천")
    st.write("LangChain과 RAG 파이프라인을 사용하여 개인의 투자 성향에 맞는 주식을 추천합니다.")

    # --- 사용자 컨텍스트 입력 ---
    st.subheader("1. 투자 프로필 입력")
    user_context = st.text_area(
        "자신의 투자 성향, 선호하는 산업, 투자 기간 등을 자유롭게 작성해주세요.",
        # 사용자 컨텍스트 예시
        "저는 기술주 중심의 성장을 추구하는 30대 투자자입니다. 변동성이 크더라도 장기적인 관점에서 높은 수익률을 기대하며, 특히 인공지능(AI) 및 클라우드 컴퓨팅 분야에 관심이 많습니다. 안정적인 배당주보다는 혁신적인 기술을 가진 기업에 투자하고 싶습니다.",
        height=150
    )

    if st.button("🚀 추천 받기"):
        if not user_context:
            st.warning("투자 프로필을 입력해주세요.")
            st.stop()

        with st.spinner("AI가 맞춤형 종목을 분석하고 있습니다..."):
            vectorstore = get_vectorstore()

            # --- RAG 파이프라인 실행 ---
            if vectorstore:
                # 1. Retrieval: Pinecone에서 사용자 컨텍스트와 유사한 주식 검색
                retriever = vectorstore.as_retriever(search_kwargs={'k': 10})
                
                # 2. Augment & 3. Generation: LLM을 통해 최종 추천 생성
                template = """
                당신은 전문 주식 애널리스트입니다. 사용자의 투자 프로필과 아래의 주식 후보군 정보를 바탕으로, 가장 적합한 주식 3개를 추천하고 그 이유를 상세히 설명해주세요.

                [사용자 투자 프로필]
                {context}

                [주식 후보군 정보]
                {question}

                [답변 형식]
                - 추천 종목 1: [종목명 (Ticker)]
                  - 추천 이유: (사용자 프로필과 연관 지어 구체적으로 설명)
                - 추천 종목 2: [종목명 (Ticker)]
                  - 추천 이유: (사용자 프로필과 연관 지어 구체적으로 설명)
                - 추천 종목 3: [종목명 (Ticker)]
                  - 추천 이유: (사용자 프로필과 연관 지어 구체적으로 설명)
                """
                prompt = PromptTemplate.from_template(template)
                
                llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0)

                rag_chain = (
                    {"context": RunnablePassthrough(), "question": retriever | format_docs}
                    | prompt
                    | llm
                    | StrOutputParser()
                )

                # 체인 실행
                result = rag_chain.invoke(user_context)

            else:
                # Pinecone 연결 실패 시, 가상 결과 출력
                st.warning("Pinecone DB에 연결되지 않아 가상 추천 결과를 표시합니다.")
                result = """
- 추천 종목 1: Microsoft (MSFT)
  - 추천 이유: 사용자는 AI 및 클라우드 컴퓨팅 분야에 관심이 많습니다. Microsoft는 Azure 클라우드 서비스와 OpenAI와의 파트너십을 통해 이 두 분야에서 강력한 리더십을 보여주고 있어 장기 성장 가능성이 매우 높습니다.

- 추천 종목 2: NVIDIA (NVDA)
  - 추천 이유: AI 기술의 핵심인 GPU 시장을 독점하고 있어, 사용자의 '혁신적인 기술 기업' 선호도와 정확히 일치합니다. 높은 변동성을 감수하고 높은 수익을 추구하는 성향에 적합합니다.

- 추천 종목 3: Alphabet (GOOGL)
  - 추천 이유: Google Cloud Platform(GCP)을 통해 클라우드 시장에서 꾸준히 성장하고 있으며, DeepMind를 통해 AI 연구 분야에서도 선두를 달리고 있습니다. 기술주 중심의 포트폴리오에 안정성과 성장성을 더해줄 수 있는 훌륭한 선택입니다.
                """

            st.subheader("✨ AI 추천 결과")
            st.markdown(result)

# --- 데이터베이스 구축을 위한 가이드 (별도 실행 필요) ---
def build_vector_db_guide():
    st.info(
        """
        **개발자 안내:** 이 시스템이 실제로 동작하려면 Pinecone에 벡터 데이터베이스를 구축해야 합니다.
        아래는 데이터베이스를 구축하는 스크립트의 예시입니다. 이 코드는 별도의 Python 파일로 만들어 **한 번만 실행**하면 됩니다.
        
        ```python
        # build_db.py (예시)
        import streamlit as st
        import pandas as pd
        from langchain_openai import OpenAIEmbeddings
        from langchain_pinecone import PineconeVectorStore
        from langchain.docstore.document import Document
        
        # S&P 500 목록 가져오기 (예시: 위키피디아)
        # 실제로는 yfinance 등을 사용해 더 정확한 정보를 가져와야 합니다.
        sp500_url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        sp500_df = pd.read_html(sp500_url)[0]
        
        # Document 객체로 변환
        documents = []
        for _, row in sp500_df.head(50).iterrows(): # 시간/비용 문제로 50개만 샘플링
            content = f"Company: {row['Security']}, Sector: {row['GICS Sector']}. Info: {row['GICS Sub-Industry']}"
            doc = Document(
                page_content=content,
                metadata={
                    'ticker': row['Symbol'],
                    'name': row['Security'],
                    'sector': row['GICS Sector']
                }
            )
            documents.append(doc)
        
        # 임베딩 및 Pinecone에 저장
        embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        index_name = "sp500-stock-recommendations"
        
        # Pinecone에 문서 업로드 (인덱스가 없으면 새로 생성)
        vectorstore = PineconeVectorStore.from_documents(
            documents, 
            embedding=embeddings, 
            index_name=index_name
        )
        print(f"'{index_name}' 인덱스에 {len(documents)}개의 문서를 성공적으로 업로드했습니다.")
        ```
        """
    )

if __name__ == "__main__":
    render()
    build_vector_db_guide()
```

## 4. 다음 단계 및 고려사항

1.  **Vector DB 구축**: 위 코드의 `build_vector_db_guide()` 섹션에 설명된 것처럼, `build_db.py`와 같은 별도 스크립트를 만들어 **단 한 번 실행**하여 Pinecone에 실제 주식 데이터를 저장해야 합니다. (OpenAI 임베딩 API와 Pinecone 사용에 비용이 발생할 수 있습니다.)
2.  **데이터 품질 향상**: `build_db.py` 예시에서는 위키피디아의 간단한 정보만 사용했습니다. 실제 시스템에서는 `yfinance`로 기업 정보(summary)를 가져오고, 뉴스 API로 최신 이슈를 수집 및 요약하여 `page_content`를 더 풍부하게 만들어야 합니다.
3.  **사용자 프로필 연동**: 현재는 사용자가 직접 투자 성향을 입력하지만, Supabase에 저장된 사용자 프로필(`st.session_state.profile`)을 가져와 기본값으로 채워주는 기능을 추가하면 더 편리한 서비스를 제공할 수 있습니다.
4.  **에러 처리 및 UI/UX**: 실제 서비스에서는 API 호출 실패, 타임아웃 등 다양한 예외 상황에 대한 처리를 강화하고, 사용자에게 진행 상황을 더 친절하게 안내하는 UI/UX 개선이 필요합니다.

이 가이드를 따라 "맞춤형 상품 추천" 페이지를 고도화된 RAG 시스템으로 성공적으로 전환하시길 바랍니다.
