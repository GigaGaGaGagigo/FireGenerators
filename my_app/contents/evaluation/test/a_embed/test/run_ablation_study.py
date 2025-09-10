"""
통합된 Ablation Study 실행 스크립트
- 실험 설계 (ablation_study.py)
- 실제 추천 시스템 연동 (connect_with_rec.py)
- 결과 분석 및 리포트 생성
"""

import os
import sys
import time
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Any
import json
from datetime import datetime
from dataclasses import dataclass

# 현재 파일의 경로를 기준으로 모듈 import
current_file = Path(__file__).resolve()
eval_dir = current_file.parent

sys.path.append(str(eval_dir))

# 기존 모듈들 import
from my_app.contents.evaluation.ablation_study.ablation_study import AblationStudyDesigner, ExperimentConfig
from my_app.contents.evaluation.ablation_study.connect_with_rec import RecommendationSystemEvaluator

@dataclass
class AblationResult:
    """개별 실험 결과"""
    experiment_id: str
    config: ExperimentConfig
    user_profile: Dict
    recommendations: List[Dict]
    metrics: Dict
    success: bool
    error_message: str = None

class ComprehensiveAblationStudy:
    """
    포괄적인 Ablation Study 실행 클래스
    """
    
    def __init__(self, profiles_csv_path: str = None):
        self.eval_dir = Path(__file__).parent
        
        # 실험 설계자 초기화
        self.designer = AblationStudyDesigner()
        
        # 추천 시스템 평가자 초기화
        self.evaluator = RecommendationSystemEvaluator(profiles_csv_path)
        
        # 결과 저장 변수
        self.results: List[AblationResult] = []
        self.summary_report = {}
        
        print(f"📊 Ablation Study 초기화 완료")
        print(f"콘텐츠 DB: {len(self.evaluator.content_db)}개")
        print(f"프로필 데이터: {len(self.evaluator.profiles_df)}명")
        print(f"사용 가능한 벡터 모델: {self.evaluator.available_models}")
    
    def run_full_experiment(self, sample_users: int = 10, sample_experiments: int = None) -> Dict:
        """전체 Ablation Study 실험 실행"""
        print(f"\n🚀 포괄적인 Ablation Study 시작")
        print(f"샘플 사용자: {sample_users}명")
        
        start_time = time.time()
        
        # 1. 실험 설계
        print(f"\n1️⃣ 실험 설계 단계...")
        experiments = self.designer.design_experiments()
        
        if sample_experiments:
            experiments = experiments[:sample_experiments]
            print(f"실험 샘플링: {len(experiments)}개 실험으로 제한")
        
        # 2. 사용자 샘플 선택
        print(f"\n2️⃣ 사용자 샘플 선택...")
        sample_profiles = self.evaluator.profiles_df.sample(
            n=min(sample_users, len(self.evaluator.profiles_df))
        )
        
        print(f"선택된 실험: {len(experiments)}개")
        print(f"선택된 사용자: {len(sample_profiles)}명")
        print(f"총 실험 케이스: {len(experiments)} × {len(sample_profiles)} = {len(experiments) * len(sample_profiles)}")
        
        # 3. 실험 실행
        print(f"\n3️⃣ 실험 실행 단계...")
        self._run_experiments(experiments, sample_profiles)
        
        # 4. 결과 분석
        print(f"\n4️⃣ 결과 분석 단계...")
        summary = self._analyze_results()
        
        total_time = time.time() - start_time
        
        # 5. 리포트 생성
        print(f"\n5️⃣ 리포트 생성...")
        report = self._generate_report(summary, total_time)
        
        # 6. 결과 저장
        self._save_results(report)
        
        print(f"\n✅ Ablation Study 완료 (총 소요시간: {total_time:.1f}초)")
        
        return report
    
    def _run_experiments(self, experiments: List[ExperimentConfig], profiles: pd.DataFrame):
        """실험 실행 루프"""
        total_cases = len(experiments) * len(profiles)
        completed = 0
        
        for exp_idx, experiment in enumerate(experiments, 1):
            print(f"\n📋 실험 {exp_idx}/{len(experiments)}: {experiment.experiment_id}")
            print(f"   검색모델: {experiment.search_model}")
            print(f"   필터링: {experiment.filtering_strategy}")
            print(f"   리랭킹: α={experiment.reranking_params['alpha']}, β={experiment.reranking_params['beta']}, γ={experiment.reranking_params['gamma']}")
            
            experiment_results = []
            
            for user_idx, (_, profile) in enumerate(profiles.iterrows(), 1):
                completed += 1
                progress = (completed / total_cases) * 100
                
                print(f"   [{user_idx}/{len(profiles)}] {profile['name']} ({progress:.1f}%)", end=" ")
                
                try:
                    # 개별 실험 실행
                    recommendations, metrics = self.evaluator.run_recommendation_pipeline(
                        profile, experiment
                    )
                    
                    result = AblationResult(
                        experiment_id=experiment.experiment_id,
                        config=experiment,
                        user_profile=profile.to_dict(),
                        recommendations=recommendations,
                        metrics=metrics,
                        success=True
                    )
                    
                    print(f"✅ {len(recommendations)}개 추천")
                    
                except Exception as e:
                    result = AblationResult(
                        experiment_id=experiment.experiment_id,
                        config=experiment,
                        user_profile=profile.to_dict(),
                        recommendations=[],
                        metrics={},
                        success=False,
                        error_message=str(e)
                    )
                    
                    print(f"❌ 실패: {str(e)[:50]}")
                
                self.results.append(result)
                experiment_results.append(result)
            
            # 실험별 중간 요약
            success_count = sum(1 for r in experiment_results if r.success)
            avg_recommendations = np.mean([len(r.recommendations) for r in experiment_results if r.success]) if success_count > 0 else 0
            avg_response_time = np.mean([r.metrics.get('response_time_ms', 0) for r in experiment_results if r.success]) if success_count > 0 else 0
            
            print(f"   📊 실험 요약: 성공률 {success_count}/{len(experiment_results)} ({success_count/len(experiment_results)*100:.1f}%)")
            print(f"      평균 추천수: {avg_recommendations:.1f}개, 평균 응답시간: {avg_response_time:.1f}ms")
    
    def _analyze_results(self) -> Dict:
        """결과 분석"""
        if not self.results:
            return {"error": "분석할 결과가 없습니다"}
        
        # 성공한 실험만 분석
        successful_results = [r for r in self.results if r.success]
        
        if not successful_results:
            return {"error": "성공한 실험이 없습니다"}
        
        # 실험별 성능 집계
        experiment_performance = {}
        
        for result in successful_results:
            exp_id = result.experiment_id
            
            if exp_id not in experiment_performance:
                experiment_performance[exp_id] = {
                    'config': result.config,
                    'total_cases': 0,
                    'recommendations': [],
                    'response_times': [],
                    'relevance_scores': [],
                    'diversity_scores': []
                }
            
            perf = experiment_performance[exp_id]
            perf['total_cases'] += 1
            perf['recommendations'].append(len(result.recommendations))
            perf['response_times'].append(result.metrics.get('response_time_ms', 0))
            
            # 관련성 점수 계산 (단순화: 추천 개수 기반)
            relevance = min(len(result.recommendations) / 5.0, 1.0)  # 5개 추천을 100%로
            perf['relevance_scores'].append(relevance)
            
            # 다양성 점수 계산 (카테고리 다양성)
            categories = set()
            for rec in result.recommendations:
                if 'category' in rec:
                    categories.add(rec['category'])
            diversity = len(categories) / max(len(result.recommendations), 1)
            perf['diversity_scores'].append(diversity)
        
        # 통계 계산
        summary = {}
        
        for exp_id, perf in experiment_performance.items():
            summary[exp_id] = {
                'experiment_id': exp_id,
                'search_model': perf['config'].search_model,
                'filtering_strategy': perf['config'].filtering_strategy,
                'reranking_params': perf['config'].reranking_params,
                'total_cases': perf['total_cases'],
                'avg_recommendations': np.mean(perf['recommendations']),
                'std_recommendations': np.std(perf['recommendations']),
                'avg_response_time': np.mean(perf['response_times']),
                'std_response_time': np.std(perf['response_times']),
                'avg_relevance': np.mean(perf['relevance_scores']),
                'std_relevance': np.std(perf['relevance_scores']),
                'avg_diversity': np.mean(perf['diversity_scores']),
                'std_diversity': np.std(perf['diversity_scores'])
            }
        
        return summary
    
    def _generate_report(self, summary: Dict, total_time: float) -> Dict:
        """종합 리포트 생성"""
        if 'error' in summary:
            return {'error': summary['error'], 'timestamp': datetime.now().isoformat()}
        
        # 최고 성능 실험 찾기
        best_relevance = max(summary.keys(), key=lambda k: summary[k]['avg_relevance'])
        best_speed = min(summary.keys(), key=lambda k: summary[k]['avg_response_time'])
        best_diversity = max(summary.keys(), key=lambda k: summary[k]['avg_diversity'])
        
        # 전체 통계
        total_experiments = len(summary)
        total_cases = len(self.results)
        successful_cases = len([r for r in self.results if r.success])
        
        report = {
            'metadata': {
                'timestamp': datetime.now().isoformat(),
                'total_time_seconds': total_time,
                'total_experiments': total_experiments,
                'total_cases': total_cases,
                'successful_cases': successful_cases,
                'success_rate': (successful_cases / total_cases * 100) if total_cases > 0 else 0,
                'content_db_size': len(self.evaluator.content_db),
                'available_models': self.evaluator.available_models
            },
            'performance_summary': summary,
            'best_performers': {
                'relevance': {
                    'experiment_id': best_relevance,
                    'score': summary[best_relevance]['avg_relevance'],
                    'config': {
                        'search_model': summary[best_relevance]['search_model'],
                        'filtering': summary[best_relevance]['filtering_strategy'],
                        'reranking': summary[best_relevance]['reranking_params']
                    }
                },
                'speed': {
                    'experiment_id': best_speed,
                    'response_time_ms': summary[best_speed]['avg_response_time'],
                    'config': {
                        'search_model': summary[best_speed]['search_model'],
                        'filtering': summary[best_speed]['filtering_strategy'],
                        'reranking': summary[best_speed]['reranking_params']
                    }
                },
                'diversity': {
                    'experiment_id': best_diversity,
                    'score': summary[best_diversity]['avg_diversity'],
                    'config': {
                        'search_model': summary[best_diversity]['search_model'],
                        'filtering': summary[best_diversity]['filtering_strategy'],
                        'reranking': summary[best_diversity]['reranking_params']
                    }
                }
            },
            'detailed_results': self.results  # 상세 결과 포함
        }
        
        return report
    
    def _save_results(self, report: Dict):
        """결과 저장"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # JSON 리포트 저장 (상세 결과 제외)
        report_summary = report.copy()
        del report_summary['detailed_results']  # 용량 절약을 위해 상세 결과는 별도 저장
        
        summary_path = self.eval_dir / f"ablation_report_{timestamp}.json"
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(report_summary, f, ensure_ascii=False, indent=2, default=str)
        
        # CSV 요약 저장
        if 'performance_summary' in report and report['performance_summary']:
            df = pd.DataFrame.from_dict(report['performance_summary'], orient='index')
            csv_path = self.eval_dir / f"ablation_summary_{timestamp}.csv"
            df.to_csv(csv_path, index=False, encoding='utf-8-sig')
        
        # 상세 결과 별도 저장 (필요시)
        detailed_path = self.eval_dir / f"ablation_detailed_{timestamp}.json"
        detailed_data = [
            {
                'experiment_id': r.experiment_id,
                'user_name': r.user_profile.get('name', 'Unknown'),
                'success': r.success,
                'num_recommendations': len(r.recommendations),
                'response_time_ms': r.metrics.get('response_time_ms', 0),
                'error': r.error_message
            }
            for r in self.results
        ]
        
        with open(detailed_path, 'w', encoding='utf-8') as f:
            json.dump(detailed_data, f, ensure_ascii=False, indent=2)
        
        print(f"📁 결과 저장 완료:")
        print(f"   요약 리포트: {summary_path.name}")
        print(f"   성능 요약: {csv_path.name}")
        print(f"   상세 결과: {detailed_path.name}")
    
    def print_summary(self):
        """결과 요약 출력"""
        if not hasattr(self, 'summary_report') or not self.summary_report:
            print("❌ 출력할 결과가 없습니다. run_full_experiment()를 먼저 실행하세요.")
            return
        
        report = self.summary_report
        
        if 'error' in report:
            print(f"❌ 에러: {report['error']}")
            return
        
        metadata = report['metadata']
        best = report['best_performers']
        
        print("\n" + "="*80)
        print("                  ABLATION STUDY 최종 결과")
        print("="*80)
        
        print(f"\n📊 전체 통계:")
        print(f"   총 실험 수: {metadata['total_experiments']}개")
        print(f"   총 테스트 케이스: {metadata['total_cases']}개") 
        print(f"   성공률: {metadata['success_rate']:.1f}%")
        print(f"   총 소요시간: {metadata['total_time_seconds']:.1f}초")
        
        print(f"\n🏆 최고 성능 구성:")
        
        print(f"\n   🎯 관련성 최고:")
        rel_config = best['relevance']['config']
        print(f"      실험 ID: {best['relevance']['experiment_id']}")
        print(f"      점수: {best['relevance']['score']:.3f}")
        print(f"      설정: {rel_config['search_model']} + {rel_config['filtering']} + α={rel_config['reranking']['alpha']}")
        
        print(f"\n   ⚡ 속도 최고:")
        speed_config = best['speed']['config']
        print(f"      실험 ID: {best['speed']['experiment_id']}")
        print(f"      응답시간: {best['speed']['response_time_ms']:.1f}ms")
        print(f"      설정: {speed_config['search_model']} + {speed_config['filtering']} + α={speed_config['reranking']['alpha']}")
        
        print(f"\n   🌈 다양성 최고:")
        div_config = best['diversity']['config']
        print(f"      실험 ID: {best['diversity']['experiment_id']}")
        print(f"      점수: {best['diversity']['score']:.3f}")
        print(f"      설정: {div_config['search_model']} + {div_config['filtering']} + α={div_config['reranking']['alpha']}")
        
        print(f"\n💡 권장사항:")
        if best['relevance']['experiment_id'] == best['speed']['experiment_id'] == best['diversity']['experiment_id']:
            print(f"   🎉 '{best['relevance']['experiment_id']}' 설정이 모든 메트릭에서 최고 성능!")
        else:
            print(f"   균형잡힌 성능을 위해서는 추가 분석이 필요합니다.")
            print(f"   현재 하이브리드 방식과 비교하여 최적 설정을 선택하세요.")

def main():
    """메인 실행 함수"""
    print("🚀 통합 Ablation Study 실행")
    
    # Ablation Study 초기화
    study = ComprehensiveAblationStudy()
    
    # 전체 실험 실행 (샘플링)
    report = study.run_full_experiment(
        sample_users=5,        # 5명 사용자로 테스트
        sample_experiments=6   # 6개 실험으로 제한
    )
    
    # 결과 요약 출력
    study.summary_report = report
    study.print_summary()
    
    return study

if __name__ == "__main__":
    study = main()