"""
LLM Judge 평가 스크립트 (CSV 기반)
데이터베이스 연결 없이 CSV 파일만으로 LLM 평가 실행

사용법:
python llm_judge.py
"""

import os
import json
import pandas as pd
import numpy as np
import asyncio
from typing import Dict, List
from dataclasses import dataclass, asdict
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# 환경변수 로드
project_root = Path(__file__).resolve().parents[3]  # FireGenerators/
load_dotenv(project_root / '.env')

# 추천 시스템 경로 설정
current_file = Path(__file__).resolve()
contents_dir = current_file.parents[1]  # my_app/contents/
rec_dir = contents_dir / "recommendation"

# sys.path에 추천 시스템 경로 추가
import sys
for path in [str(rec_dir), str(contents_dir)]:
    if path not in sys.path:
        sys.path.insert(0, path)

# 파일 존재 확인
hybrid_file = rec_dir / "hybrid_recommender_v2.py"
explanation_file = rec_dir / "explanation_generator.py"

print(f"📁 추천 시스템 디렉토리: {rec_dir}")
print(f"📄 hybrid_recommender_v2.py 존재: {hybrid_file.exists()}")
print(f"📄 explanation_generator.py 존재: {explanation_file.exists()}")

# LLM 클라이언트들
try:
    import openai
    print(f"📦 OpenAI 버전: {openai.__version__}")
    if os.getenv('OPENAI_API_KEY'):
        print("✅ OpenAI API 연결")
    else:
        print("⚠️ OpenAI API 키 없음")
        openai = None
except ImportError:
    openai = None
    print("❌ OpenAI 라이브러리 없음")

try:
    import google.generativeai as genai
    genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
    print("✅ Google Gemini API 연결")
except ImportError:
    genai = None
    print("❌ Google Gemini 라이브러리 없음")

try:
    import anthropic
    anthropic_client = anthropic.Anthropic(api_key=os.getenv('CLAUDE_API_KEY'))
    print("✅ Claude API 연결")
except ImportError:
    anthropic_client = None
    print("❌ Anthropic 라이브러리 없음")

# 추천 시스템 import
print(f"🔍 현재 Python 경로: {sys.path[:3]}...")  # 처음 3개만 출력

# 추천 시스템 함수들을 동적으로 로드
get_hybrid_recommendations = None
generate_explanation = None

try:
    print("📦 추천 시스템 import 시도 중...")
    import importlib.util
    
    # hybrid_recommender_v2.py 로드
    spec = importlib.util.spec_from_file_location("hybrid_recommender_v2", hybrid_file)
    if spec and spec.loader:
        hybrid_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hybrid_module)
        get_hybrid_recommendations = hybrid_module.get_hybrid_recommendations
        print("✅ 추천 시스템 연결 성공")
    else:
        raise ImportError("hybrid_recommender_v2.py 스펙 로드 실패")
        
except Exception as e:
    print(f"❌ 추천 시스템 import 실패: {e}")
    def get_hybrid_recommendations(*args, **kwargs):
        del args, kwargs  # pylint 경고 해결
        return {"success": False, "results": [], "error": f"추천 시스템 import 실패: {e}"}

try:
    print("📝 설명 생성기 import 시도 중...")
    
    # explanation_generator.py 로드
    spec = importlib.util.spec_from_file_location("explanation_generator", explanation_file)
    if spec and spec.loader:
        explanation_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(explanation_module)
        generate_explanation = explanation_module.generate_explanation
        print("✅ 설명 생성기 연결 성공")
    else:
        raise ImportError("explanation_generator.py 스펙 로드 실패")
        
except Exception as e:
    print(f"❌ 설명 생성기 import 실패: {e}")
    def generate_explanation(*args, **kwargs):
        del args, kwargs  # pylint 경고 해결
        return f"설명 생성 실패: {e}"


@dataclass
class LLMEvaluationResult:
    """LLM 평가 결과"""
    user_id: str
    user_name: str
    real_recommendations: List[Dict]
    llm_scores: Dict[str, float]  # {model: overall_score}
    llm_detailed_scores: Dict[str, Dict[str, float]]  # {model: {metric: score}}
    llm_reasoning: Dict[str, str]  # {model: reasoning}
    average_llm_score: float
    timestamp: str


class SimpleLLMJudge:
    """CSV 기반 간단한 LLM Judge"""
    
    def __init__(self, csv_path: str = None):
        """초기화"""
        self.result_dir = Path(__file__).parent / "final_result"
        self.result_dir.mkdir(exist_ok=True)
        
        # CSV 파일 경로 설정
        if csv_path:
            self.csv_path = Path(csv_path)
        else:
            self.csv_path = Path(__file__).parent / "profiles_test_rows.csv"
        
        # 사용자 데이터 로드
        self.load_user_data()
        
        # 평가 프롬프트
        self.evaluation_prompt = self._create_evaluation_prompt()
    
    def load_user_data(self):
        """CSV에서 사용자 데이터 로드"""
        try:
            self.users_df = pd.read_csv(self.csv_path)
            print(f"👥 CSV에서 {len(self.users_df)}명 사용자 로드")
        except Exception as e:
            print(f"❌ CSV 로드 실패: {e}")
            self.users_df = pd.DataFrame()
    
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
다음 4가지 관점에서 이 추천(콘텐츠)과 맞춤 설명의 품질을 1-5점으로 평가하세요:

1. **적합성 (Suitability)**: 사용자 지식 수준에 적합한가?
2. **관련성 (Relevance)**: 사용자 관심사와 얼마나 관련있는 추천인가?
3. **다양성 (Diversity)**: 추천 콘텐츠들이 다양한 관점을 제공하는가?
4. **일관성 (Coherence)**: 콘텐츠와 맞춤 설명이 자연스럽고 논리적으로 연결되는가?

**응답 형식 (JSON):**
{{
    "suitability_score": [1-5], 
    "relevance_score": [1-5],
    "diversity_score": [1-5],
    "coherence_score": [1-5],
    "overall_score": [1-5],
    "detailed_reasoning": "구체적인 평가 이유를 3-4문장으로 설명"
}}
"""
    
    def get_real_recommendations(self, user_profile: Dict) -> List[Dict]:
        """실제 추천 시스템을 사용한 추천 생성"""
        def safe_eval(field):
            try:
                if isinstance(field, str) and field.strip():
                    return eval(field)
                return []
            except:
                return []
        
        # 사용자 컨텍스트 생성 (추천 시스템 형식에 맞춤)
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
            # 실제 추천 시스템 호출 (평가 모드: 데이터베이스 저장 비활성화)
            result = get_hybrid_recommendations(
                user=user_context,
                top_n=5,  # 5개 추천
                use_llm_rerank=True,  # LLM 리랭킹 활성화 
                evaluation_mode=True  # 평가 모드: DB 저장 건너뛰기
            )
            
            if result.get('success') and result.get('results'):
                recommendations = result['results']
                print(f"    📋 실제 추천 시스템에서 {len(recommendations)}개 추천 받음")
                
                # 각 추천에 대해 맞춤 설명 생성
                user_level = user_context.get('knowledge_level', 'Beginner')
                for i, rec in enumerate(recommendations):
                    try:
                        # 평가 모드: 캐시 조회 건너뛰기 (DB 저장 방지)
                        explanation = generate_explanation(
                            level=user_level,
                            content_title=rec.get('title', ''),
                            content_description=rec.get('content', ''),
                            contents_id=None  # 캐시 조회 건너뛰기로 DB 저장 방지
                        )
                        rec['custom_explanation'] = explanation
                        print(f"      ✨ 추천 {i+1} 맞춤 설명 생성 완료")
                    except Exception as e:
                        rec['custom_explanation'] = f"설명 생성 실패: {str(e)}"
                        print(f"      ⚠️ 추천 {i+1} 설명 생성 실패: {e}")
                
                return recommendations
            else:
                print(f"    ⚠️ 추천 실패: {result.get('error', 'Unknown error')}")
                return self._get_fallback_recommendations(user_profile)
                
        except Exception as e:
            print(f"    ❌ 추천 시스템 호출 오류: {e}")
            return self._get_fallback_recommendations(user_profile)
    
    def _get_fallback_recommendations(self, user_profile: Dict) -> List[Dict]:
        """추천 시스템 실패 시 백업 추천"""
        level = user_profile.get('knowledge_level', 'Beginner')
        
        # 간단한 백업 추천
        fallback_recs = [
            {"title": f"{level} 레벨 금융 기초", "content": f"{level} 수준의 기본 금융 지식", "level": level, "tags": ["기초"]},
            {"title": f"{level} 투자 가이드", "content": f"{level} 수준의 투자 방법", "level": level, "tags": ["투자"]},
            {"title": f"{level} 자산 관리", "content": f"{level} 수준의 자산 관리법", "level": level, "tags": ["자산관리"]}
        ]
        
        print(f"    🔄 백업 추천 사용 ({len(fallback_recs)}개)")
        return fallback_recs
    
    async def evaluate_with_llm(self, user_profile: Dict, recommendations: List[Dict], llm_model: str) -> Dict:
        """특정 LLM 모델로 평가"""
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
                recommendations_text += f"   내용: {rec.get('content', 'N/A')}\n"
                recommendations_text += f"   난이도: {rec.get('level', 'N/A')}\n"
                recommendations_text += f"   태그: {', '.join(rec.get('tags', []))}\n"
                
                # 맞춤 설명이 있으면 포함
                custom_explanation = rec.get('custom_explanation', '')
                if custom_explanation and custom_explanation != 'N/A':
                    recommendations_text += f"   맞춤 설명: {custom_explanation[:150]}{'...' if len(custom_explanation) > 150 else ''}\n"
                
                recommendations_text += "\n"
            
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
            
            return {
                "success": True,
                "evaluation": evaluation
            }
            
        except Exception as e:
            print(f"❌ LLM 평가 실패 ({llm_model}): {e}")
            
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _call_llm(self, prompt: str, model: str) -> str:
        """LLM API 호출"""
        if model == "gpt-4o-mini" and openai:
            try:
                client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=1000
                )
                return response.choices[0].message.content
            except Exception as e:
                print(f"OpenAI API 오류: {e}")
                raise e
        
        elif model == "gemini-1.5-flash" and genai:
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
                    "suitability_score": float(parsed.get("suitability_score", 0)),
                    "relevance_score": float(parsed.get("relevance_score", 0)),
                    "diversity_score": float(parsed.get("diversity_score", 0)),
                    "coherence_score": float(parsed.get("coherence_score", 0)),
                    "overall_score": float(parsed.get("overall_score", 0)),
                    "detailed_reasoning": str(parsed.get("detailed_reasoning", "파싱 실패"))
                }
            else:
                # JSON이 없으면 숫자만 추출
                import re
                numbers = re.findall(r'\b[1-5]\b', response)
                if len(numbers) >= 5:  # 4개 세부 점수 + 1개 전체 점수
                    return {
                        "suitability_score": float(numbers[0]),
                        "relevance_score": float(numbers[1]),
                        "diversity_score": float(numbers[2]),
                        "coherence_score": float(numbers[3]),
                        "overall_score": float(numbers[4]),
                        "detailed_reasoning": "숫자만 추출됨"
                    }
                else:
                    raise ValueError("점수를 찾을 수 없음")
                    
        except Exception as e:
            print(f"⚠️ LLM 응답 파싱 실패: {e}")
            return {
                "suitability_score": 0.0,
                "relevance_score": 0.0,
                "diversity_score": 0.0,
                "coherence_score": 0.0,
                "overall_score": 0.0,
                "detailed_reasoning": f"파싱 실패: {str(e)}"
            }
    
    async def run_evaluation(self, max_users: int = 10, 
                            llm_models: List[str] = ["gpt-4o-mini"]) -> List[LLMEvaluationResult]:
        """LLM 평가 실행"""
        print(f"🤖 LLM Judge 평가 시작")
        print(f"  {max_users}명 사용자 × {len(llm_models)}개 LLM")
        
        if self.users_df.empty:
            print("❌ 사용자 데이터가 없습니다.")
            return []
        
        # 사용자 샘플 선택
        sample_users = self.users_df.head(max_users)
        print(f"👥 평가 대상 사용자: {len(sample_users)}명")
        
        all_results = []
        
        for _, user_row in sample_users.iterrows():
            user = user_row.to_dict()
            print(f"\n👤 {user['name']} 평가 중...")
            
            # 실제 추천 시스템 호출
            recommendations = self.get_real_recommendations(user)
            if not recommendations:
                print(f"  ⚠️ 추천 결과가 없어 다음 사용자로 넘어갑니다.")
                continue
            
            # LLM 모델별 평가
            llm_scores = {}
            llm_detailed_scores = {}
            llm_reasoning = {}
            
            for llm_model in llm_models:
                print(f"    🤖 {llm_model} 평가 중...")
                
                try:
                    result = await self.evaluate_with_llm(user, recommendations, llm_model)
                    
                    if result['success']:
                        evaluation = result['evaluation']
                        # LLM에서 제공한 overall_score 사용, 없으면 4개 점수의 평균으로 계산
                        overall_score = evaluation.get('overall_score', 0)
                        if overall_score == 0:
                            overall_score = (
                                evaluation.get('suitability_score', 0) +
                                evaluation.get('relevance_score', 0) +
                                evaluation.get('diversity_score', 0) +
                                evaluation.get('coherence_score', 0)
                            ) / 4.0
                        
                        llm_scores[llm_model] = overall_score
                        llm_detailed_scores[llm_model] = {
                            'suitability': evaluation.get('suitability_score', 0),
                            'relevance': evaluation.get('relevance_score', 0),
                            'diversity': evaluation.get('diversity_score', 0),
                            'coherence': evaluation.get('coherence_score', 0)
                        }
                        llm_reasoning[llm_model] = evaluation['detailed_reasoning']
                        print(f"      ✅ 전체: {overall_score:.1f} | 적합성: {evaluation.get('suitability_score', 0):.1f} | 관련성: {evaluation.get('relevance_score', 0):.1f}")
                    else:
                        print(f"      ❌ 평가 실패: {result['error']}")
                        llm_scores[llm_model] = 0.0
                        llm_detailed_scores[llm_model] = {
                            'suitability': 0, 'relevance': 0, 'diversity': 0, 'coherence': 0
                        }
                        llm_reasoning[llm_model] = f"평가 실패: {result['error']}"
                
                except Exception as e:
                    print(f"      ❌ 평가 중 오류: {e}")
                    llm_scores[llm_model] = 0.0
                    llm_detailed_scores[llm_model] = {
                        'suitability': 0, 'relevance': 0, 'diversity': 0, 'coherence': 0
                    }
                    llm_reasoning[llm_model] = f"오류: {str(e)}"
                
                # API 호출 간격 (속도 제한 방지)
                await asyncio.sleep(1)
            
            # 결과 저장
            avg_llm_score = np.mean(list(llm_scores.values())) if llm_scores else 0.0
            
            result = LLMEvaluationResult(
                user_id=user['id'],
                user_name=user['name'],
                real_recommendations=recommendations,
                llm_scores=llm_scores,
                llm_detailed_scores=llm_detailed_scores,
                llm_reasoning=llm_reasoning,
                average_llm_score=avg_llm_score,
                timestamp=datetime.now().isoformat()
            )
            
            all_results.append(result)
            print(f"  📊 평균 LLM 점수: {avg_llm_score:.3f}")
        
        # 결과 저장
        self.save_results(all_results)
        
        print(f"\n✅ LLM Judge 평가 완료! 총 {len(all_results)}개 결과")
        return all_results
    
    def save_results(self, results: List[LLMEvaluationResult]):
        """결과 저장"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # JSON 상세 결과
        detailed_path = self.result_dir / f"llm_evaluation_detailed_{timestamp}.json"
        with open(detailed_path, 'w', encoding='utf-8') as f:
            json.dump([asdict(r) for r in results], f, ensure_ascii=False, indent=2)
        
        # CSV 요약 결과 (세부 점수 포함)
        summary_data = []
        for r in results:
            row = {
                'user_name': r.user_name,
                'num_recommendations': len(r.real_recommendations),
                'average_llm_score': r.average_llm_score,
                **r.llm_scores,  # 각 LLM 모델별 전체 점수
                'timestamp': r.timestamp
            }
            
            # 각 모델별 세부 점수 추가
            for model, detailed_scores in r.llm_detailed_scores.items():
                for metric, score in detailed_scores.items():
                    row[f'{model}_{metric}'] = score
            
            summary_data.append(row)
        
        summary_df = pd.DataFrame(summary_data)
        csv_path = self.result_dir / f"llm_evaluation_summary_{timestamp}.csv"
        summary_df.to_csv(csv_path, index=False, encoding='utf-8-sig')
        
        # 추천 콘텐츠 로데이터 CSV 저장
        recommendation_csv_path = self.result_dir / f"recommendation_test_{timestamp}.csv"
        self.save_recommendations_csv(results, recommendation_csv_path)
        
        print(f"💾 평가 결과 저장:")
        print(f"  상세: {detailed_path}")
        print(f"  요약: {csv_path}")
        print(f"  추천 로데이터: {recommendation_csv_path}")
    
    def save_recommendations_csv(self, results: List[LLMEvaluationResult], csv_path: Path):
        """추천 콘텐츠들을 CSV로 저장"""
        rec_data = []
        
        for result in results:
            user_info = {
                'user_name': result.user_name,
                'user_id': result.user_id,
                'average_llm_score': result.average_llm_score
            }
            
            for i, rec in enumerate(result.real_recommendations, 1):
                row = {
                    **user_info,
                    'recommendation_rank': i,
                    'card_id': rec.get('card_id', 'N/A'),
                    'title': rec.get('title', 'N/A'),
                    'content': rec.get('content', 'N/A')[:200] + '...' if len(str(rec.get('content', ''))) > 200 else rec.get('content', 'N/A'),
                    'custom_explanation': rec.get('custom_explanation', 'N/A')[:300] + '...' if len(str(rec.get('custom_explanation', ''))) > 300 else rec.get('custom_explanation', 'N/A'),
                    'level': rec.get('level', 'N/A'),
                    'tags': ', '.join(rec.get('tags', [])) if isinstance(rec.get('tags'), list) else str(rec.get('tags', 'N/A')),
                    'category': rec.get('category', 'N/A'),
                    'subcategory': rec.get('subcategory', 'N/A'),
                    'created_at': rec.get('created_at', 'N/A'),
                    'source': rec.get('source', 'N/A'),
                    **{f'llm_{model}': score for model, score in result.llm_scores.items()},
                    **{f'llm_{model}_{metric}': score for model, detailed_scores in result.llm_detailed_scores.items() for metric, score in detailed_scores.items()},
                    'timestamp': result.timestamp
                }
                rec_data.append(row)
        
        if rec_data:
            rec_df = pd.DataFrame(rec_data)
            rec_df.to_csv(csv_path, index=False, encoding='utf-8-sig')
            print(f"📋 총 {len(rec_data)}개 추천 콘텐츠 저장")
        else:
            print("⚠️ 저장할 추천 콘텐츠가 없습니다.")


async def main():
    """메인 실행"""
    print("🤖 LLM Judge 평가 시작")
    
    # OpenAI만 사용
    available_models = []
    if openai and os.getenv('OPENAI_API_KEY'):
        available_models.append("gpt-4o-mini")
        print("✅ OpenAI GPT-4o-mini 사용")
    else:
        print("❌ OpenAI API 키가 없습니다. .env 파일에 OPENAI_API_KEY를 설정하세요.")
        return
    
    evaluator = SimpleLLMJudge()
    
    # LLM 평가 실행 (30명 전체)
    results = await evaluator.run_evaluation(
        max_users=30,           # 30명 사용자 (전체)
        llm_models=available_models  # OpenAI GPT-4o-mini만
    )
    
    if results:
        # 간단한 통계
        print(f"\n📊 평가 결과 요약:")
        all_scores = [r.average_llm_score for r in results]
        print(f"  평균 점수: {np.mean(all_scores):.3f}")
        print(f"  점수 범위: {np.min(all_scores):.3f} ~ {np.max(all_scores):.3f}")
        
        # 모델별 점수 비교
        if len(available_models) > 1:
            print(f"\n🔬 모델별 점수:")
            for model in available_models:
                model_scores = [r.llm_scores.get(model, 0) for r in results]
                if any(score > 0 for score in model_scores):
                    print(f"  {model}: {np.mean(model_scores):.3f}")


if __name__ == "__main__":
    asyncio.run(main())