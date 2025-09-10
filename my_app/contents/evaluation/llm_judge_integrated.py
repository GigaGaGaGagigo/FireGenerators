"""
FIREgenerator LLM Judge 통합 평가 시스템
pipeline_evaluation.py 결과를 받아서 LLM으로 정밀 평가

사용법:
1. python pipeline_evaluation.py (1차 평가)
2. python result_analyzer.py (시각화)  
3. python llm_judge_integrated.py (2차 LLM 평가)
"""

import os
import sys
import json
import time
import pandas as pd
import numpy as np 
import asyncio
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# 환경변수 로드
project_root = Path(__file__).resolve().parents[3]  # FireGenerators/
load_dotenv(project_root / '.env')

# 추천 시스템 경로 설정 (실제 추천 실행을 위해)
current_file = Path(__file__).resolve()
my_app_dir = current_file.parents[3]
contents_dir = current_file.parents[2]  
rec_dir = contents_dir / "recommendation"

for path in [str(rec_dir), str(contents_dir), str(my_app_dir)]:
    if path not in sys.path:
        sys.path.insert(0, path)

# LLM 클라이언트들
try:
    import openai
    openai.api_key = os.getenv('OPENAI_API_KEY')
except ImportError:
    openai = None

try:
    import google.generativeai as genai
    genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
except ImportError:
    genai = None

try:
    import anthropic
    anthropic_client = anthropic.Anthropic(api_key=os.getenv('CLAUDE_API_KEY'))
except ImportError:
    anthropic_client = None

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

# 추천 시스템 import
try:
    from hybrid_recommender_v2 import get_hybrid_recommendations, get_supabase_client
    print("✅ 추천 시스템 연결 성공")
except ImportError as e:
    print(f"⚠️ 추천 시스템 연결 실패: {e}")
    def get_hybrid_recommendations(*args, **kwargs):
        return {"success": False, "results": [], "error": "Import failed"}
    def get_supabase_client():
        return None


@dataclass
class LLMEvaluationResult:
    """LLM 평가 결과"""
    experiment_id: str
    user_id: str
    user_name: str
    recommendations: List[Dict]
    llm_scores: Dict[str, float]  # {model: score}
    llm_reasoning: Dict[str, str]  # {model: reasoning}
    average_llm_score: float
    rule_based_score: float
    langfuse_trace_ids: Dict[str, str]  # {model: trace_id}
    evaluation_time: float
    timestamp: str


class LLMJudgeIntegrated:
    """pipeline_evaluation.py 결과와 통합된 LLM Judge"""
    
    def __init__(self):
        """초기화"""
        self.result_dir = Path(__file__).parent / "final_result"
        self.supabase = get_supabase_client()
        self.load_user_data()
        
        # 평가 프롬프트
        self.evaluation_prompt = self._create_evaluation_prompt()
    
    def load_user_data(self):
        """사용자 데이터 로드"""
        try:
            if self.supabase:
                response = self.supabase.table("profiles_test").select("*").execute()
                self.users = {user['id']: user for user in response.data}
                print(f"👥 사용자 데이터 로드: {len(self.users)}명")
            else:
                self.users = {}
        except Exception as e:
            print(f"❌ 사용자 데이터 로드 실패: {e}")
            self.users = {}
    
    def _create_evaluation_prompt(self):
        """LLM 평가 프롬프트 생성"""
        return """
당신은 금융 교육 콘텐츠 추천 시스템의 전문 평가자입니다.

**사용자 정보:**
- 이름: {user_name}
- 관심사: {interests}
- 감정 상태: {emotions}
- 지식 수준: {knowledge_level}
- 투자 목표: {goals}

**추천된 콘텐츠들:**
{recommendations_text}

**평가 기준:**
다음 4가지 관점에서 이 추천의 품질을 1-5점으로 평가하세요:

1. **관련성 (Relevance)**: 사용자 관심사와 얼마나 잘 맞는가?
2. **적합성 (Suitability)**: 사용자 지식 수준에 적합한가?
3. **다양성 (Diversity)**: 추천 콘텐츠들이 다양한 관점을 제공하는가?
4. **실용성 (Practicality)**: 실제로 사용자에게 도움이 될 것인가?

**응답 형식 (JSON):**
{{
    "relevance_score": [1-5],
    "suitability_score": [1-5], 
    "diversity_score": [1-5],
    "practicality_score": [1-5],
    "overall_score": [1-5],
    "detailed_reasoning": "구체적인 평가 이유를 3-4문장으로 설명"
}}
"""
    
    def load_pipeline_results(self):
        """pipeline_evaluation.py 결과 파일 로드"""
        # 최신 상세 결과 파일 찾기
        detailed_files = list(self.result_dir.glob("evaluation_detailed_*.json"))
        if not detailed_files:
            print("❌ pipeline_evaluation.py 결과 파일이 없습니다.")
            return None
        
        latest_file = max(detailed_files, key=lambda x: x.stat().st_mtime)
        print(f"📂 로드할 파일: {latest_file.name}")
        
        with open(latest_file, 'r', encoding='utf-8') as f:
            detailed_results = json.load(f)
        
        return detailed_results
    
    def select_top_experiments(self, detailed_results: List[Dict], top_n: int = 5) -> List[str]:
        """상위 N개 실험 설정 선택"""
        # 실험별 성능 계산
        experiment_scores = {}
        
        for result in detailed_results:
            exp_id = result['experiment']
            if exp_id not in experiment_scores:
                experiment_scores[exp_id] = []
            
            metrics = result['metrics']
            if metrics['success']:
                # 종합 점수 계산 (pipeline_evaluation.py와 동일한 공식)
                composite = (
                    metrics['relevance'] * 0.4 +
                    metrics['diversity'] * 0.3 +
                    min(metrics['count'] / 3.0, 1.0) * 0.2 +
                    1.0 * 0.1  # success=True이므로 1.0
                )
                experiment_scores[exp_id].append(composite)
        
        # 실험별 평균 점수
        avg_scores = {}
        for exp_id, scores in experiment_scores.items():
            if scores:
                avg_scores[exp_id] = np.mean(scores)
        
        # 상위 N개 선택
        top_experiments = sorted(avg_scores.items(), key=lambda x: x[1], reverse=True)[:top_n]
        top_exp_ids = [exp_id for exp_id, _ in top_experiments]
        
        print(f"🏆 선정된 상위 {len(top_exp_ids)}개 실험:")
        for i, (exp_id, score) in enumerate(top_experiments, 1):
            print(f"  {i}. {exp_id}: {score:.3f}")
        
        return top_exp_ids
    
    def get_actual_recommendations(self, user_profile: Dict, experiment_config: Dict) -> List[Dict]:
        """실제 추천 시스템을 실행해서 추천 결과 받기"""
        # 사용자 컨텍스트 생성 (pipeline_evaluation.py와 동일)
        def safe_eval(field):
            try:
                return eval(field) if isinstance(field, str) and field.strip() else []
            except:
                return []
        
        user_context = {
            'user_id': user_profile.get('id', 'unknown'),
            'name': user_profile.get('name', 'Unknown'),
            'interests': safe_eval(user_profile.get('interests_categories', [])),
            'emotions': safe_eval(user_profile.get('investment_emotions', [])),
            'goals': safe_eval(user_profile.get('investment_goal', [])),
            'knowledge_level': user_profile.get('knowledge_level', 'Beginner'),
            'level': user_profile.get('knowledge_level', 'Beginner'),
            'interest_tags': safe_eval(user_profile.get('interests_categories', [])),
            'recent_seen_card_ids': [],
            'liked_tags': []
        }
        
        try:
            # 추천 실행
            result = get_hybrid_recommendations(
                user=user_context,
                top_n=10,
                use_llm_rerank=(experiment_config.get('llm', 'none') != 'none')
            )
            
            if result.get('success'):
                return result.get('results', [])
            else:
                return []
                
        except Exception as e:
            print(f"⚠️ 추천 실행 실패: {e}")
            return []
    
    async def evaluate_with_llm(self, user_profile: Dict, recommendations: List[Dict], llm_model: str) -> Dict:
        """특정 LLM 모델로 평가"""
        # Langfuse 트레이스 시작
        trace = None
        if langfuse:
            trace = langfuse.trace(
                name="llm_judge_evaluation",
                metadata={
                    "user_id": user_profile.get('id'),
                    "llm_model": llm_model,
                    "num_recommendations": len(recommendations)
                }
            )
        
        try:
            # 프롬프트 생성
            def safe_eval(field):
                try:
                    return eval(field) if isinstance(field, str) else []
                except:
                    return []
            
            recommendations_text = ""
            for i, rec in enumerate(recommendations, 1):
                recommendations_text += f"{i}. 제목: {rec.get('title', 'N/A')}\n"
                recommendations_text += f"   내용: {rec.get('content', 'N/A')[:100]}...\n"
                recommendations_text += f"   난이도: {rec.get('level', 'N/A')}\n"
                recommendations_text += f"   태그: {', '.join(rec.get('tags', []))}\n\n"
            
            prompt = self.evaluation_prompt.format(
                user_name=user_profile.get('name', 'Unknown'),
                interests=', '.join(safe_eval(user_profile.get('interests_categories', []))),
                emotions=', '.join(safe_eval(user_profile.get('investment_emotions', []))),
                knowledge_level=user_profile.get('knowledge_level', 'Unknown'),
                goals=', '.join(safe_eval(user_profile.get('investment_goal', []))),
                recommendations_text=recommendations_text
            )
            
            # LLM 호출
            response = await self._call_llm(prompt, llm_model)
            
            # 응답 파싱
            evaluation = self._parse_llm_response(response)
            
            # Langfuse에 기록
            if trace:
                trace.score(
                    name="llm_evaluation_score",
                    value=evaluation.get('overall_score', 0),
                    comment=f"LLM: {llm_model}"
                )
                trace.update(
                    input={"prompt": prompt[:500] + "..."},
                    output=evaluation
                )
            
            return {
                "success": True,
                "evaluation": evaluation,
                "trace_id": trace.id if trace else None
            }
            
        except Exception as e:
            print(f"❌ LLM 평가 실패 ({llm_model}): {e}")
            
            if trace:
                trace.update(
                    level="ERROR",
                    status_message=str(e)
                )
            
            return {
                "success": False,
                "error": str(e),
                "trace_id": trace.id if trace else None
            }
    
    async def _call_llm(self, prompt: str, model: str) -> str:
        """LLM API 호출"""
        if model == "gpt-4o-mini" and openai:
            try:
                response = openai.ChatCompletion.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=1000
                )
                return response.choices[0].message.content
            except Exception as e:
                print(f"OpenAI API 오류: {e}")
                raise e
        
        elif model == "gemini-flash" and genai:
            try:
                model_instance = genai.GenerativeModel('gemini-1.5-flash')
                response = model_instance.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.1,
                        max_output_tokens=1000
                    )
                )
                return response.text
            except Exception as e:
                print(f"Gemini API 오류: {e}")
                raise e
        
        elif model == "claude" and anthropic_client:
            try:
                response = anthropic_client.messages.create(
                    model="claude-3-haiku-20240307",
                    max_tokens=1000,
                    temperature=0.1,
                    messages=[{"role": "user", "content": prompt}]
                )
                return response.content[0].text
            except Exception as e:
                print(f"Claude API 오류: {e}")
                raise e
        
        else:
            raise ValueError(f"지원되지 않는 모델: {model}")
    
    def _parse_llm_response(self, response: str) -> Dict:
        """LLM 응답 파싱"""
        try:
            # JSON 부분 추출 시도
            start = response.find('{')
            end = response.rfind('}') + 1
            
            if start != -1 and end > start:
                json_str = response[start:end]
                parsed = json.loads(json_str)
                
                # 필수 필드 확인 및 기본값 설정
                return {
                    "relevance_score": float(parsed.get("relevance_score", 0)),
                    "suitability_score": float(parsed.get("suitability_score", 0)),
                    "diversity_score": float(parsed.get("diversity_score", 0)),
                    "practicality_score": float(parsed.get("practicality_score", 0)),
                    "overall_score": float(parsed.get("overall_score", 0)),
                    "detailed_reasoning": str(parsed.get("detailed_reasoning", "파싱 실패"))
                }
            else:
                # JSON이 없으면 숫자만 추출
                import re
                numbers = re.findall(r'\b[1-5]\b', response)
                if len(numbers) >= 5:
                    return {
                        "relevance_score": float(numbers[0]),
                        "suitability_score": float(numbers[1]),
                        "diversity_score": float(numbers[2]),
                        "practicality_score": float(numbers[3]),
                        "overall_score": float(numbers[4]),
                        "detailed_reasoning": "숫자만 추출됨"
                    }
                else:
                    raise ValueError("점수를 찾을 수 없음")
                    
        except Exception as e:
            print(f"⚠️ LLM 응답 파싱 실패: {e}")
            return {
                "relevance_score": 0.0,
                "suitability_score": 0.0,
                "diversity_score": 0.0,
                "practicality_score": 0.0,
                "overall_score": 0.0,
                "detailed_reasoning": f"파싱 실패: {str(e)}"
            }
    
    async def run_llm_evaluation(self, top_n_experiments: int = 10, 
                                max_users: int = 20,
                                llm_models: List[str] = ["gpt-4o-mini"]) -> List[LLMEvaluationResult]:
        """LLM 평가 실행"""
        print(f"🤖 LLM Judge 평가 시작")
        print(f"  상위 {top_n_experiments}개 실험 × {max_users}명 사용자 × {len(llm_models)}개 LLM")
        
        # 1. pipeline_evaluation.py 결과 로드
        detailed_results = self.load_pipeline_results()
        if not detailed_results:
            return []
        
        # 2. 상위 실험 선정
        top_experiments = self.select_top_experiments(detailed_results, top_n_experiments)
        
        # 3. 사용자 샘플 선택
        sample_users = list(self.users.values())[:max_users]
        print(f"👥 평가 대상 사용자: {len(sample_users)}명")
        
        # 4. 각 조합별 LLM 평가
        all_results = []
        
        for exp_id in top_experiments:
            # 실험 설정 추출 (pipeline_evaluation.py 결과에서)
            exp_config = self._extract_experiment_config(detailed_results, exp_id)
            
            for user in sample_users:
                print(f"\n🔬 [{exp_id}] {user['name']} 평가 중...")
                
                # 실제 추천 실행
                recommendations = self.get_actual_recommendations(user, exp_config)
                
                if not recommendations:
                    print("  ⚠️ 추천 결과가 없어 평가 건너뜀")
                    continue
                
                # 기존 rule-based 점수 (pipeline_evaluation.py와 동일 방식)
                rule_score = self._calculate_rule_based_score(recommendations, user)
                
                # LLM 모델별 평가
                llm_scores = {}
                llm_reasoning = {}
                trace_ids = {}
                
                for llm_model in llm_models:
                    print(f"    🤖 {llm_model} 평가 중...")
                    
                    try:
                        result = await self.evaluate_with_llm(user, recommendations, llm_model)
                        
                        if result['success']:
                            evaluation = result['evaluation']
                            llm_scores[llm_model] = evaluation['overall_score']
                            llm_reasoning[llm_model] = evaluation['detailed_reasoning']
                            trace_ids[llm_model] = result.get('trace_id')
                            print(f"      ✅ 점수: {evaluation['overall_score']:.2f}")
                        else:
                            print(f"      ❌ 평가 실패: {result['error']}")
                            llm_scores[llm_model] = 0.0
                            llm_reasoning[llm_model] = f"평가 실패: {result['error']}"
                    
                    except Exception as e:
                        print(f"      ❌ 평가 중 오류: {e}")
                        llm_scores[llm_model] = 0.0
                        llm_reasoning[llm_model] = f"오류: {str(e)}"
                
                # 결과 저장
                avg_llm_score = np.mean(list(llm_scores.values())) if llm_scores else 0.0
                
                result = LLMEvaluationResult(
                    experiment_id=exp_id,
                    user_id=user['id'],
                    user_name=user['name'],
                    recommendations=recommendations,
                    llm_scores=llm_scores,
                    llm_reasoning=llm_reasoning,
                    average_llm_score=avg_llm_score,
                    rule_based_score=rule_score,
                    langfuse_trace_ids=trace_ids,
                    evaluation_time=0.0,  # TODO: 시간 측정
                    timestamp=datetime.now().isoformat()
                )
                
                all_results.append(result)
                
                print(f"  📊 Rule-based: {rule_score:.3f} | LLM 평균: {avg_llm_score:.3f}")
        
        # 결과 저장
        self.save_llm_results(all_results)
        
        print(f"\n✅ LLM Judge 평가 완료! 총 {len(all_results)}개 결과")
        return all_results
    
    def _extract_experiment_config(self, detailed_results: List[Dict], exp_id: str) -> Dict:
        """실험 설정 추출"""
        for result in detailed_results:
            if result['experiment'] == exp_id:
                return result.get('config', {})
        return {}
    
    def _calculate_rule_based_score(self, recommendations: List[Dict], user: Dict) -> float:
        """Rule-based 점수 계산 (pipeline_evaluation.py와 동일)"""
        if not recommendations:
            return 0.0
        
        def safe_eval(field):
            try:
                return eval(field) if isinstance(field, str) and field.strip() else []
            except:
                return []
        
        user_interests = set(safe_eval(user.get('interests_categories', [])))
        user_level = user.get('knowledge_level', 'Beginner')
        
        total_score = 0.0
        for rec in recommendations:
            score = 0.0
            
            # 관심사 매칭 (50%)
            rec_tags = set(rec.get('tags', []))
            if user_interests & rec_tags:
                score += 0.5
            
            # 레벨 매칭 (50%)
            if rec.get('level') == user_level:
                score += 0.5
            elif abs(self._level_to_num(rec.get('level')) - self._level_to_num(user_level)) <= 1:
                score += 0.25
            
            total_score += score
        
        return total_score / len(recommendations)
    
    def _level_to_num(self, level: str) -> int:
        """레벨을 숫자로 변환"""
        mapping = {'Beginner': 1, 'Intermediate': 2, 'Advanced': 3}
        return mapping.get(level, 1)
    
    def save_llm_results(self, results: List[LLMEvaluationResult]):
        """LLM 평가 결과 저장"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # JSON 상세 결과
        detailed_path = self.result_dir / f"llm_evaluation_detailed_{timestamp}.json"
        with open(detailed_path, 'w', encoding='utf-8') as f:
            json.dump([asdict(r) for r in results], f, ensure_ascii=False, indent=2)
        
        # CSV 요약 결과
        summary_data = []
        for r in results:
            row = {
                'experiment_id': r.experiment_id,
                'user_name': r.user_name,
                'num_recommendations': len(r.recommendations),
                'rule_based_score': r.rule_based_score,
                'average_llm_score': r.average_llm_score,
                'score_difference': r.average_llm_score - r.rule_based_score,
                **r.llm_scores,  # 각 LLM 모델별 점수
                'timestamp': r.timestamp
            }
            summary_data.append(row)
        
        summary_df = pd.DataFrame(summary_data)
        csv_path = self.result_dir / f"llm_evaluation_summary_{timestamp}.csv"
        summary_df.to_csv(csv_path, index=False, encoding='utf-8-sig')
        
        print(f"💾 LLM 평가 결과 저장:")
        print(f"  상세: {detailed_path}")
        print(f"  요약: {csv_path}")


async def main():
    """메인 실행"""
    print("🤖 FIREgenerator LLM Judge 통합 평가 시작")
    
    evaluator = LLMJudgeIntegrated()
    
    # LLM 평가 실행
    results = await evaluator.run_llm_evaluation(
        top_n_experiments=10,    # 상위 10개 실험만
        max_users=20,           # 20명 사용자만
        llm_models=["gpt-4o-mini", "gemini-flash", "claude"]  # 3개 LLM
    )
    
    if results:
        # 간단한 비교 분석
        print(f"\n📊 Rule-based vs LLM 비교:")
        rule_scores = [r.rule_based_score for r in results]
        llm_scores = [r.average_llm_score for r in results]
        
        print(f"  Rule-based 평균: {np.mean(rule_scores):.3f}")
        print(f"  LLM 평균: {np.mean(llm_scores):.3f}")
        print(f"  상관계수: {np.corrcoef(rule_scores, llm_scores)[0,1]:.3f}")
        
        # 차이가 큰 케이스 찾기
        max_diff_idx = np.argmax([abs(r.average_llm_score - r.rule_based_score) for r in results])
        max_diff = results[max_diff_idx]
        print(f"  최대 차이: {max_diff.experiment_id} - {max_diff.user_name}")
        print(f"    Rule: {max_diff.rule_based_score:.3f} vs LLM: {max_diff.average_llm_score:.3f}")


if __name__ == "__main__":
    asyncio.run(main())