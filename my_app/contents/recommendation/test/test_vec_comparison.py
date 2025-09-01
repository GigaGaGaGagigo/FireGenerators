"""
4개 임베딩 모델 성능 비교 테스트 스크립트
- ko-sroberta, sentence, upstage, bge-m3
"""

from vector_search import vector_candidates
import json
import os
import time
from typing import Dict, List

# ========================================
# 1. 설정 및 초기화
# ========================================

# 비교할 모델 리스트
MODELS_TO_TEST = [
    ("ko-sroberta", "한국어 특화 모델"),
    ("sentence", "다중언어 MiniLM"),
    ("upstage", "Upstage API"),
    ("bge-m3", "BGE-M3 다중언어")
]

# 유사도 임계값 설정
SIM_THRESHOLD = 0.15
TOP_K = 5

current_dir = os.path.dirname(os.path.abspath(__file__))

def load_content_meta(model_key: str) -> List[Dict]:
    """모델별 콘텐츠 메타데이터 로드"""
    try:
        index_dir = os.path.join(current_dir, "index", model_key)
        meta_file = os.path.join(index_dir, "content_meta.json")
        
        if not os.path.exists(meta_file):
            print(f"❌ {model_key} 모델의 메타데이터 파일이 없습니다: {meta_file}")
            return []
            
        with open(meta_file, "r", encoding="utf-8") as f:
            contents = json.load(f)
        return contents
    except Exception as e:
        print(f"❌ {model_key} 메타데이터 로드 실패: {e}")
        return []

def check_model_availability() -> List[tuple]:
    """사용 가능한 모델 확인"""
    available_models = []
    
    print("🔍 모델 가용성 확인 중...")
    for model_key, model_desc in MODELS_TO_TEST:
        contents = load_content_meta(model_key)
        if contents:
            print(f"✅ {model_key} ({model_desc}) - {len(contents)}개 콘텐츠")
            available_models.append((model_key, model_desc))
        else:
            print(f"❌ {model_key} ({model_desc}) - 사용 불가")
    
    return available_models

# ========================================
# 2. 검색 및 비교 함수
# ========================================

def search_with_model(query: str, model_key: str) -> List[Dict]:
    """특정 모델로 벡터 검색 수행"""
    try:
        start_time = time.time()
        results = vector_candidates(query, k=TOP_K, model_key=model_key)
        search_time = time.time() - start_time
        
        # 결과에 검색 시간 추가
        for result in results:
            result['search_time'] = search_time
            
        return results
    except Exception as e:
        print(f"❌ {model_key} 검색 실패: {e}")
        return []

def compare_models(query: str, available_models: List[tuple]) -> Dict:
    """모든 모델로 검색하고 결과 비교"""
    print(f"\n🔍 검색 쿼리: '{query}'")
    print("=" * 80)
    
    comparison_results = {}
    
    for model_key, model_desc in available_models:
        print(f"\n📊 [{model_key}] {model_desc} 검색 중...")
        
        results = search_with_model(query, model_key)
        filtered_results = [r for r in results if r['score'] >= SIM_THRESHOLD]
        
        comparison_results[model_key] = {
            'model_desc': model_desc,
            'raw_results': results,
            'filtered_results': filtered_results,
            'search_time': results[0]['search_time'] if results else 0,
            'total_found': len(results),
            'above_threshold': len(filtered_results)
        }
        
        # 간단한 결과 요약 출력
        if filtered_results:
            print(f"   ✅ {len(filtered_results)}개 결과 (임계값 {SIM_THRESHOLD} 이상)")
            print(f"   ⚡ 검색 시간: {results[0]['search_time']:.3f}초")
            print(f"   🏆 최고 점수: {max(r['score'] for r in results):.4f}")
        else:
            print(f"   ❌ 임계값 이상 결과 없음 (최고 점수: {max(r['score'] for r in results):.4f})")
    
    return comparison_results

def display_detailed_results(comparison_results: Dict, available_models: List[tuple]):
    """상세 결과 표시"""
    print("\n" + "=" * 85)
    print("📋 상세 비교 결과")
    print("=" * 85)
    
    # 성능 요약 테이블
    print("\n📊 성능 비교 표")
    print("-" * 80)
    print(f"{'모델명':<15} | {'시간(초)':<8} | {'총결과':<6} | {'유효결과':<8} | {'최고점수':<10}")
    print("-" * 80)
    
    for model_key, model_desc in available_models:
        if model_key in comparison_results:
            data = comparison_results[model_key]
            max_score = max(r['score'] for r in data['raw_results']) if data['raw_results'] else 0
            print(f"{model_key:<15} | {data['search_time']:<8.3f} | {data['total_found']:<6} | {data['above_threshold']:<8} | {max_score:<10.4f}")
    
    print("-" * 80)
    
    # 각 모델별 상위 결과 표시
    for model_key, model_desc in available_models:
        if model_key not in comparison_results:
            continue
            
        data = comparison_results[model_key]
        print(f"\n🔍 [{model_key}] {model_desc} - 상위 결과")
        print("-" * 50)
        
        if data['filtered_results']:
            for i, result in enumerate(data['filtered_results'][:3], 1):  # 상위 3개만
                print(f"{i}. 점수: {result['score']:.4f}")
                print(f"   제목: {result.get('title', 'Unknown')}")
                print(f"   태그: {result.get('tags', [])}")
                print(f"   내용: {result.get('content', '')[:100]}...")
                print()
        else:
            print("   임계값 이상 결과 없음")
            if data['raw_results']:
                best = data['raw_results'][0]
                print(f"   (최고 점수: {best['score']:.4f} - {best.get('title', 'Unknown')})")

def display_ranking_comparison(comparison_results: Dict):
    """모델별 순위 비교"""
    print("\n" + "=" * 80)
    print("🏆 모델 성능 랭킹")
    print("=" * 80)
    
    # 유효 결과 개수 기준 랭킹
    valid_results_ranking = []
    for model_key, data in comparison_results.items():
        valid_results_ranking.append((model_key, data['above_threshold'], data['model_desc']))
    
    valid_results_ranking.sort(key=lambda x: x[1], reverse=True)
    
    print("\n📊 유효 결과 개수 랭킹:")
    for i, (model_key, count, desc) in enumerate(valid_results_ranking, 1):
        print(f"{i}. {model_key} ({desc}): {count}개")
    
    # 최고 점수 기준 랭킹
    max_score_ranking = []
    for model_key, data in comparison_results.items():
        if data['raw_results']:
            max_score = max(r['score'] for r in data['raw_results'])
            max_score_ranking.append((model_key, max_score, data['model_desc']))
    
    max_score_ranking.sort(key=lambda x: x[1], reverse=True)
    
    print("\n🎯 최고 유사도 점수 랭킹:")
    for i, (model_key, score, desc) in enumerate(max_score_ranking, 1):
        print(f"{i}. {model_key} ({desc}): {score:.4f}")
    
    # 검색 속도 랭킹
    speed_ranking = []
    for model_key, data in comparison_results.items():
        speed_ranking.append((model_key, data['search_time'], data['model_desc']))
    
    speed_ranking.sort(key=lambda x: x[1])
    
    print("\n⚡ 검색 속도 랭킹:")
    for i, (model_key, time_sec, desc) in enumerate(speed_ranking, 1):
        print(f"{i}. {model_key} ({desc}): {time_sec:.3f}초")

# ========================================
# 3. 메인 실행 함수
# ========================================

def main():
    print("🚀 임베딩 모델 성능 비교 테스트")
    print("=" * 50)
    
    # 사용 가능한 모델 확인
    available_models = check_model_availability()
    
    if not available_models:
        print("❌ 사용 가능한 모델이 없습니다. 먼저 임베딩 인덱스를 생성해주세요.")
        return
    
    print(f"\n✅ {len(available_models)}개 모델 준비 완료")
    print(f"📊 설정: 상위 {TOP_K}개 검색, 유사도 임계값 {SIM_THRESHOLD}")
    
    while True:
        # 사용자 입력
        print("\n" + "=" * 50)
        query = input("🔍 검색할 텍스트를 입력하세요 (종료: quit): ").strip()
        
        if query.lower() in ['quit', 'exit', 'q']:
            print("👋 테스트를 종료합니다.")
            break
            
        if not query:
            print("❌ 검색어를 입력해주세요.")
            continue
        
        # 모든 모델로 검색 및 비교
        comparison_results = compare_models(query, available_models)
        
        # 상세 결과 표시
        display_detailed_results(comparison_results, available_models)
        
        # 랭킹 비교
        display_ranking_comparison(comparison_results)
        
        # 계속할지 확인
        continue_test = input("\n다른 검색어로 테스트하시겠습니까? (y/n, 기본 y): ").strip().lower()
        if continue_test in ['n', 'no']:
            break

if __name__ == "__main__":
    main()