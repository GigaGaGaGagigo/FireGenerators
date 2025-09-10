"""
FIREgenerator 추천 시스템 A-E 단계별 평가 파이프라인
간단하고 명확한 성능 평가 시스템

A. 검색 모델 비교 (ko-sroberta vs bge-m3 vs hybrid)
B. 필터링 전략 (vector_only vs hybrid)
C. 리랭킹 계수 (α, β, γ 최적화)
D. LLM 리랭킹 (GPT vs Gemini vs none)
E. 프롬프트 전략 (generic vs adaptive)
"""

import os
import sys
import json
import time
import pandas as pd
import numpy as np
from typing import Dict, List, Any
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# 환경변수 로드 (evaluation 폴더로 옮겼으므로 경로 수정)
project_root = Path(__file__).resolve().parents[3]  # FireGenerators/
load_dotenv(project_root / '.env')
 
# 추천 시스템 모듈 경로 설정 - 절대 경로 사용
current_file = Path(__file__).resolve()
# /Users/green/finalproject/FireGenerators/my_app/contents/evaluation/pipeline_evaluation.py
 
# 상위 디렉토리들로 이동 (evaluation 폴더로 옮겨졌으므로 경로 수정)
my_app_dir = current_file.parents[2]  # my_app/
contents_dir = current_file.parents[1]  # contents/
rec_dir = contents_dir / "recommendation"  # contents/recommendation/

# sys.path에 추가
sys.path.insert(0, str(rec_dir))
sys.path.insert(0, str(contents_dir))
sys.path.insert(0, str(my_app_dir))
 
print(f"📁 추천 시스템 경로: {rec_dir}")
print(f"🔍 hybrid_recommender_v2.py 존재: {(rec_dir / 'hybrid_recommender_v2.py').exists()}")
print(f"📋 sys.path에 추가된 경로들:")
for path in [str(rec_dir), str(contents_dir), str(my_app_dir)]:
    print(f"  - {path}")

# 기존 추천 시스템 import
try:
    # 방법 1: 명시적 패키지 경로
    from contents.recommendation.hybrid_recommender_v2 import get_hybrid_recommendations, get_supabase_client
    print("✅ 추천 시스템 연결 성공 (패키지 import)")
except ImportError:
    try:
        # 방법 2: 상대 import 시도  
        from ..recommendation.hybrid_recommender_v2 import get_hybrid_recommendations, get_supabase_client
        print("✅ 추천 시스템 연결 성공 (상대 import)")
    except ImportError:
        try:
            # 방법 3: 절대 import 시도
            from hybrid_recommender_v2 import get_hybrid_recommendations, get_supabase_client
            print("✅ 추천 시스템 연결 성공 (절대 import)")
        except ImportError as e:
            print(f"❌ 모든 import 방법 실패: {e}")
            print("⚠️ 실행은 계속하지만 추천 시스템을 사용할 수 없습니다.")
            # Mock 함수로 대체
            def get_hybrid_recommendations(*args, **kwargs):
                return {"success": False, "results": [], "error": "Import failed"}
            def get_supabase_client():
                return None

# Langfuse 설정 (선택적)
try:
    from langfuse.client import Langfuse
    langfuse = Langfuse(
        secret_key=os.getenv('LANGFUSE_SECRET_KEY'),
        public_key=os.getenv('LANGFUSE_PUBLIC_KEY'),
        host=os.getenv('LANGFUSE_HOST', 'https://us.cloud.langfuse.com')
    )
    print("✅ Langfuse 연결 성공")
except Exception as e:
    langfuse = None
    print(f"⚠️ Langfuse 연결 실패 (선택사항):{e}")


class SimpleEvaluator:
    """간단한 추천 시스템 평가기"""

    def __init__(self):
        """데이터 로드"""
        self.setup_data()
        self.results_dir = Path(__file__).parent / "final_result"
        self.results_dir.mkdir(exist_ok=True)

    def setup_data(self):
        """사용자와 콘텐츠 데이터 로드"""
        try:
            # Supabase 연결
            supabase = get_supabase_client()

            # 사용자 프로필 로드
            response = supabase.table("profiles_test").select("*").execute()
            self.users = response.data

            print(f"👥 사용자: {len(self.users)}명")

        except Exception as e:
            print(f"❌ 데이터 로드 실패: {e}")
            self.users = []

    def create_configs(self):
        """A-E 단계별 실험 설정 생성"""
        configs = []

        # 기본 설정 (현재 시스템 상태 반영)
        base_config = {
            'search_model': 'hybrid',
            'filtering': 'hybrid',
            'alpha': 0.6, 'beta': 0.3, 'gamma': 0.1,
            'llm': 'gpt-4o-mini',
            'prompt': 'level_specific'  # 현재 시스템이 level별 프롬프트 사용 중
        }
        configs.append(('baseline', base_config))

        # A단계: 검색 모델 비교
        for model in ['ko-sroberta', 'bge-m3', 'hybrid']:
            config = base_config.copy()
            config['search_model'] = model
            config['llm'] = 'none'  # 순수 검색 성능
            configs.append((f'A_search_{model}', config))

        # B단계: 필터링 비교
        for filtering in ['vector_only', 'hybrid']:
            config = base_config.copy()
            config['filtering'] = filtering
            config['llm'] = 'none'
            configs.append((f'B_filter_{filtering}', config))

        # C단계: 리랭킹 계수
        rerank_weights = [(0.7,0.2,0.1), (0.6,0.3,0.1), (0.5,0.4,0.1), (0.5,0.3,0.2)]
        for i, (a,b,g) in enumerate(rerank_weights):
            config = base_config.copy()
            config['alpha'], config['beta'], config['gamma'] = a, b, g
            config['llm'] = 'none'
            configs.append((f'C_rerank_{i+1}', config))

        # D단계: LLM 비교
        for llm in ['gpt-4o-mini', 'gemini-flash', 'claude']:
            config = base_config.copy()
            config['llm'] = llm
            configs.append((f'D_llm_{llm}', config))

        # E단계: 프롬프트 비교 (현재 시스템은 이미 level_specific 사용 중)
        for prompt in ['generic', 'level_specific', 'adaptive']:
            config = base_config.copy()
            config['prompt'] = prompt
            configs.append((f'E_prompt_{prompt}', config))

        return configs

    def parse_user_profile(self, user):
        """사용자 프로필 파싱"""
        def safe_eval(field):
            try:
                return eval(field) if isinstance(field, str) and field.strip() else []
            except:
                return []

        return {
            'user_id': user.get('id', 'unknown'),
            'name': user.get('name', 'Unknown'),
            'interests': safe_eval(user.get('interests_categories', [])),
            'emotions': safe_eval(user.get('investment_emotions', [])),
            'goals': safe_eval(user.get('investment_goal', [])),
            'knowledge_level': user.get('knowledge_level', 'Beginner'),
            'level': user.get('knowledge_level', 'Beginner'),
            'interest_tags': safe_eval(user.get('interests_categories', [])),
            'recent_seen_card_ids': [],
            'liked_tags': []
        }

    def run_single_test(self, user, config, exp_name):
        """단일 사용자-설정 테스트"""
        trace = None
        if langfuse:
            trace = langfuse.trace(
                name=exp_name,
                user_id=user.get('id'),
                metadata=config
            )

        start_time = time.time()

        try:
            # 사용자 컨텍스트 생성
            user_context = self.parse_user_profile(user)

            span = None
            if trace:
                span = trace.span(
                    name="get-hybrid-recommendations",
                    input=user_context,
                    metadata={
                        'top_n': 3,
                        'use_llm_rerank': (config['llm'] != 'none')
                    }
                )

            # 추천 실행 (기존 시스템 활용)
            result = get_hybrid_recommendations(
                user=user_context,
                top_n=3,
                use_llm_rerank=(config['llm'] != 'none')
            )

            if span:
                span.update(output=result)

            # 결과 처리
            if result.get('success'):
                recommendations = result.get('results', [])
                metrics = {
                    'success': True,
                    'count': len(recommendations),
                    'time_ms': (time.time() - start_time) * 1000,
                    'relevance': self.calculate_relevance(recommendations, user_context),
                    'diversity': self.calculate_diversity(recommendations)
                }
            else:
                metrics = {
                    'success': False,
                    'count': 0,
                    'time_ms': (time.time() - start_time) * 1000,
                    'relevance': 0.0,
                    'diversity': 0.0,
                    'error': result.get('error', 'Unknown error')
                }

            if trace:
                trace.update(output=metrics)

            return metrics

        except Exception as e:
            metrics = {
                'success': False,
                'count': 0,
                'time_ms': (time.time() - start_time) * 1000,
                'relevance': 0.0,
                'diversity': 0.0,
                'error': str(e)
            }
            if trace:
                trace.update(output=metrics)
            return metrics

    def calculate_relevance(self, recommendations, user_context):
        """
        관련성 점수를 계산합니다. Jaccard 유사도와 레벨 근접성을 이용해 각 아이템의 점수를 계산하고,
        추천된 모든 아이템의 점수 평균을 반환합니다. nDCG 방식에서 발견된 점수 1.0 고정 문제를 해결하기 위해
        순위 기반 정규화를 제거하고, 대신 점수 계산 자체를 더 세분화하여 분산을 확보합니다.
        """
        if not recommendations:
            return 0.0

        total_score = 0.0
        user_interests = set(user_context.get('interests', []))
        user_level_num = self.level_to_num(user_context.get('knowledge_level','Beginner'))

        for rec in recommendations:
           # 1. 관심사 점수 (Jaccard 유사도)
            rec_tags = set(rec.get('tags', []))
            intersection = len(user_interests & rec_tags)
            union = len(user_interests | rec_tags)
            interest_score = intersection / union if union > 0 else 0.0

            # 2. 레벨 점수
            rec_level_num = self.level_to_num(rec.get('level'))
            level_diff = abs(rec_level_num - user_level_num)
            if level_diff == 0:
                level_score = 1.0
            elif level_diff == 1:
                level_score = 0.5
            else:
                level_score = 0.0

            # 최종 관련성 점수 (가중치: 관심사 60%, 레벨 40%)
            score = (interest_score * 0.6) + (level_score * 0.4)
            total_score += score

        return total_score / len(recommendations) if recommendations else 0.0

    def calculate_diversity(self, recommendations):
        """다양성 점수 계산"""
        if not recommendations:
            return 0.0

        # 레벨 다양성
        levels = [rec.get('level', 'Beginner') for rec in recommendations]
        level_diversity = len(set(levels)) / len(levels)

        # 태그 다양성  
        all_tags = []
        for rec in recommendations:
            all_tags.extend(rec.get('tags', []))
        tag_diversity = len(set(all_tags)) / max(len(all_tags), 1)

        return (level_diversity + tag_diversity) / 2

    def level_to_num(self, level):
        """레벨을 숫자로 변환"""
        mapping = {'Beginner': 1, 'Intermediate': 2, 'Advanced': 3}
        return mapping.get(level, 1)

    def run_full_evaluation(self, max_users=10):
        """전체 평가 실행"""
        print(f"🧪 A-E 단계별 평가 시작 (사용자 {max_users}명)")
        
        # 실험 설정
        configs = self.create_configs()
        sample_users = self.users[:max_users]
        
        print(f"📋 실험 설정: {len(configs)}개")
        print(f"👥 테스트 사용자: {len(sample_users)}명")
        
        # 전체 결과 저장
        all_results = []
        config_summaries = {}
        
        # 각 설정별로 실험
        for exp_name, config in configs:
            print(f"\n🔬 [{exp_name}] 실험 중...")
            
            config_results = []
            
            # 각 사용자별로 테스트
            for user in sample_users:
                metrics = self.run_single_test(user, config, exp_name)
                
                result_record = {
                    'experiment': exp_name,
                    'user_id': user.get('id'),
                    'user_name': user.get('name'),
                    'config': config,
                    'metrics': metrics,
                    'timestamp': datetime.now().isoformat()
                }
                
                all_results.append(result_record)
                config_results.append(metrics)
            
            # 설정별 요약 통계
            successful_results = [r for r in config_results if r['success']]
            
            if successful_results:
                config_summaries[exp_name] = {
                    'config': config,
                    'success_rate': len(successful_results) / len(config_results),
                    'avg_count': np.mean([r['count'] for r in successful_results]),
                    'avg_time_ms': np.mean([r['time_ms'] for r in successful_results]),
                    'avg_relevance': np.mean([r['relevance'] for r in successful_results]),
                    'avg_diversity': np.mean([r['diversity'] for r in successful_results]),
                    'total_tests': len(config_results)
                }
            else:
                config_summaries[exp_name] = {
                    'config': config,
                    'success_rate': 0.0,
                    'avg_count': 0.0,
                    'avg_time_ms': 0.0,
                    'avg_relevance': 0.0,
                    'avg_diversity': 0.0,
                    'total_tests': len(config_results)
                }
            
            # 진행 상황 출력
            summary = config_summaries[exp_name]
            print(f"  ✅ 성공률: {summary['success_rate']:.1%}")
            print(f"  📊 평균 추천: {summary['avg_count']:.1f}개")
            print(f"  ⏱️ 평균 시간: {summary['avg_time_ms']:.0f}ms")
            print(f"  🎯 관련성: {summary['avg_relevance']:.3f}")
            print(f"  🌈 다양성: {summary['avg_diversity']:.3f}")
        
        # 결과 저장
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 상세 결과 (JSON)
        detailed_path = self.results_dir / f"evaluation_detailed_{timestamp}.json"
        with open(detailed_path, 'w', encoding='utf-8') as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)
        
        # 요약 결과 (CSV)
        summary_data = []
        for exp_name, summary in config_summaries.items():
            row = {'experiment': exp_name, **summary}
            row['config'] = str(row['config'])  # dict를 문자열로 변환
            summary_data.append(row)
        
        summary_df = pd.DataFrame(summary_data)
        csv_path = self.results_dir / f"evaluation_summary_{timestamp}.csv"
        summary_df.to_csv(csv_path, index=False, encoding='utf-8-sig')
        
        # 단계별 최고 성능 찾기
        best_configs_per_stage = self.find_best_configs_per_stage(config_summaries)
        
        # 결과 출력
        print(f"\n🎉 평가 완료!")
        print(f"📁 상세 결과: {detailed_path}")
        print(f"📊 요약 결과: {csv_path}")
        
        print("\n🏆 단계별 최고 성능 🏆")
        for stage, best_config in best_configs_per_stage.items():
            stage_name = {
                'A_search': 'A. 검색 모델',
                'B_filter': 'B. 필터링 전략',
                'C_rerank': 'C. 리랭킹 계수',
                'D_llm': 'D. LLM 리랭킹',
                'E_prompt': 'E. 프롬프트 전략'
            }.get(stage, stage)
            
            print(f"\n--- {stage_name} ---")
            print(f"  🚀 최적 설정: {best_config['name']}")
            print(f"     - 종합 점수: {best_config['score']:.3f}")
            print(f"     - 관련성: {best_config['relevance']:.3f}")
            print(f"     - 다양성: {best_config['diversity']:.3f}")

        return {
            'detailed_path': str(detailed_path),
            'summary_path': str(csv_path),
            'best_configs_per_stage': best_configs_per_stage,
            'total_experiments': len(all_results),
            'config_summaries': config_summaries
        }

    def find_best_configs_per_stage(self, summaries):
        """각 평가 단계(A, B, C, D, E)별로 최고 성능 설정을 찾습니다."""

        # 1. 실험 결과를 단계별로 그룹화
        staged_summaries = {
            'A_search': {},
            'B_filter': {},
            'C_rerank': {},
            'D_llm': {},
            'E_prompt': {}
        }

        for name, summary in summaries.items():
            if name.startswith('A_search'):
                staged_summaries['A_search'][name] = summary
            elif name.startswith('B_filter'):
                staged_summaries['B_filter'][name] = summary
            elif name.startswith('C_rerank'):
                staged_summaries['C_rerank'][name] = summary
            elif name.startswith('D_llm'):
                staged_summaries['D_llm'][name] = summary
            elif name.startswith('E_prompt'):
                staged_summaries['E_prompt'][name] = summary

        # 2. 각 단계별 최고 점수 설정 찾기
        best_configs = {}
        for stage, stage_summaries in staged_summaries.items():
            if not stage_summaries:
                continue

            best_score = -1
            best_config_in_stage = None

            for name, summary in stage_summaries.items():
                # 종합 점수 = 관련성(40%) + 다양성(30%) + 추천수(20%) + 성공률(10%)
                score = (
                    summary['avg_relevance'] * 0.4 +
                    summary['avg_diversity'] * 0.3 +
                    min(summary['avg_count'] / 3.0, 1.0) * 0.2 +  # 3개 추천 기준
                    summary['success_rate'] * 0.1
                )

                if score > best_score:
                    best_score = score
                    best_config_in_stage = {
                        'name': name,
                        'score': score,
                        'relevance': summary['avg_relevance'],
                        'diversity': summary['avg_diversity'],
                        'count': summary['avg_count'],
                        'success_rate': summary['success_rate'],
                        'config': summary['config']
                    }

            if best_config_in_stage:
                best_configs[stage] = best_config_in_stage

        return best_configs


def main():
    """메인 실행"""
    print("🚀 FIREgenerator 추천 시스템 평가 시작")

    evaluator = SimpleEvaluator()

    if not evaluator.users:
        print("❌ 사용자 데이터가 없습니다")
        return None

    results = evaluator.run_full_evaluation(max_users=len(evaluator.users))  # 모든 사용자 사용
    return results


if __name__ == "__main__":
    results = main()
    if results:
        print(f"\n✅ 평가 완료! 결과: {results['summary_path']}")
    else:
        print("❌ 평가 실패")