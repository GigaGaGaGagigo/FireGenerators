"""
B1 (벡터만 후보군) vs B2 (하이브리드 후보군) 비교 실험
level_strict=False 조건에서 후보군 수집 전략 비교
"""

import os
import sys
import time
import pandas as pd
from typing import Dict, List, Any, Tuple
import numpy as np
from pathlib import Path
import json
from datetime import datetime

# 경로 설정
current_file = Path(__file__).resolve()
ablation_study_dir = current_file.parent
eval_dir = ablation_study_dir.parent
contents_dir = eval_dir.parent
rec_dir = contents_dir / "recommendation"

# sys.path에 경로 추가
if str(rec_dir) not in sys.path:
    sys.path.insert(0, str(rec_dir))
if str(contents_dir) not in sys.path:
    sys.path.insert(0, str(contents_dir))

# 추천 시스템 모듈 import
try:
    from hybrid_recommender_v2 import (
        get_hybrid_recommendations,
        load_contents_from_supabase,
        normalize_card,
        DEFAULT_PARAMS,
        get_supabase_client
    )
    print("✅ 추천 시스템 모듈 import 성공")
except ImportError as e:
    print(f"⚠️ 추천 시스템 모듈 import 실패: {e}")
    print("📋 Mock 모드로 계속 진행...")
    
    # Mock functions for testing
    def get_hybrid_recommendations(*args, **kwargs):
        return {
            "success": True, 
            "results": [
                {"title": "Mock Content 1", "card_id": "mock1", "level": "Beginner", "tags": ["투자"]},
                {"title": "Mock Content 2", "card_id": "mock2", "level": "Intermediate", "tags": ["주식"]},
                {"title": "Mock Content 3", "card_id": "mock3", "level": "Advanced", "tags": ["펀드"]}
            ],
            "metadata": {"processing_time": 0.1, "total_candidates": 3, "final_recommendations": 3}
        }
    def load_contents_from_supabase():
        return [
            {"card_id": "mock1", "title": "Mock Content 1", "level": "Beginner", "tags": ["투자"]},
            {"card_id": "mock2", "title": "Mock Content 2", "level": "Intermediate", "tags": ["주식"]},
            {"card_id": "mock3", "title": "Mock Content 3", "level": "Advanced", "tags": ["펀드"]}
        ]
    def normalize_card(card):
        return card
    DEFAULT_PARAMS = {"top_n": 3, "level_strict": False}
    def get_supabase_client():
        return None

class CandidateCollectionComparator:
    """후보군 수집 전략 비교 실험 클래스"""
    
    def __init__(self):
        self.supabase = get_supabase_client()
        self.profiles_df = self.load_test_profiles()
        self.contents = load_contents_from_supabase()
        print(f"✅ 테스트 환경 준비 완료: 사용자 {len(self.profiles_df)}명, 콘텐츠 {len(self.contents)}개")
    
    def load_test_profiles(self) -> pd.DataFrame:
        """테스트용 사용자 프로필 로드"""
        try:
            response = self.supabase.table("profiles_test").select("*").execute()
            profiles_df = pd.DataFrame(response.data)
            print(f"✅ Supabase profiles_test에서 {len(profiles_df)}명 로드")
            return profiles_df
        except Exception as e:
            print(f"⚠️ Supabase 연결 실패, CSV 파일 사용: {e}")
            csv_path = ablation_study_dir / "profiles_test_rows.csv"
            if csv_path.exists():
                return pd.read_csv(csv_path)
            else:
                print("❌ 대체 CSV 파일도 없음")
                return pd.DataFrame()
    
    def create_vector_only_recommender(self, user_profile: Dict, **params) -> Dict:
        """B1: 벡터만 후보군 수집 추천"""
        start_time = time.time()
        
        try:
            # 기본 하이브리드 추천에서 벡터 검색 부분만 사용하도록 수정
            import sys
            from pathlib import Path
            rec_path = Path(__file__).parent.parent.parent / "recommendation"
            if str(rec_path) not in sys.path:
                sys.path.insert(0, str(rec_path))
            
            from vector_search import vector_candidates
            from context_builder import build_user_context_text
            
            # 사용자 컨텍스트 생성
            ctx_text = build_user_context_text(
                user_profile.get('user_summary', ''),
                user_profile.get('knowledge_summary', ''),
                user_profile.get('interest_tags', []),
                user_profile.get('emotions', 0)
            )
            
            # 레벨 호환 콘텐츠 필터링 (완화 모드)
            from hybrid_recommender_v2 import get_level_compatible_contents, multi_model_vector_search
            user_level = user_profile.get('investment_level', 'Beginner')
            level_filtered_cards = get_level_compatible_contents(
                self.contents, user_level, strict=False  # level_strict=False
            )
            
            # 벡터 검색만 수행
            vec_ids, vec_scores, model_sources = multi_model_vector_search(
                ctx_text,
                level_filtered_cards=level_filtered_cards,
                models=["ko-sroberta", "bge-m3"],
                k=params.get("k_vec", 10),
                sim_threshold=params.get("sim_threshold", 0.15)
            )
            
            # 벡터 후보만 사용 (룰 기반 후보 제외)
            vector_candidates = vec_ids[:params.get("top_n", 3)]
            
            # 결과 구성
            card_map = {c["card_id"]: c for c in self.contents}
            results = []
            for i, cid in enumerate(vector_candidates):
                card = card_map.get(cid)
                if card:
                    result_card = {
                        **card,
                        'recommendation_rank': i + 1,
                        'recommendation_source': 'vector_only',
                        'vector_score': vec_scores.get(cid, 0.0),
                        'vector_model': model_sources.get(cid, 'unknown')
                    }
                    results.append(result_card)
            
            processing_time = time.time() - start_time
            
            return {
                "success": True,
                "results": results,
                "metadata": {
                    "processing_time": processing_time,
                    "total_candidates": len(vec_ids),
                    "final_recommendations": len(results),
                    "candidate_collection_strategy": "vector_only",
                    "level_strict": False,
                    "parameters": params
                },
                "error": None
            }
            
        except Exception as e:
            return {
                "success": False,
                "results": [],
                "metadata": {"processing_time": time.time() - start_time},
                "error": str(e)
            }
    
    def create_hybrid_recommender(self, user_profile: Dict, **params) -> Dict:
        """B2: 하이브리드 후보군 수집 추천"""
        # 기존 하이브리드 추천 시스템 사용 (level_strict=False)
        enhanced_params = {
            **DEFAULT_PARAMS,
            "level_strict": False,  # 완화된 레벨 필터링
            **params
        }
        
        result = get_hybrid_recommendations(user_profile, **enhanced_params)
        
        if result.get("success") and "metadata" in result:
            # 메타데이터에 후보군 수집 전략 추가
            result["metadata"]["candidate_collection_strategy"] = "hybrid"
        
        return result
    
    def evaluate_single_user(self, user_profile: Dict, experiment_configs: List[Dict]) -> List[Dict]:
        """단일 사용자에 대한 실험 수행"""
        results = []
        
        for config in experiment_configs:
            strategy = config["candidate_collection_strategy"]
            params = config["params"]
            
            if strategy == "vector_only":
                result = self.create_vector_only_recommender(user_profile, **params)
            elif strategy == "hybrid":
                result = self.create_hybrid_recommender(user_profile, **params)
            else:
                continue
            
            # 성능 메트릭 계산
            metrics = self.calculate_metrics(result, user_profile)
            
            experiment_result = {
                "user_id": user_profile.get("id", "unknown"),
                "experiment_id": config["experiment_id"],
                "strategy": strategy,
                "success": result.get("success", False),
                "metrics": metrics,
                "result": result
            }
            
            results.append(experiment_result)
            print(f"  ✅ {config['experiment_id']}: {len(result.get('results', []))}개 추천")
        
        return results
    
    def calculate_metrics(self, result: Dict, user_profile: Dict) -> Dict:
        """성능 메트릭 계산"""
        if not result.get("success"):
            return {
                "recommendation_count": 0,
                "response_time": result.get("metadata", {}).get("processing_time", 0),
                "relevance_score": 0.0,
                "diversity_score": 0.0
            }
        
        recommendations = result.get("results", [])
        metadata = result.get("metadata", {})
        
        # 기본 메트릭
        recommendation_count = len(recommendations)
        response_time = metadata.get("processing_time", 0) * 1000  # ms 변환
        
        # 관련성 점수 (간단한 태그 매칭 기반)
        user_interests = set(user_profile.get("interests_categories", []))
        relevance_scores = []
        
        for rec in recommendations:
            rec_tags = set(rec.get("tags", []))
            if user_interests and rec_tags:
                overlap = len(user_interests.intersection(rec_tags))
                relevance = overlap / len(user_interests)
            else:
                relevance = 0.0
            relevance_scores.append(relevance)
        
        avg_relevance = np.mean(relevance_scores) if relevance_scores else 0.0
        
        # 다양성 점수 (추천된 콘텐츠의 레벨 다양성)
        levels = [rec.get("level", "Beginner") for rec in recommendations]
        unique_levels = len(set(levels))
        max_levels = 3  # Beginner, Intermediate, Advanced
        diversity_score = unique_levels / max_levels if levels else 0.0
        
        return {
            "recommendation_count": recommendation_count,
            "response_time": response_time,
            "relevance_score": avg_relevance,
            "diversity_score": diversity_score
        }
    
    def run_comparison_experiment(self, num_users: int = 10) -> Dict:
        """B1 vs B2 비교 실험 실행"""
        print(f"\n🚀 후보군 수집 전략 비교 실험 시작 (사용자 {num_users}명)")
        
        # 실험 설정
        experiment_configs = [
            {
                "experiment_id": "B1_vector_only_candidates",
                "candidate_collection_strategy": "vector_only",
                "params": {"top_n": 3, "k_vec": 10, "sim_threshold": 0.15}
            },
            {
                "experiment_id": "B2_hybrid_candidates", 
                "candidate_collection_strategy": "hybrid",
                "params": {"top_n": 3, "k_vec": 10, "k_rule": 10}
            }
        ]
        
        # 사용자 샘플링
        test_users = self.profiles_df.head(num_users).to_dict('records')
        
        # 실험 실행
        all_results = []
        start_time = time.time()
        
        for i, user in enumerate(test_users, 1):
            print(f"\n👤 사용자 {i}/{num_users} 테스트 중...")
            user_results = self.evaluate_single_user(user, experiment_configs)
            all_results.extend(user_results)
        
        total_time = time.time() - start_time
        
        # 결과 분석
        analysis = self.analyze_results(all_results)
        
        # 최종 리포트
        final_report = {
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "total_time_seconds": total_time,
                "total_users": num_users,
                "total_experiments": len(experiment_configs),
                "total_cases": len(all_results),
                "successful_cases": sum(1 for r in all_results if r["success"])
            },
            "experiment_results": analysis,
            "raw_results": all_results
        }
        
        # 결과 저장
        self.save_results(final_report)
        
        return final_report
    
    def analyze_results(self, all_results: List[Dict]) -> Dict:
        """결과 분석 및 통계 계산"""
        analysis = {}
        
        # 전략별 그룹화
        strategies = {}
        for result in all_results:
            strategy = result["strategy"]
            if strategy not in strategies:
                strategies[strategy] = []
            strategies[strategy].append(result)
        
        # 각 전략별 통계 계산
        for strategy, results in strategies.items():
            successful_results = [r for r in results if r["success"]]
            
            if successful_results:
                metrics_list = [r["metrics"] for r in successful_results]
                
                analysis[strategy] = {
                    "total_cases": len(results),
                    "successful_cases": len(successful_results),
                    "success_rate": len(successful_results) / len(results) * 100,
                    "avg_recommendations": np.mean([m["recommendation_count"] for m in metrics_list]),
                    "std_recommendations": np.std([m["recommendation_count"] for m in metrics_list]),
                    "avg_response_time": np.mean([m["response_time"] for m in metrics_list]),
                    "std_response_time": np.std([m["response_time"] for m in metrics_list]),
                    "avg_relevance": np.mean([m["relevance_score"] for m in metrics_list]),
                    "std_relevance": np.std([m["relevance_score"] for m in metrics_list]),
                    "avg_diversity": np.mean([m["diversity_score"] for m in metrics_list]),
                    "std_diversity": np.std([m["diversity_score"] for m in metrics_list])
                }
            else:
                analysis[strategy] = {
                    "total_cases": len(results),
                    "successful_cases": 0,
                    "success_rate": 0,
                    "error": "No successful cases"
                }
        
        return analysis
    
    def save_results(self, report: Dict):
        """결과 저장"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # JSON 리포트 저장
        report_path = ablation_study_dir / f"candidate_collection_report_{timestamp}.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        # CSV 요약 저장
        summary_data = []
        for strategy, stats in report["experiment_results"].items():
            if "error" not in stats:
                summary_data.append({
                    "전략": strategy,
                    "성공률": f"{stats['success_rate']:.1f}%",
                    "평균_추천수": f"{stats['avg_recommendations']:.1f}",
                    "평균_응답시간": f"{stats['avg_response_time']:.1f}ms",
                    "평균_관련성": f"{stats['avg_relevance']:.3f}",
                    "평균_다양성": f"{stats['avg_diversity']:.3f}"
                })
        
        summary_df = pd.DataFrame(summary_data)
        csv_path = ablation_study_dir / f"candidate_collection_summary_{timestamp}.csv"
        summary_df.to_csv(csv_path, index=False, encoding='utf-8-sig')
        
        print(f"\n📊 결과 저장 완료:")
        print(f"  - 상세 리포트: {report_path}")
        print(f"  - 요약 CSV: {csv_path}")

def main():
    """메인 실행 함수"""
    print("🔍 B1 (벡터만) vs B2 (하이브리드) 후보군 수집 비교 실험")
    
    comparator = CandidateCollectionComparator()
    
    # 실험 실행 (10명 사용자 대상)
    report = comparator.run_comparison_experiment(num_users=10)
    
    # 결과 요약 출력
    print("\n🏆 실험 결과 요약:")
    for strategy, stats in report["experiment_results"].items():
        if "error" not in stats:
            print(f"\n📈 {strategy}:")
            print(f"  - 평균 추천수: {stats['avg_recommendations']:.1f}개")
            print(f"  - 평균 응답시간: {stats['avg_response_time']:.1f}ms")
            print(f"  - 평균 관련성: {stats['avg_relevance']:.3f}")
            print(f"  - 평균 다양성: {stats['avg_diversity']:.3f}")
    
    return report

if __name__ == "__main__":
    main()