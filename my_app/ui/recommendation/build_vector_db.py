import os
import pandas as pd
import yfinance as yf
from pinecone import Pinecone, ServerlessSpec
from langchain_openai import OpenAIEmbeddings
from dotenv import load_dotenv
from tqdm import tqdm
import time

# --- 1. 초기 설정: 환경 변수 및 상수 정의 ---
print("[1/6] 🚀 초기 설정 시작...")

# .env 파일에서 환경 변수 로드
# 이 스크립트가 있는 위치 기준으로 상위 폴더의 .env 파일을 찾습니다.
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
    print("  - .env 파일 로드 성공")
else:
    print("  - .env 파일을 찾을 수 없습니다. 환경 변수가 직접 설정되었는지 확인합니다.")

# Pinecone 및 OpenAI API 키 설정
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not PINECONE_API_KEY or not OPENAI_API_KEY:
    raise ValueError("❌ API 키가 설정되지 않았습니다. .env 파일을 확인해주세요.")

# 상수 정의
PINECONE_INDEX_NAME = "sp500-rag-pipeline"
EMBEDDING_MODEL = "text-embedding-3-small"
# text-embedding-3-small 모델의 차원수는 1536 입니다.
EMBEDDING_DIMENSION = 1536
BATCH_SIZE = 100 # Pinecone에 한번에 업로드할 배치 크기

print("[1/6] ✅ 초기 설정 완료")

# --- 2. Pinecone 및 임베딩 모델 초기화 ---
print("\n[2/6] 🌲 Pinecone 및 임베딩 모델 초기화 시작...")

try:
    # Pinecone 클라이언트 초기화
    pc = Pinecone(api_key=PINECONE_API_KEY)
    print("  - Pinecone 클라이언트 초기화 성공")

    # Pinecone 인덱스 확인 및 생성
    if PINECONE_INDEX_NAME not in pc.list_indexes().names():
        print(f"  - '{PINECONE_INDEX_NAME}' 인덱스가 존재하지 않아 새로 생성합니다.")
        pc.create_index(
            name=PINECONE_INDEX_NAME,
            dimension=EMBEDDING_DIMENSION,
            metric="cosine", # 코사인 유사도 사용
            spec=ServerlessSpec(cloud="aws", region="us-east-1")
        )
        # 인덱스가 준비될 때까지 잠시 대기
        print("  - 인덱스 생성 중... 잠시 기다려주세요.")
        time.sleep(10)
    else:
        print(f"  - '{PINECONE_INDEX_NAME}' 인덱스가 이미 존재합니다.")

    pinecone_index = pc.Index(PINECONE_INDEX_NAME)
    print("  - Pinecone 인덱스 연결 성공")

    # LangChain의 OpenAI 임베딩 모델 초기화
    embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL, openai_api_key=OPENAI_API_KEY)
    print("  - OpenAI 임베딩 모델 초기화 성공")

except Exception as e:
    raise RuntimeError(f"❌ 초기화 중 오류 발생: {e}")

print("[2/6] ✅ Pinecone 및 임베딩 모델 초기화 완료")

# --- 3. S&P 500 종목 목록 로드 ---
print("\n[3/6] 📂 S&P 500 종목 목록 로드 시작...")

try:
    sp500_list_path = os.path.join(os.path.dirname(__file__), 'data_sp500', 'sp500_list.csv')
    sp500_df = pd.read_csv(sp500_list_path)
    tickers = sp500_df['Symbol'].tolist()
    print(f"  - 총 {len(tickers)}개의 Ticker를 로드했습니다.")
except Exception as e:
    raise FileNotFoundError(f"❌ S&P 500 목록 파일을 로드할 수 없습니다: {sp500_list_path}. 오류: {e}")

print("[3/6] ✅ S&P 500 종목 목록 로드 완료")

# --- 4. 데이터 수집 및 벡터화 준비 ---
print("\n[4/6] 📊 데이터 수집 및 벡터화 준비 시작...")

all_data_to_upsert = []
failed_tickers = []

# tqdm을 사용하여 진행 상황 시각화
for ticker in tqdm(tickers, desc="S&P 500 기업 정보 수집 중"):
    try:
        # yfinance를 통해 Ticker 정보 다운로드
        stock = yf.Ticker(ticker)
        info = stock.info

        # 필요한 정보 추출
        long_name = info.get('longName')
        long_summary = info.get('longBusinessSummary')

        # 기업 정보가 충분한지 확인
        if not long_name or not long_summary or len(long_summary) < 100:
            # print(f"  - ⚠️  '{ticker}': 정보가 부족하여 건너뜁니다.")
            failed_tickers.append((ticker, "정보 부족"))
            continue

        # Pinecone에 저장할 데이터 구성
        # id는 Ticker로 지정하여 중복 방지
        # text 필드에 임베딩할 원본 텍스트를 저장
        data = {
            'id': ticker,
            'metadata': {
                'ticker': ticker,
                'name': long_name,
                'text': long_summary
            }
        }
        all_data_to_upsert.append(data)

    except Exception as e:
        # print(f"  - ❌ '{ticker}': 데이터 수집 중 오류 발생 - {e}")
        failed_tickers.append((ticker, str(e)))
    
    # yfinance API 과부하 방지를 위한 약간의 딜레이
    time.sleep(0.1)

print(f"  - 총 {len(all_data_to_upsert)}개 기업의 정보 수집 완료.")
print(f"  - {len(failed_tickers)}개 기업 정보 수집 실패.")
if failed_tickers:
    print(f"  - 실패 Ticker: {[t[0] for t in failed_tickers[:5]]}...")

print("[4/6] ✅ 데이터 수집 및 벡터화 준비 완료")

# --- 5. 텍스트 임베딩 ---
print("\n[5/6] 🧠 텍스트 임베딩 시작...")

# 임베딩할 텍스트만 추출
texts_to_embed = [item['metadata']['text'] for item in all_data_to_upsert]

try:
    # 배치 단위로 텍스트 임베딩 실행
    embedded_vectors = embeddings.embed_documents(texts_to_embed, chunk_size=BATCH_SIZE)
    print(f"  - 총 {len(embedded_vectors)}개의 텍스트를 성공적으로 임베딩했습니다.")

    # 원본 데이터에 임베딩된 벡터 추가
    for i, item in enumerate(all_data_to_upsert):
        item['values'] = embedded_vectors[i]

except Exception as e:
    raise RuntimeError(f"❌ 텍스트 임베딩 중 오류 발생: {e}")

print("[5/6] ✅ 텍스트 임베딩 완료")

# --- 6. Pinecone에 데이터 업로드 (Upsert) ---
print("\n[6/6] ☁️ Pinecone에 데이터 업로드 시작...")

try:
    # 배치 단위로 나누어 업로드
    for i in tqdm(range(0, len(all_data_to_upsert), BATCH_SIZE), desc="Pinecone에 업로드 중"):
        batch = all_data_to_upsert[i:i + BATCH_SIZE]
        if batch:
            pinecone_index.upsert(vectors=batch)
    
    # 최종 인덱스 상태 확인
    index_stats = pinecone_index.describe_index_stats()
    print("  - 업로드 완료!")
    print(f"  - 최종 인덱스 상태: {index_stats}")

except Exception as e:
    raise RuntimeError(f"❌ Pinecone에 데이터 업로드 중 오류 발생: {e}")

print("[6/6] ✅ Pinecone에 데이터 업로드 완료")

print("\n🎉 모든 작업이 성공적으로 완료되었습니다! 이제 RAG 파이프라인을 사용할 준비가 되었습니다.")
