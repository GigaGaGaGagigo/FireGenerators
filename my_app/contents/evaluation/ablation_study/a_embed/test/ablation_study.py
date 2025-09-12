import pandas as pd
import numpy as np
from itertools import product
from typing import Dict, List, Tuple, Any
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

@dataclass
class ExperimentConfig:
    """실험 설정 클래스"""
    search_model: str
    filtering_strategy: str
    reranking_params: Dict[str, float]
    llm_model: str
    prompt_strategy: str
    experiment_id: str = None
    
    def __post_init__(self):
        if not self.experiment_id:
            self.experiment_id = f"{self.search_model}_{self.filtering_strategy}_{self.llm_model}_{self.prompt_strategy}"

class AblationStudyDesigner:
    """
    Ablation Study 실험 설계 및 관리 클래스
    """
    def __init__(self):
        self.target_metrics = {
            "judge_score": 4.0,      # > 4.0
            "human_llm_correlation": 0.7,  # > 0.7
            "ndcg_3": 0.8           # > 0.8
        }
        
    def design_experiments(self) -> List[ExperimentConfig]:
        """
        5단계 Ablation Study 실험 설계
        """
        print("🔬 Ablation Study 실험 설계 시작...")
        
        # 1단계: 검색 모델 비교
        search_models = ["ko-sroberta", "bge-m3", "hybrid"]
        
        # 2단계: 필터링 전략
        filtering_strategies = ["vector_only", "vector_plus_rules"]
        
        # 3단계: 리랭킹 계수 조합
        reranking_combinations = [
            {"alpha": 0.8, "beta": 0.1, "gamma": 0.1},  # 벡터 중심
            {"alpha": 0.6, "beta": 0.3, "gamma": 0.1},  # 균형
            {"alpha": 0.5, "beta": 0.3, "gamma": 0.2},  # 태그 고려
            {"alpha": 0.7, "beta": 0.2, "gamma": 0.1},  # 현재 사용 (기준선)
            {"alpha": 0.4, "beta": 0.4, "gamma": 0.2}   # 레벨 중심
        ]
        
        # 4단계: LLM 모델 비교
        llm_models = ["gpt-4o-mini", "gemini-flash", "claude-3-haiku"]
        
        # 5단계: 프롬프트 전략
        prompt_strategies = ["generic", "level_specific", "adaptive"]
        
        # 실험 조합 생성
        experiments = []
        
        # Phase 1: 검색 모델만 변경 (기준 설정 고정)
        baseline_config = {
            "filtering_strategy": "vector_plus_rules",
            "reranking_params": {"alpha": 0.7, "beta": 0.2, "gamma": 0.1},
            "llm_model": "gpt-4o-mini", 
            "prompt_strategy": "generic"
        }
        
        for search_model in search_models:
            config = ExperimentConfig(
                search_model=search_model,
                **baseline_config
            )
            experiments.append(config)
            
        print(f"📊 Phase 1 (검색 모델): {len(search_models)}개 실험")
        
        # Phase 2: 최적 검색 모델 + 필터링 전략 변경
        best_search = "hybrid"  # 가정 (실제로는 Phase 1 결과로 결정)
        
        for filtering in filtering_strategies:
            config = ExperimentConfig(
                search_model=best_search,
                filtering_strategy=filtering,
                reranking_params=baseline_config["reranking_params"],
                llm_model=baseline_config["llm_model"],
                prompt_strategy=baseline_config["prompt_strategy"]
            )
            experiments.append(config)
            
        print(f"📊 Phase 2 (필터링): {len(filtering_strategies)}개 실험")
        
        # Phase 3: 리랭킹 계수 최적화
        for reranking_params in reranking_combinations:
            config = ExperimentConfig(
                search_model=best_search,
                filtering_strategy="vector_plus_rules",  # Phase 2 최적 가정
                reranking_params=reranking_params,
                llm_model=baseline_config["llm_model"],
                prompt_strategy=baseline_config["prompt_strategy"]
            )
            experiments.append(config)
            
        print(f"📊 Phase 3 (리랭킹): {len(reranking_combinations)}개 실험")
        
        # Phase 4: LLM 모델 비교
        best_reranking = {"alpha": 0.7, "beta": 0.2, "gamma": 0.1}  # Phase 3 최적 가정
        
        for llm_model in llm_models:
            config = ExperimentConfig(
                search_model=best_search,
                filtering_strategy="vector_plus_rules",
                reranking_params=best_reranking,
                llm_model=llm_model,
                prompt_strategy=baseline_config["prompt_strategy"]
            )
            experiments.append(config)
            
        print(f"📊 Phase 4 (LLM 모델): {len(llm_models)}개 실험")
        
        # Phase 5: 프롬프트 전략 최적화
        best_llm = "gpt-4o-mini"  # Phase 4 최적 가정
        
        for prompt_strategy in prompt_strategies:
            config = ExperimentConfig(
                search_model=best_search,
                filtering_strategy="vector_plus_rules",
                reranking_params=best_reranking,
                llm_model=best_llm,
                prompt_strategy=prompt_strategy
            )
            experiments.append(config)
            
        print(f"📊 Phase 5 (프롬프트): {len(prompt_strategies)}개 실험")
        
        # 중복 제거
        unique_experiments = []
        seen_ids = set()
        
        for exp in experiments:
            if exp.experiment_id not in seen_ids:
                unique_experiments.append(exp)
                seen_ids.add(exp.experiment_id)
                
        print(f"✅ 총 {len(unique_experiments)}개 고유 실험 설계 완료")
        return unique_experiments
    
    def create_experiment_plan(self, experiments: List[ExperimentConfig]) -> pd.DataFrame:
        """실험 계획을 DataFrame으로 정리"""
        data = []
        
        for i, exp in enumerate(experiments, 1):
            data.append({
                "experiment_id": i,
                "config_id": exp.experiment_id,
                "search_model": exp.search_model,
                "filtering": exp.filtering_strategy,
                "alpha": exp.reranking_params["alpha"],
                "beta": exp.reranking_params["beta"], 
                "gamma": exp.reranking_params["gamma"],
                "llm_model": exp.llm_model,
                "prompt_strategy": exp.prompt_strategy,
                "phase": self._get_phase(exp),
                "priority": self._get_priority(exp)
            })
            
        df = pd.DataFrame(data)
        return df
    
    def _get_phase(self, exp: ExperimentConfig) -> str:
        """실험이 속한 단계 판정"""
        if exp.search_model in ["ko-sroberta", "bge-m3"] and exp.llm_model == "gpt-4o-mini":
            return "Phase1_Search"
        elif exp.filtering_strategy in ["vector_only", "vector_plus_rules"]:
            return "Phase2_Filtering"
        elif exp.reranking_params["alpha"] != 0.7:
            return "Phase3_Reranking"
        elif exp.llm_model != "gpt-4o-mini":
            return "Phase4_LLM"
        elif exp.prompt_strategy != "generic":
            return "Phase5_Prompt"
        else:
            return "Baseline"
    
    def _get_priority(self, exp: ExperimentConfig) -> int:
        """실험 우선순위 (1=높음, 3=낮음)"""
        # 현재 설정과 유사한 것들을 우선순위 높게
        if (exp.search_model == "hybrid" and 
            exp.reranking_params["alpha"] == 0.7):
            return 1
        elif exp.search_model in ["ko-sroberta", "bge-m3"]:
            return 2
        else:
            return 3

# 사용자 프로필 샘플 준비
class UserProfileSampler:
    """
    사용자 프로필 20개 샘플 생성/로드
    """
    def __init__(self):
        self.profiles = self._create_sample_profiles()
    
    def _create_sample_profiles(self) -> List[Dict]:
        """다양한 사용자 프로필 샘플 생성"""
        profiles = []
        
        # 감정 상태 조합
        emotions = ["anxious", "confident", "confused", "motivated", "overwhelmed"]
        interests = ["investment", "saving", "debt", "retirement", "budget"]
        knowledge_levels = ["beginner", "intermediate", "advanced"]
        
        profile_id = 1
        for emotion in emotions:
            for interest in interests:
                if profile_id > 20:
                    break
                    
                knowledge = np.random.choice(knowledge_levels)
                
                profile = {
                    "id": f"user_{profile_id:03d}",
                    "emotion_state": emotion,
                    "primary_interest": interest,
                    "knowledge_level": knowledge,
                    "knowledge_summary": f"{knowledge} level user interested in {interest}, feeling {emotion}",
                    "user_summary": f"User seeks {interest} guidance with {emotion} mindset",
                    "created_at": datetime.now().isoformat()
                }
                profiles.append(profile)
                profile_id += 1
                
        return profiles[:20]
    
    def get_profiles(self) -> List[Dict]:
        return self.profiles
    
    def save_profiles(self, filename: str = None):
        """프로필을 JSON 파일로 저장"""
        if filename is None:
            # 현재 파일 위치를 기준으로 evaluation 폴더에 저장
            current_dir = Path(__file__).parent
            filename = current_dir / "user_profiles_sample.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.profiles, f, ensure_ascii=False, indent=2)
        print(f"💾 사용자 프로필 저장: {filename}")

# 메인 실행
def main():
    """Ablation Study 설계 및 샘플 데이터 준비"""
    print("🚀 Ablation Study 설계 시작\n")
    
    # 1. 실험 설계
    designer = AblationStudyDesigner()
    experiments = designer.design_experiments()
    
    # 2. 실험 계획표 생성
    experiment_plan = designer.create_experiment_plan(experiments)
    
    # 3. 사용자 프로필 샘플 준비
    user_sampler = UserProfileSampler()
    user_profiles = user_sampler.get_profiles()
    
    # 4. 결과 저장 (evaluation 폴더에 저장)
    current_dir = Path(__file__).parent
    csv_path = current_dir / "ablation_study_plan.csv"
    experiment_plan.to_csv(csv_path, index=False, encoding='utf-8-sig')
    user_sampler.save_profiles()
    
    print(f"\n📊 실험 계획 요약:")
    print(f"- 총 실험 수: {len(experiments)}")
    print(f"- 사용자 프로필: {len(user_profiles)}개")
    print(f"- 예상 총 평가 수: {len(experiments)} × {len(user_profiles)} = {len(experiments) * len(user_profiles)}")
    
    print(f"\n📋 단계별 실험 수:")
    phase_counts = experiment_plan['phase'].value_counts()
    for phase, count in phase_counts.items():
        print(f"- {phase}: {count}개")
    
    print(f"\n🎯 목표 메트릭:")
    for metric, target in designer.target_metrics.items():
        print(f"- {metric}: > {target}")
        
    print(f"\n✅ 파일 저장 완료:")
    print(f"- {csv_path}")
    print(f"- {current_dir / 'user_profiles_sample.json'}")
    
    return experiment_plan, user_profiles, experiments

if __name__ == "__main__":
    experiment_plan, user_profiles, experiments = main()