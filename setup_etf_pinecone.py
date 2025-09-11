import os
import json
from dotenv import load_dotenv
from pinecone import Pinecone
from langchain_openai import OpenAIEmbeddings
from tqdm.auto import tqdm
import time
import yfinance as yf

def upload_data_to_existing_index():
    """기존 'rag-etf' 인덱스에 데이터를 업로드합니다."""
    
    print("--- 기존 Pinecone 인덱스에 데이터 업로드 시작 ---")
    
    # 1. 환경 변수 로드
    print("1. 환경 변수 로드 중...")
    load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
    pinecone_api_key = os.getenv("PINECONE_API_KEY")
    openai_api_key = os.getenv("OPENAI_API_KEY")

    if not pinecone_api_key or not openai_api_key:
        print("오류: PINECONE_API_KEY 또는 OPENAI_API_KEY를 .env 파일에서 찾을 수 없습니다.")
        return

    # 2. 확장된 ETF 티커 목록
    etf_tickers = ['VOO', 'IVV', 'SPY', 'VTI', 'QQQ', 'VUG', 'VEA', 'IEFA', 'VTV', 'BND', 'AGG', 'IWF', 'GLD', 'VXUS', 'IEMG', 'VGT', 'IJH', 'VWO', 'VIG', 'VO', 'VB', 'BNDX', 'EFA', 'XLK', 'SCHD', 'QQQM', 'ITOT', 'IVW', 'IWD', 'VYM', 'XLY', 'XLF', 'XLP', 'XLE', 'XLV', 'XLI', 'IAU', 'VT', 'SCHF', 'VEU', 'SDY', 'RSP']
    print(f"- {len(etf_tickers)}개의 ETF에 대한 데이터 수집을 시작합니다.")

    # 3. 클라이언트 초기화 및 인덱스 연결
    print("3. Pinecone 및 OpenAI 클라이언트 초기화 중...")
    pc = Pinecone(api_key=pinecone_api_key)
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small", openai_api_key=openai_api_key)
    
    index_name = "rag-etf"
    if index_name not in pc.list_indexes().names():
        print(f"오류: '{index_name}' 인덱스를 찾을 수 없습니다. Pinecone에서 인덱스가 삭제되었는지 확인해주세요.")
        return
    index = pc.Index(index_name)
    
    # 4. 데이터 수집, 임베딩 및 업로드
    print("4. yfinance에서 데이터 수집 및 Pinecone 업로드 시작...")
    batch_size = 50
    
    etf_data_to_upsert = []
    for ticker_symbol in tqdm(etf_tickers, desc="Fetching data from yfinance"):
        try:
            ticker = yf.Ticker(ticker_symbol)
            info = ticker.info
            if info.get('longBusinessSummary'):
                etf_data_to_upsert.append(info)
        except Exception:
            print(f"Warning: Could not fetch data for {ticker_symbol}")
            pass # 오류 발생 시 건너뛰기
        time.sleep(1) # 1초 지연 추가

    print(f"- {len(etf_data_to_upsert)}개의 유효한 ETF 데이터를 수집했습니다. 이제 임베딩 및 업로드를 진행합니다.")

    for i in tqdm(range(0, len(etf_data_to_upsert), batch_size), desc="Embedding and Upserting to Pinecone"):
        batch = etf_data_to_upsert[i:i+batch_size]
        ids = [item['symbol'] for item in batch]
        texts = [item['longBusinessSummary'] for item in batch]
        
        metadata = []
        for item in batch:
            meta = {
                'longName': str(item.get('longName', '')),
                'fundFamily': str(item.get('fundFamily', '')),
                'category': str(item.get('category', '')),
                'totalAssets': float(item.get('totalAssets', 0) or 0),
                'expenseRatio': float(item.get('expenseRatio', 0) or 0),
                'yahoo_url': f"https://finance.yahoo.com/quote/{item.get('symbol')}",
                'text': str(item.get('longBusinessSummary', ''))
            }
            metadata.append(meta)

        embeds = embeddings.embed_documents(texts)
        index.upsert(vectors=zip(ids, embeds, metadata))
        
    print(f"--- {len(etf_data_to_upsert)}개 데이터 업로드 완료 ---")
    print("--- 최종 인덱스 정보 ---")
    print(index.describe_index_stats())

if __name__ == "__main__":
    upload_data_to_existing_index()