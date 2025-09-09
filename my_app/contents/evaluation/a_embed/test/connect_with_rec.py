import os
import sys
import time
import pandas as pd
from typing import Dict, List, Any, Tuple
import numpy as np
from pathlib import Path
import json

# 추천 시스템 모듈 import 및 경로 설정
current_file = Path(__file__).resolve()
ablation_study_dir = current_file.parent  # ablation_study/
eval_dir = ablation_study_dir.parent  # evaluation/
contents_dir = eval_dir.parent  # contents/
rec_dir = contents_dir / "recommendation"  # contents/recommendation/

# sys.path에 경로 추가
if str(rec_dir) not in sys.path:
    sys.path.insert(0, str(rec_dir))
if str(contents_dir) not in sys.path:
    sys.path.insert(0, str(contents_dir))

# 실제 모듈 import
try:
    from data_access import load_all_cards
    from vector_search import vector_candidates
    from hybrid_recommender_v2 import (
        get_hybrid_recommendations, 
        load_contents_from_supabase,
        normalize_card,
        DEFAULT_PARAMS
    )
    print("✅ 추천 시스템 모듈 import 성공")
except ImportError as e:
    print(f"⚠️ 추천 시스템 모듈 import 실패: {e}")
    # 대안 로직
    def load_all_cards(*args, **kwargs):
        return []
    def vector_candidates(*args, **kwargs):
        return []
    def get_hybrid_recommendations(*args, **kwargs):
        return {"success": False, "results": [], "error": "Module not available"}
    def load_contents_from_supabase():
        return []
    def normalize_card(card):
        return card
    DEFAULT_PARAMS = {"top_n": 3}

class RecommendationSystemEvaluator:
    """
    기존 추천 시스템과 Ablation Study 연동 클래스
    """
    def __init__(self, profiles_csv_path: str = None):
        self.base_dir = Path(__file__).parent
        self.recommendation_dir = contents_dir / "recommendation"
        
        # 프로필 데이터 로드
        if profiles_csv_path:
            self.profiles_df = pd.read_csv(profiles_csv_path)
        else:
            # profiles_test DB에서 직접 로드
            try:
                from hybrid_recommender_v2 import get_supabase_client
                supabase = get_supabase_client()
                response = supabase.table("profiles_test").select("*").execute()
                self.profiles_df = pd.DataFrame(response.data)
                print(f"📚 profiles_test DB에서 로드: {len(self.profiles_df)}명")
            except Exception as e:
                print(f"⚠️ profiles_test DB 로드 실패: {e}, CSV 파일 사용")
                self.profiles_df = pd.read_csv(self.base_dir / "profiles_test_rows.csv")
        
        # 콘텐츠 데이터 로드 (실제 hybrid_recommender_v2.py의 로직 사용)
        try:
            # 1순위: Supabase DB
            self.content_db = load_contents_from_supabase()
            print(f"📚 Supabase에서 콘텐츠 로드: {len(self.content_db)}개")
            
            # 만약 Supabase가 비어있으면 JSON 백업 사용
            if not self.content_db:
                self.content_db = load_all_cards(str(contents_dir))
                self.content_db = [normalize_card(c) for c in self.content_db]
                print(f"📚 JSON 백업에서 콘텐츠 로드: {len(self.content_db)}개")
                
        except Exception as e:
            print(f"⚠️ 콘텐츠 로드 실패: {e}")
            self.content_db = []
        
        print(f"👥 프로필 데이터: {len(self.profiles_df)}명")
        
        # 벡터 인덱스 파일 확인
        self._check_vector_indexes()

    def _check_vector_indexes(self):
        """벡터 인덱스 파일 존재 여부 확인"""
        index_base_dir = self.recommendation_dir / "index"
        models = ["ko-sroberta", "bge-m3"]
        
        self.available_models = []
        
        for model in models:
            model_dir = index_base_dir / model
            required_files = ["content.index", "content_ids.json", "content_meta.json"]
            
            if all((model_dir / file).exists() for file in required_files):
                self.available_models.append(model)
                print(f"✅ {model} 벡터 인덱스 사용 가능")
            else:
                print(f"⚠️ {model} 벡터 인덱스 파일 누락: {model_dir}")
        
        if not self.available_models:
            print("❌ 사용 가능한 벡터 인덱스가 없습니다")
    
    def create_user_context(self, profile: pd.Series) -> Dict:
        """프로필을 사용자 컨텍스트로 변환"""
        interests = profile.get('interests_categories', '[]')
        if isinstance(interests, str):
            try:
                interests = eval(interests)
            except:
                interests = []
        
        emotions = profile.get('investment_emotions', '[]')
        if isinstance(emotions, str):
            try:
                emotions = eval(emotions)
            except:
                emotions = []
        
        goals = profile.get('investment_goal', '[]')
        if isinstance(goals, str):
            try:
                goals = eval(goals)
            except:
                goals = []
        
        return {
            "user_id": profile.get('id', 'test_user'),
            "name": profile.get('name', 'Test User'),
            "interests": interests,
            "emotions": emotions,
            "goals": goals,
            "investment_level": profile.get('investment_level', 'Beginner'),
            "knowledge_level": profile.get('knowledge_level', 'Beginner'),
            "risk_tolerance": profile.get('risk_tolerance', 50),
            "user_summary": profile.get('user_summary', ''),
            "age": profile.get('age', 25),
            "gender": profile.get('gender', 'unknown'),
            # hybrid_recommender_v2.py에서 요구하는 필드들
            "level": profile.get('knowledge_level', 'Beginner'),
            "interest_tags": interests,
            "recent_seen_card_ids": [],
            "liked_tags": []
        }

    def _search_with_ko_sroberta(self, user_context: Dict, top_k: int = 20) -> List[Dict]:
        """ko-sroberta 모델로 벡터 검색"""
        if "ko-sroberta" not in self.available_models:
            print("Ko-SRoBERTa 벡터 인덱스를 사용할 수 없습니다.")
            return self.content_db[:top_k] if self.content_db else []
        
        try:
            # 사용자 쿼리 생성
            query_parts = []
            query_parts.extend(user_context.get('interests', []))
            query_parts.extend(user_context.get('emotions', []))
            query_parts.extend(user_context.get('goals', []))
            user_query = " ".join(query_parts)
            
            if not user_query.strip():
                return self.content_db[:top_k] if self.content_db else []
            
            # vector_candidates 함수 사용 (hybrid_recommender_v2.py에서 import)
            results = vector_candidates(user_query, k=top_k, model_key="ko-sroberta")
            
            # card_id로 매칭하여 전체 콘텐츠 데이터 가져오기
            card_map = {c['card_id']: c for c in self.content_db}
            matched_contents = []
            
            for result in results:
                card_id = str(result.get('card_id', ''))
                if card_id in card_map:
                    content = card_map[card_id].copy()
                    content['score'] = result.get('score', 0.0)
                    matched_contents.append(content)
            
            return matched_contents
            
        except Exception as e:
            print(f"Ko-SRoBERTa 벡터 검색 실패: {e}")
            return self.content_db[:top_k] if self.content_db else []

    def _search_with_bge_m3(self, user_context: Dict, top_k: int = 20) -> List[Dict]:
        """bge-m3 모델로 벡터 검색"""
        if "bge-m3" not in self.available_models:
            print("BGE-M3 벡터 인덱스를 사용할 수 없습니다.")
            return self.content_db[:top_k] if self.content_db else []
        
        try:
            # 사용자 쿼리 생성
            query_parts = []
            query_parts.extend(user_context.get('interests', []))
            query_parts.extend(user_context.get('emotions', []))
            query_parts.extend(user_context.get('goals', []))
            user_query = " ".join(query_parts)
            
            if not user_query.strip():
                return self.content_db[:top_k] if self.content_db else []
            
            # vector_candidates 함수 사용
            results = vector_candidates(user_query, k=top_k, model_key="bge-m3")
            
            # card_id로 매칭하여 전체 콘텐츠 데이터 가져오기
            card_map = {c['card_id']: c for c in self.content_db}
            matched_contents = []
            
            for result in results:
                card_id = str(result.get('card_id', ''))
                if card_id in card_map:
                    content = card_map[card_id].copy()
                    content['score'] = result.get('score', 0.0)
                    matched_contents.append(content)
            
            return matched_contents
            
        except Exception as e:
            print(f"BGE-M3 벡터 검색 실패: {e}")
            return self.content_db[:top_k] if self.content_db else []

    def _search_hybrid(self, user_context: Dict, top_k: int = 20) -> List[Dict]:
        """하이브리드 검색 (현재 사용 중인 방식) - get_hybrid_recommendations 사용"""
        try:
            # get_hybrid_recommendations 함수 사용 (실제 하이브리드 로직)
            result = get_hybrid_recommendations(
                user=user_context,
                top_n=top_k,
                use_llm_rerank=False  # Ablation Study에서는 LLM 리랭킹 비활성화
            )
            
            if result.get('success'):
                return result.get('results', [])
            else:
                print(f"하이브리드 추천 실패: {result.get('error', 'Unknown error')}")
                return []
            
        except Exception as e:
            print(f"하이브리드 검색 실패: {e}")
            # 대안: 두 모델 결과 병합
            if len(self.available_models) >= 2:
                ko_results = self._search_with_ko_sroberta(user_context, top_k//2)
                bge_results = self._search_with_bge_m3(user_context, top_k//2)
                
                # 간단한 결합
                combined = {}
                for result in ko_results + bge_results:
                    card_id = result.get('card_id', result.get('id'))
                    if card_id not in combined:
                        combined[card_id] = result
                
                return list(combined.values())[:top_k]
            else:
                # 사용 가능한 모델이 하나도 없으면 랜덤 리턴
                import random
                return random.sample(self.content_db, min(top_k, len(self.content_db))) if self.content_db else []

    def _search_content(self, user_context: Dict, search_model: str, top_k: int = 20) -> List[Dict]:
        """검색 모델별 콘텐츠 검색"""
        if search_model == "ko-sroberta":
            return self._search_with_ko_sroberta(user_context, top_k)
        elif search_model == "bge-m3":
            return self._search_with_bge_m3(user_context, top_k)
        elif search_model == "hybrid":
            return self._search_hybrid(user_context, top_k)
        else:
            raise ValueError(f"Unknown search model: {search_model}")

    def _filter_content(self, 
                       search_results: List[Dict], 
                       user_context: Dict, 
                       strategy: str) -> List[Dict]:
        """필터링 전략 적용"""
        if strategy == "vector_only":
            return search_results
        elif strategy == "vector_plus_rules":
            return self._apply_rule_based_filter(search_results, user_context)
        else:
            raise ValueError(f"Unknown filtering strategy: {strategy}")

    def _apply_rule_based_filter(self, results: List[Dict], user_context: Dict) -> List[Dict]:
        """룰 기반 필터링"""
        # 난이도 매칭
        user_level = user_context.get("knowledge_level", "Beginner")
        
        filtered = []
        for content in results:
            content_level = content.get("level", "Beginner")
            
            # 레벨 매칭 로직
            if self._is_level_match(user_level, content_level):
                # 관심사 매칭
                if self._is_interest_match(user_context, content):
                    filtered.append(content)
                    
        return filtered

    def _is_level_match(self, user_level: str, content_level: str) -> bool:
        """난이도 매칭 확인"""
        level_map = {"Beginner": 1, "Intermediate": 2, "Advanced": 3}
        user_score = level_map.get(user_level, 1)
        content_score = level_map.get(content_level, 1)
        
        # ±1 레벨까지 허용
        return abs(user_score - content_score) <= 1

    def _is_interest_match(self, user_context: Dict, content: Dict) -> bool:
        """관심사 매칭 확인"""
        user_interests = user_context.get("interests", [])
        content_tags = content.get("tags", [])
        
        # 관심사와 태그 중 하나라도 일치하면 True
        return bool(set(user_interests) & set(content_tags))

    def _rerank_content(self, 
                       filtered_results: List[Dict], 
                       user_context: Dict,
                       reranking_params: Dict) -> List[Dict]:
        """리랭킹 계수 적용"""
        alpha = reranking_params["alpha"]  # 벡터 유사도 가중치
        beta = reranking_params["beta"]    # 난이도 매칭 가중치  
        gamma = reranking_params["gamma"]  # 태그 매칭 가중치
        
        scored_results = []
        for content in filtered_results:
            # 각 요소별 점수 계산
            vector_score = self._calculate_vector_score(user_context, content)
            level_score = self._calculate_level_score(user_context, content)
            tag_score = self._calculate_tag_score(user_context, content)
            
            # 최종 점수 = α×벡터 + β×레벨 + γ×태그
            final_score = alpha * vector_score + beta * level_score + gamma * tag_score
            
            scored_results.append({
                **content,
                "final_score": final_score,
                "score_breakdown": {
                    "vector": vector_score,
                    "level": level_score, 
                    "tag": tag_score
                }
            })
        
        # 점수순 정렬
        scored_results.sort(key=lambda x: x["final_score"], reverse=True)
        return scored_results

    def _calculate_vector_score(self, user_context: Dict, content: Dict) -> float:
        """벡터 유사도 점수 계산"""
        # 기존 검색 점수가 있다면 사용
        if 'score' in content:
            return float(content['score'])
        elif 'final_score' in content:
            return float(content['final_score'])
        else:
            # 임시 점수 (실제로는 임베딩 유사도 계산)
            return np.random.uniform(0.5, 1.0)

    def _calculate_level_score(self, user_context: Dict, content: Dict) -> float:
        """난이도 매칭 점수"""
        if self._is_level_match(
            user_context.get("knowledge_level", "Beginner"),
            content.get("level", "Beginner")
        ):
            return 1.0
        else:
            return 0.3

    def _calculate_tag_score(self, user_context: Dict, content: Dict) -> float:
        """태그 매칭 점수"""
        if self._is_interest_match(user_context, content):
            return 1.0
        else:
            return 0.2

    def _llm_rerank(self, 
                   reranked_results: List[Dict], 
                   user_context: Dict,
                   llm_model: str) -> List[Dict]:
        """LLM 기반 리랭킹"""
        # TODO: 실제 LLM 리랭킹 구현 (Gemini API 사용)
        return reranked_results  # 임시로 그대로 반환

    def _generate_explanations(self, 
                             recommendations: List[Dict],
                             user_context: Dict,
                             llm_model: str,
                             prompt_strategy: str) -> List[Dict]:
        """추천 설명 생성"""
        # TODO: 프롬프트 전략별 설명 생성 (Gemini API 사용)
        for rec in recommendations:
            emotions = user_context.get('emotions', [])
            interests = user_context.get('interests', [])
            emotion_str = ", ".join(emotions) if emotions else "균형"
            interest_str = ", ".join(interests) if interests else "일반적인 투자"
            
            rec["explanation"] = f"이 콘텐츠는 {emotion_str} 감정 상태에서 {interest_str} 관련 학습에 도움이 됩니다."
        
        return recommendations

    def run_recommendation_pipeline(self, 
                                  user_profile: pd.Series,
                                  config: 'ExperimentConfig') -> Tuple[List[Dict], Dict]:
        """
        Ablation Study용 추천 파이프라인 실행
        """
        start_time = time.time()
        
        # 사용자 컨텍스트 생성
        user_context = self.create_user_context(user_profile)
        
        # 1. 검색 단계
        search_results = self._search_content(user_context, config.search_model, top_k=50)
        
        # 2. 필터링 단계  
        filtered_results = self._filter_content(search_results, user_context, config.filtering_strategy)
        
        # 3. 리랭킹 단계
        reranked_results = self._rerank_content(filtered_results, user_context, config.reranking_params)
        
        # 4. LLM 리랭킹 (선택적)
        if config.llm_model != "none":
            final_results = self._llm_rerank(reranked_results, user_context, config.llm_model)
        else:
            final_results = reranked_results
        
        # 5. 설명 생성
        results_with_explanation = self._generate_explanations(
            final_results[:5], user_context, config.llm_model, config.prompt_strategy
        )
        
        # 메트릭 계산
        end_time = time.time()
        metrics = {
            "response_time_ms": (end_time - start_time) * 1000,
            "total_candidates": len(search_results),
            "filtered_candidates": len(filtered_results),
            "final_recommendations": len(results_with_explanation)
        }
        
        return results_with_explanation, metrics

    def test_with_sample_users(self, num_users: int = 5) -> Dict:
        """샘플 사용자들로 테스트 실행"""
        print(f"\n🧪 {num_users}명 샘플 사용자 테스트 시작...")
        
        # 랜덤 샘플 선택
        sample_profiles = self.profiles_df.sample(n=min(num_users, len(self.profiles_df)))
        
        from dataclasses import dataclass
        @dataclass 
        class TestConfig:
            search_model: str = "hybrid"
            filtering_strategy: str = "vector_only"  # 필터링을 완화하여 테스트
            reranking_params: Dict = None
            llm_model: str = "none"  # LLM 설명 생성 비활성화
            prompt_strategy: str = "generic"
            
            def __post_init__(self):
                if self.reranking_params is None:
                    self.reranking_params = {"alpha": 0.7, "beta": 0.2, "gamma": 0.1}
        
        test_config = TestConfig()
        test_results = []
        
        for idx, (_, profile) in enumerate(sample_profiles.iterrows()):
            print(f"\n[{idx+1}/{num_users}] {profile['name']} 테스트 중...")
            
            # 사용자 컨텍스트 미리 확인
            user_context = self.create_user_context(profile)
            print(f"  관심사: {user_context.get('interests', [])}")
            print(f"  감정: {user_context.get('emotions', [])}")
            print(f"  레벨: {user_context.get('knowledge_level', 'Unknown')}")
            
            try:
                results, metrics = self.run_recommendation_pipeline(profile, test_config)
                
                test_result = {
                    'user_id': profile.get('id'),
                    'user_name': profile.get('name'),
                    'num_recommendations': len(results),
                    'metrics': metrics,
                    'sample_titles': [r.get('title', 'No Title')[:50] for r in results[:3]]
                }
                test_results.append(test_result)
                
                print(f"  ✅ {len(results)}개 추천 생성 (응답시간: {metrics['response_time_ms']:.1f}ms)")
                print(f"  검색 후보: {metrics['total_candidates']}개, 필터링 후: {metrics['filtered_candidates']}개")
                
            except Exception as e:
                print(f"  ❌ 테스트 실패: {e}")
                import traceback
                traceback.print_exc()
                test_results.append({
                    'user_id': profile.get('id'),
                    'user_name': profile.get('name'),
                    'error': str(e)
                })
        
        return {
            'total_tests': len(test_results),
            'successful_tests': len([r for r in test_results if 'error' not in r]),
            'test_results': test_results
        }

def integration_test():
    """추천 시스템 연동 테스트"""
    print("🔗 추천 시스템 연동 테스트...")
    
    try:
        evaluator = RecommendationSystemEvaluator()
        
        # 기본 시스템 상태 체크
        print(f"\n📊 시스템 상태:")
        print(f"콘텐츠 DB: {len(evaluator.content_db)}개")
        print(f"사용 가능한 벡터 모델: {evaluator.available_models}")
        
        if not evaluator.content_db:
            print("⚠️ 콘텐츠 데이터가 비어있습니다. Supabase 설정을 확인하거나 JSON 파일을 준비해주세요.")
            return None
            
        # 샘플 사용자들로 테스트
        test_results = evaluator.test_with_sample_users(num_users=3)
        
        print("\n📊 테스트 결과 요약:")
        print(f"전체 테스트: {test_results['total_tests']}개")
        print(f"성공한 테스트: {test_results['successful_tests']}개")
        
        if test_results['total_tests'] > 0:
            success_rate = test_results['successful_tests'] / test_results['total_tests'] * 100
            print(f"성공률: {success_rate:.1f}%")
        
        # 성공한 테스트들의 평균 응답시간 계산
        successful_results = [r for r in test_results['test_results'] if 'error' not in r]
        if successful_results:
            avg_response_time = np.mean([r['metrics']['response_time_ms'] for r in successful_results])
            print(f"평균 응답시간: {avg_response_time:.1f}ms")
            
            # 샘플 결과 보여주기
            print("\n📄 샘플 추천 결과:")
            for i, result in enumerate(successful_results[:2], 1):
                print(f"{i}. {result['user_name']}: {result['num_recommendations']}개 추천")
                for j, title in enumerate(result['sample_titles'], 1):
                    print(f"   {j}) {title}")
        
        return evaluator
        
    except Exception as e:
        print(f"❌ 연동 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    evaluator = integration_test()