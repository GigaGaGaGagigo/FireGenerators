"""
FIREgenerator 추천 시스템 평가 결과 분석기
A-E 단계별 결과를 보기 좋게 분석하고 시각화

Usage:
    python result_analyzer.py
"""

import json
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from datetime import datetime
import matplotlib
matplotlib.use('Agg')  # GUI 없는 환경 대응

# 한글 폰트 설정 (macOS 호환)
try:
    # macOS 기본 폰트들 시도
    import matplotlib.font_manager as fm
    available_fonts = [f.name for f in fm.fontManager.ttflist]
    
    if 'AppleGothic' in available_fonts:
        plt.rcParams['font.family'] = ['AppleGothic']
    elif 'Arial Unicode MS' in available_fonts:
        plt.rcParams['font.family'] = ['Arial Unicode MS']  
    elif 'Helvetica' in available_fonts:
        plt.rcParams['font.family'] = ['Helvetica']
    else:
        plt.rcParams['font.family'] = ['DejaVu Sans']
        print("⚠️ 한글 폰트를 찾을 수 없어 영어 폰트를 사용합니다")
    
    plt.rcParams['axes.unicode_minus'] = False
    print(f"✅ 폰트 설정 완료: {plt.rcParams['font.family']}")
    
except Exception as e:
    print(f"⚠️ 폰트 설정 실패: {e}")
    plt.rcParams['font.family'] = ['DejaVu Sans']

class ResultAnalyzer:
    """평가 결과 분석 및 시각화"""
    
    def __init__(self, result_dir):
        self.result_dir = Path(result_dir)
        self.summary_data = None
        self.detailed_data = None
        
    def load_latest_results(self):
        """최신 결과 파일 로드"""
        # 가장 최신 파일들 찾기
        summary_files = list(self.result_dir.glob("evaluation_summary_*.csv"))
        detailed_files = list(self.result_dir.glob("evaluation_detailed_*.json"))
        
        if not summary_files or not detailed_files:
            print("❌ 결과 파일이 없습니다. pipeline_evaluation.py를 먼저 실행하세요.")
            return False
        
        # 가장 최신 파일 선택
        latest_summary = max(summary_files, key=lambda x: x.stat().st_mtime)
        latest_detailed = max(detailed_files, key=lambda x: x.stat().st_mtime)
        
        print(f"📊 분석할 파일들:")
        print(f"  Summary: {latest_summary.name}")
        print(f"  Detailed: {latest_detailed.name}")
        
        # 데이터 로드
        try:
            self.summary_data = pd.read_csv(latest_summary)
            with open(latest_detailed, 'r', encoding='utf-8') as f:
                self.detailed_data = json.load(f)
            
            print(f"✅ 데이터 로드 완료")
            print(f"  실험 설정: {len(self.summary_data)}개")
            print(f"  상세 결과: {len(self.detailed_data)}개")
            return True
            
        except Exception as e:
            print(f"❌ 데이터 로드 실패: {e}")
            return False
    
    def analyze_summary(self):
        """요약 결과 분석"""
        if self.summary_data is None:
            return
        
        print("\n" + "="*50)
        print("📈 SUMMARY 분석")
        print("="*50)
        
        # 1. 전체 성능 순위
        print("\n🏆 전체 성능 순위 (종합 점수)")
        summary_sorted = self.summary_data.copy()
        
        # 종합 점수 계산
        summary_sorted['composite_score'] = (
            summary_sorted['avg_relevance'] * 0.4 +
            summary_sorted['avg_diversity'] * 0.3 +
            (summary_sorted['avg_count'] / 3.0).clip(upper=1.0) * 0.2 +
            summary_sorted['success_rate'] * 0.1
        )
        
        summary_sorted = summary_sorted.sort_values('composite_score', ascending=False)
        
        for i, (_, row) in enumerate(summary_sorted.head(10).iterrows(), 1):
            print(f"{i:2d}. {row['experiment']:<20} | "
                  f"종합: {row['composite_score']:.3f} | "
                  f"관련성: {row['avg_relevance']:.3f} | "
                  f"다양성: {row['avg_diversity']:.3f} | "
                  f"추천수: {row['avg_count']:.1f}")
        
        # 2. 단계별 최고 성능
        print("\n🎯 A-E 단계별 최고 성능")
        
        stages = {
            'A': 'A_search_',
            'B': 'B_filter_',
            'C': 'C_rerank_',
            'D': 'D_llm_',
            'E': 'E_prompt_'
        }
        
        for stage, prefix in stages.items():
            stage_data = summary_sorted[summary_sorted['experiment'].str.startswith(prefix)]
            if not stage_data.empty:
                best = stage_data.iloc[0]
                print(f"  {stage}단계: {best['experiment']:<20} | 종합: {best['composite_score']:.3f}")
        
        # 3. 성능 지표별 분석
        print(f"\n📊 성능 지표 통계")
        metrics = ['avg_relevance', 'avg_diversity', 'avg_count', 'success_rate']
        stats = self.summary_data[metrics].describe()
        print(stats.round(3))
        
        return summary_sorted
    
    def analyze_detailed_by_stage(self):
        """A-E 단계별 상세 분석"""
        if self.detailed_data is None:
            return
        
        print("\n" + "="*50)
        print("🔍 DETAILED 분석 (A-E 단계별)")
        print("="*50)
        
        # 상세 데이터를 DataFrame으로 변환
        detailed_df = pd.DataFrame(self.detailed_data)
        
        # 실험 단계 분류
        def get_stage(exp_name):
            if exp_name.startswith('A_'):
                return 'A_검색모델'
            elif exp_name.startswith('B_'):
                return 'B_필터링'
            elif exp_name.startswith('C_'):
                return 'C_리랭킹'
            elif exp_name.startswith('D_'):
                return 'D_LLM'
            elif exp_name.startswith('E_'):
                return 'E_프롬프트'
            elif exp_name == 'baseline':
                return 'Z_baseline'
            else:
                return 'X_기타'
        
        detailed_df['stage'] = detailed_df['experiment'].apply(get_stage)
        detailed_df['user_stage'] = detailed_df['stage'] + '_' + detailed_df['user_name']
        
        # 메트릭 추출
        detailed_df['success'] = detailed_df['metrics'].apply(lambda x: x.get('success', False))
        detailed_df['count'] = detailed_df['metrics'].apply(lambda x: x.get('count', 0))
        detailed_df['relevance'] = detailed_df['metrics'].apply(lambda x: x.get('relevance', 0.0))
        detailed_df['diversity'] = detailed_df['metrics'].apply(lambda x: x.get('diversity', 0.0))
        detailed_df['time_ms'] = detailed_df['metrics'].apply(lambda x: x.get('time_ms', 0.0))
        
        # 단계별 분석
        for stage in sorted(detailed_df['stage'].unique()):
            if stage == 'X_기타':
                continue
                
            stage_data = detailed_df[detailed_df['stage'] == stage]
            
            print(f"\n{'='*20} {stage} {'='*20}")
            
            # 실험별 성능
            stage_summary = stage_data.groupby('experiment').agg({
                'success': 'mean',
                'count': 'mean',
                'relevance': 'mean',
                'diversity': 'mean',
                'time_ms': 'mean'
            }).round(3)
            
            # 종합 점수 계산
            stage_summary['composite'] = (
                stage_summary['relevance'] * 0.4 +
                stage_summary['diversity'] * 0.3 +
                (stage_summary['count'] / 3.0).clip(upper=1.0) * 0.2 +
                stage_summary['success'] * 0.1
            ).round(3)
            
            stage_summary = stage_summary.sort_values('composite', ascending=False)
            print(stage_summary)
            
            # 최고/최저 성능
            if len(stage_summary) > 1:
                best_exp = stage_summary.index[0]
                worst_exp = stage_summary.index[-1]
                print(f"\n🏆 최고: {best_exp} (종합: {stage_summary.loc[best_exp, 'composite']:.3f})")
                print(f"📉 최저: {worst_exp} (종합: {stage_summary.loc[worst_exp, 'composite']:.3f})")
        
        return detailed_df
    
    def create_visualizations(self, summary_sorted, detailed_df):
        """시각화 생성"""
        print(f"\n📊 시각화 생성 중...")
        
        # 그래프 저장 폴더
        viz_dir = self.result_dir / "visualizations"
        viz_dir.mkdir(exist_ok=True)
        
        # 1. 전체 성능 비교 (상위 10개)
        plt.figure(figsize=(12, 8))
        top10 = summary_sorted.head(10)
        
        x = range(len(top10))
        width = 0.2
        
        plt.bar([i - width for i in x], top10['avg_relevance'], width, label='관련성', alpha=0.8)
        plt.bar([i for i in x], top10['avg_diversity'], width, label='다양성', alpha=0.8)
        plt.bar([i + width for i in x], top10['avg_count']/3, width, label='추천수(정규화)', alpha=0.8)
        
        plt.xlabel('실험 설정')
        plt.ylabel('점수')
        plt.title('상위 10개 실험 성능 비교')
        plt.xticks(x, [exp[:15] + '...' if len(exp) > 15 else exp for exp in top10['experiment']], rotation=45)
        plt.legend()
        plt.tight_layout()
        plt.savefig(viz_dir / 'top10_performance.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        # 2. 단계별 성능 박스플롯
        if detailed_df is not None and len(detailed_df) > 0:
            fig, axes = plt.subplots(2, 2, figsize=(15, 10))
            
            # 관련성
            detailed_df.boxplot(column='relevance', by='stage', ax=axes[0,0])
            axes[0,0].set_title('단계별 관련성 점수')
            axes[0,0].set_xlabel('단계')
            
            # 다양성
            detailed_df.boxplot(column='diversity', by='stage', ax=axes[0,1])
            axes[0,1].set_title('단계별 다양성 점수')
            axes[0,1].set_xlabel('단계')
            
            # 추천 개수
            detailed_df.boxplot(column='count', by='stage', ax=axes[1,0])
            axes[1,0].set_title('단계별 추천 개수')
            axes[1,0].set_xlabel('단계')
            
            # 응답 시간
            detailed_df.boxplot(column='time_ms', by='stage', ax=axes[1,1])
            axes[1,1].set_title('단계별 응답 시간')
            axes[1,1].set_xlabel('단계')
            
            plt.suptitle('A-E 단계별 성능 분포')
            plt.tight_layout()
            plt.savefig(viz_dir / 'stage_performance_boxplot.png', dpi=300, bbox_inches='tight')
            plt.close()
        
        # 3. 히트맵 (실험 x 지표)
        pivot_data = summary_sorted.head(15)[['experiment', 'avg_relevance', 'avg_diversity', 'avg_count', 'success_rate']].set_index('experiment')
        
        plt.figure(figsize=(10, 12))
        sns.heatmap(pivot_data, annot=True, fmt='.3f', cmap='YlOrRd', cbar_kws={'label': '점수'})
        plt.title('실험별 성능 히트맵 (상위 15개)')
        plt.ylabel('실험')
        plt.xlabel('성능 지표')
        plt.tight_layout()
        plt.savefig(viz_dir / 'performance_heatmap.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"✅ 시각화 완료! 저장 위치: {viz_dir}")
        print(f"  - top10_performance.png: 상위 10개 성능 비교")
        print(f"  - stage_performance_boxplot.png: 단계별 성능 분포")
        print(f"  - performance_heatmap.png: 실험별 성능 히트맵")
    
    def export_analysis_report(self, summary_sorted, detailed_df):
        """분석 보고서 내보내기"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = self.result_dir / f"analysis_report_{timestamp}.md"
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("# FIREgenerator 추천 시스템 평가 분석 보고서\n\n")
            f.write(f"생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            # 요약 통계
            f.write("## 📊 전체 성능 요약\n\n")
            f.write("### 상위 5개 실험 설정\n\n")
            f.write("| 순위 | 실험명 | 종합점수 | 관련성 | 다양성 | 추천수 | 성공률 |\n")
            f.write("|------|--------|----------|--------|--------|--------|--------|\n")
            
            for i, (_, row) in enumerate(summary_sorted.head(5).iterrows(), 1):
                f.write(f"| {i} | {row['experiment']} | {row['composite_score']:.3f} | "
                       f"{row['avg_relevance']:.3f} | {row['avg_diversity']:.3f} | "
                       f"{row['avg_count']:.1f} | {row['success_rate']:.1%} |\n")
            
            # A-E 단계별 최고 성능
            f.write("\n### A-E 단계별 최고 성능\n\n")
            f.write("| 단계 | 최고 성능 실험 | 종합점수 |\n")
            f.write("|------|----------------|----------|\n")
            
            stages = {'A': 'A_search_', 'B': 'B_filter_', 'C': 'C_rerank_', 'D': 'D_llm_', 'E': 'E_prompt_'}
            for stage, prefix in stages.items():
                stage_data = summary_sorted[summary_sorted['experiment'].str.startswith(prefix)]
                if not stage_data.empty:
                    best = stage_data.iloc[0]
                    f.write(f"| {stage}단계 | {best['experiment']} | {best['composite_score']:.3f} |\n")
            
            # 결론 및 권장사항
            f.write("\n## 💡 단계별 결론 및 권장사항\n\n")
            
            stage_names = {
                'A': 'A. 검색 모델',
                'B': 'B. 필터링 전략',
                'C': 'C. 리랭킹 계수',
                'D': 'D. LLM 리랭킹',
                'E': 'E. 프롬프트 전략'
            }

            for stage_code, prefix in stages.items():
                stage_data = summary_sorted[summary_sorted['experiment'].str.startswith(prefix)]
                if not stage_data.empty:
                    best_in_stage = stage_data.iloc[0]
                    f.write(f"### {stage_names.get(stage_code, '알 수 없는 단계')}\n\n")
                    f.write(f"- **최적 설정**: `{best_in_stage['experiment']}`\n")
                    f.write(f"  - **종합 점수**: {best_in_stage['composite_score']:.3f} (관련성: {best_in_stage['avg_relevance']:.3f}, 다양성: {best_in_stage['avg_diversity']:.3f})\n")
                    
                    if len(stage_data) > 1:
                        second_best = stage_data.iloc[1]
                        if (best_in_stage['composite_score'] - second_best['composite_score']) < 0.05:
                             f.write(f"  - **참고**: `{second_best['experiment']}`도 유사한 성능을 보였습니다 (점수: {second_best['composite_score']:.3f}).\n")
                    
                    f.write(f"- **권장사항**: 현재 단계에서는 **`{best_in_stage['experiment'].replace(prefix, '')}`** 설정을 사용하는 것을 권장합니다.\n\n")

            f.write("\n### 종합 권장사항\n")
            f.write("각 단계별 최적 설정을 조합하여 최종 추천 파이프라인을 구성하는 것을 권장합니다. "
                    "각 단계의 최적 설정이 서로에게 미치는 영향을 고려하여 통합 테스트를 추가로 진행하는 것이 좋습니다.\n")
        
        print(f"📝 분석 보고서 생성: {report_path}")
        return report_path


def main():
    """메인 실행 함수"""
    print("🔍 FIREgenerator 평가 결과 분석기 시작")
    
    # 결과 디렉토리 설정
    result_dir = Path(__file__).parent / "final_result"
    
    if not result_dir.exists():
        print("❌ final_result 폴더가 없습니다.")
        return
    
    # 분석기 초기화
    analyzer = ResultAnalyzer(result_dir)
    
    # 데이터 로드
    if not analyzer.load_latest_results():
        return
    
    # 요약 분석
    summary_sorted = analyzer.analyze_summary()
    
    # 상세 분석 (A-E 단계별)
    detailed_df = analyzer.analyze_detailed_by_stage()
    
    # 시각화 생성
    if summary_sorted is not None:
        analyzer.create_visualizations(summary_sorted, detailed_df)
    
    # 분석 보고서 생성
    if summary_sorted is not None:
        analyzer.export_analysis_report(summary_sorted, detailed_df)
    
    print("\n✅ 분석 완료!")


if __name__ == "__main__":
    main()
