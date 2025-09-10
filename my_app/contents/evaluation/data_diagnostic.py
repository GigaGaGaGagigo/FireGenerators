"""
데이터 진단기 - 현재 평가 결과가 왜 비슷한지 원인 분석

분석 항목:
1. 사용자 프로필 다양성 분석
2. 콘텐츠 데이터 분포 분석  
3. 실험 설정별 실제 동작 확인
4. 추천 결과 중복도 분석
"""

import json
import pandas as pd
import numpy as np
from pathlib import Path
from collections import Counter
import matplotlib.pyplot as plt
import seaborn as sns

# 폰트 설정 (macOS 호환)
try:
    import matplotlib.font_manager as fm
    available_fonts = [f.name for f in fm.fontManager.ttflist]
    
    if 'AppleGothic' in available_fonts:
        plt.rcParams['font.family'] = ['AppleGothic']
    elif 'Arial Unicode MS' in available_fonts:
        plt.rcParams['font.family'] = ['Arial Unicode MS']  
    else:
        plt.rcParams['font.family'] = ['DejaVu Sans']
    
    plt.rcParams['axes.unicode_minus'] = False
except:
    plt.rcParams['font.family'] = ['DejaVu Sans']


class DataDiagnostic:
    """데이터 및 실험 결과 진단"""
    
    def __init__(self):
        self.result_dir = Path(__file__).parent / "final_result"
        self.user_data = None
        self.content_data = None
        self.evaluation_results = None
    
    def load_evaluation_results(self):
        """최신 평가 결과 로드"""
        detailed_files = list(self.result_dir.glob("evaluation_detailed_*.json"))
        
        if not detailed_files:
            print("❌ 평가 결과 파일이 없습니다. pipeline_evaluation.py를 먼저 실행하세요.")
            return False
        
        latest_file = max(detailed_files, key=lambda x: x.stat().st_mtime)
        print(f"📂 분석할 파일: {latest_file.name}")
        
        with open(latest_file, 'r', encoding='utf-8') as f:
            self.evaluation_results = json.load(f)
        
        print(f"✅ 평가 결과 로드: {len(self.evaluation_results)}개 기록")
        return True
    
    def load_user_data(self):
        """사용자 데이터 로드"""
        try:
            # pipeline_evaluation.py에서 사용한 것과 동일한 방식
            import sys
            current_file = Path(__file__).resolve()
            my_app_dir = current_file.parents[2]
            contents_dir = current_file.parents[1]
            rec_dir = contents_dir / "recommendation"

            for path in [str(rec_dir), str(contents_dir), str(my_app_dir)]:
                if path not in sys.path:
                    sys.path.insert(0, path)
            
            from hybrid_recommender_v2 import get_supabase_client
            
            supabase = get_supabase_client()
            response = supabase.table("profiles_test").select("*").execute()
            self.user_data = response.data
            
            print(f"👥 사용자 데이터 로드: {len(self.user_data)}명")
            return True
            
        except Exception as e:
            print(f"❌ 사용자 데이터 로드 실패: {e}")
            return False
    
    def analyze_user_diversity(self):
        """사용자 프로필 다양성 분석"""
        print(f"\n{'='*50}")
        print("👥 사용자 프로필 다양성 분석")
        print(f"{ '='*50}")
        
        if not self.user_data:
            print("❌ 사용자 데이터가 없습니다")
            return
        
        # 1. 지식 수준 분포
        levels = [user.get('knowledge_level', 'Unknown') for user in self.user_data]
        level_counts = Counter(levels)
        print(f"\n📊 지식 수준 분포:")
        for level, count in level_counts.most_common():
            print(f"  {level}: {count}명 ({count/len(self.user_data)*100:.1f}%)")
        
        # 2. 관심사 다양성
        all_interests = []
        for user in self.user_data:
            interests = user.get('interests_categories', [])
            if isinstance(interests, str):
                try:
                    interests = eval(interests)
                except:
                    interests = []
            all_interests.extend(interests)
        
        interest_counts = Counter(all_interests)
        print(f"\n🎯 관심사 다양성 (상위 10개):")
        for interest, count in interest_counts.most_common(10):
            print(f"  {interest}: {count}번 ({count/len(self.user_data)*100:.1f}%)")
        
        # 3. 감정 상태 분포
        all_emotions = []
        for user in self.user_data:
            emotions = user.get('investment_emotions', [])
            if isinstance(emotions, str):
                try:
                    emotions = eval(emotions)
                except:
                    emotions = []
            all_emotions.extend(emotions)
        
        emotion_counts = Counter(all_emotions)
        print(f"\n😊 감정 상태 분포:")
        for emotion, count in emotion_counts.most_common():
            print(f"  {emotion}: {count}번 ({count/len(self.user_data)*100:.1f}%)")
        
        # 4. 프로필 유사도 분석
        print(f"\n🔍 프로필 유사도 분석:")
        similar_pairs = self._find_similar_users()
        if similar_pairs:
            print(f"  매우 유사한 사용자 쌍: {len(similar_pairs)}개")
            for user1, user2, similarity in similar_pairs[:3]:
                print(f"    {user1} vs {user2}: {similarity:.3f}")
        else:
            print("  매우 유사한 사용자 쌍이 없습니다")
    
    def _find_similar_users(self):
        """유사한 사용자 찾기"""
        similar_pairs = []
        
        for i, user1 in enumerate(self.user_data):
            for j, user2 in enumerate(self.user_data[i+1:], i+1):
                # 관심사 유사도
                interests1 = set(self._safe_eval(user1.get('interests_categories', [])))
                interests2 = set(self._safe_eval(user2.get('interests_categories', [])))
                
                if interests1 and interests2:
                    jaccard = len(interests1 & interests2) / len(interests1 | interests2)
                    
                    # 레벨도 같고, 관심사 유사도가 높으면
                    if (user1.get('knowledge_level') == user2.get('knowledge_level') and 
                        jaccard > 0.7):
                        similar_pairs.append((
                            user1.get('name', f'User{i}'),
                            user2.get('name', f'User{j}'), 
                            jaccard
                        ))
        
        return sorted(similar_pairs, key=lambda x: x[2], reverse=True)
    
    def _safe_eval(self, field):
        """안전한 eval"""
        try:
            return eval(field) if isinstance(field, str) and field.strip() else []
        except:
            return []
    
    def analyze_experiment_results(self):
        """실험 결과 분석"""
        print(f"\n{'='*50}")
        print("🧪 실험 결과 분포 분석")
        print(f"{ '='*50}")
        
        if not self.evaluation_results:
            print("❌ 평가 결과가 없습니다")
            return
        
        # 실험별 성능 분포
        experiment_stats = {}
        
        for result in self.evaluation_results:
            exp_id = result['experiment']
            metrics = result['metrics']
            
            if exp_id not in experiment_stats:
                experiment_stats[exp_id] = {
                    'success': [],
                    'count': [],
                    'relevance': [],
                    'diversity': [],
                    'time_ms': []
                }
            
            experiment_stats[exp_id]['success'].append(metrics.get('success', False))
            experiment_stats[exp_id]['count'].append(metrics.get('count', 0))
            experiment_stats[exp_id]['relevance'].append(metrics.get('relevance', 0))
            experiment_stats[exp_id]['diversity'].append(metrics.get('diversity', 0))
            experiment_stats[exp_id]['time_ms'].append(metrics.get('time_ms', 0))
        
        # 통계 계산
        print(f"\n📊 실험별 성능 통계:")
        print(f"{ '실험명':<20} {'성공률':<8} {'추천수':<8} {'관련성':<8} {'다양성':<8} {'표준편차':<10}")
        print("-" * 80)
        
        overall_stats = {
            'success_rates': [],
            'avg_counts': [],
            'avg_relevances': [],
            'avg_diversities': []
        }
        
        for exp_id, stats in experiment_stats.items():
            success_rate = np.mean(stats['success'])
            avg_count = np.mean(stats['count'])
            avg_relevance = np.mean(stats['relevance'])
            avg_diversity = np.mean(stats['diversity'])
            
            # 표준편차 (관련성 기준)
            std_relevance = np.std(stats['relevance'])
            
            print(f"{exp_id:<20} {success_rate:<8.3f} {avg_count:<8.1f} {avg_relevance:<8.3f} {avg_diversity:<8.3f} {std_relevance:<10.3f}")
            
            overall_stats['success_rates'].append(success_rate)
            overall_stats['avg_counts'].append(avg_count)
            overall_stats['avg_relevances'].append(avg_relevance)
            overall_stats['avg_diversities'].append(avg_diversity)
        
        # 전체 분산 분석
        print(f"\n📈 전체 분산 분석:")
        print(f"  성공률 분산: {np.var(overall_stats['success_rates']):.6f}")
        print(f"  추천수 분산: {np.var(overall_stats['avg_counts']):.6f}" ) 
        print(f"  관련성 분산: {np.var(overall_stats['avg_relevances']):.6f}")
        print(f"  다양성 분산: {np.var(overall_stats['avg_diversities']):.6f}")
        
        # 분산이 낮으면 문제
        if np.var(overall_stats['avg_relevances']) < 0.001:
            print(f"  ⚠️ 관련성 점수 분산이 매우 낮습니다! ({np.var(overall_stats['avg_relevances']):.6f})")
            print(f"     → 모든 실험이 비슷한 성능을 보이고 있습니다")
        
        if np.var(overall_stats['avg_diversities']) < 0.001:
            print(f"  ⚠️ 다양성 점수 분산이 매우 낮습니다! ({np.var(overall_stats['avg_diversities']):.6f})")
            print(f"     → 추천 결과들이 너무 유사합니다")
    
    def analyze_recommendation_overlap(self):
        """추천 결과 중복도 분석"""
        print(f"\n{'='*50}")
        print("🔄 추천 결과 중복도 분석")
        print(f"{ '='*50}")
        
        if not self.evaluation_results:
            return
        
        # 사용자별-실험별 추천 결과 수집
        user_recommendations = {}
        
        for result in self.evaluation_results:
            user_id = result['user_id']
            exp_id = result['experiment']
            
            if user_id not in user_recommendations:
                user_recommendations[user_id] = {}
            
            # 실제 추천 결과가 있는지 확인 (현재는 metrics만 있음)
            user_recommendations[user_id][exp_id] = result['metrics'].get('count', 0)
        
        # 사용자별 실험 간 성능 차이 분석
        low_variance_users = []
        
        for user_id, experiments in user_recommendations.items():
            if len(experiments) > 1:
                counts = list(experiments.values())
                variance = np.var(counts)
                
                if variance < 0.1:  # 분산이 매우 낮으면
                    low_variance_users.append((user_id, variance, counts))
        
        print(f"\n🔍 실험 간 성능 차이가 거의 없는 사용자:")
        print(f"  총 {len(low_variance_users)}명 / {len(user_recommendations)}명")
        
        if low_variance_users:
            print(f"  예시:")
            for user_id, variance, counts in low_variance_users[:5]:
                if self.user_data:
                    user_name = next((u['name'] for u in self.user_data if u['id'] == user_id), f"User_{user_id}")
                else:
                    user_name = f"User_{user_id}"
                print(f"    {user_name}: 분산 {variance:.3f}, 추천수 {counts}")
        
        # 전체적으로 모든 실험이 비슷한 결과를 내는지 확인
        if len(low_variance_users) / len(user_recommendations) > 0.8:
            print(f"\n⚠️ 경고: 80% 이상의 사용자에서 실험 간 차이가 거의 없습니다!")
            print(f"   → 실험 설정이 실제로 추천 결과에 영향을 주지 않고 있을 가능성")
    
    def analyze_config_impact(self):
        """실험 설정이 실제로 영향을 주는지 분석"""
        print(f"\n{'='*50}")
        print("⚙️ 실험 설정 영향도 분석")
        print(f"{ '='*50}")
        
        if not self.evaluation_results:
            return
        
        # A-E 단계별 그룹핑
        stage_groups = {
            'A_search': [],
            'B_filter': [],
            'C_rerank': [],
            'D_llm': [],
            'E_prompt': [],
            'baseline': []
        }
        
        for result in self.evaluation_results:
            exp_id = result['experiment']
            metrics = result['metrics']
            
            # 단계 분류
            if exp_id.startswith('A_'):
                stage_groups['A_search'].append(metrics)
            elif exp_id.startswith('B_'):
                stage_groups['B_filter'].append(metrics)
            elif exp_id.startswith('C_'):
                stage_groups['C_rerank'].append(metrics)
            elif exp_id.startswith('D_'):
                stage_groups['D_llm'].append(metrics)
            elif exp_id.startswith('E_'):
                stage_groups['E_prompt'].append(metrics)
            elif exp_id == 'baseline':
                stage_groups['baseline'].append(metrics)
        
        # 단계별 분산 분석
        print(f"\n📊 단계별 성능 분산:")
        print(f"{ '단계':<10} {'실험수':<8} {'관련성분산':<12} {'다양성분산':<12} {'영향도'}")
        print("-" * 60)
        
        for stage, results in stage_groups.items():
            if not results:
                continue
                
            relevance_scores = [r.get('relevance', 0) for r in results]
            diversity_scores = [r.get('diversity', 0) for r in results]
            
            rel_var = np.var(relevance_scores) if len(relevance_scores) > 1 else 0
            div_var = np.var(diversity_scores) if len(diversity_scores) > 1 else 0
            
            # 영향도 판정
            if rel_var > 0.01 or div_var > 0.01:
                impact = "높음"
            elif rel_var > 0.001 or div_var > 0.001:
                impact = "보통"
            else:
                impact = "낮음"
            
            print(f"{stage:<10} {len(results):<8} {rel_var:<12.6f} {div_var:<12.6f} {impact}")
    
    def generate_diagnostic_report(self):
        """진단 보고서 생성"""
        print(f"\n{'='*50}")
        print("📋 진단 보고서 요약")
        print(f"{ '='*50}")
        
        # 문제점들 수집
        issues = []
        recommendations = []
        
        # 사용자 다양성 체크
        if self.user_data:
            levels = [user.get('knowledge_level', 'Unknown') for user in self.user_data]
            level_counts = Counter(levels)
            dominant_level = level_counts.most_common(1)[0]
            
            if dominant_level[1] / len(self.user_data) > 0.7:
                issues.append(f"사용자의 {dominant_level[1]/len(self.user_data)*100:.1f}%가 '{dominant_level[0]}' 레벨로 편중됨")
                recommendations.append("다양한 지식 수준의 사용자 데이터 추가 필요")
        
        # 실험 결과 분산 체크
        if self.evaluation_results:
            experiment_stats = {}
            for result in self.evaluation_results:
                exp_id = result['experiment']
                metrics = result['metrics']
                
                if exp_id not in experiment_stats:
                    experiment_stats[exp_id] = []
                experiment_stats[exp_id].append(metrics.get('relevance', 0))
            
            avg_relevances = [np.mean(scores) for scores in experiment_stats.values()]
            overall_var = np.var(avg_relevances)
            
            if overall_var < 0.001:
                issues.append(f"실험 간 관련성 점수 분산이 매우 낮음 ({overall_var:.6f})")
                recommendations.append("평가 지표 개선 또는 실험 설정 차별화 필요")
        
        print(f"\n🚨 발견된 문제점:")
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")
        
        print(f"\n💡 개선 권장사항:")
        for i, rec in enumerate(recommendations, 1):
            print(f"  {i}. {rec}")
        
        if not issues:
            print("  ✅ 특별한 문제점이 발견되지 않았습니다")
        
        # 파일로 저장
        report_path = self.result_dir / f"diagnostic_report_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("FIREgenerator 추천 시스템 진단 보고서\n")
            f.write("=" * 50 + "\n\n")
            f.write("발견된 문제점:\n")
            for issue in issues:
                f.write(f"- {issue}\n")
            f.write("\n개선 권장사항:\n")
            for rec in recommendations:
                f.write(f"- {rec}\n")
        
        print(f"\n📄 진단 보고서 저장: {report_path}")
    
    def run_full_diagnostic(self):
        """전체 진단 실행"""
        print("🔍 FIREgenerator 데이터 진단 시작")
        print("=" * 60)
        
        # 데이터 로드
        if not self.load_evaluation_results():
            return
        
        self.load_user_data()
        
        # 분석 실행
        self.analyze_user_diversity()
        self.analyze_experiment_results()
        self.analyze_recommendation_overlap()
        self.analyze_config_impact()
        self.generate_diagnostic_report()
        
        print(f"\n✅ 진단 완료!")


def main():
    """메인 실행"""
    diagnostic = DataDiagnostic()
    diagnostic.run_full_diagnostic()


if __name__ == "__main__":
    main()
