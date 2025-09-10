"""
Human Feedback 수집기
LLM Judge 결과를 보고 사람이 직접 평가

사용법:
1. python llm_judge_integrated.py 실행 (LLM 평가 완료)
2. python human_feedback_collector.py 실행
3. 콘솔에서 각 결과에 1-5점 평가
"""

import json
import pandas as pd
from pathlib import Path
from datetime import datetime
import os
from dotenv import load_dotenv

# 환경변수 로드
project_root = Path(__file__).resolve().parents[3]
load_dotenv(project_root / '.env')

# Langfuse 설정
try:
    from langfuse import Langfuse
    langfuse = Langfuse(
        secret_key=os.getenv('LANGFUES_SECRET_KEY'),
        public_key=os.getenv('LANGFUES_PUBLIC_KEY'),
        host=os.getenv('LANGFUES_HOST', 'https://us.cloud.langfuse.com')
    )
    print("✅ Langfuse 연결 성공")
except ImportError:
    langfuse = None
    print("⚠️ Langfuse 연결 실패")


class HumanFeedbackCollector:
    """Human Feedback 수집기"""
    
    def __init__(self):
        self.result_dir = Path(__file__).parent / "final_result"
        self.feedback_results = []
    
    def load_llm_results(self):
        """최신 LLM 평가 결과 로드"""
        llm_files = list(self.result_dir.glob("llm_evaluation_detailed_*.json"))
        
        if not llm_files:
            print("❌ LLM 평가 결과가 없습니다. llm_judge_integrated.py를 먼저 실행하세요.")
            return None
        
        latest_file = max(llm_files, key=lambda x: x.stat().st_mtime)
        print(f"📂 로드할 파일: {latest_file.name}")
        
        with open(latest_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def display_recommendation(self, result):
        """추천 결과를 보기 좋게 표시"""
        print(f"\n{'='*60}")
        print(f"🧪 실험: {result['experiment_id']}")
        print(f"👤 사용자: {result['user_name']}")
        print(f"📊 Rule-based 점수: {result['rule_based_score']:.3f}")
        print(f"🤖 LLM 평균 점수: {result['average_llm_score']:.3f}")
        print(f"{'='*60}")
        
        print(f"\n📋 추천된 콘텐츠들:")
        for i, rec in enumerate(result['recommendations'], 1):
            print(f"\n{i}. 📖 {rec.get('title', 'N/A')}")
            print(f"   💡 {rec.get('content', 'N/A')[:150]}...")
            print(f"   🎯 난이도: {rec.get('level', 'N/A')}")
            print(f"   🏷️ 태그: {', '.join(rec.get('tags', []))}")
        
        # LLM 모델별 점수 표시
        print(f"\n🤖 LLM 모델별 점수:")
        for model, score in result['llm_scores'].items():
            print(f"   {model}: {score:.2f}점")
        
        # LLM 평가 이유 (첫 번째 모델 것만)
        if result['llm_reasoning']:
            first_reasoning = list(result['llm_reasoning'].values())[0]
            print(f"\n💭 LLM 평가 이유:")
            print(f"   {first_reasoning}")
    
    def get_human_feedback(self, result):
        """사람의 피드백 입력받기"""
        while True:
            try:
                print(f"\n🙋 당신의 평가를 입력하세요:")
                print(f"   1점: 매우 나쁨")
                print(f"   2점: 나쁨") 
                print(f"   3점: 보통")
                print(f"   4점: 좋음")
                print(f"   5점: 매우 좋음")
                
                score = input("점수 (1-5): ").strip()
                
                if score in ['1', '2', '3', '4', '5']:
                    score = int(score)
                    break
                else:
                    print("❌ 1-5 사이의 숫자를 입력하세요.")
            
            except KeyboardInterrupt:
                print("\n\n👋 평가를 중단합니다.")
                return None, None
        
        # 코멘트 입력
        print(f"\n💬 추가 의견이 있으시면 입력하세요 (엔터로 건너뛰기):")
        comment = input("의견: ").strip()
        
        return score, comment if comment else "의견 없음"
    
    def save_to_langfuse(self, result, human_score, human_comment):
        """Langfuse에 Human Feedback 저장"""
        if not langfuse:
            return None
        
        try:
            # 해당 결과의 trace ID가 있으면 사용
            trace_ids = result.get('langfuse_trace_ids', {})
            
            if trace_ids:
                # 첫 번째 trace에 human feedback 추가
                first_trace_id = list(trace_ids.values())[0]
                
                score = langfuse.score(
                    name="human_feedback",
                    value=human_score,
                    trace_id=first_trace_id,
                    comment=f"Human: {human_comment}"
                )
                
                print(f"✅ Langfuse에 저장됨 (Score ID: {score.id})")
                return score.id
            else:
                # 새로운 trace 생성
                trace = langfuse.trace(
                    name="human_feedback_evaluation",
                    metadata={
                        "experiment_id": result['experiment_id'],
                        "user_name": result['user_name'],
                        "evaluation_type": "human_feedback"
                    }
                )
                
                score = langfuse.score(
                    name="human_feedback",
                    value=human_score,
                    trace_id=trace.id,
                    comment=f"Human: {human_comment}"
                )
                
                print(f"✅ Langfuse에 새 trace로 저장됨 (Score ID: {score.id})")
                return score.id
                
        except Exception as e:
            print(f"⚠️ Langfuse 저장 실패: {e}")
            return None
    
    def collect_all_feedback(self):
        """모든 LLM 결과에 대해 Human Feedback 수집"""
        print("🙋 Human Feedback 수집기 시작")
        
        # LLM 결과 로드
        llm_results = self.load_llm_results()
        if not llm_results:
            return
        
        print(f"📊 평가할 결과: {len(llm_results)}개")
        print("💡 Ctrl+C로 언제든지 중단 가능합니다.")
        
        completed = 0
        
        for i, result in enumerate(llm_results, 1):
            print(f"\n\n[{i}/{len(llm_results)}] 평가 진행 중...")
            
            # 추천 결과 표시
            self.display_recommendation(result)
            
            # Human Feedback 입력
            human_score, human_comment = self.get_human_feedback(result)
            
            if human_score is None:  # 중단됨
                break
            
            # 결과 저장
            feedback_record = {
                'experiment_id': result['experiment_id'],
                'user_name': result['user_name'],
                'human_score': human_score,
                'human_comment': human_comment,
                'rule_based_score': result['rule_based_score'],
                'llm_average_score': result['average_llm_score'],
                'llm_scores': result['llm_scores'],
                'timestamp': datetime.now().isoformat(),
                'langfuse_score_id': None
            }
            
            # Langfuse에 저장
            langfuse_id = self.save_to_langfuse(result, human_score, human_comment)
            feedback_record['langfuse_score_id'] = langfuse_id
            
            self.feedback_results.append(feedback_record)
            completed += 1
            
            print(f"✅ 피드백 저장 완료 ({completed}개 완료)")
        
        # 최종 결과 저장
        if self.feedback_results:
            self.save_feedback_results()
            self.print_summary()
    
    def save_feedback_results(self):
        """Human Feedback 결과 파일로 저장"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # JSON 상세 결과
        json_path = self.result_dir / f"human_feedback_{timestamp}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(self.feedback_results, f, ensure_ascii=False, indent=2)
        
        # CSV 요약
        csv_data = []
        for record in self.feedback_results:
            csv_data.append({
                'experiment_id': record['experiment_id'],
                'user_name': record['user_name'],
                'human_score': record['human_score'],
                'rule_based_score': record['rule_based_score'],
                'llm_average_score': record['llm_average_score'],
                'human_vs_rule_diff': record['human_score'] - record['rule_based_score'],
                'human_vs_llm_diff': record['human_score'] - record['llm_average_score'],
                'comment': record['human_comment'],
                'timestamp': record['timestamp']
            })
        
        csv_df = pd.DataFrame(csv_data)
        csv_path = self.result_dir / f"human_feedback_summary_{timestamp}.csv"
        csv_df.to_csv(csv_path, index=False, encoding='utf-8-sig')
        
        print(f"\n💾 Human Feedback 결과 저장:")
        print(f"  상세: {json_path}")
        print(f"  요약: {csv_path}")
    
    def print_summary(self):
        """결과 요약 출력"""
        if not self.feedback_results:
            return
        
        import numpy as np
        
        human_scores = [r['human_score'] for r in self.feedback_results]
        rule_scores = [r['rule_based_score'] for r in self.feedback_results]
        llm_scores = [r['llm_average_score'] for r in self.feedback_results]
        
        print(f"\n📊 Human Feedback 요약:")
        print(f"  총 평가 개수: {len(human_scores)}개")
        print(f"  Human 평균: {np.mean(human_scores):.3f}")
        print(f"  Rule 평균: {np.mean(rule_scores):.3f}")
        print(f"  LLM 평균: {np.mean(llm_scores):.3f}")
        
        # 상관계수
        human_rule_corr = np.corrcoef(human_scores, rule_scores)[0,1]
        human_llm_corr = np.corrcoef(human_scores, llm_scores)[0,1]
        
        print(f"\n🔗 상관계수:")
        print(f"  Human vs Rule: {human_rule_corr:.3f}")
        print(f"  Human vs LLM: {human_llm_corr:.3f}")
        
        # 가장 차이나는 케이스
        differences = [abs(h - l) for h, l in zip(human_scores, llm_scores)]
        max_diff_idx = np.argmax(differences)
        max_diff_case = self.feedback_results[max_diff_idx]
        
        print(f"\n📈 Human vs LLM 최대 차이 케이스:")
        print(f"  실험: {max_diff_case['experiment_id']}")
        print(f"  사용자: {max_diff_case['user_name']}")
        print(f"  Human: {max_diff_case['human_score']} vs LLM: {max_diff_case['llm_average_score']:.2f}")
        print(f"  의견: {max_diff_case['human_comment']}")


def main():
    """메인 실행"""
    collector = HumanFeedbackCollector()
    collector.collect_all_feedback()
    
    print(f"\n🎉 Human Feedback 수집 완료!")
    print(f"📊 Langfuse 대시보드: https://us.cloud.langfuse.com")


if __name__ == "__main__":
    main()